"""Characterize uploads and local source materialization without provider calls."""
from contextlib import contextmanager
from copy import deepcopy
from io import BytesIO
from pathlib import Path
import asyncio
from shutil import copy2

import pytest
from fastapi import UploadFile
from fastapi.responses import FileResponse

from app.db import mock_data as db
from app.db.persistence import STORAGE_ROOT
from app.persistence.local_artifacts import LocalArtifactStore
from app.routers import sources as router
from app.responses import ArtifactFileResponse


@pytest.fixture
def empty_source(client):
    library = client.post("/libraries", json={"name": "Upload tests"}).json()
    return client.post("/sources", json={"library_id": library["id"], "title": "Synthetic notes"}).json()


def stored(source):
    return next(item for item in db.sources if item["id"] == source["id"])


def upload(client, source, content, filename="notes.txt"):
    return client.post(f"/sources/{source['id']}/upload", files={"file": (filename, content)})


def test_upload_bytes_absolute_path_and_download_filename(client, empty_source):
    content = b"Original\r\nbytes\x00\xff\n"
    filename = "Café notes.TXT"
    response = upload(client, empty_source, content, filename)
    assert response.status_code == 200
    record = stored(empty_source)
    path = STORAGE_ROOT / "uploads" / f"{empty_source['id']}.txt"
    assert record["file_path"] == str(path)
    assert path.is_absolute() and path.read_bytes() == content
    assert record["file_name"] == filename
    assert record["processing_status"] == "uploaded"
    assert not path.with_suffix(".txt.tmp").exists()
    download = client.get(f"/sources/{empty_source['id']}/file")
    assert download.status_code == 200 and download.content == content
    assert download.headers["content-disposition"] == FileResponse(path, filename=filename).headers["content-disposition"]
    record["file_name"] = None
    fallback = client.get(f"/sources/{empty_source['id']}/file")
    assert fallback.content == content
    assert fallback.headers["content-disposition"] == FileResponse(path, filename=path.name).headers["content-disposition"]


@pytest.mark.parametrize("content,status,message", [
    (b"", 400, "The uploaded file is empty."),
    (b"x" * (25 * 1024 * 1024 + 1), 413, "Upload limit is 25 MB."),
])
def test_rejected_upload_cleans_partial_and_preserves_prior(client, empty_source, content, status, message):
    assert upload(client, empty_source, b"original").status_code == 200
    before = deepcopy(stored(empty_source))
    response = upload(client, empty_source, content)
    assert response.status_code == status and response.json() == {"detail": message}
    assert stored(empty_source) == before
    path = Path(before["file_path"])
    assert path.read_bytes() == b"original"
    assert not path.with_suffix(".txt.tmp").exists()


def test_exact_upload_limit_is_accepted(client, empty_source):
    content = b"x" * (25 * 1024 * 1024)
    assert upload(client, empty_source, content).status_code == 200
    assert Path(stored(empty_source)["file_path"]).read_bytes() == content


@pytest.mark.parametrize("same_extension", [True, False])
def test_replacement_removes_prior_artifacts_before_interpretation(client, source, same_extension):
    record, _ = source
    previous = deepcopy(stored(record))
    old_paths = [Path(previous[key]) for key in ("file_path", "extracted_text_path", "chunks_path")]
    assert all(path.exists() for path in old_paths)
    filename = "replacement.md" if same_extension else "replacement.txt"
    assert upload(client, record, b"replacement", filename).status_code == 200
    current = stored(record)
    path = Path(current["file_path"])
    assert path.read_bytes() == b"replacement"
    assert all(not old.exists() for old in old_paths if old != path)
    assert current["extracted_text_path"] is None and current["chunks_path"] is None
    assert current["processing_status"] == "uploaded"


def test_interpretation_history_blocks_replacement(client, source, knowledge):
    record, _ = source
    before = deepcopy(stored(record))
    path = Path(before["file_path"])
    original = path.read_bytes()
    response = upload(client, record, b"replacement", "replacement.md")
    assert response.status_code == 409
    assert response.json() == {"detail": "This source already has interpretation history. Add a new source for a replacement file."}
    assert stored(record) == before and path.read_bytes() == original
    assert not path.with_suffix(".md.tmp").exists()


@pytest.mark.parametrize("failure", ["read", "write", "replace"])
def test_upload_io_failure_cleans_partial_and_preserves_record(client, empty_source, monkeypatch, failure):
    assert upload(client, empty_source, b"original").status_code == 200
    before = deepcopy(stored(empty_source))
    path = Path(before["file_path"])

    class BrokenReader(BytesIO):
        def read(self, size=-1):
            if self.tell():
                raise OSError("simulated read failure")
            return super().read(3)

    class FailingStore(LocalArtifactStore):
        @contextmanager
        def open_binary_write(self, target):
            with super().open_binary_write(target) as handle:
                class Writer:
                    def write(self, data):
                        handle.write(data[:1])
                        raise OSError("simulated write failure")
                yield Writer() if failure == "write" else handle

        def replace(self, temporary, destination):
            if failure == "replace":
                raise OSError("simulated replace failure")
            super().replace(temporary, destination)

    monkeypatch.setattr(router, "_artifact_store", FailingStore())
    stream = BrokenReader(b"new content") if failure == "read" else BytesIO(b"new content")
    with pytest.raises(OSError, match=f"simulated {failure} failure"):
        router.upload_source_file(empty_source["id"], UploadFile(file=stream, filename="notes.txt"))
    assert stored(empty_source) == before
    assert path.read_bytes() == b"original"
    assert not path.with_suffix(".txt.tmp").exists()


def test_missing_source_artifact_messages(client, empty_source):
    response = client.get("/sources/missing/file")
    assert response.status_code == 404 and response.json() == {"detail": "Source not found"}
    response = client.get(f"/sources/{empty_source['id']}/file")
    assert response.status_code == 404 and response.json() == {"detail": "No file uploaded for this source."}
    assert upload(client, empty_source, b"text").status_code == 200
    Path(stored(empty_source)["file_path"]).unlink()
    response = client.get(f"/sources/{empty_source['id']}/file")
    assert response.status_code == 404 and response.json() == {"detail": "Uploaded file not found on disk."}
    stored(empty_source)["file_type"] = ".pdf"
    for action in ("recover-structure", "refine-asset-sections"):
        response = client.post(f"/sources/{empty_source['id']}/{action}")
        assert response.status_code == 404 and response.json() == {"detail": "Uploaded PDF file not found on disk."}


def test_local_materialization_returns_original_path_without_copy(tmp_path):
    path = tmp_path / "source.txt"
    path.write_bytes(b"original")
    store = LocalArtifactStore()
    before = set(tmp_path.iterdir())
    with store.materialize(path) as materialized:
        assert materialized is path
        assert materialized.read_bytes() == b"original"
        assert set(tmp_path.iterdir()) == before
    assert path.read_bytes() == b"original" and set(tmp_path.iterdir()) == before
    with pytest.raises(RuntimeError):
        with store.materialize(path):
            raise RuntimeError("parser failure")
    assert path.exists() and set(tmp_path.iterdir()) == before


def test_extraction_uses_original_path_inside_materialization(client, empty_source, monkeypatch):
    assert upload(client, empty_source, b"Practice with focused goals.", "notes.md").status_code == 200
    expected = Path(stored(empty_source)["file_path"])
    active = []
    original_parser = router.extract_text_from_file

    class TrackingStore(LocalArtifactStore):
        @contextmanager
        def materialize(self, path):
            assert path == expected
            active.append(path)
            try:
                yield path
            finally:
                active.pop()

    def parser(file_path, file_type):
        assert active == [expected]
        assert file_path == str(expected) and file_type == ".md"
        return original_parser(file_path, file_type)

    monkeypatch.setattr(router, "_artifact_store", TrackingStore())
    monkeypatch.setattr(router, "extract_text_from_file", parser)
    assert client.post(f"/sources/{empty_source['id']}/process").status_code == 200
    assert not active and expected.exists()


@pytest.fixture
def temporary_store(tmp_path):
    class TemporaryStore(LocalArtifactStore):
        active = False
        exits = 0
        temporary = tmp_path / "materialized.bin"

        @contextmanager
        def materialize(self, path):
            copy2(path, self.temporary)
            self.active = True
            try:
                yield self.temporary
            finally:
                self.temporary.unlink()
                self.active = False
                self.exits += 1

    return TemporaryStore()


@pytest.mark.parametrize("range_header,status,body", [
    (None, 200, b"0123456789"),
    ("bytes=2-5", 206, b"2345"),
    ("bytes=99-", 416, b""),
])
def test_temporary_download_lifetime_and_headers(client, empty_source, monkeypatch, temporary_store,
                                               range_header, status, body):
    assert upload(client, empty_source, b"0123456789", "Café notes.txt").status_code == 200
    url = f"/sources/{empty_source['id']}/file"
    headers = {"Range": range_header} if range_header else {}
    original = client.get(url, headers=headers)
    monkeypatch.setattr(router, "_artifact_store", temporary_store)
    response = client.get(url, headers=headers)
    assert response.status_code == original.status_code == status
    assert response.content == original.content == body
    assert response.headers == original.headers
    assert temporary_store.exits == 1 and not temporary_store.active
    assert not temporary_store.temporary.exists()
    assert Path(stored(empty_source)["file_path"]).read_bytes() == b"0123456789"


@pytest.mark.parametrize("failure", ["send", "cancel", "stat"])
def test_materialization_exits_on_response_failure_or_cancellation(tmp_path, temporary_store, failure):
    path = tmp_path / "source.txt"
    path.write_bytes(b"x" * (FileResponse.chunk_size + 1))
    response = ArtifactFileResponse(path, temporary_store, filename="source.txt")
    scope = {"type": "http", "method": "GET", "headers": []}

    async def receive():
        return {"type": "http.disconnect"}

    async def send(message):
        assert temporary_store.active and temporary_store.temporary.exists()
        if message["type"] == "http.response.body":
            if failure == "send":
                raise OSError("send failed")
            asyncio.current_task().cancel()
            await asyncio.sleep(0)

    async def execute():
        if failure == "stat":
            # Exercise FileResponse failure before it sends any body.
            response.stat_result = None
            original_materialize = temporary_store.materialize

            @contextmanager
            def missing_path(path):
                with original_materialize(path):
                    yield tmp_path / "absent.txt"

            temporary_store.materialize = missing_path
        await response(scope, receive, send)

    expected = {"send": OSError, "cancel": asyncio.CancelledError, "stat": RuntimeError}[failure]
    with pytest.raises(expected):
        asyncio.run(execute())
    assert temporary_store.exits == 1 and not temporary_store.active
    assert not temporary_store.temporary.exists()
    assert response.path == path and path.exists()


def test_missing_artifact_does_not_enter_materialization(client, empty_source, monkeypatch, temporary_store):
    assert upload(client, empty_source, b"text").status_code == 200
    Path(stored(empty_source)["file_path"]).unlink()
    monkeypatch.setattr(router, "_artifact_store", temporary_store)
    response = client.get(f"/sources/{empty_source['id']}/file")
    assert response.status_code == 404
    assert response.json() == {"detail": "Uploaded file not found on disk."}
    assert temporary_store.exits == 0 and not temporary_store.temporary.exists()

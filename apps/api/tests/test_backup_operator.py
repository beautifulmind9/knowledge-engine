from io import BytesIO
import json
from pathlib import Path
import sys
from urllib.parse import unquote, urlsplit

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "scripts"))
from backup_operator import BackupError, StorageReader, download, finalize, inventory, preflight
from verify_hosted_backup import load_and_verify, restore_local


class Response(BytesIO):
    pass


class PartialResponse(Response):
    def __init__(self, initial):
        super().__init__(initial)
        self.calls = 0

    def read(self, size=-1):
        self.calls += 1
        if self.calls > 1:
            raise OSError("synthetic interrupted transfer")
        return super().read(3)


class StorageFixture:
    def __init__(self, objects):
        self.objects = objects
        self.metadata_overrides = {}
        self.duplicate = None
        self.partial = None
        self.gets = []

    def open(self, request, timeout):
        assert timeout == 60
        assert request.get_header("Apikey") == "secret"
        route = unquote(urlsplit(request.full_url).path).removeprefix("/storage/v1")
        if request.method == "POST":
            payload = json.loads(request.data)
            prefix = payload["prefix"] + "/"
            records = []
            for key, body in self.objects.items():
                if key.startswith(prefix) and "/" not in key[len(prefix):]:
                    name = key[len(prefix):]
                    if payload["search"] in name:
                        override = self.metadata_overrides.get(key, {})
                        records.append({"name": name, "id": override.get("id", "id-" + name),
                                        "metadata": override.get("metadata", {"size": len(body)}),
                                        "updated_at": override.get("updated_at", "2026-10-25T00:00:00Z")})
            if self.duplicate and self.duplicate.startswith(prefix):
                name = self.duplicate[len(prefix):]
                records.append({"name": name, "id": "duplicate", "metadata": {"size": 1},
                                "updated_at": "2026-10-25T00:00:00Z"})
            start = payload["offset"]
            return Response(json.dumps(records[start:start + payload["limit"]]).encode())
        key = route.split("/", 3)[3]
        self.gets.append(key)
        if key == self.partial:
            return PartialResponse(self.objects[key])
        return Response(self.objects[key])


def snapshot(tmp_path):
    value = {"schema_version": 2, "libraries": [{"id": "library"}], "sources": [
        {"id": "source", "file_path": "uploads/source.pdf",
         "extracted_text_path": "text/source.txt", "chunks_path": "chunks/source.json"}],
        "extraction_jobs": [{"id": "job", "status": "completed"}],
        "knowledge_assets": [{"id": "asset", "source_id": "source"}],
        "outputs": [], "usage": {}}
    path = tmp_path / "snapshot.json"
    path.write_text(json.dumps(value))
    return path, value


def reader(fixture):
    return StorageReader("https://offline.supabase.co", "secret", "bucket", "workspace", fixture)


def test_complete_synthetic_inventory_download_finalize_and_restore(tmp_path):
    snapshot_path, value = snapshot(tmp_path)
    objects = {"workspace/uploads/source.pdf": b"pdf", "workspace/text/source.txt": b"text",
               "workspace/chunks/source.json": b"chunks"}
    fixture = StorageFixture(objects)
    storage = reader(fixture)
    before_path = tmp_path / "metadata-before.ndjson"
    assert inventory(snapshot_path, before_path, storage) == {"sources": 1, "artifacts": 3, "bytes": 13}
    assert fixture.gets == []

    assert download(before_path, tmp_path, storage) == {"artifacts": 3, "bytes": 13}
    assert sorted(fixture.gets) == sorted(objects)
    after_path = tmp_path / "metadata-after.ndjson"
    assert inventory(snapshot_path, after_path, storage) == {"sources": 1, "artifacts": 3, "bytes": 13}
    assert before_path.read_bytes() == after_path.read_bytes()

    consistency = {"revision": 4, "partition_marker": None, "source_count": 1,
                   "asset_count": 1, "job_count": 1, "output_count": 0,
                   "allowance": {"admitted_attempts": 2}, "reservation_count": 2}
    (tmp_path / "consistency-before.json").write_text(json.dumps(consistency))
    (tmp_path / "consistency-after.json").write_text(json.dumps(consistency))
    (tmp_path / "database.dump").write_bytes(b"synthetic pg17 dump")
    assert finalize(tmp_path, "commit") == {
        "sources": 1, "artifacts": 3, "knowledge_assets": 1, "extraction_jobs": 1, "outputs": 0}
    manifest, restored_snapshot = load_and_verify(tmp_path)
    assert manifest["snapshot_revision"] == 4 and restored_snapshot == value
    assert restore_local(tmp_path, tmp_path / "restore") == {"sources": 1, "artifacts": 3}


@pytest.mark.parametrize("defect", ["missing_size", "duplicate"])
def test_inventory_fails_closed_without_downloading(defect, tmp_path):
    snapshot_path, _value = snapshot(tmp_path)
    objects = {"workspace/uploads/source.pdf": b"pdf", "workspace/text/source.txt": b"text",
               "workspace/chunks/source.json": b"chunks"}
    fixture = StorageFixture(objects)
    if defect == "missing_size":
        fixture.metadata_overrides["workspace/uploads/source.pdf"] = {"metadata": {}}
    else:
        fixture.duplicate = "workspace/uploads/source.pdf"
    with pytest.raises(BackupError):
        inventory(snapshot_path, tmp_path / "metadata.ndjson", reader(fixture))
    assert fixture.gets == []
    assert not (tmp_path / "metadata.ndjson").exists()


def test_partial_transfer_never_publishes_artifact(tmp_path):
    snapshot_path, _value = snapshot(tmp_path)
    objects = {"workspace/uploads/source.pdf": b"abcdef", "workspace/text/source.txt": b"text",
               "workspace/chunks/source.json": b"chunks"}
    fixture = StorageFixture(objects)
    inventory_path = tmp_path / "metadata.ndjson"
    inventory(snapshot_path, inventory_path, reader(fixture))
    fixture.partial = "workspace/chunks/source.json"
    with pytest.raises(OSError, match="interrupted"):
        download(inventory_path, tmp_path, reader(fixture))
    target = tmp_path / "objects/chunks/source.json"
    assert not target.exists() and not target.with_name("source.json.partial").exists()
    assert not (tmp_path / "artifacts.ndjson").exists()


@pytest.mark.parametrize("defect", ["revision", "checksum"])
def test_finalize_fails_closed_on_fence_or_checksum_change(defect, tmp_path):
    snapshot_path, _value = snapshot(tmp_path)
    objects = {"workspace/uploads/source.pdf": b"pdf", "workspace/text/source.txt": b"text",
               "workspace/chunks/source.json": b"chunks"}
    fixture = StorageFixture(objects)
    before = tmp_path / "metadata-before.ndjson"
    inventory(snapshot_path, before, reader(fixture))
    download(before, tmp_path, reader(fixture))
    inventory(snapshot_path, tmp_path / "metadata-after.ndjson", reader(fixture))
    consistency = {"revision": 4, "partition_marker": None, "source_count": 1,
                   "asset_count": 1, "job_count": 1, "output_count": 0}
    (tmp_path / "consistency-before.json").write_text(json.dumps(consistency))
    after = dict(consistency)
    if defect == "revision":
        after["revision"] = 5
    (tmp_path / "consistency-after.json").write_text(json.dumps(after))
    (tmp_path / "database.dump").write_bytes(b"dump")
    if defect == "checksum":
        (tmp_path / "objects/uploads/source.pdf").write_bytes(b"changed")
    with pytest.raises(BackupError):
        finalize(tmp_path, "commit")
    assert not (tmp_path / "manifest.json").exists()


def test_preflight_is_local_only_and_requires_empty_destination(tmp_path):
    destination = tmp_path / "backup"
    result = preflight(destination, 0)
    assert destination.stat().st_mode & 0o777 == 0o700
    assert result["stop"].startswith("STOP:")
    (destination / "existing").write_text("keep")
    with pytest.raises(BackupError, match="new or empty"):
        preflight(destination, 0)

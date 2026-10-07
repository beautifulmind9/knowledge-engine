"""Characterize private backup, integrity, and deletion at the artifact boundary."""
from copy import deepcopy
from io import BytesIO
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import pytest

from app.db import mock_data as db
from app.db.persistence import STORAGE_ROOT
from app.persistence.local_artifacts import LocalArtifactStore
from app.routers import control

KEYS = ("file_path", "extracted_text_path", "chunks_path")
RESTORE = "Private backup. Stop the server. Extract storage into a NEW empty directory. Set KNOWLEDGE_ENGINE_STORAGE to that storage directory, then start the app. Never overwrite a live database.\n"


def record(source):
    return next(s for s in db.sources if s["id"] == source[0]["id"])


def snapshot():
    return deepcopy(dict(libraries=db.libraries, sources=db.sources, extraction_jobs=db.extraction_jobs,
                         knowledge_assets=db.knowledge_assets, outputs=db.outputs, usage=db.usage))


@pytest.mark.parametrize("key", KEYS)
@pytest.mark.parametrize("directory", [False, True])
def test_integrity_missing_or_directory_artifact(client, source, key, directory):
    item = record(source)
    path = Path(item[key])
    path.unlink()
    if directory:
        path.mkdir()
    assert client.get('/data/integrity').json() == {
        "ok": False, "issues": [{"id": item["id"], "problem": "missing " + key}]}


def test_integrity_storage_failure_is_not_missing(client, source, monkeypatch):
    def fail(path):
        raise OSError("storage unavailable")
    monkeypatch.setattr(control._artifact_store, "status", fail)
    with pytest.raises(OSError, match="storage unavailable"):
        client.get('/data/integrity')


def test_export_matches_original_zip_and_does_not_mutate_live_state(client, source, monkeypatch):
    before = snapshot()
    expected_state = deepcopy(before)
    reference = BytesIO()
    with ZipFile(reference, 'w', ZIP_DEFLATED) as archive:
        for item in expected_state['sources']:
            for key in KEYS:
                path = Path(item[key]).resolve()
                relative = 'storage/' + str(path.relative_to(STORAGE_ROOT))
                archive.write(path, relative)
                item[key] = relative
        archive.writestr('storage/state.json', json.dumps(expected_state, indent=2))
        archive.writestr('RESTORE.txt', RESTORE)

    reads = []
    class TrackingStore(LocalArtifactStore):
        def open_binary_read(self, path):
            assert snapshot() == before
            reads.append(path)
            return super().open_binary_read(path)
    monkeypatch.setattr(control, '_artifact_store', TrackingStore())
    response = client.get('/data/export')
    assert response.status_code == 200
    assert response.headers['content-type'] == 'application/zip'
    assert response.headers['content-disposition'] == 'attachment; filename="knowledge-engine-backup.zip"'
    assert reads == [Path(record(source)[key]).resolve() for key in KEYS]
    with ZipFile(BytesIO(response.content)) as actual, ZipFile(reference) as expected:
        assert actual.namelist() == expected.namelist()
        for name in actual.namelist():
            assert actual.read(name) == expected.read(name)
            # Generated entries have current timestamps; source entries retain disk metadata.
            if name not in ('storage/state.json', 'RESTORE.txt'):
                for attr in ('date_time', 'external_attr', 'compress_type', 'CRC', 'file_size', 'compress_size'):
                    assert getattr(actual.getinfo(name), attr) == getattr(expected.getinfo(name), attr)
        assert actual.read('RESTORE.txt') == RESTORE.encode()
        assert actual.read('storage/state.json') == json.dumps(expected_state, indent=2).encode()
    assert snapshot() == before


@pytest.mark.parametrize('operation', ['export', 'delete'])
@pytest.mark.parametrize('symlink', [False, True])
def test_outside_storage_refused(client, source, tmp_path, operation, symlink):
    item = record(source)
    outside = tmp_path / 'legacy.txt'
    outside.write_text('private')
    if symlink:
        path = Path(item['chunks_path'])
        path.unlink()
        path.symlink_to(outside)
    else:
        item['chunks_path'] = str(outside)
    before = snapshot()
    if operation == 'export':
        response = client.get('/data/export')
        message = 'A legacy file is outside storage. Move it into storage before export.'
    else:
        response = client.delete('/sources/' + item['id'])
        message = 'A legacy file is outside the private storage directory. Resolve its location before deletion.'
    assert response.status_code == 409 and response.json() == {'detail': message}
    assert snapshot() == before
    assert all(Path(item[key]).is_file() for key in KEYS)
    assert outside.read_text() == 'private'


@pytest.mark.parametrize('missing', [None, *KEYS])
def test_delete_finishes_artifacts_before_records_and_persistence(client, source, knowledge, monkeypatch, missing):
    item = record(source)
    paths = [Path(item[key]).resolve() for key in KEYS]
    if missing:
        Path(item[missing]).unlink()
    before = snapshot()
    removed = []
    class TrackingStore(LocalArtifactStore):
        def remove(self, path):
            assert snapshot() == before
            super().remove(path)
            removed.append(path)
    monkeypatch.setattr(control, '_artifact_store', TrackingStore())
    saves = []
    def persist():
        assert removed == paths and all(not path.exists() for path in paths)
        assert not db.sources and not db.extraction_jobs and not db.knowledge_assets
        saves.append(True)
    monkeypatch.setattr(control, 'persist_state', persist)
    response = client.delete('/sources/' + item['id'])
    assert response.status_code == 200
    assert response.json() == {'deleted_source_id': item['id'], 'deleted_output_histories': 0}
    assert saves == [True]


@pytest.mark.parametrize('operation', ['delete', 'export'])
@pytest.mark.parametrize('failure', ['resolve', 'io'])
def test_adapter_failure_does_not_succeed_or_remove_records(client, source, monkeypatch, operation, failure):
    before = snapshot()
    calls = []
    class FailingStore(LocalArtifactStore):
        def resolve(self, path):
            if failure == 'resolve':
                raise OSError('adapter failed')
            return super().resolve(path)
        def remove(self, path):
            calls.append(path)
            if len(calls) == 2:
                raise OSError('adapter failed')
            super().remove(path)
        def open_binary_read(self, path):
            raise OSError('adapter failed')
    monkeypatch.setattr(control, '_artifact_store', FailingStore())
    monkeypatch.setattr(control, 'persist_state', lambda: pytest.fail('must not persist'))
    with pytest.raises(OSError, match='adapter failed'):
        if operation == 'delete':
            client.delete('/sources/' + record(source)['id'])
        else:
            client.get('/data/export')
    assert snapshot() == before
    if operation == 'delete' and failure == 'io':
        assert not Path(record(source)['file_path']).exists()
        assert Path(record(source)['extracted_text_path']).exists()


def test_dependent_outputs_require_opt_in_and_remove_complete_histories(client, source, knowledge):
    sid = record(source)['id']
    # Cover both explicit multi-source provenance and the legacy canonical fallback.
    db.outputs.extend([
        {'id': 'a', 'root_output_id': 'root-a', 'knowledge_snapshot': [{'canonical_asset': {'source_id': 'other'}, 'source_ids': ['other', sid]}]},
        {'id': 'a-child', 'root_output_id': 'root-a', 'knowledge_snapshot': []},
        {'id': 'b', 'root_output_id': 'root-b', 'knowledge_snapshot': [{'canonical_asset': {'source_id': sid}}]},
        {'id': 'b-child', 'root_output_id': 'root-b', 'knowledge_snapshot': []},
        {'id': 'keep', 'root_output_id': 'keep', 'knowledge_snapshot': []},
    ])
    before = snapshot()
    response = client.delete('/sources/' + sid)
    assert response.status_code == 409
    assert response.json() == {'detail': "Saved output histories contain this source's knowledge. Set delete_outputs=true to delete those histories too, or keep the source."}
    assert snapshot() == before
    assert all(Path(record(source)[key]).exists() for key in KEYS)
    response = client.delete('/sources/' + sid + '?delete_outputs=true')
    assert response.status_code == 200
    assert response.json() == {'deleted_source_id': sid, 'deleted_output_histories': 2}
    assert db.outputs == [before['outputs'][-1]]
    assert not db.sources and not db.knowledge_assets and not db.extraction_jobs


@pytest.mark.parametrize('method', ['status', 'stat'])
def test_export_metadata_failure_propagates(client, source, monkeypatch, method):
    before = snapshot()
    def fail(path):
        raise PermissionError('cannot inspect artifact')
    monkeypatch.setattr(control._artifact_store, method, fail)
    with pytest.raises(PermissionError, match='cannot inspect artifact'):
        client.get('/data/export')
    assert snapshot() == before


@pytest.mark.parametrize('key', KEYS)
def test_export_skips_missing_artifacts_without_rewriting_them(client, source, key):
    item = record(source)
    Path(item[key]).unlink()
    before = snapshot()
    response = client.get('/data/export')
    assert response.status_code == 200
    with ZipFile(BytesIO(response.content)) as archive:
        state = json.loads(archive.read('storage/state.json'))
        assert state['sources'][0][key] == item[key]
        assert 'storage/' + str(Path(item[key]).relative_to(STORAGE_ROOT)) not in archive.namelist()
    assert snapshot() == before


def test_export_directory_race_matches_zipfile_write(client, source, monkeypatch):
    item = record(source)
    path = Path(item['file_path'])
    before = snapshot()
    raced = []

    class RacingStore(LocalArtifactStore):
        def status(self, target):
            result = super().status(target)
            if target == path and not raced:
                # The original check saw a file, but export metadata now sees a directory.
                target.unlink()
                target.mkdir()
                raced.append(target)
            return result

    monkeypatch.setattr(control, '_artifact_store', RacingStore())
    response = client.get('/data/export')
    assert response.status_code == 200 and raced == [path]
    relative = 'storage/' + str(path.relative_to(STORAGE_ROOT))
    reference = BytesIO()
    with ZipFile(reference, 'w', ZIP_DEFLATED) as archive:
        archive.write(path, relative)
    with ZipFile(BytesIO(response.content)) as actual, ZipFile(reference) as expected:
        entry = actual.getinfo(relative + '/')
        original = expected.getinfo(relative + '/')
        assert entry.is_dir() and entry.CRC == entry.file_size == entry.compress_size == 0
        for attr in ('date_time', 'external_attr', 'compress_type', 'CRC', 'file_size', 'compress_size'):
            assert getattr(entry, attr) == getattr(original, attr)
        assert actual.read(entry) == expected.read(original) == b''
        assert actual.testzip() is None
        state = json.loads(actual.read('storage/state.json'))
        assert state['sources'][0]['file_path'] == relative
    assert snapshot() == before


@pytest.mark.parametrize('endpoint', ['/data/integrity', '/data/export'])
@pytest.mark.parametrize('key', KEYS)
@pytest.mark.parametrize('error', [PermissionError(13, 'denied'), OSError(5, 'I/O failure'), OSError(40, 'symlink loop')])
def test_underlying_stat_failures_propagate(client, source, monkeypatch, endpoint, key, error):
    path = Path(record(source)[key])
    before = snapshot()
    original_stat = Path.stat
    calls = []

    def failing_stat(target, *args, **kwargs):
        if target == path:
            calls.append(target)
            raise error
        return original_stat(target, *args, **kwargs)

    monkeypatch.setattr(Path, 'stat', failing_stat)
    with pytest.raises(type(error)) as actual:
        client.get(endpoint)
    assert actual.value is error and calls
    assert snapshot() == before


@pytest.mark.parametrize('method', ['exists', 'status'])
@pytest.mark.parametrize('error', [PermissionError(13, 'denied'), OSError(5, 'I/O failure'), OSError(40, 'symlink loop')])
def test_local_presence_checks_do_not_hide_stat_failures(tmp_path, monkeypatch, method, error):
    path = tmp_path / 'artifact'
    def failing_stat(target, *args, **kwargs):
        raise error
    monkeypatch.setattr(Path, 'stat', failing_stat)
    with pytest.raises(type(error)) as actual:
        getattr(LocalArtifactStore(), method)(path)
    assert actual.value is error


def test_local_presence_distinguishes_absence_from_non_artifacts(tmp_path):
    store = LocalArtifactStore()
    file = tmp_path / 'file'
    file.write_bytes(b'bytes')
    dangling = tmp_path / 'dangling'
    dangling.symlink_to(tmp_path / 'missing')
    for path in (tmp_path / 'missing', dangling, file / 'impossible-child'):
        assert store.status(path) == 'missing'
        assert not store.exists(path)
    assert store.status(file) == 'artifact' and store.exists(file)
    assert store.status(tmp_path) == 'other' and store.exists(tmp_path)

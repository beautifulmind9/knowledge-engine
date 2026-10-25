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
from app.persistence.supabase_artifacts import SupabaseArtifactStore, HostedArtifactStoreError
from app.routers import control
from app.routers import sources as source_router

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


def test_integrity_uses_one_bulk_presence_inventory(client, source, monkeypatch):
    calls=[];original=control._artifact_store
    class TrackingStore:
        def status_many(self,paths):
            paths=list(paths);calls.append(paths)
            return original.status_many(paths)
        def status(self,path):pytest.fail('integrity must use bulk presence')
        def read_text(self,path,**kwargs):pytest.fail('integrity must not read artifact content')
        def open_binary_read(self,path):pytest.fail('integrity must not read artifact content')
    monkeypatch.setattr(control,'_artifact_store',TrackingStore())
    assert client.get('/data/integrity').json()=={'ok':True,'issues':[]}
    assert len(calls)==1 and len(calls[0])==3 and len(set(calls[0]))==3


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


class HostedExportStore(SupabaseArtifactStore):
    """Offline hosted boundary backed by fixture files; never performs HTTP."""

    def __init__(self, sizes):
        self.storage_root = STORAGE_ROOT
        self.sizes = sizes
        self.reads = []

    def relative_locator(self, path):
        path = Path(path)
        return path.relative_to(STORAGE_ROOT) if path.is_absolute() else path

    def size_many(self, paths):
        return {path: self.sizes.get(path) for path in paths}

    def status(self, path):
        return "artifact"

    def open_binary_read(self, path):
        self.reads.append(path)
        return Path(path).open("rb")


@pytest.mark.parametrize("total, expected", [
    (control.HOSTED_EXPORT_ARTIFACT_BYTES_LIMIT, 200),
    (control.HOSTED_EXPORT_ARTIFACT_BYTES_LIMIT + 1, 413),
])
def test_hosted_export_size_boundary_precedes_artifact_reads(client, source, monkeypatch, total, expected):
    paths = [Path(record(source)[key]).resolve() for key in KEYS]
    store = HostedExportStore({paths[0]: total, paths[1]: 0, paths[2]: 0})
    monkeypatch.setattr(control, "_artifact_store", store)

    response = client.get("/data/export")

    assert response.status_code == expected
    if expected == 413:
        assert store.reads == []
        assert "disk-backed operator backup" in response.json()["detail"]
    else:
        assert store.reads == paths


def test_hosted_export_missing_or_unavailable_size_fails_before_download(client, source, monkeypatch):
    paths = [Path(record(source)[key]).resolve() for key in KEYS]
    store = HostedExportStore({paths[0]: 1, paths[1]: 1})
    monkeypatch.setattr(control, "_artifact_store", store)
    response = client.get("/data/export")
    assert response.status_code == 409
    assert store.reads == []

    def unavailable(_paths):
        raise HostedArtifactStoreError("private remote details")
    store.size_many = unavailable
    response = client.get("/data/export")
    assert response.status_code == 503
    assert "private remote details" not in response.text
    assert store.reads == []


def test_hosted_export_deduplicates_size_inventory_and_archive_entry(client, source, monkeypatch):
    item = record(source)
    shared = Path(item["file_path"]).resolve()
    item["extracted_text_path"] = str(shared)
    item["chunks_path"] = str(shared)
    seen = []
    store = HostedExportStore({shared: control.HOSTED_EXPORT_ARTIFACT_BYTES_LIMIT})
    original = store.size_many
    def track(paths):
        seen.append(list(paths))
        return original(paths)
    store.size_many = track
    monkeypatch.setattr(control, "_artifact_store", store)

    response = client.get("/data/export")

    assert response.status_code == 200
    assert seen == [[shared]]
    assert store.reads == [shared]
    with ZipFile(BytesIO(response.content)) as archive:
        artifact_names = [name for name in archive.namelist() if name not in ("storage/state.json", "RESTORE.txt")]
        assert len(artifact_names) == 1


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
def test_delete_persists_records_before_artifact_cleanup(client, source, knowledge, monkeypatch, missing):
    item = record(source)
    paths = [Path(item[key]).resolve() for key in KEYS]
    if missing:
        Path(item[missing]).unlink()
    removed = []
    persisted = []
    class TrackingStore(LocalArtifactStore):
        def remove(self, path):
            assert not any(item['id'] == item_id for item in db.sources)
            assert persisted
            super().remove(path)
            removed.append(path)
    monkeypatch.setattr(control, '_artifact_store', TrackingStore())
    saves = []
    def persist():
        assert not db.sources and not db.extraction_jobs and not db.knowledge_assets
        missing_path = Path(item[missing]).resolve() if missing else None
        assert all(path.exists() for path in paths if path != missing_path)
        persisted.append(True)
        assert not db.sources and not db.extraction_jobs and not db.knowledge_assets
        saves.append(True)
    monkeypatch.setattr(control, 'persist_state', persist)
    item_id = item['id']
    response = client.delete('/sources/' + item['id'])
    assert response.status_code == 200
    assert response.json() == {'deleted_source_id': item['id'], 'deleted_output_histories': 0}
    assert saves == [True]
    assert removed == paths


@pytest.mark.parametrize('operation', ['delete', 'export'])
@pytest.mark.parametrize('failure', ['resolve', 'io'])
def test_adapter_failure_keeps_delete_state_consistent_and_export_fails_closed(client, source, monkeypatch, operation, failure):
    before = snapshot()
    source_id = record(source)['id']
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
    if operation == 'delete' and failure == 'io':
        monkeypatch.setattr(control, 'persist_state', lambda: None)
        response = client.delete('/sources/' + source_id)
        assert response.status_code == 200
        assert response.json()['artifact_cleanup_pending'] is True
        assert not any(item['id'] == source_id for item in db.sources)
        assert len(calls) == 3  # cleanup continues for this source's other artifacts
        assert not Path(calls[0]).exists() and Path(calls[1]).exists() and not Path(calls[2]).exists()
        assert all(asset['source_id'] != source_id for asset in db.knowledge_assets)
    else:
        monkeypatch.setattr(control, 'persist_state', lambda: pytest.fail('must not persist'))
        with pytest.raises(OSError, match='adapter failed'):
            if operation == 'delete':
                client.delete('/sources/' + source_id)
            else:
                client.get('/data/export')
        assert snapshot() == before


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


def test_unuploaded_and_partly_prepared_materials_delete_without_output_opt_in(client, source, knowledge):
    sibling, _ = source
    incomplete = client.post("/sources", json={
        "library_id": sibling["library_id"], "title": "Not yet uploaded",
    }).json()
    response = client.delete(f"/sources/{incomplete['id']}")
    assert response.status_code == 200
    assert response.json() == {"deleted_source_id": incomplete["id"], "deleted_output_histories": 0}
    assert [item["id"] for item in db.sources] == [sibling["id"]]
    assert db.knowledge_assets == [knowledge]

    # Existing useful knowledge is also removable without deleting saved work
    # when no output history depends on it.
    response = client.delete(f"/sources/{sibling['id']}")
    assert response.status_code == 200
    assert response.json()["deleted_source_id"] == sibling["id"]
    assert not db.sources and not db.knowledge_assets


def test_delete_persistence_failure_restores_live_records_and_reports_failure(client, source, knowledge, monkeypatch):
    sibling, _ = source
    source_record = next(item for item in db.sources if item['id'] == sibling['id'])
    artifact_paths = [Path(source_record[key]) for key in KEYS]
    def fail_save():
        raise RuntimeError("Synthetic persistence failure.")
    monkeypatch.setattr(control, "persist_state", fail_save)

    response = client.delete(f"/sources/{sibling['id']}")

    assert response.status_code == 400
    assert any(item["id"] == sibling["id"] for item in db.sources)
    assert db.knowledge_assets == [knowledge]
    assert all(path.is_file() for path in artifact_paths)


@pytest.mark.parametrize('conflict_kind', ['same_source_update', 'reconciliation_exhaustion'])
def test_delete_state_conflict_keeps_source_and_required_artifacts(client, source, monkeypatch, conflict_kind):
    from app.db.persistence import StateMutationConflict

    source_record = record(source)
    source_id = source_record['id']
    paths = [Path(source_record[key]) for key in KEYS]
    removals = []
    original_store = control._artifact_store

    class TrackingStore(LocalArtifactStore):
        def remove(self, path):
            removals.append(path)
            super().remove(path)

    monkeypatch.setattr(control, '_artifact_store', TrackingStore())

    def stale_save():
        # save_state's bounded reconciliation restores its latest persisted
        # snapshot before raising; model that contract at the route boundary.
        latest = deepcopy(source_record)
        if conflict_kind == 'same_source_update':
            latest['title'] = 'Concurrent identity edit'
        db.sources[:] = [latest]
        message = (
            'Hosted state changed repeatedly; this update could not be saved safely.'
            if conflict_kind == 'reconciliation_exhaustion'
            else 'Hosted state changed concurrently; this update could not be reconciled safely.'
        )
        raise StateMutationConflict(message)

    monkeypatch.setattr(control, 'persist_state', stale_save)
    response = client.delete(f'/sources/{source_id}')

    assert response.status_code == 400
    assert any(item['id'] == source_id for item in db.sources)
    if conflict_kind == 'same_source_update':
        assert db.sources[0]['title'] == 'Concurrent identity edit'
    assert removals == []
    assert all(path.is_file() for path in paths)
    monkeypatch.setattr(control, '_artifact_store', original_store)


def test_delete_reconciliation_preserves_independent_create_and_only_removes_target_artifacts(
    client, source, monkeypatch
):
    source_record = record(source)
    source_id = source_record['id']
    paths = [Path(source_record[key]) for key in KEYS]
    sibling_record = deepcopy(source_record)
    sibling_record.update(id='source_concurrent', title='Independent material')
    sibling_paths = [path.parent / f'concurrent-{path.name}' for path in paths]
    for path in sibling_paths:
        path.write_bytes(b'sibling artifact')
        sibling_record[KEYS[sibling_paths.index(path)]] = str(path)

    def rebase_delete():
        # Simulate a successful bounded rebase that retained an independent
        # concurrent create before the artifact cleanup phase.
        db.sources[:] = [sibling_record]

    monkeypatch.setattr(control, 'persist_state', rebase_delete)
    response = client.delete(f'/sources/{source_id}')

    assert response.status_code == 200
    assert [item['id'] for item in db.sources] == ['source_concurrent']
    assert all(not path.exists() for path in paths)
    assert all(path.is_file() and path.read_bytes() == b'sibling artifact' for path in sibling_paths)


def test_duplicate_delete_does_not_repeat_artifact_cleanup(client, source, monkeypatch):
    source_id = record(source)['id']
    removed = []
    original_remove = control._artifact_store.remove

    def track_remove(path):
        removed.append(path)
        original_remove(path)

    monkeypatch.setattr(control._artifact_store, 'remove', track_remove)
    first = client.delete(f'/sources/{source_id}')
    count = len(removed)
    second = client.delete(f'/sources/{source_id}')

    assert first.status_code == 200
    assert second.status_code == 404
    assert len(removed) == count == len(KEYS)


@pytest.mark.parametrize("failure_stage", ["upload", "read"])
def test_failed_material_can_be_deleted_without_touching_sibling_knowledge(
    client, source, knowledge, monkeypatch, failure_stage
):
    sibling, _ = source
    sibling_record = record(source)
    sibling_paths = {key: Path(sibling_record[key]).read_bytes() for key in KEYS}
    sibling_jobs = deepcopy(db.extraction_jobs)
    sibling_assets = deepcopy(db.knowledge_assets)
    failed = client.post("/sources", json={
        "library_id": sibling["library_id"], "title": "Incomplete material",
    }).json()

    if failure_stage == "upload":
        def fail_upload(*args, **kwargs):
            raise RuntimeError("Synthetic storage write failure.")
        monkeypatch.setattr(source_router, "_write_source_upload", fail_upload)
        response = client.post(f"/sources/{failed['id']}/upload", files={"file": ("broken.txt", b"content")})
        assert response.status_code == 400
        assert next(item for item in db.sources if item["id"] == failed["id"])["file_path"] is None
    else:
        assert client.post(f"/sources/{failed['id']}/upload", files={"file": ("broken.txt", b"content")}).status_code == 200
        assert Path(next(item for item in db.sources if item["id"] == failed["id"])["file_path"]).exists()
        monkeypatch.setattr(source_router, "extract_text_from_file", lambda **_: (_ for _ in ()).throw(ValueError("Synthetic read failure.")))
        assert client.post(f"/sources/{failed['id']}/process").status_code == 400

    removed = client.delete(f"/sources/{failed['id']}")
    assert removed.status_code == 200
    assert removed.json() == {"deleted_source_id": failed["id"], "deleted_output_histories": 0}
    assert [item["id"] for item in db.sources] == [sibling["id"]]
    assert db.extraction_jobs == sibling_jobs
    assert db.knowledge_assets == sibling_assets == [knowledge]
    assert {key: Path(sibling_record[key]).read_bytes() for key in KEYS} == sibling_paths


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

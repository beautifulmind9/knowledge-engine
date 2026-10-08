"""Adversarial publication tests: failures can happen AFTER remote mutation."""
from copy import deepcopy
from pathlib import Path
from urllib.error import URLError

import pytest

from app.db import mock_data as db, persistence
from app.persistence.factory import STORAGE_ROOT
from app.persistence.supabase_artifacts import SupabaseArtifactStore
from app.routers import sources, control, structure
from app.services import text_extraction, text_chunking
from test_supabase_artifacts import StorageAPI
from app.persistence import supabase_artifacts as module


@pytest.fixture
def published_source(client, monkeypatch):
    api = StorageAPI()
    monkeypatch.setattr(module, 'build_opener', lambda *args: api)
    store = SupabaseArtifactStore(STORAGE_ROOT, 'https://offline.supabase.co', 'sb_secret_offline',
                                  'knowledge-engine-artifacts', 'workspace-a')
    for consumer in (sources, control, structure, text_extraction, text_chunking):
        monkeypatch.setattr(consumer, '_artifact_store', store)
    monkeypatch.setattr(persistence, 'PERSISTENCE_MODE', 'hosted')
    monkeypatch.setattr(persistence, 'get_artifact_store', lambda: store)
    class State:
        snapshot = None
        failure = None
        def save(self, state):
            if self.failure == 'before_commit':
                raise RuntimeError('State save failed.')
            self.snapshot = deepcopy(state)
            if self.failure == 'after_commit':
                raise RuntimeError('State save outcome unknown.')
    state = State()
    monkeypatch.setattr(persistence, 'get_state_store', lambda: state)
    library = client.post('/libraries', json={'name': 'Publication'}).json()
    item = client.post('/sources', json={'library_id': library['id'], 'title': 'Publication'}).json()
    sid = item['id']
    assert client.post(f'/sources/{sid}/upload', files={'file': ('notes.md', b'old bytes')}).status_code == 200
    assert client.post(f'/sources/{sid}/process').status_code == 200
    record = next(s for s in db.sources if s['id'] == sid)
    assert record['chunks_path'] and record['extracted_text_path']
    return record, store, api, state


@pytest.mark.parametrize('failure', ['before_upload', 'after_upload', 'after_upload_and_cleanup'])
def test_failed_upload_preserves_published_bytes_and_derived_state(client, published_source, failure):
    record, store, api, state = published_source
    before = deepcopy(record)
    saved = deepcopy(state.snapshot)
    objects = dict(api.objects)
    original = api.open
    def faulty(request, timeout):
        if request.method == 'POST' and '/object/knowledge-engine-artifacts/' in request.full_url:
            if failure == 'before_upload':
                raise URLError('private diagnostic')
            result = original(request, timeout)  # Server commits new object first.
            result.close()
            raise URLError('response lost')
        if request.method == 'DELETE' and failure == 'after_upload_and_cleanup':
            raise URLError('cleanup denied')
        return original(request, timeout)
    api.open = faulty
    response = client.post(f"/sources/{record['id']}/upload", files={'file': ('new.md', b'changed bytes')})
    assert response.status_code == 400
    assert response.json() == {'detail': 'Hosted artifact transport failed.'}
    assert record == before and state.snapshot == saved
    for key, value in objects.items():
        assert api.objects[key] == value
    assert store.read_text(Path(record['file_path'])) == 'old bytes'
    assert store.read_text(Path(record['extracted_text_path'])) == 'old bytes'
    assert client.get('/data/integrity').json() == {'ok': True, 'issues': []}
    if failure == 'after_upload_and_cleanup':
        assert len(api.objects) == len(objects) + 1  # Private unreferenced orphan.
    else:
        assert api.objects == objects


@pytest.mark.parametrize('cleanup_fails', [False, True])
def test_publish_invalidates_derived_data_before_best_effort_cleanup(client, published_source, cleanup_fails):
    record, store, api, state = published_source
    before = deepcopy(record)
    old_objects = dict(api.objects)
    original = api.open
    deletions = []
    def cleanup(request, timeout):
        if request.method == 'DELETE':
            deletions.append(request.full_url)
            published = state.snapshot['sources'][0]
            assert published['file_path'] != store.relative_locator(Path(before['file_path'])).as_posix()
            assert published['processing_status'] == record['processing_status'] == 'uploaded'
            assert published['chunks_path'] is published['extracted_text_path'] is None
            assert record['chunks_path'] is record['extracted_text_path'] is None
            if cleanup_fails:
                raise URLError('delete failed')
        return original(request, timeout)
    api.open = cleanup
    assert client.post(f"/sources/{record['id']}/upload", files={'file': ('new.md', b'changed bytes')}).status_code == 200
    assert record['file_path'] != before['file_path']
    assert Path(record['file_path']).suffix == '.md'
    assert store.read_text(Path(record['file_path'])) == 'changed bytes'
    assert len(deletions) == 3
    assert all('.tmp' not in request.full_url for request in api.requests)
    assert client.get(f"/sources/{record['id']}/extracted-text").status_code == 404
    assert client.get('/data/integrity').json() == {'ok': True, 'issues': []}
    if cleanup_fails:
        assert all(api.objects[k] == value for k, value in old_objects.items())
    else:
        assert all(k not in api.objects for k in old_objects)


@pytest.mark.parametrize('failure', ['before_commit', 'after_commit'])
def test_state_save_failure_keeps_both_versions_for_reload(client, published_source, failure):
    record, store, api, state = published_source
    before = deepcopy(record)
    prior_snapshot = deepcopy(state.snapshot)
    prior_objects = dict(api.objects)
    state.failure = failure
    response = client.post(f"/sources/{record['id']}/upload", files={'file': ('new.md', b'changed bytes')})
    assert response.status_code == 400
    assert record == before  # Live view still refers to unchanged old bytes.
    assert len(api.objects) == len(prior_objects) + 1
    assert all(api.objects[k] == value for k, value in prior_objects.items())
    if failure == 'before_commit':
        assert state.snapshot == prior_snapshot
    else:
        recovered = state.snapshot['sources'][0]
        assert store.read_text(Path(recovered['file_path'])) == 'changed bytes'
        assert recovered['chunks_path'] is recovered['extracted_text_path'] is None
        assert recovered['processing_status'] == 'uploaded'


@pytest.mark.parametrize('content,status', [(b'', 400), (b'x' * (25 * 1024 * 1024 + 1), 413)])
def test_rejected_version_never_publishes_or_uploads(client, published_source, content, status):
    record, store, api, state = published_source
    before = deepcopy(record)
    objects = dict(api.objects)
    api.requests.clear()
    response = client.post(f"/sources/{record['id']}/upload", files={'file': ('new.md', content)})
    assert response.status_code == status
    assert record == before and api.objects == objects
    assert not any(request.method == 'POST' for request in api.requests)


@pytest.mark.parametrize('kind', ['bad_status', 'incomplete'])
def test_source_errors_never_expose_malformed_http_diagnostics(client, published_source, kind, caplog):
    from http.client import BadStatusLine, IncompleteRead
    record, store, api, state = published_source
    record['chunks_path'] = None
    record['extracted_text_path'] = None
    original = api.open
    def malformed(request, timeout):
        if request.method == 'GET':
            if kind == 'bad_status':
                raise BadStatusLine('sb_secret_remote-private-response')
            raise IncompleteRead(b'sb_secret_remote-private-body', 50)
        return original(request, timeout)
    api.open = malformed
    response = client.post(f"/sources/{record['id']}/extract")
    assert response.status_code == 400
    assert response.json() == {'detail': 'Hosted artifact transport failed.'}
    assert 'sb_secret_remote' not in response.text + caplog.text

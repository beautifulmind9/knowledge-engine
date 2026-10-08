"""Storage API tests use an in-memory opener; no network or SDK calls."""
from io import BytesIO
import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlsplit
from zipfile import ZipFile

import pytest

from app.persistence import supabase_artifacts as module
from app.persistence.supabase_artifacts import SupabaseArtifactStore, HostedArtifactStoreError
from storage_test_guard import StorageNetworkDenied
from test_persistence_factory import run_configuration


class StorageAPI:
    def __init__(self):
        self.objects = {}
        self.calls = []
        self.failure = None
        self.requests = []

    def open(self, request, timeout):
        assert timeout == 30
        assert request.get_header('Apikey') == 'sb_secret_offline'
        assert request.get_header('Authorization') is None  # Secret keys are not JWTs.
        self.requests.append(request)
        route = unquote(urlsplit(request.full_url).path).removeprefix('/storage/v1')
        self.calls.append((request.method, route))
        if self.failure:
            if isinstance(self.failure, Exception):
                raise self.failure
            code, body = self.failure
            raise HTTPError(request.full_url, code, 'remote secret diagnostic', {}, BytesIO(json.dumps(body).encode()))
        if route.startswith('/object/list/'):
            payload = json.loads(request.data)
            prefix = payload['prefix'] + '/'
            objects = []
            folders = set()
            for key in self.objects:
                if key.startswith(prefix):
                    rest = key[len(prefix):]
                    if '/' in rest:
                        folders.add(rest.split('/')[0])
                    else:
                        objects.append({'name': rest, 'id': 'object-id', 'metadata': {'size': len(self.objects[key])},
                                        'created_at': '2026-10-08T00:00:00Z', 'updated_at': '2026-10-08T00:00:00Z'})
            entries = [{'name': name, 'id': None, 'metadata': None} for name in folders] + objects
            # Folder evidence sorts first on a name tie, never overwrites a byte entry.
            items = sorted((entry for entry in entries if payload.get('search', '') in entry['name']),
                           key=lambda entry: entry['name'])
            start = payload['offset']
            return BytesIO(json.dumps(items[start:start + payload['limit']]).encode())
        key = route.split('/', 3)[3]
        if request.method == 'POST':
            assert request.get_header('X-upsert') == 'true'
            self.objects[key] = request.data
            return BytesIO(json.dumps({'Key': 'knowledge-engine-artifacts/' + key, 'Id': 'object-id'}).encode())
        if key not in self.objects:
            raise HTTPError(request.full_url, 400, 'missing', {}, BytesIO(b'{"code":"NoSuchKey","statusCode":"404","message":"Object not found"}'))
        if request.method == 'DELETE':
            del self.objects[key]
            return BytesIO(b'{"message":"Successfully deleted"}')
        assert request.method == 'GET'
        return BytesIO(self.objects[key])


@pytest.fixture
def storage(tmp_path, monkeypatch):
    api = StorageAPI()
    monkeypatch.setattr(module, 'build_opener', lambda *args: api)
    store = SupabaseArtifactStore(tmp_path / 'logical-root', 'https://offline.supabase.co',
                                  'sb_secret_offline', 'knowledge-engine-artifacts', 'workspace-a')
    return store, api


def test_text_workspace_and_normalization(storage):
    store, api = storage
    store.create_directory(store.storage_root / 'text')
    assert not api.calls and not store.storage_root.exists()
    store.write_text(store.storage_root / 'text' / 'hello.txt', 'héllo\n')
    assert api.objects == {'workspace-a/text/hello.txt': 'héllo\n'.encode()}
    assert store.read_text(Path('text/./hello.txt')) == 'héllo\n'
    other = SupabaseArtifactStore(store.storage_root, 'https://offline.supabase.co', 'sb_secret_offline',
                                  'knowledge-engine-artifacts', 'workspace-b')
    assert not other.exists(Path('text/hello.txt'))
    other.write_text(Path('text/hello.txt'), 'other')
    assert store.read_text(Path('text/hello.txt')) == 'héllo\n'
    api.objects['workspace-a/invalid.txt'] = b'\xffa'
    with pytest.raises(UnicodeDecodeError):
        store.read_text(Path('invalid.txt'))
    assert store.read_text(Path('invalid.txt'), errors='ignore') == 'a'


@pytest.mark.parametrize('locator', ['../escape', 'a/../escape', '/outside/file', 'a\\b', 'a%2Fb', 'a:b', 'a\x00b'])
@pytest.mark.parametrize('operation', ['create_directory', 'status', 'remove', 'write_text', 'materialize'])
def test_invalid_locators_never_call_api(storage, locator, operation):
    store, api = storage
    with pytest.raises(ValueError):
        if operation == 'materialize':
            with store.materialize(Path(locator)):
                pass
        elif operation == 'write_text':
            store.write_text(Path(locator), 'data')
        else:
            getattr(store, operation)(Path(locator))
    assert not api.calls


def test_binary_contexts_and_materialization_cleanup(storage):
    store, api = storage
    path = Path('uploads/report.pdf')
    with store.open_binary_write(path) as handle:
        handle.write(b'bytes')
        assert not api.objects
    assert handle.closed
    with store.open_binary_read(path) as reader:
        assert reader.read() == b'bytes'
    assert reader.closed
    with store.materialize(path) as local:
        assert local.name == 'report.pdf' and local.read_bytes() == b'bytes'
    assert not local.exists() and not local.parent.exists()
    with pytest.raises(RuntimeError):
        with store.materialize(path) as failed:
            raise RuntimeError('parser failed')
    assert not failed.exists() and not failed.parent.exists()
    with pytest.raises(RuntimeError):
        with store.open_binary_write(path) as writer:
            writer.write(b'partial')
            raise RuntimeError('caller failed')
    assert writer.closed and store.read_text(path) == 'bytes'


def test_presence_and_removal(storage):
    store, api = storage
    path = Path('uploads/file.txt')
    assert store.status(path) == 'missing' and not store.exists(path)
    store.remove(path)
    with pytest.raises(FileNotFoundError):
        store.read_text(path)
    with pytest.raises(FileNotFoundError):
        with store.materialize(path):
            pass
    store.write_text(path, '')
    assert store.status(path) == 'artifact' and store.exists(path)
    assert store.status(Path('uploads')) == 'other' and store.exists(Path('uploads'))
    assert store.status(store.storage_root) == 'other'
    store.remove(path)
    assert not store.exists(path)


@pytest.mark.parametrize('failure', [(403, {'code': 'AccessDenied'}), (401, {}), (500, {}),
                                     (404, {'code': 'NoSuchBucket'}), (404, {}),
                                     (400, {'code': 'InvalidJWT'}), URLError('secret')])
@pytest.mark.parametrize('operation', ['status', 'exists', 'read_text', 'remove', 'write_text'])
def test_failures_are_never_absence_or_secret_exposure(storage, failure, operation, caplog):
    store, api = storage
    api.failure = failure
    with pytest.raises(HostedArtifactStoreError) as error:
        if operation == 'write_text':
            store.write_text(Path('file.txt'), 'x')
        else:
            getattr(store, operation)(Path('file.txt'))
    assert 'secret' not in str(error.value) + caplog.text
    assert 'workspace-a' not in str(error.value) + caplog.text


def test_replace_overwrites_and_pre_mutation_failure_preserves_both(storage):
    store, api = storage
    temporary, destination = Path('temp'), Path('destination')
    store.write_text(temporary, 'new')
    store.write_text(destination, 'old')
    store.replace(temporary, destination)
    assert store.read_text(destination) == 'new' and not store.exists(temporary)
    store.replace(destination, destination)
    with pytest.raises(FileNotFoundError):
        store.replace(temporary, destination)
    store.write_text(temporary, 'retry')
    original = api.open
    def failing_upload(request, timeout):
        if request.method == 'POST' and '/destination' in request.full_url:
            raise URLError('private')
        return original(request, timeout)
    api.open = failing_upload
    with pytest.raises(HostedArtifactStoreError):
        store.replace(temporary, destination)
    assert store.read_text(temporary) == 'retry' and store.read_text(destination) == 'new'


@pytest.mark.parametrize('name', ['SUPABASE_URL', 'SUPABASE_SECRET_KEY', 'KNOWLEDGE_ENGINE_STORAGE_BUCKET', 'KNOWLEDGE_ENGINE_WORKSPACE_KEY'])
def test_factory_missing_storage_config(tmp_path, name):
    run_configuration('''
        import os
        os.environ['KNOWLEDGE_ENGINE_DATABASE_URL'] = 'offline'
        os.environ['KNOWLEDGE_ENGINE_WORKSPACE_KEY'] = 'offline'
        os.environ.pop(NAME, None)
        try:
            import app.persistence.factory
        except RuntimeError as error:
            assert NAME in str(error)
        else:
            raise AssertionError('missing configuration accepted')
    '''.replace('NAME', repr(name)), tmp_path / 'root', 'hosted')


@pytest.mark.parametrize('field,value', [('url','http://offline.supabase.co'), ('url','https://user:pass@offline.supabase.co'),
                                       ('url','https://offline.supabase.co/path'), ('secret_key','sb_publishable_foo'),
                                       ('bucket','../bucket'), ('workspace_key','a/b'), ('workspace_key','..'),
                                       ('workspace_key',' a ')])
def test_invalid_configuration_fails_closed(tmp_path, field, value):
    settings = dict(storage_root=tmp_path, url='https://offline.supabase.co', secret_key='sb_secret_offline',
                    bucket='private', workspace_key='workspace')
    settings[field] = value
    with pytest.raises(RuntimeError):
        SupabaseArtifactStore(**settings)


def test_network_guard_denies_unmocked_adapter(tmp_path, caplog):
    store = SupabaseArtifactStore(tmp_path, 'https://offline.supabase.co', 'sb_secret_offline', 'private', 'workspace')
    with pytest.raises(StorageNetworkDenied):
        store.exists(Path('file'))
    assert 'sb_secret' not in caplog.text


def test_hosted_product_flows(client, monkeypatch):
    from app.persistence.factory import STORAGE_ROOT
    from app.db import mock_data as db
    from app.routers import sources, control, structure
    from app.services import text_extraction, text_chunking
    api = StorageAPI()
    monkeypatch.setattr(module, 'build_opener', lambda *args: api)
    store = SupabaseArtifactStore(STORAGE_ROOT, 'https://offline.supabase.co', 'sb_secret_offline',
                                  'knowledge-engine-artifacts', 'workspace-a')
    for consumer in (sources, control, structure, text_extraction, text_chunking):
        monkeypatch.setattr(consumer, '_artifact_store', store)
    library = client.post('/libraries', json={'name': 'Hosted'}).json()
    source = client.post('/sources', json={'library_id': library['id'], 'title': 'Hosted notes'}).json()
    sid = source['id']
    content = 'Use specific goals and practical activities to help participants learn.'
    assert client.post(f'/sources/{sid}/upload', files={'file': ('notes.md', content, 'text/markdown')}).status_code == 200
    assert client.post(f'/sources/{sid}/process').status_code == 200
    assert client.get(f'/sources/{sid}/chunks').status_code == 200
    # Simulate source records reloaded from a hosted root-relative snapshot.
    reloaded = next(s for s in db.sources if s['id'] == sid)
    for key in ('file_path', 'extracted_text_path', 'chunks_path'):
        reloaded[key] = Path(reloaded[key]).relative_to(STORAGE_ROOT).as_posix()
    assert client.get(f'/sources/{sid}/file').content == content.encode()
    assert client.get(f'/sources/{sid}/extracted-text').status_code == 200
    item = next(s for s in db.sources if s['id'] == sid)
    for key in ('file_path', 'extracted_text_path', 'chunks_path'):
        assert store.status(Path(item[key])) == 'artifact'
        assert not (STORAGE_ROOT / item[key]).exists()
    assert client.get('/data/integrity').json() == {'ok': True, 'issues': []}
    exported = client.get('/data/export')
    assert exported.status_code == 200
    with ZipFile(BytesIO(exported.content)) as archive:
        state = json.loads(archive.read('storage/state.json'))
        for key in ('file_path', 'extracted_text_path', 'chunks_path'):
            name = state['sources'][0][key]
            assert name.startswith('storage/') and archive.read(name)
        assert archive.testzip() is None
    assert client.delete(f'/sources/{sid}').status_code == 200
    assert not api.objects


def test_hosted_startup_needs_no_storage_directory(tmp_path):
    run_configuration("""
        import asyncio
        import os
        from unittest.mock import patch
        os.environ['KNOWLEDGE_ENGINE_DATABASE_URL'] = 'offline'
        os.environ['KNOWLEDGE_ENGINE_WORKSPACE_KEY'] = 'offline'
        with patch('app.persistence.postgres.PostgresStateStore.load', return_value=None):
            from app.main import app, lifespan
            from app.persistence.factory import STORAGE_ROOT
            async def start():
                async with lifespan(app):
                    assert not STORAGE_ROOT.exists()
            asyncio.run(start())
            assert not STORAGE_ROOT.exists()
    """, tmp_path / 'absent-root', 'hosted')


def test_legacy_explicit_missing_and_prefix_pagination(storage):
    store, api = storage
    api.failure = (400, {'error': 'not_found', 'message': 'Object not found', 'statusCode': '404'})
    with pytest.raises(FileNotFoundError):
        store.read_text(Path('missing'))
    store.remove(Path('missing'))
    api.failure = None
    for i in range(105):
        api.objects[f'workspace-a/prefix/name-{i:03}'] = b'x'
    api.objects['workspace-a/prefix/name-z'] = b'x'
    assert store.status(Path('prefix/name-z')) == 'artifact'
    assert store.status(Path('prefix/name')) == 'missing'


def test_upload_and_delete_failures_close_working_files(storage):
    store, api = storage
    api.failure = URLError('private')
    with pytest.raises(HostedArtifactStoreError):
        with store.open_binary_write(Path('file')) as working:
            working.write(b'bytes')
    assert working.closed
    api.failure = None
    store.write_text(Path('temp'), 'new')
    original = api.open
    def fail_delete(request, timeout):
        if request.method == 'DELETE':
            raise URLError('private')
        return original(request, timeout)
    api.open = fail_delete
    with pytest.raises(HostedArtifactStoreError):
        store.replace(Path('temp'), Path('destination'))
    assert store.read_text(Path('temp')) == store.read_text(Path('destination')) == 'new'


def test_raw_network_guard_and_inherited_configuration(tmp_path):
    import socket
    from urllib.request import urlopen
    for call in (lambda: socket.getaddrinfo('offline.supabase.co', 443),
                 lambda: urlopen('https://offline.supabase.co')):
        with pytest.raises(StorageNetworkDenied):
            call()
    run_configuration("""
        import os
        from storage_test_guard import StorageNetworkDenied
        os.environ['KNOWLEDGE_ENGINE_DATABASE_URL'] = 'offline'
        os.environ['KNOWLEDGE_ENGINE_WORKSPACE_KEY'] = 'offline'
        from app.persistence.factory import get_artifact_store
        from pathlib import Path
        try:
            get_artifact_store().exists(Path('file'))
        except StorageNetworkDenied:
            pass
        else:
            raise AssertionError('unguarded storage network')
    """, tmp_path / 'root', 'hosted')


def test_hosted_snapshots_have_portable_locators_without_mutating_records(storage, monkeypatch):
    from app.db import persistence
    store, api = storage
    monkeypatch.setattr(persistence, 'PERSISTENCE_MODE', 'hosted')
    monkeypatch.setattr(persistence, 'STORAGE_ROOT', store.storage_root)
    monkeypatch.setattr(persistence, 'get_artifact_store', lambda: store)
    saved = []
    class State:
        def save(self, state):
            saved.append(state)
    monkeypatch.setattr(persistence, 'get_state_store', State)
    source = {'id': 'source', 'file_path': str(store.storage_root / 'uploads/one.txt'),
              'extracted_text_path': 'extracted_text/one.txt', 'chunks_path': None}
    persistence.save_state([], [source], [], [])
    assert saved[0]['sources'][0]['file_path'] == 'uploads/one.txt'
    assert source['file_path'].startswith(str(store.storage_root))
    assert saved[0]['sources'][0]['extracted_text_path'] == 'extracted_text/one.txt'
    store.write_text(Path(saved[0]['sources'][0]['file_path']), 'portable')
    second = SupabaseArtifactStore(store.storage_root.parent / 'another-machine',
                                   'https://offline.supabase.co', 'sb_secret_offline',
                                   'knowledge-engine-artifacts', 'workspace-a')
    assert second.read_text(Path(saved[0]['sources'][0]['file_path'])) == 'portable'
    source['file_path'] = '/outside/one.txt'
    with pytest.raises(ValueError):
        persistence.save_state([], [source], [], [])
    assert len(saved) == 1


@pytest.mark.parametrize('payload', [b'a\r\nb\rc\n', b'\r', b'\n', b'\r\n', b'', b'Caf\xc3\xa9\xff\r\nx'])
@pytest.mark.parametrize('errors', ['strict', 'ignore', 'replace'])
def test_text_newline_and_utf8_parity(storage, tmp_path, payload, errors):
    from app.persistence.local_artifacts import LocalArtifactStore
    store, api = storage
    api.objects['workspace-a/parity.txt'] = payload
    local = tmp_path / 'parity.txt'
    local.write_bytes(payload)
    if errors == 'strict' and b'\xff' in payload:
        with pytest.raises(UnicodeDecodeError):
            store.read_text(Path('parity.txt'), errors=errors)
        with pytest.raises(UnicodeDecodeError):
            LocalArtifactStore().read_text(local, errors=errors)
    else:
        assert store.read_text(Path('parity.txt'), errors=errors) == LocalArtifactStore().read_text(local, errors=errors)


@pytest.mark.parametrize('kind', ['object', 'prefix', 'both'])
def test_exact_byte_object_wins_over_prefix(storage, kind):
    store, api = storage
    if kind in ('prefix', 'both'):
        api.objects['workspace-a/key/child'] = b'child'
    if kind in ('object', 'both'):
        api.objects['workspace-a/key'] = b'bytes'
    assert store.status(Path('key')) == ('other' if kind == 'prefix' else 'artifact')
    if kind == 'both':
        listing = store._list('workspace-a', search='key')
        assert [entry['id'] for entry in listing] == [None, 'object-id']
        assert store.read_text(Path('key')) == 'bytes'


def test_exact_byte_evidence_on_later_page(storage):
    store, api = storage
    original = api.open
    offsets = []
    def pages(request, timeout):
        if '/object/list/' in request.full_url:
            payload = json.loads(request.data)
            offsets.append(payload['offset'])
            if payload['offset'] == 0:
                entries = [{'name': 'key', 'id': None, 'metadata': None}] + [
                    {'name': f'key-extra-{i}', 'id': 'id', 'metadata': {'size': 1}} for i in range(99)]
            else:
                entries = [{'name': 'key', 'id': 'byte-object', 'metadata': {'size': 1}}]
            return BytesIO(json.dumps(entries).encode())
        return original(request, timeout)
    api.open = pages
    assert store.status(Path('key')) == 'artifact' and offsets == [0, 100]


@pytest.mark.parametrize('phase', ['open', 'success_body', 'error_body'])
@pytest.mark.parametrize('kind', ['bad_status', 'incomplete'])
def test_http_protocol_errors_are_sanitized(storage, phase, kind, caplog):
    from http.client import BadStatusLine, IncompleteRead
    from app.persistence.supabase_artifacts import HostedArtifactTransportError
    store, api = storage
    error = BadStatusLine('sb_secret_private-remote-text') if kind == 'bad_status' else IncompleteRead(b'sb_secret_private', 50)
    class BrokenBody(BytesIO):
        def read(self, *args):
            raise error
    body = BrokenBody(b'partial')
    def broken(request, timeout):
        if phase == 'open':
            raise error
        if phase == 'error_body':
            raise HTTPError(request.full_url, 404, 'private', {}, body)
        return body
    api.open = broken
    with pytest.raises(HostedArtifactTransportError) as actual:
        store.read_text(Path('file'))
    assert str(actual.value) == 'Hosted artifact transport failed.'
    assert 'sb_secret_private' not in str(actual.value) + caplog.text
    assert actual.value.__suppress_context__
    if phase != 'open':
        assert body.closed


@pytest.mark.parametrize('locator', ['', '.', 'root'])
@pytest.mark.parametrize('operation', ['write_text', 'read_text', 'remove', 'binary_write', 'binary_read', 'materialize', 'replace_source', 'replace_destination'])
def test_root_byte_locators_rejected_without_api(storage, locator, operation):
    store, api = storage
    path = store.storage_root if locator == 'root' else Path(locator)
    with pytest.raises(ValueError):
        if operation == 'write_text':
            store.write_text(path, 'x')
        elif operation.startswith('replace'):
            store.replace(path, Path('dest')) if operation == 'replace_source' else store.replace(Path('temp'), path)
        elif operation in ('binary_write', 'binary_read', 'materialize'):
            method = {'binary_write': store.open_binary_write, 'binary_read': store.open_binary_read, 'materialize': store.materialize}[operation]
            with method(path):
                pass
        else:
            getattr(store, operation)(path)
    assert not api.calls


def test_exact_url_encoding_and_upsert(storage):
    store, api = storage
    path = Path("folder/Café notes+#?.txt")
    store.write_text(path, 'first')
    request = api.requests[-1]
    assert request.full_url == 'https://offline.supabase.co/storage/v1/object/knowledge-engine-artifacts/workspace-a/folder/Caf%C3%A9%20notes%2B%23%3F.txt'
    assert request.method == 'POST' and request.get_header('X-upsert') == 'true'
    assert request.get_header('Content-type') == 'application/octet-stream'
    store.write_text(path, 'overwritten')
    assert store.read_text(path) == 'overwritten'
    assert api.requests[-1].full_url == request.full_url and api.requests[-1].method == 'GET'
    store.remove(path)
    assert api.requests[-1].full_url == request.full_url and api.requests[-1].method == 'DELETE'
    store.remove(path)  # Explicit missing object is a safe no-op.
    assert not api.objects


@pytest.mark.parametrize('locator', ['a%2fb', 'a%2Fb', 'a%5Cb', '%252f', '%2e%2e/escape', 'a\\b'])
def test_encoded_separators_never_reinterpreted(storage, locator):
    store, api = storage
    with pytest.raises(ValueError):
        with store.open_binary_write(Path(locator)):
            pass
    assert not api.requests


@pytest.mark.parametrize('status', [301, 302, 303, 307, 308])
def test_redirects_are_rejected_without_followup(storage, status):
    from urllib.request import Request
    store, api = storage
    api.failure = (status, {'message': 'redirect'})
    assert module._NoRedirect().redirect_request(Request('https://offline.supabase.co'), None, status,
                                               'redirect', {}, 'https://other.example') is None
    with pytest.raises(HostedArtifactStoreError):
        store.read_text(Path('file'))
    assert len(api.requests) == 1


def test_materialization_download_failure_removes_temporary_directory(storage, monkeypatch):
    store, api = storage
    original = module.TemporaryDirectory
    directories = []
    def tracked(*args, **kwargs):
        temporary = original(*args, **kwargs)
        directories.append(Path(temporary.name))
        return temporary
    monkeypatch.setattr(module, 'TemporaryDirectory', tracked)
    api.failure = URLError('private')
    with pytest.raises(HostedArtifactStoreError):
        with store.materialize(Path('report.pdf')):
            pytest.fail('failed download yielded a path')
    assert directories and not directories[0].exists()


@pytest.mark.parametrize('status', [301, 302, 303, 307, 308])
def test_real_redirect_handler_chain_with_fake_http_response(tmp_path, monkeypatch, status):
    from email.message import Message
    from urllib.request import HTTPSHandler, build_opener
    from urllib.response import addinfourl
    seen = []
    class FakeHTTPS(HTTPSHandler):
        def https_open(self, request):
            seen.append(request.full_url)
            headers = Message()
            headers['Location'] = 'https://offline.supabase.co/redirect-target'
            response = addinfourl(BytesIO(b'{"message":"redirect"}'), headers, request.full_url, code=status)
            response.msg = 'Redirect'
            return response
    def fake_opener(*handlers):
        assert any(isinstance(handler, module._NoRedirect) for handler in handlers)
        return build_opener(*handlers, FakeHTTPS())
    monkeypatch.setattr(module, 'build_opener', fake_opener)
    monkeypatch.setattr('socket.socket.connect', lambda *args: pytest.fail('unexpected socket'))
    store = SupabaseArtifactStore(tmp_path, 'https://localhost', 'sb_secret_offline', 'private', 'workspace')
    with pytest.raises(HostedArtifactStoreError):
        store.read_text(Path('file'))
    assert seen == ['https://localhost/storage/v1/object/private/workspace/file']



def test_generic_replace_lost_response_can_follow_remote_mutation(storage):
    store, api = storage
    store.write_text(Path('temporary'), 'new')
    store.write_text(Path('destination'), 'old')
    original = api.open
    def lost_response(request, timeout):
        if request.method == 'POST' and request.full_url.endswith('/destination'):
            response = original(request, timeout)
            response.close()
            raise URLError('response lost after remote commit')
        return original(request, timeout)
    api.open = lost_response
    with pytest.raises(HostedArtifactStoreError):
        store.replace(Path('temporary'), Path('destination'))
    assert store.read_text(Path('destination')) == 'new'
    assert store.read_text(Path('temporary')) == 'new'

"""Render configuration/ingress tests: no server or external connections."""
import os
from pathlib import Path
import subprocess

import pytest
import yaml  # Already pinned in requirements-lock.txt (uvicorn[standard]).
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.beta_access import same_origin
from app.deployment import public_host, LOCAL_HOSTS, HostedHTTPSMiddleware
from test_persistence_factory import run_configuration

REPO_ROOT = Path(__file__).resolve().parents[3]
HOST = 'private-beta.onrender.com'


def test_local_host_defaults_ignore_inherited_host_config(monkeypatch, client):
    monkeypatch.setenv('KNOWLEDGE_ENGINE_PUBLIC_HOST', '*')
    assert public_host('local') is None
    assert LOCAL_HOSTS == ['localhost', '127.0.0.1', '[::1]', 'testserver']
    assert client.get('/health').json() == {'status': 'ok'}
    assert client.get('/health', headers={'Host': HOST}).status_code == 400
    assert client.get('/').status_code == 200


@pytest.mark.parametrize('host', ['', '*', '*.onrender.com', 'localhost', '127.0.0.1', '[::1]',
                                  'https://beta.onrender.com', 'beta.onrender.com/path',
                                  'beta.onrender.com?x=1', 'beta.onrender.com#fragment',
                                  'beta.onrender.com:443', ' beta.onrender.com', 'beta.onrender.com ',
                                  'beta.onrender.com,evil.example', 'beta..com', '-beta.com',
                                  'beta-.com', 'beta.com.', 'user@beta.com', 'βeta.com',
                                  'beta.com\n', 'x' * 64 + '.com', '.com'])
def test_invalid_public_hostname_rejected_without_echo(monkeypatch, host):
    monkeypatch.setenv('KNOWLEDGE_ENGINE_PUBLIC_HOST', host)
    with pytest.raises(RuntimeError, match='KNOWLEDGE_ENGINE_PUBLIC_HOST') as error:
        public_host('hosted')
    assert str(error.value) == 'Hosted deployment requires KNOWLEDGE_ENGINE_PUBLIC_HOST as a valid DNS hostname.'


@pytest.mark.parametrize('host', [HOST, 'Private-Beta.OnRender.Com', 'beta.example.com'])
def test_valid_hostname_normalized(monkeypatch, host):
    monkeypatch.setenv('KNOWLEDGE_ENGINE_PUBLIC_HOST', host)
    assert public_host('hosted') == host.lower()


@pytest.mark.parametrize('missing', ['KNOWLEDGE_ENGINE_DATABASE_URL', 'KNOWLEDGE_ENGINE_WORKSPACE_KEY',
                                   'SUPABASE_URL', 'SUPABASE_SECRET_KEY', 'KNOWLEDGE_ENGINE_STORAGE_BUCKET',
                                   'KNOWLEDGE_ENGINE_BETA_PASSWORD', 'KNOWLEDGE_ENGINE_SESSION_SECRET',
                                   'KNOWLEDGE_ENGINE_PUBLIC_HOST'])
def test_hosted_required_configuration_fails_before_io_or_local_fallback(tmp_path, missing):
    code = '''
        import os
        from unittest.mock import patch
        os.environ['KNOWLEDGE_ENGINE_DATABASE_URL'] = 'offline-dsn'
        os.environ['KNOWLEDGE_ENGINE_WORKSPACE_KEY'] = 'offline-workspace'
        secrets = [os.environ[name] for name in ('SUPABASE_SECRET_KEY', 'KNOWLEDGE_ENGINE_BETA_PASSWORD',
                                                 'KNOWLEDGE_ENGINE_SESSION_SECRET')]
        os.environ.pop(MISSING)
        with patch('app.persistence.postgres.PostgresStateStore.load', side_effect=AssertionError('state IO')), \
             patch('app.persistence.sqlite.SQLiteStateStore.__init__', side_effect=AssertionError('local state')), \
             patch('app.persistence.local_artifacts.LocalArtifactStore.__init__', side_effect=AssertionError('local artifacts')):
            try:
                import app.main
            except RuntimeError as error:
                assert MISSING in str(error)
                assert all(secret not in str(error) for secret in secrets)
            else:
                raise AssertionError('missing required hosted configuration accepted')
    '''.replace('MISSING', repr(missing))
    root = tmp_path / 'must-not-exist'
    run_configuration(code, root, 'hosted')
    assert not root.exists()


def test_real_hosted_app_boot_health_auth_static_and_ai_disabled_without_disk(tmp_path):
    # Fresh import uses the actual hosted factory, app, middleware and lifespan.
    # Only the state boundary is mocked; the HTTP transport/network guards remain.
    run_configuration('''
        import os
        from pathlib import Path
        from unittest.mock import patch
        from fastapi.testclient import TestClient
        os.environ['KNOWLEDGE_ENGINE_DATABASE_URL'] = 'offline-dsn'
        os.environ['KNOWLEDGE_ENGINE_WORKSPACE_KEY'] = 'offline-workspace'
        host = os.environ['KNOWLEDGE_ENGINE_PUBLIC_HOST']
        root = Path(os.environ['KNOWLEDGE_ENGINE_STORAGE'])
        with patch('app.persistence.postgres.PostgresStateStore.load', return_value=None) as load, \
             patch('app.persistence.postgres.PostgresStateStore.save') as save, \
             patch('app.persistence.sqlite.SQLiteStateStore.__init__', side_effect=AssertionError('local state')), \
             patch('app.persistence.local_artifacts.LocalArtifactStore.__init__', side_effect=AssertionError('local artifacts')), \
             patch('app.services.ai_gateway.genai.Client', side_effect=AssertionError('Gemini IO')) as provider:
            from app.main import app
            from app.persistence.factory import get_state_store, get_artifact_store
            from app.persistence.postgres import PostgresStateStore
            from app.persistence.supabase_artifacts import SupabaseArtifactStore
            from app.beta_access import CSRF_COOKIE
            assert isinstance(get_state_store(), PostgresStateStore)
            assert isinstance(get_artifact_store(), SupabaseArtifactStore)
            assert 'GEMINI_API_KEY' not in os.environ
            with TestClient(app, base_url='http://' + host, follow_redirects=False) as client:
                load.assert_called_once()
                # Dependency failures after startup cannot turn process health into dependency health.
                load.side_effect = AssertionError('health attempted state load')
                with patch.object(SupabaseArtifactStore, '_request', side_effect=AssertionError('Storage IO')):
                    assert client.get('/health').json() == {'status': 'ok'}
                    assert client.get('/health', headers={'Host': 'localhost'}).status_code == 400
                    assert client.get('/health', headers={'Host': 'evil.example'}).status_code == 400
                    assert client.get('/libraries').status_code == 401
                    assert client.get('/docs').status_code == 401
                    assert client.get('/login').status_code == 200
                    assert client.get('/static/style.css').status_code == 200
                    assert client.get('/static/app.js').status_code == 401
                    login = client.post('/login', data={'password': os.environ['KNOWLEDGE_ENGINE_BETA_PASSWORD']},
                                        headers={'Origin': 'https://' + host, 'X-Forwarded-Proto': 'http'})
                    assert login.status_code == 303
                    assert all('Secure' in value for value in login.headers.get_list('set-cookie'))
                    # Simulate TLS offload: app sees HTTP but cookies arrive from public HTTPS.
                    cookies = '; '.join(name + '=' + value for name, value in client.cookies.items())
                    headers = {'Cookie': cookies, 'Origin': 'https://' + host,
                               'X-CSRF-Token': client.cookies.get(CSRF_COOKIE)}
                    assert client.get('/', headers=headers).status_code == 200
                    for name in ('app.js', 'api.js', 'enhancements.js', 'creator-direction.js'):
                        assert client.get('/static/' + name, headers=headers).status_code == 200
                    result = client.post('/libraries', json={'name': 'Hosted offline'}, headers=headers)
                    assert result.status_code == 200
                    assert save.called
                    assert client.get('/usage', headers=headers).json()['configured'] is False
                    result = client.post('/knowledge-extractions/offline-job/run', headers=headers)
                    assert result.status_code == 400
                    assert 'not configured' in result.json()['detail']
                    assert client.post('/logout', headers=headers).status_code == 303
                provider.assert_not_called()
            assert not root.exists()
    ''', tmp_path / 'no-persistent-disk', 'hosted')


@pytest.fixture
def ingress():
    app = FastAPI()
    @app.post('/origin')
    async def check(request: Request):
        from fastapi.responses import JSONResponse
        return JSONResponse({'scheme': request.url.scheme}, status_code=200 if same_origin(request) else 403)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=[HOST], www_redirect=False)
    app.add_middleware(HostedHTTPSMiddleware, host=HOST)
    # Mirrors --no-proxy-headers: no source address may supply proxy authority.
    return app


@pytest.mark.parametrize('origin,expected', [('https://' + HOST, 200), ('http://' + HOST, 403),
                                          ('https://evil.example', 403), ('null', 403)])
@pytest.mark.parametrize('forwarded', [{}, {'X-Forwarded-Proto': 'http', 'X-Forwarded-Host': 'evil.example'},
                                     {'X-Forwarded-Proto': 'https', 'X-Forwarded-For': '127.0.0.1',
                                      'Forwarded': 'host=evil.example;proto=https'}])
def test_fixed_https_origin_ignores_forwarding_headers(ingress, origin, expected, forwarded):
    with TestClient(ingress, base_url='http://' + HOST) as client:
        response = client.post('/origin', headers={'Origin': origin, **forwarded})
        assert response.status_code == expected
        assert response.json()['scheme'] == 'https'


@pytest.mark.parametrize('host', ['localhost', 'testserver', 'evil.example', HOST + ':443',
                                 HOST + ':junk', HOST + '.evil.example', HOST + '.'])
def test_host_spoofing_is_rejected_before_origin_or_auth(ingress, host):
    with TestClient(ingress, base_url='http://' + HOST) as client:
        response = client.post('/origin', headers={'Host': host, 'Origin': 'https://' + HOST,
                                                   'X-Forwarded-Host': HOST, 'X-Forwarded-Proto': 'https'})
        assert response.status_code == 400
        assert response.text == 'Invalid host header'


def test_duplicate_host_header_rejected(ingress):
    with TestClient(ingress, base_url='http://' + HOST) as client:
        response = client.post('/origin', headers=[('Host', HOST), ('Host', 'evil.example')])
        assert response.status_code == 400


def test_blueprint_one_free_service_no_disks_or_secret_values():
    blueprint = yaml.safe_load((REPO_ROOT / 'render.yaml').read_text())
    assert set(blueprint) == {'services'}
    assert len(blueprint['services']) == 1
    service = blueprint['services'][0]
    assert service['type'] == 'web' and service['runtime'] == 'python' and service['plan'] == 'free'
    assert service['buildCommand'] == 'pip install -r apps/api/requirements-lock.txt'
    assert service['startCommand'] == 'bash scripts/render_start.sh'
    assert service['healthCheckPath'] == '/health'
    assert 'disk' not in service and service['numInstances'] == 1
    env = {item['key']: item for item in service['envVars']}
    for key in ('KNOWLEDGE_ENGINE_DATABASE_URL', 'KNOWLEDGE_ENGINE_WORKSPACE_KEY', 'SUPABASE_URL',
                'SUPABASE_SECRET_KEY', 'KNOWLEDGE_ENGINE_BETA_PASSWORD'):
        assert env[key] == {'key': key, 'sync': False}
    assert env['KNOWLEDGE_ENGINE_SESSION_SECRET'] == {
        'key': 'KNOWLEDGE_ENGINE_SESSION_SECRET', 'generateValue': True}
    assert env['KNOWLEDGE_ENGINE_PUBLIC_HOST'] == {
        'key': 'KNOWLEDGE_ENGINE_PUBLIC_HOST',
        'fromService': {'name': service['name'], 'type': service['type'],
                        'envVarKey': 'RENDER_EXTERNAL_HOSTNAME'}}
    assert env['KNOWLEDGE_ENGINE_PERSISTENCE_MODE']['value'] == 'hosted'
    assert env['GEMINI_FREE_TIER_CONFIRMED']['value'] == 'false'
    assert 'GEMINI_API_KEY' not in env


def test_start_command_from_any_directory_uses_render_port_and_one_worker(tmp_path):
    # Execute the real shell script, replacing only Python with a local argument recorder.
    recorder = tmp_path / 'python'
    recorder.write_text('#!/bin/bash\nprintf "%s\\n" "$PWD" "$@"\n')
    recorder.chmod(0o700)
    env = {**os.environ, 'PATH': str(tmp_path) + ':' + os.environ['PATH'], 'PORT': '18765',
           'KNOWLEDGE_ENGINE_PERSISTENCE_MODE': 'hosted'}
    result = subprocess.run(['bash', str(REPO_ROOT / 'scripts/render_start.sh')], cwd=tmp_path,
                            env=env, text=True, capture_output=True, timeout=5)
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [str(REPO_ROOT), '-m', 'uvicorn', 'app.main:app',
                                         '--app-dir', 'apps/api', '--host', '0.0.0.0', '--port', '18765',
                                         '--workers', '1', '--no-proxy-headers']
    env.pop('PORT')
    result = subprocess.run(['bash', str(REPO_ROOT / 'scripts/render_start.sh')], env=env,
                            text=True, capture_output=True, timeout=5)
    assert result.returncode != 0 and 'Render PORT must be set' in result.stderr
    env['KNOWLEDGE_ENGINE_PERSISTENCE_MODE'] = 'local'
    result = subprocess.run(['bash', str(REPO_ROOT / 'scripts/render_start.sh')], env=env,
                            text=True, capture_output=True, timeout=5)
    assert result.returncode != 0 and 'requires hosted persistence' in result.stderr

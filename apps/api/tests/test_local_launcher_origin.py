"""Exercise the real local launcher configuration without sockets or provider IO."""
from pathlib import Path
import runpy
from unittest.mock import patch

from fastapi.testclient import TestClient
import pytest
import uvicorn

import app.main as main

ROOT = Path(__file__).resolve().parents[3]


def launcher_options(monkeypatch):
    monkeypatch.setattr('sys.argv', [str(ROOT / 'scripts/run.py')])
    with patch('dotenv.load_dotenv'), patch('uvicorn.run') as run:
        runpy.run_path(str(ROOT / 'scripts/run.py'), run_name='__main__')
    assert run.call_args.args == ('app.main:app',)
    return run.call_args.kwargs


class ObserveScheme:
    def __init__(self):
        self.schemes = []

    async def __call__(self, scope, receive, send):
        if scope['type'] == 'http':
            self.schemes.append(scope['scheme'])
        await main.app(scope, receive, send)


def configured_app(options, observer):
    config = uvicorn.Config(observer, **options)
    config.load()
    return config.loaded_app


def test_live_failure_reproduction_with_old_uvicorn_proxy_default():
    observer = ObserveScheme()
    app = configured_app({'proxy_headers': True}, observer)
    with TestClient(app, base_url='http://localhost:8000', client=('127.0.0.1', 12345)) as client:
        response = client.get('/static/app.js', headers={
            'Origin': 'http://localhost:8000', 'X-Forwarded-Proto': 'https',
            'Sec-Fetch-Site': 'same-origin', 'Sec-Fetch-Mode': 'cors', 'Sec-Fetch-Dest': 'script',
        })
    assert observer.schemes == ['https']
    assert response.status_code == 403
    assert response.json() == {'detail': 'Cross-origin access is disabled for this local private beta.'}


@pytest.mark.parametrize('authority', ['localhost:8000', '127.0.0.1:8000'])
@pytest.mark.parametrize('path', ['/static/app.js', '/static/creator-direction.js', '/static/enhancements.js', '/static/api.js'])
def test_real_local_launcher_keeps_loopback_origin_and_effective_scheme_consistent(monkeypatch, authority, path):
    options = launcher_options(monkeypatch)
    observer = ObserveScheme()
    app = configured_app(options, observer)
    with TestClient(app, base_url='http://' + authority, client=('127.0.0.1', 12345)) as client:
        response = client.get(path, headers={
            'Origin': 'http://' + authority, 'X-Forwarded-Proto': 'https',
            'Sec-Fetch-Site': 'same-origin', 'Sec-Fetch-Mode': 'cors', 'Sec-Fetch-Dest': 'script',
        })
    assert response.status_code == 200, (response.status_code, response.text)
    assert observer.schemes == ['http']
    assert 'javascript' in response.headers['content-type']


@pytest.mark.parametrize('origin', [
    'https://localhost:8000', 'http://evil.example', 'https://evil.example',
    'https://another-workspace-8000.app.github.dev', 'http://localhost:8001',
    'http://127.0.0.1:8000', 'http://user:password@localhost:8000',
    'http://localhost:8000/path', 'http://localhost:8000?query',
    'http://localhost:8000#fragment', 'null', 'https://[invalid',
])
def test_local_launcher_rejects_other_origins_despite_forwarding_and_fetch_headers(monkeypatch, origin):
    # Even an inherited all-proxies-trusted setting cannot override proxy_headers=False.
    monkeypatch.setenv('FORWARDED_ALLOW_IPS', '*')
    options = launcher_options(monkeypatch)
    assert options['proxy_headers'] is False
    app = configured_app(options, ObserveScheme())
    with TestClient(app, base_url='http://localhost:8000', client=('127.0.0.1', 12345)) as client:
        response = client.get('/static/app.js', headers={
            'Origin': origin, 'X-Forwarded-Proto': 'https',
            'X-Forwarded-Host': 'localhost:8000', 'Forwarded': 'host=localhost:8000;proto=https',
            'Sec-Fetch-Site': 'same-origin', 'Sec-Fetch-Mode': 'cors', 'Sec-Fetch-Dest': 'script',
        })
    assert response.status_code == 403


@pytest.mark.parametrize('host', ['localhost:8001', '127.0.0.1:8000', 'evil.example:8000'])
def test_local_launcher_rejects_mismatched_host_or_port(monkeypatch, host):
    app = configured_app(launcher_options(monkeypatch), ObserveScheme())
    with TestClient(app, base_url='http://localhost:8000', client=('127.0.0.1', 12345)) as client:
        assert client.get('/static/app.js', headers={
            'Host': host, 'Origin': 'http://localhost:8000',
            'X-Forwarded-Host': 'localhost:8000', 'X-Forwarded-Proto': 'http',
        }).status_code == 403


def test_local_launcher_preserves_beta_authentication_and_csrf(monkeypatch):
    import secrets
    from app.beta_access import BetaAccess, SESSION_COOKIE
    gate = BetaAccess('fixture-password', secrets.token_urlsafe(32))
    app = configured_app(launcher_options(monkeypatch), ObserveScheme())
    with patch.object(main.app.state, 'beta_access', gate):
        with TestClient(app, base_url='http://localhost:8000', client=('127.0.0.1', 12345), follow_redirects=False) as client:
            headers = {'Origin': 'http://localhost:8000', 'X-Forwarded-Proto': 'https'}
            assert client.get('/static/app.js', headers=headers).status_code == 401
            token, csrf = gate.issue_session()
            headers['Cookie'] = SESSION_COOKIE + '=' + token
            assert client.get('/static/app.js', headers=headers).status_code == 200
            assert client.post('/libraries', headers=headers, json={'name': 'Blocked'}).status_code == 403
            headers['X-CSRF-Token'] = csrf
            assert client.post('/libraries', headers=headers, json={'name': 'Allowed'}).status_code == 200


def test_local_launcher_does_not_special_case_missing_script_filename(monkeypatch):
    app = configured_app(launcher_options(monkeypatch), ObserveScheme())
    with TestClient(app, base_url='http://localhost:8000', client=('127.0.0.1', 12345)) as client:
        assert client.get('/static/create-direction.js', headers={
            'Origin': 'http://localhost:8000', 'X-Forwarded-Proto': 'https',
        }).status_code == 404

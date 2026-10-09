"""Local Codespaces static-module requests; in-process HTTP only."""
from unittest.mock import patch

import pytest

from fastapi.testclient import TestClient

import app.main as main

HOST = 'fixture-workspace-8000.app.github.dev'


def test_unconfigured_forwarded_https_module_origin_is_rejected():
    with patch.object(main, 'local_forwarding_host', None), \
            patch.object(main, 'same_origin', wraps=main.same_origin) as origin_check:
        with TestClient(main.app, base_url='http://' + HOST) as client:
            response = client.get('/static/app.js', headers={'Origin': 'https://' + HOST})
    assert response.status_code == 403
    assert response.json() == {'detail': 'Cross-origin access is disabled for this local private beta.'}
    request = origin_check.call_args.args[0]
    assert request.url.scheme == 'http'
    assert request.headers['host'] == HOST
    assert request.headers['origin'] == 'https://' + HOST


def test_codespaces_local_modules_and_security(tmp_path):
    from test_persistence_factory import run_configuration
    run_configuration('''
        import os
        from fastapi.testclient import TestClient
        os.environ['CODESPACES'] = 'true'
        os.environ['CODESPACE_NAME'] = 'fixture-workspace'
        os.environ['GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN'] = 'app.github.dev'
        from app.main import app
        from app.beta_access import BetaAccess, SESSION_COOKIE
        import secrets
        host = 'fixture-workspace-8000.app.github.dev'
        with TestClient(app, base_url='http://' + host, follow_redirects=False) as client:
            for module in ('app.js', 'enhancements.js', 'creator-direction.js', 'api.js',
                           'knowledge-browser.js', 'output-revision.js'):
                response = client.get('/static/' + module, headers={'Origin': 'https://' + host})
                assert response.status_code == 200, (response.status_code, response.text)
                assert 'javascript' in response.headers['content-type']
            for origin in ('https://evil.example', 'https://other-workspace-8000.app.github.dev',
                           'https://' + host + ':443', 'https://' + host + '/path', 'null'):
                assert client.get('/static/app.js', headers={'Origin': origin}).status_code == 403
            for bad_host in ('other-workspace-8000.app.github.dev', host + '.evil.example'):
                assert client.get('/static/app.js', headers={'Host': bad_host}).status_code == 400
            assert client.get('/static/app.js', headers={
                'Origin': 'https://evil.example', 'X-Forwarded-Host': host,
                'X-Forwarded-Proto': 'https'}).status_code == 403
            # Even when explicitly gated locally, a proxy-origin exception cannot bypass auth/CSRF.
            gate = BetaAccess('fixture-password', secrets.token_urlsafe(32))
            app.state.beta_access = gate
            headers = {'Origin': 'https://' + host}
            assert client.get('/static/app.js', headers=headers).status_code == 401
            token, csrf = gate.issue_session()
            headers['Cookie'] = SESSION_COOKIE + '=' + token
            assert client.get('/static/app.js', headers=headers).status_code == 200
            assert client.post('/libraries', json={'name': 'Denied'}, headers=headers).status_code == 403
            headers['X-CSRF-Token'] = csrf
            assert client.post('/libraries', json={'name': 'Allowed'}, headers=headers).status_code == 200
            headers['Origin'] = 'https://evil.example'
            assert client.post('/libraries', json={'name': 'Denied'}, headers=headers).status_code == 403
    ''', tmp_path / 'local-proxy', 'local')


@pytest.mark.parametrize('mode', ['local', 'hosted'])
def test_forwarding_host_is_exact_and_local_only(monkeypatch, mode):
    from app.deployment import local_https_forwarding_host
    monkeypatch.setenv('CODESPACES', 'true')
    monkeypatch.setenv('CODESPACE_NAME', 'fixture-workspace')
    monkeypatch.setenv('GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN', 'app.github.dev')
    assert local_https_forwarding_host(mode) == (HOST if mode == 'local' else None)


@pytest.mark.parametrize('name,value', [
    ('CODESPACES', 'false'), ('CODESPACES', ''),
    ('CODESPACE_NAME', ''), ('CODESPACE_NAME', '*'),
    ('CODESPACE_NAME', 'fixture.evil'), ('CODESPACE_NAME', '-fixture'),
    ('CODESPACE_NAME', 'fixture-'), ('CODESPACE_NAME', 'a' * 59),
    ('GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN', 'evil.example'),
    ('GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN', 'app.github.dev.evil.example'),
])
def test_forwarding_host_invalid_environment_fails_closed(monkeypatch, name, value):
    from app.deployment import local_https_forwarding_host
    monkeypatch.setenv('CODESPACES', 'true')
    monkeypatch.setenv('CODESPACE_NAME', 'fixture-workspace')
    monkeypatch.setenv('GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN', 'app.github.dev')
    monkeypatch.setenv(name, value)
    assert local_https_forwarding_host('local') is None


def test_forwarding_does_not_relax_other_local_scheme_checks(client):
    assert client.get('/static/app.js', headers={'Origin': 'https://testserver',
                      'X-Forwarded-Proto': 'https'}).status_code == 403
    assert client.get('/static/app.js', headers={'Origin': 'http://testserver'}).status_code == 200


@pytest.mark.parametrize('authority', ['localhost:8000', '127.0.0.1:8000'])
def test_codespaces_origin_with_rewritten_loopback_host(authority):
    # Safari's Origin survives the tunnel, while Uvicorn sees HTTP and loopback Host.
    with patch.object(main, 'local_forwarding_host', HOST), \
            patch.object(main, 'same_origin', wraps=main.same_origin) as origin_check:
        with TestClient(main.app, base_url='http://' + authority) as client:
            response = client.get('/static/app.js', headers={
                'Origin': 'https://' + HOST,
                'Referer': 'https://' + HOST + '/',
                'Sec-Fetch-Dest': 'script', 'Sec-Fetch-Mode': 'cors',
                'Sec-Fetch-Site': 'same-origin',
            })
    request = origin_check.call_args.args[0]
    assert request.url.scheme == 'http'
    assert request.headers['host'] == authority
    assert response.status_code == 200, (response.status_code, response.text)
    assert 'javascript' in response.headers['content-type']


@pytest.mark.parametrize('authority', ['localhost:8000', '127.0.0.1:8000'])
@pytest.mark.parametrize('origin', [
    'https://evil.example', 'https://other-workspace-8000.app.github.dev',
    'http://' + HOST, 'https://' + HOST + ':443', 'https://' + HOST + '/path',
    'https://' + HOST + '?query', 'https://' + HOST + '#fragment',
    'https://user@' + HOST, 'null',
])
def test_loopback_proxy_rejects_other_and_malformed_origins(authority, origin):
    with patch.object(main, 'local_forwarding_host', HOST):
        with TestClient(main.app, base_url='http://' + authority) as client:
            response = client.get('/static/app.js', headers={
                'Origin': origin, 'X-Forwarded-Host': HOST, 'X-Forwarded-Proto': 'https',
                'Forwarded': 'host=' + HOST + ';proto=https', 'Sec-Fetch-Site': 'same-origin',
            })
    assert response.status_code == 403


@pytest.mark.parametrize('authority', [
    'localhost', '127.0.0.1', 'localhost:8001', '127.0.0.1:8001',
    'testserver:8000', 'evil.example:8000', 'localhost.evil.example:8000',
    '[::1]:8000', '0.0.0.0:8000',
])
def test_proxy_origin_has_no_general_authority_bypass(authority):
    with patch.object(main, 'local_forwarding_host', HOST):
        with TestClient(main.app, base_url='http://testserver') as client:
            assert client.get('/static/app.js', headers={
                'Host': authority, 'Origin': 'https://' + HOST, 'X-Forwarded-Host': HOST,
                'X-Forwarded-Proto': 'https',
            }).status_code == 403


@pytest.mark.parametrize('authority', ['localhost:8000', '127.0.0.1:8000'])
def test_non_codespaces_loopback_origin_behavior_unchanged(authority):
    with patch.object(main, 'local_forwarding_host', None):
        with TestClient(main.app, base_url='http://' + authority) as client:
            assert client.get('/static/app.js', headers={'Origin': 'https://' + HOST}).status_code == 403
            assert client.get('/static/app.js', headers={'Origin': 'http://' + authority}).status_code == 200
            assert client.get('/static/app.js', headers={'Origin': 'https://' + authority}).status_code == 403


@pytest.mark.parametrize('authority', ['localhost:8000', '127.0.0.1:8000'])
def test_loopback_proxy_preserves_beta_gate_and_csrf(authority):
    import secrets
    from app.beta_access import BetaAccess, SESSION_COOKIE
    gate = BetaAccess('fixture-password', secrets.token_urlsafe(32))
    with patch.object(main, 'local_forwarding_host', HOST), \
            patch.object(main.app.state, 'beta_access', gate):
        with TestClient(main.app, base_url='http://' + authority, follow_redirects=False) as client:
            headers = {'Origin': 'https://' + HOST}
            assert client.get('/static/app.js', headers=headers).status_code == 401
            token, csrf = gate.issue_session()
            headers['Cookie'] = SESSION_COOKIE + '=' + token
            assert client.get('/static/app.js', headers=headers).status_code == 200
            assert client.post('/libraries', headers=headers, json={'name': 'Blocked'}).status_code == 403
            headers['X-CSRF-Token'] = csrf
            assert client.post('/libraries', headers=headers, json={'name': 'Allowed'}).status_code == 200
            headers['Origin'] = 'https://evil.example'
            assert client.post('/libraries', headers=headers, json={'name': 'Blocked'}).status_code == 403

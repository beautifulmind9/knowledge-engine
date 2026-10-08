"""Gate tests exercise the local app with an injected gate, never hosted stores."""
import base64
from copy import deepcopy
import hashlib
import hmac
import json
import secrets

from fastapi.testclient import TestClient
import pytest

from app.beta_access import BetaAccess, CSRF_COOKIE, SESSION_COOKIE, SESSION_LIFETIME, LOGIN_ERROR
from app.main import app
from app.db import mock_data as db
from test_persistence_factory import run_configuration

PASSWORD = 'private-fixture-password-学習'
ORIGIN = 'https://testserver'


@pytest.fixture
def gated(monkeypatch):
    now = [1_800_000_000.0]
    secret = secrets.token_urlsafe(32)
    gate = BetaAccess(PASSWORD, secret, clock=lambda: now[0], throttle_clock=lambda: now[0])
    monkeypatch.setattr(app.state, 'beta_access', gate)
    with TestClient(app, base_url=ORIGIN, follow_redirects=False) as client:
        yield client, gate, now, secret


def login(client, password=PASSWORD, **kwargs):
    return client.post('/login', json={'password': password}, headers={'Origin': ORIGIN}, **kwargs)


def csrf(client):
    return {'X-CSRF-Token': client.cookies.get(CSRF_COOKIE)}


def test_local_ungated_by_default(client, monkeypatch):
    assert app.state.beta_access is None
    monkeypatch.setenv('KNOWLEDGE_ENGINE_BETA_PASSWORD', 'inherited-password')
    monkeypatch.setenv('KNOWLEDGE_ENGINE_SESSION_SECRET', 'weak-placeholder')
    assert BetaAccess.from_environment('local') is None
    assert client.get('/').status_code == 200
    assert client.get('/libraries').status_code == 200
    assert client.post('/libraries', json={'name': 'Local'}).status_code == 200
    assert client.get('/openapi.json').status_code == 200


@pytest.mark.parametrize('name', ['KNOWLEDGE_ENGINE_BETA_PASSWORD', 'KNOWLEDGE_ENGINE_SESSION_SECRET'])
def test_hosted_missing_gate_config_fails_before_state_load(tmp_path, name):
    code = '''
        import os
        from unittest.mock import patch
        os.environ['KNOWLEDGE_ENGINE_DATABASE_URL'] = 'offline'
        os.environ['KNOWLEDGE_ENGINE_WORKSPACE_KEY'] = 'offline'
        os.environ.pop(NAME, None)
        with patch('app.persistence.postgres.PostgresStateStore.load', side_effect=AssertionError('state load before gate validation')):
            try:
                import app.main
            except RuntimeError as error:
                assert NAME in str(error)
                assert os.environ.get('SUPABASE_SECRET_KEY', 'not-present') not in str(error)
            else:
                raise AssertionError('missing gate configuration accepted')
    '''.replace('NAME', repr(name))
    run_configuration(code, tmp_path / 'root', 'hosted')


@pytest.mark.parametrize('secret', ['', ' ', 'short', 'a' * 64, 'CHANGE_ME_' * 8,
                                  'abcdefghijklmnopqrstuvwxyz' * 3, '0123456789abcdef' * 4,
                                  'your_session_secret_' + 'x' * 50, 'abcDEFghiJKL' * 4])
def test_weak_secrets_rejected_without_values_in_errors(secret):
    with pytest.raises(RuntimeError) as error:
        BetaAccess(PASSWORD, secret)
    assert PASSWORD not in str(error.value)
    if secret.strip():
        assert secret not in str(error.value)


@pytest.mark.parametrize('password', ['', ' ', 'p' * 1025])
def test_invalid_password_config_sanitized(password):
    with pytest.raises(RuntimeError) as error:
        BetaAccess(password, secrets.token_urlsafe(32))
    assert not password.strip() or password not in str(error.value)


def test_navigation_api_and_health_exceptions(gated):
    client, gate, now, secret = gated
    response = client.get('/')
    assert response.status_code == 303 and response.headers['location'] == '/login'
    assert client.get('/', headers={'Accept': 'application/json'}).status_code == 401
    assert client.get('/libraries').json() == {'detail': 'Sign in to continue.'}
    assert client.get('/health').json() == {'status': 'ok'}
    assert client.get('/login').status_code == 200
    assert client.get('/static/style.css').status_code == 200
    assert client.get('/libraries', headers={'Accept': 'text/html', 'Sec-Fetch-Mode': 'cors'}).status_code == 401


@pytest.mark.parametrize('path', ['/', '/libraries', '/sources', '/sources/source-fixture/file',
                                  '/sources/source-fixture/structure', '/knowledge-assets/search?q=private',
                                  '/knowledge-extractions', '/workshops', '/outputs', '/usage', '/data/integrity',
                                  '/data/export', '/openapi.json', '/docs', '/redoc', '/docs/oauth2-redirect',
                                  '/static/index.html', '/static/app.js', '/static/api.js', '/static/enhancements.js',
                                  '/static/login.html', '/static/../index.html', '/static/%2e%2e/index.html', '/health/', '/login/'])
def test_sensitive_routes_are_gated(gated, path):
    client, gate, now, secret = gated
    before = deepcopy(db.sources)
    response = client.get(path, headers={'Accept': 'application/json'})
    assert response.status_code == 401
    assert PASSWORD not in response.text and secret not in response.text
    assert db.sources == before


@pytest.mark.parametrize('method', ['POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'])
@pytest.mark.parametrize('path', ['/libraries', '/sources/missing', '/outputs', '/usage/resume', '/logout', '/health'])
def test_unauthenticated_methods_never_reach_application(gated, method, path):
    client, gate, now, secret = gated
    assert client.request(method, path, json={'name': 'unauthorized'}).status_code == 401
    assert not db.libraries and not db.sources


def test_correct_password_session_cookie_attributes_and_secret_free_payload(gated, caplog):
    client, gate, now, secret = gated
    response = login(client)
    assert response.status_code == 303 and response.headers['location'] == '/'
    cookies = response.headers.get_list('set-cookie')
    assert len(cookies) == 2
    for cookie in cookies:
        assert 'Secure' in cookie and 'SameSite=strict' in cookie and 'Path=/' in cookie
        assert 'Domain=' not in cookie and 'Max-Age=43200' in cookie
    assert 'HttpOnly' in cookies[0] and 'HttpOnly' not in cookies[1]
    token = client.cookies.get(SESSION_COOKIE)
    data = gate.verify_session(token)
    assert data['csrf'] == client.cookies.get(CSRF_COOKIE)
    assert data['exp'] == data['iat'] + SESSION_LIFETIME
    payload = base64.urlsafe_b64decode(token.split('.')[0] + '==').decode()
    assert PASSWORD not in payload and secret not in payload
    assert PASSWORD not in response.text + str(response.headers) + caplog.text
    assert secret not in response.text + str(response.headers) + caplog.text
    assert token not in caplog.text and data['csrf'] not in caplog.text
    assert client.get('/').status_code == 200
    assert client.get('/libraries').status_code == 200
    assert client.get('/docs').status_code == 200
    assert client.get('/openapi.json').status_code == 200


def test_form_login_generic_feedback_and_no_echo(gated, caplog):
    client, gate, now, secret = gated
    wrong = '<script>private-wrong-password</script>'
    response = client.post('/login', data={'password': wrong}, headers={'Origin': ORIGIN, 'Accept': 'text/html'})
    assert response.status_code == 401 and LOGIN_ERROR in response.text
    assert wrong not in response.text + caplog.text and secret not in response.text + caplog.text
    assert 'id="login-error" hidden' not in response.text
    assert not response.headers.get('set-cookie')
    good = client.post('/login', data={'password': PASSWORD}, headers={'Origin': ORIGIN})
    assert good.status_code == 303


@pytest.mark.parametrize('body,content_type', [('not-json-password', 'application/json'), ('{"password":123}', 'application/json'),
                                            ('{"password":"\\ud800"}', 'application/json'), ('private' * 2000, 'application/json'),
                                            ('password=private', 'text/plain')])
def test_malformed_login_never_echoes_input(gated, body, content_type):
    client, gate, now, secret = gated
    response = client.post('/login', content=body, headers={'Origin': ORIGIN, 'Content-Type': content_type})
    assert response.status_code == 401 and response.json() == {'detail': LOGIN_ERROR}
    assert 'private' not in response.text and secret not in response.text


@pytest.mark.parametrize('token', ['', 'not-a-session', '.', 'a.b.c', 'a.' + 'a' * 43, 'x' * 2000,
                                  '%%.%%', 'null.null', 'a=.' + 'b' * 43, 'é.invalid', '"broken'])
def test_malformed_cookies_rejected(gated, token):
    client, gate, now, secret = gated
    assert gate.verify_session(token) is None
    if token.isascii():
        response = client.get('/libraries', headers={'Cookie': f'{SESSION_COOKIE}={token}'})
        assert response.status_code == 401


@pytest.mark.parametrize('change', ['payload', 'signature', 'expired', 'wrong_secret', 'wrong_password'])
def test_invalid_sessions_rejected(gated, change):
    client, gate, now, secret = gated
    token, csrf_value = gate.issue_session()
    if change == 'payload':
        payload, signature = token.split('.')
        token = ('a' if payload[0] != 'a' else 'b') + payload[1:] + '.' + signature
    elif change == 'signature':
        payload, signature = token.split('.')
        token = payload + '.' + ('a' if signature[0] != 'a' else 'b') + signature[1:]
    elif change == 'expired':
        now[0] += SESSION_LIFETIME
    elif change == 'wrong_secret':
        token, csrf_value = BetaAccess(PASSWORD, secrets.token_urlsafe(32), clock=lambda: now[0]).issue_session()
    else:
        token, csrf_value = BetaAccess('different-private-password', secret, clock=lambda: now[0]).issue_session()
    assert gate.verify_session(token) is None
    assert client.get('/libraries', headers={'Cookie': f'{SESSION_COOKIE}={token}'}).status_code == 401


@pytest.mark.parametrize('payload', [None, [], {'v': True}, {'v': 1, 'iat': 'bad', 'exp': 0, 'csrf': 'a' * 43},
                                     {'v': 1, 'iat': 1_800_000_001, 'exp': 1_800_000_001 + SESSION_LIFETIME, 'csrf': 'a' * 43},
                                     {'v': 1, 'iat': 1_800_000_000, 'exp': 1_800_000_000 + SESSION_LIFETIME * 2, 'csrf': 'a' * 43}])
def test_signed_but_invalid_payloads_fail_closed(gated, payload):
    client, gate, now, secret = gated
    encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b'=').decode()
    signature = base64.urlsafe_b64encode(hmac.digest(gate._key, encoded.encode(), 'sha256')).rstrip(b'=').decode()
    assert gate.verify_session(encoded + '.' + signature) is None


@pytest.mark.parametrize('method', ['POST', 'PUT', 'PATCH', 'DELETE'])
@pytest.mark.parametrize('token_kind', ['missing', 'wrong', 'other_session', 'readable_cookie_tampered'])
def test_authenticated_unsafe_requests_require_bound_csrf(gated, method, token_kind):
    client, gate, now, secret = gated
    login(client)
    header = {}
    if token_kind == 'wrong':
        header = {'X-CSRF-Token': 'wrong'}
    elif token_kind == 'other_session':
        header = {'X-CSRF-Token': gate.issue_session()[1]}
    elif token_kind == 'readable_cookie_tampered':
        # A freely chosen readable cookie is not authority: the signed session is.
        client.cookies.set(CSRF_COOKIE, 'forged', domain='testserver.local', path='/')
        header = {'X-CSRF-Token': 'forged'}
    response = client.request(method, '/libraries', json={'name': 'Forbidden'}, headers=header)
    assert response.status_code == 403
    assert not db.libraries


def test_authenticated_get_and_correct_csrf_post(gated):
    client, gate, now, secret = gated
    login(client)
    assert client.get('/libraries').status_code == 200
    response = client.post('/libraries', json={'name': 'Private'}, headers=csrf(client))
    assert response.status_code == 200
    assert len(db.libraries) == 1
    assert client.delete('/libraries/' + response.json()['id'], headers=csrf(client)).status_code == 200
    assert not db.libraries
    # HEAD/OPTIONS are method errors in this existing API, never CSRF errors.
    assert client.head('/libraries').status_code == 405
    assert client.options('/libraries').status_code == 405


def test_logout_is_post_and_csrf_protected_and_clears_cookies(gated):
    client, gate, now, secret = gated
    login(client)
    assert client.post('/logout').status_code == 403
    assert client.get('/logout').status_code == 405
    response = client.post('/logout', headers=csrf(client))
    assert response.status_code == 303 and response.headers['location'] == '/login'
    for cookie in response.headers.get_list('set-cookie'):
        assert 'Max-Age=0' in cookie and 'Secure' in cookie and 'SameSite=strict' in cookie and 'Domain=' not in cookie
    assert not client.cookies.get(SESSION_COOKIE) and not client.cookies.get(CSRF_COOKIE)
    assert client.get('/libraries').status_code == 401


@pytest.mark.parametrize('origin', ['https://evil.example', 'http://testserver', 'https://testserver.evil.example', 'null',
                                   'https://testserver/path', 'https://user@testserver', 'https://[invalid'])
def test_cross_origin_rejected_even_with_valid_session_and_csrf(gated, origin):
    client, gate, now, secret = gated
    login(client)
    response = client.post('/libraries', json={'name': 'Blocked'}, headers={**csrf(client), 'Origin': origin})
    assert response.status_code == 403 and not db.libraries
    assert response.headers['cache-control'] == 'no-store'
    assert response.headers['x-content-type-options'] == 'nosniff'
    assert 'unsafe-inline' not in response.headers['content-security-policy']


def test_login_requires_origin_and_does_not_set_cookies_cross_origin(gated):
    client, gate, now, secret = gated
    for headers in ({}, {'Origin': 'https://evil.example'}):
        response = client.post('/login', json={'password': PASSWORD}, headers=headers)
        assert response.status_code == 403 and not response.headers.get('set-cookie')
    assert login(client).status_code == 303


@pytest.mark.parametrize('path', ['/', '/login', '/libraries', '/static/app.js', '/health'])
def test_security_headers_on_all_gate_responses_and_login_csp(gated, path):
    client, gate, now, secret = gated
    response = client.get(path)
    assert response.headers['x-content-type-options'] == 'nosniff'
    assert response.headers['cache-control'] == 'no-store'
    csp = response.headers['content-security-policy']
    assert "script-src 'self'" in csp and "form-action 'self'" in csp
    assert 'unsafe-inline' not in csp
    if path == '/login':
        assert '<script' not in response.text and 'onload=' not in response.text
        assert 'type="password"' in response.text and 'PRIVATE BETA' in response.text
        assert 'KNOWLEDGE_ENGINE_' not in response.text


def test_throttle_is_bounded_and_recovers_without_sleep(gated):
    client, gate, now, secret = gated
    for _ in range(5):
        assert login(client, 'wrong').status_code == 401
    for _ in range(10):
        response = login(client)
        assert response.status_code == 429 and response.headers['retry-after'] == '300'
    assert len(gate._failures) == 5
    now[0] += 300
    assert login(client).status_code == 303
    assert not gate._failures

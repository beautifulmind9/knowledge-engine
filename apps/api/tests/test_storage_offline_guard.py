"""Target guards must fire BEFORE remote requests can reach a loopback proxy."""
import asyncio
from http.client import HTTPConnection
import os
from urllib.request import build_opener, ProxyHandler

import httpx
import pytest
import requests

from storage_test_guard import StorageNetworkDenied
from test_persistence_factory import run_configuration


@pytest.mark.parametrize('target', ['http://offline.supabase.co/object', 'https://offline.supabase.co/object'])
@pytest.mark.parametrize('client', ['urllib', 'requests', 'httpx', 'httpx_async', 'tunnel'])
def test_loopback_proxy_cannot_relay_supabase_target(monkeypatch, target, client):
    for name in ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'http_proxy', 'https_proxy', 'all_proxy'):
        monkeypatch.setenv(name, 'http://127.0.0.1:54321')
    monkeypatch.delenv('NO_PROXY', raising=False)
    monkeypatch.delenv('no_proxy', raising=False)
    # If a guard fails, fail BEFORE any socket attempt, even toward loopback.
    def unexpected_connect(*args, **kwargs):
        pytest.fail('remote target reached connection stage')
    monkeypatch.setattr('socket.socket.connect', unexpected_connect)
    with pytest.raises(StorageNetworkDenied):
        if client == 'urllib':
            build_opener(ProxyHandler({'http': 'http://127.0.0.1:54321', 'https': 'http://127.0.0.1:54321'})).open(target)
        elif client == 'requests':
            requests.get(target)
        elif client == 'httpx':
            with httpx.Client(proxy='http://127.0.0.1:54321') as transport:
                transport.get(target)
        elif client == 'httpx_async':
            async def send():
                async with httpx.AsyncClient(proxy='http://127.0.0.1:54321') as transport:
                    await transport.get(target)
            asyncio.run(send())
        else:
            HTTPConnection('127.0.0.1', 54321).set_tunnel('offline.supabase.co', 443)


def test_subprocess_guard_clears_inherited_loopback_proxies(tmp_path, monkeypatch):
    for name in ('HTTP_PROXY', 'https_proxy', 'ALL_PROXY', 'no_proxy'):
        monkeypatch.setenv(name, 'http://127.0.0.1:54321')
    run_configuration('''
        import os
        import socket
        from urllib.request import urlopen
        from storage_test_guard import StorageNetworkDenied
        assert not any(key.lower() in ('http_proxy', 'https_proxy', 'all_proxy', 'no_proxy') for key in os.environ)
        # Even proxies set AFTER startup cannot bypass the URL guard.
        os.environ['https_proxy'] = 'http://127.0.0.1:54321'
        def unexpected(*args, **kwargs):
            raise AssertionError('guard allowed connection stage')
        socket.socket.connect = unexpected
        try:
            urlopen('https://offline.supabase.co')
        except StorageNetworkDenied:
            pass
        else:
            raise AssertionError('unguarded target URL')
    ''', tmp_path / 'root')


@pytest.mark.parametrize('asynchronous', [False, True])
def test_redirect_from_loopback_to_supabase_is_guarded(monkeypatch, asynchronous):
    seen = []
    def unexpected_connect(*args, **kwargs):
        pytest.fail('redirect reached a socket')
    monkeypatch.setattr('socket.socket.connect', unexpected_connect)
    target = 'https://offline.supabase.co/remote'
    if asynchronous:
        class LocalTransport(httpx.AsyncBaseTransport):
            async def handle_async_request(self, request):
                seen.append(str(request.url))
                return httpx.Response(302, headers={'Location': target})
        async def send():
            async with httpx.AsyncClient(transport=LocalTransport(), trust_env=False, follow_redirects=True,
                                         mounts={'https://offline.supabase.co': httpx.AsyncHTTPTransport(proxy='http://127.0.0.1:54321')}) as client:
                await client.get('http://localhost/start')
        with pytest.raises(StorageNetworkDenied):
            asyncio.run(send())
    else:
        class LocalTransport(httpx.BaseTransport):
            def handle_request(self, request):
                seen.append(str(request.url))
                return httpx.Response(302, headers={'Location': target})
        with httpx.Client(transport=LocalTransport(), trust_env=False, follow_redirects=True,
                          mounts={'https://offline.supabase.co': httpx.HTTPTransport(proxy='http://127.0.0.1:54321')}) as client:
            with pytest.raises(StorageNetworkDenied):
                client.get('http://localhost/start')
    assert seen == ['http://localhost/start']

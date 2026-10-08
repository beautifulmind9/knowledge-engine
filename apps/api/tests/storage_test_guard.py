"""Deny real Storage/remote IO before app imports, including subprocess tests.

Tests replace the Storage opener/API. Loopback remains available for the existing
local server smoke test; the adapter's real opener is denied even through proxies.
"""
import socket
import os
from urllib.parse import urlsplit
from urllib.request import OpenerDirector, Request
from http.client import HTTPConnection
import httpx
import requests

from app.persistence import supabase_artifacts

_original_getaddrinfo = socket.getaddrinfo
_original_create_connection = socket.create_connection
_original_connect = socket.socket.connect
_original_connect_ex = socket.socket.connect_ex
_original_opener_open = OpenerDirector.open
_original_set_tunnel = HTTPConnection.set_tunnel
_original_httpx_send = httpx.Client._send_single_request
_original_httpx_async_send = httpx.AsyncClient._send_single_request
_original_requests_send = requests.Session.send


class StorageNetworkDenied(AssertionError):
    pass


def deny_network(*args, **kwargs):
    # Never include the host, request, configuration, or credentials in diagnostics.
    raise StorageNetworkDenied("Real remote/Storage connections are forbidden in backend tests.")


def _check_host(host):
    if host not in ('127.0.0.1', '::1', 'localhost', None):
        deny_network()


def guarded_getaddrinfo(host, *args, **kwargs):
    _check_host(host)
    return _original_getaddrinfo('127.0.0.1' if host == 'localhost' else host, *args, **kwargs)


def guarded_create_connection(address, *args, **kwargs):
    _check_host(address[0])
    return _original_create_connection(address, *args, **kwargs)


def guarded_connect(sock, address):
    if sock.family in (socket.AF_INET, socket.AF_INET6):
        _check_host(address[0])
    return _original_connect(sock, address)


def guarded_connect_ex(sock, address):
    if sock.family in (socket.AF_INET, socket.AF_INET6):
        _check_host(address[0])
    return _original_connect_ex(sock, address)


def _check_target_url(url):
    try:
        target = urlsplit(str(url))
        if target.scheme not in ('http', 'https'):
            deny_network()
        _check_host(target.hostname)
    except ValueError:
        deny_network()


def guarded_opener_open(opener, fullurl, *args, **kwargs):
    _check_target_url(fullurl.full_url if isinstance(fullurl, Request) else fullurl)
    return _original_opener_open(opener, fullurl, *args, **kwargs)


def guarded_set_tunnel(connection, host, *args, **kwargs):
    _check_host(host)
    return _original_set_tunnel(connection, host, *args, **kwargs)


def _check_httpx_request(client, request):
    transport = client._transport_for_url(request.url)
    # Existing SDK diagnostics use MockTransport; TestClient never opens sockets.
    if isinstance(transport, (httpx.MockTransport, httpx.ASGITransport)) or type(transport).__module__ == 'starlette.testclient':
        return
    _check_target_url(request.url)


def guarded_httpx_send(client, request, *args, **kwargs):
    _check_httpx_request(client, request)
    return _original_httpx_send(client, request, *args, **kwargs)


async def guarded_httpx_async_send(client, request, *args, **kwargs):
    _check_httpx_request(client, request)
    return await _original_httpx_async_send(client, request, *args, **kwargs)


def guarded_requests_send(session, request, *args, **kwargs):
    _check_target_url(request.url)
    return _original_requests_send(session, request, *args, **kwargs)


def install_storage_guard():
    # Neutralize inherited proxies, while URL guards also protect tests that set
    # a proxy later. Check targets BEFORE a loopback proxy can receive a request.
    for name in list(os.environ):
        if name.lower() in ('http_proxy', 'https_proxy', 'all_proxy', 'no_proxy'):
            os.environ.pop(name, None)
    supabase_artifacts.build_opener = deny_network
    OpenerDirector.open = guarded_opener_open
    HTTPConnection.set_tunnel = guarded_set_tunnel
    # Check EVERY request, including requests produced while following redirects.
    httpx.Client._send_single_request = guarded_httpx_send
    httpx.AsyncClient._send_single_request = guarded_httpx_async_send
    requests.Session.send = guarded_requests_send
    socket.getaddrinfo = guarded_getaddrinfo
    socket.create_connection = guarded_create_connection
    socket.socket.connect = guarded_connect
    socket.socket.connect_ex = guarded_connect_ex

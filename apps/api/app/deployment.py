"""Explicit hosted HTTPS origin; forwarding headers never define trust.

Hosted ingress must be Render's HTTPS edge. Uvicorn ignores proxy headers, and
the application uses a configured canonical HTTPS origin instead of inferring
it from untrusted X-Forwarded-* values. Local Codespaces forwarding trusts only
the exact port-8000 hostname derived from the workspace environment.
"""
import os
import re

from starlette.responses import PlainTextResponse

LOCAL_HOSTS = ["localhost", "127.0.0.1", "[::1]", "testserver"]


def local_https_forwarding_host(mode: str) -> str | None:
    """Opt in only for this Codespace's standard port-8000 HTTPS forwarding.

    Never derive authority from request headers or permit a domain wildcard.
    Hosted mode ignores Codespaces environment variables entirely.
    """
    if (mode != "local" or os.environ.get("CODESPACES") != "true"
            or os.environ.get("GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN") != "app.github.dev"):
        return None
    name = os.environ.get("CODESPACE_NAME", "")
    # The name plus '-8000' must fit one DNS label.
    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,56}[a-z0-9])?", name):
        return None
    return f"{name}-8000.app.github.dev"


def public_host(mode: str) -> str | None:
    if mode == "local":
        return None
    if mode != "hosted":
        raise RuntimeError("Invalid persistence mode for deployment configuration.")
    host = os.environ.get("KNOWLEDGE_ENGINE_PUBLIC_HOST", "")
    # A DNS name only: no URLs, ports, IP literals, wildcards, trailing dots,
    # whitespace, or lists. Require a public-style name with at least two labels.
    labels = host.split(".")
    if (len(host) > 253 or len(labels) < 2
            or any(not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label) for label in labels)
            or not re.fullmatch(r"[A-Za-z]{2,63}", labels[-1])):
        raise RuntimeError("Hosted deployment requires KNOWLEDGE_ENGINE_PUBLIC_HOST as a valid DNS hostname.")
    return host.lower()


class HostedHTTPSMiddleware:
    """Reject noncanonical authorities before auth; use fixed HTTPS scheme.

    No forwarded host/scheme/client address is consumed. This isn't an HTTP to
    HTTPS redirect: TLS enforcement belongs to Render's edge, not a header.
    """
    def __init__(self, app, host: str):
        self.app = app
        self.host = host

    async def __call__(self, scope, receive, send):
        if scope["type"] in {"http", "websocket"}:
            hosts = [value for name, value in scope["headers"] if name.lower() == b"host"]
            if len(hosts) != 1 or hosts[0].lower() != self.host.encode("ascii"):
                if scope["type"] == "websocket":
                    await send({"type": "websocket.close", "code": 1008})
                else:
                    await PlainTextResponse("Invalid host header", status_code=400)(scope, receive, send)
                return
            scope = dict(scope, scheme="https" if scope["type"] == "http" else "wss")
        await self.app(scope, receive, send)

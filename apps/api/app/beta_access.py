"""One shared private-beta password, stateless signed sessions, and bound CSRF.

No identities, persistent sessions, or provider IO. Logout clears browser cookies;
revoking a copied token requires expiry or rotating the signing secret/password.
"""
import base64
from collections import deque
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
from threading import Lock
import time
from urllib.parse import parse_qs, urlsplit

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse

SESSION_COOKIE = "__Host-ke-beta-session"
CSRF_COOKIE = "__Host-ke-beta-csrf"
SESSION_LIFETIME = 12 * 60 * 60
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
WEB_ROOT = Path(__file__).resolve().parents[2] / "web"
LOGIN_ERROR = "Unable to sign in. Check the password and try again."


def same_origin(request: Request) -> bool:
    """Compare scheme AND authority. Reject opaque/malformed Origins explicitly."""
    origin = request.headers.get("origin")
    if origin is None:
        return True  # Session-bound CSRF still applies to authenticated writes.
    try:
        parsed = urlsplit(origin)
        return (parsed.scheme == request.url.scheme and parsed.netloc == request.headers.get("host")
                and not parsed.username and not parsed.password and not parsed.path
                and not parsed.query and not parsed.fragment)
    except ValueError:
        return False


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode(value: str) -> bytes:
    raw = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
    if _encode(raw) != value:
        raise ValueError("Noncanonical token.")
    return raw


class BetaAccess:
    def __init__(self, password: str, session_secret: str, *, clock=time.time, throttle_clock=time.monotonic):
        if not password or not password.strip():
            raise RuntimeError("Hosted beta access requires KNOWLEDGE_ENGINE_BETA_PASSWORD.")
        if not session_secret or not session_secret.strip():
            raise RuntimeError("Hosted beta access requires KNOWLEDGE_ENGINE_SESSION_SECRET.")
        lower = session_secret.lower()
        if (not re.fullmatch(r"[A-Za-z0-9_-]{43,128}", session_secret) or len(set(session_secret)) < 12
                or any(session_secret == session_secret[:size] * (len(session_secret) // size)
                       for size in range(1, len(session_secret) // 2 + 1) if len(session_secret) % size == 0)
                or any(marker in lower for marker in ("change", "replace", "placeholder", "example", "password",
                                                       "session_secret", "session-secret", "abcdefghijklmnopqrstuvwxyz", "0123456789"))):
            raise RuntimeError("KNOWLEDGE_ENGINE_SESSION_SECRET must be a strong random secret (at least 32 random bytes encoded as URL-safe text).")
        try:
            encoded_password = password.encode("utf-8")
            if len(encoded_password) > 1024:
                raise RuntimeError("KNOWLEDGE_ENGINE_BETA_PASSWORD must be at most 1024 UTF-8 bytes.")
            self._password_digest = hashlib.sha256(encoded_password).digest()
        except UnicodeError:
            raise RuntimeError("KNOWLEDGE_ENGINE_BETA_PASSWORD must be valid UTF-8 text.") from None
        # Bind signing to the password as well: changing either invalidates sessions.
        self._key = hmac.digest(session_secret.encode("ascii"), b"knowledge-engine-beta-v1\0" + self._password_digest, "sha256")
        self._clock = clock
        self._throttle_clock = throttle_clock
        self._failures = deque(maxlen=5)
        self._blocked_until = 0
        self._login_lock = Lock()

    @classmethod
    def from_environment(cls, mode: str):
        if mode == "local":
            return None
        if mode != "hosted":
            raise RuntimeError("Invalid persistence mode for beta access.")
        return cls(os.environ.get("KNOWLEDGE_ENGINE_BETA_PASSWORD", ""),
                   os.environ.get("KNOWLEDGE_ENGINE_SESSION_SECRET", ""))

    def issue_session(self) -> tuple[str, str]:
        now = int(self._clock())
        csrf = secrets.token_urlsafe(32)
        payload = _encode(json.dumps({"v": 1, "iat": now, "exp": now + SESSION_LIFETIME, "csrf": csrf},
                                     separators=(",", ":"), sort_keys=True).encode("ascii"))
        signature = _encode(hmac.digest(self._key, payload.encode("ascii"), "sha256"))
        return payload + "." + signature, csrf

    def verify_session(self, token: str | None) -> dict | None:
        if not token or len(token) > 512:
            return None
        try:
            payload, signature = token.split(".")
            if not re.fullmatch(r"[A-Za-z0-9_-]+", payload) or not re.fullmatch(r"[A-Za-z0-9_-]{43}", signature):
                return None
            expected = hmac.digest(self._key, payload.encode("ascii"), "sha256")
            if not hmac.compare_digest(expected, _decode(signature)):
                return None
            data = json.loads(_decode(payload))
            now = int(self._clock())
            if (not isinstance(data, dict) or set(data) != {"v", "iat", "exp", "csrf"}
                    or type(data["v"]) is not int or data["v"] != 1
                    or type(data["iat"]) is not int or type(data["exp"]) is not int
                    or data["exp"] - data["iat"] != SESSION_LIFETIME or data["iat"] > now or data["exp"] <= now
                    or not isinstance(data["csrf"], str) or not re.fullmatch(r"[A-Za-z0-9_-]{43}", data["csrf"])):
                return None
            return data
        except (ValueError, UnicodeError, TypeError):
            return None

    def check_password(self, submitted: str) -> str:
        """Return ok/invalid/throttled. Five failures impose a five-minute cooldown.

        Globally bounded for one owner/worker; does not trust proxy-supplied IPs.
        """
        with self._login_lock:
            now = self._throttle_clock()
            if now < self._blocked_until:
                return "throttled"
            while self._failures and self._failures[0] <= now - 300:
                self._failures.popleft()
            try:
                supplied = hashlib.sha256(submitted.encode("utf-8")).digest()
                valid = hmac.compare_digest(supplied, self._password_digest)
            except (UnicodeError, AttributeError):
                valid = False
            if valid:
                self._failures.clear()
                return "ok"
            self._failures.append(now)
            if len(self._failures) == 5:
                self._blocked_until = now + 300
            return "invalid"

    def enforce(self, request: Request):
        path, method = request.scope["path"], request.method
        if ((path == "/health" and method in {"GET", "HEAD"})
                or (path == "/login" and method in {"GET", "HEAD", "POST"})
                or (path == "/static/style.css" and method in {"GET", "HEAD"})):
            # Login CSRF: ordinary browser forms send Origin. Require an explicit
            # same-origin Origin even before a session exists.
            if path == "/login" and method == "POST" and not request.headers.get("origin"):
                return JSONResponse({"detail": "Request origin is required."}, status_code=403)
            return None
        session = self.verify_session(request.cookies.get(SESSION_COOKIE))
        if session is None:
            mode = request.headers.get("sec-fetch-mode", "")
            accept = request.headers.get("accept", "")
            navigation = (mode == "navigate" or (not mode and ("text/html" in accept or
                          (path == "/" and "application/json" not in accept))))
            if method in {"GET", "HEAD"} and navigation:
                return RedirectResponse("/login", status_code=303)
            return JSONResponse({"detail": "Sign in to continue."}, status_code=401)
        # Deny unknown methods too: only read-only methods bypass CSRF.
        if method not in SAFE_METHODS:
            supplied = request.headers.get("x-csrf-token", "")
            try:
                valid = hmac.compare_digest(supplied.encode("utf-8"), session["csrf"].encode("ascii"))
            except UnicodeError:
                valid = False
            if not valid:
                return JSONResponse({"detail": "Request verification failed."}, status_code=403)
        return None

    def set_cookies(self, response, token, csrf):
        response.set_cookie(SESSION_COOKIE, token, max_age=SESSION_LIFETIME, httponly=True,
                            secure=True, samesite="strict", path="/")
        response.set_cookie(CSRF_COOKIE, csrf, max_age=SESSION_LIFETIME, httponly=False,
                            secure=True, samesite="strict", path="/")


router = APIRouter(include_in_schema=False)


@router.api_route("/login", methods=["GET", "HEAD"])
def login_page(request: Request):
    if request.app.state.beta_access is None:
        return RedirectResponse("/", status_code=303)
    return FileResponse(WEB_ROOT / "login.html")


async def _submitted_password(request: Request) -> str:
    # Avoid schema errors that echo inputs and bound untrusted body size.
    body = bytearray()
    async for part in request.stream():
        if len(body) + len(part) > 8192:
            return ""
        body.extend(part)
    try:
        content_type = request.headers.get("content-type", "").split(";", 1)[0]
        if content_type == "application/x-www-form-urlencoded":
            values = parse_qs(body.decode("utf-8"), max_num_fields=4, errors="strict")
            return values.get("password", [""])[0]
        if content_type == "application/json":
            data = json.loads(body)
            password = data.get("password", "") if isinstance(data, dict) else ""
            return password if isinstance(password, str) else ""
    except (ValueError, UnicodeError):
        pass
    return ""


@router.post("/login")
async def login(request: Request):
    gate = request.app.state.beta_access
    if gate is None:
        return RedirectResponse("/", status_code=303)
    result = gate.check_password(await _submitted_password(request))
    if result != "ok":
        message = "Sign-in temporarily unavailable. Try again shortly." if result == "throttled" else LOGIN_ERROR
        status = 429 if result == "throttled" else 401
        if "text/html" in request.headers.get("accept", ""):
            # Only fixed messages enter this static template; never submitted values.
            page = (WEB_ROOT / "login.html").read_text(encoding="utf-8").replace('id="login-error" hidden', 'id="login-error"').replace('<!-- LOGIN_ERROR -->', message)
            response = HTMLResponse(page, status_code=status)
        else:
            response = JSONResponse({"detail": message}, status_code=status)
        if result == "throttled":
            response.headers["Retry-After"] = "300"
        return response
    response = RedirectResponse("/", status_code=303)
    gate.set_cookies(response, *gate.issue_session())
    return response


@router.post("/logout")
def logout(request: Request):
    response = RedirectResponse("/login" if request.app.state.beta_access else "/", status_code=303)
    for name, httponly in ((SESSION_COOKIE, True), (CSRF_COOKIE, False)):
        response.delete_cookie(name, httponly=httponly, secure=True, samesite="strict", path="/")
    return response

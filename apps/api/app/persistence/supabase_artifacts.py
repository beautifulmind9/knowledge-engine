"""Private server-side Storage IO. Paths are locators, never hosted filesystem IO.

Only short-lived parser/read/write working files use the local filesystem.
Replacement uploads with upsert, then deletes the source: it overwrites like
Path.replace, but is not a cross-object atomic transaction. Failed deletion raises.
"""
from contextlib import contextmanager
from http.client import HTTPException
from io import TextIOWrapper
import json
from pathlib import Path
import re
from tempfile import TemporaryDirectory, TemporaryFile
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler


class HostedArtifactStoreError(RuntimeError):
    """Sanitized Storage failure; never include credentials or remote diagnostics."""


class HostedArtifactTransportError(HostedArtifactStoreError):
    """Opening or reading an HTTP response failed; remote details are suppressed."""


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class SupabaseArtifactStore:
    def __init__(self, storage_root: Path, url: str, secret_key: str,
                 bucket: str, workspace_key: str):
        for name, value in (("SUPABASE_URL", url), ("SUPABASE_SECRET_KEY", secret_key),
                            ("KNOWLEDGE_ENGINE_STORAGE_BUCKET", bucket),
                            ("KNOWLEDGE_ENGINE_WORKSPACE_KEY", workspace_key)):
            if not value or not value.strip():
                raise RuntimeError(f"Hosted ArtifactStore requires {name}.")
        try:
            parsed = urlsplit(url)
            port = parsed.port
        except ValueError:
            raise RuntimeError("Hosted ArtifactStore requires a valid HTTPS SUPABASE_URL.") from None
        if (port not in (None, 443) or parsed.scheme != "https" or not parsed.hostname or parsed.username or
                parsed.password or parsed.path not in ("", "/") or parsed.query or
                parsed.fragment or any(c.isspace() for c in url)):
            raise RuntimeError("Hosted ArtifactStore requires a valid HTTPS SUPABASE_URL.")
        if not re.fullmatch(r"sb_secret_[A-Za-z0-9_-]+", secret_key):
            raise RuntimeError("Hosted ArtifactStore requires a server-side SUPABASE_SECRET_KEY.")
        for name, value in (("KNOWLEDGE_ENGINE_STORAGE_BUCKET", bucket),
                            ("KNOWLEDGE_ENGINE_WORKSPACE_KEY", workspace_key)):
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", value):
                raise RuntimeError(f"Hosted ArtifactStore requires a safe single-segment {name}.")
        self.storage_root = Path(storage_root).absolute()
        self._url = url.rstrip("/") + "/storage/v1"
        self._secret_key = secret_key
        self._bucket = bucket
        self._workspace_key = workspace_key

    def relative_locator(self, path: Path) -> Path:
        path = Path(path)
        if any(part == ".." for part in path.parts):
            raise ValueError("Artifact locator is outside private storage.")
        if path.is_absolute():
            try:
                path = path.relative_to(self.storage_root)
            except ValueError:
                raise ValueError("Artifact locator is outside private storage.") from None
        # Reject ambiguous encodings/separators rather than reinterpret them.
        for part in path.parts:
            if "\\" in part or "%" in part or ":" in part or any(ord(c) < 32 or ord(c) == 127 for c in part):
                raise ValueError("Invalid artifact locator.")
        return path

    def _key(self, path: Path) -> str:
        relative = self.relative_locator(path).as_posix()
        return self._workspace_key + ("/" + relative if relative != "." else "")

    def _object_route(self, path: Path) -> str:
        if self.relative_locator(path) == Path("."):
            raise ValueError("A byte artifact requires a non-root locator.")
        return "/object/" + quote(self._bucket, safe="") + "/" + quote(self._key(path), safe="/")

    def _request(self, method: str, route: str, *, data=None, payload=None, missing_ok=False):
        headers = {"apikey": self._secret_key}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        elif data is not None:
            headers.update({"Content-Type": "application/octet-stream", "x-upsert": "true"})
        request = Request(self._url + route, data=data, headers=headers, method=method)
        try:
            # No redirects: never forward privileged credentials to another origin.
            with build_opener(_NoRedirect()).open(request, timeout=30) as response:
                return response.read()
        except HTTPError as error:
            with error:
                try:
                    body = json.loads(error.read())
                except (HTTPException, URLError, OSError):
                    raise HostedArtifactTransportError("Hosted artifact transport failed.") from None
                except ValueError:
                    body = {}
            # Storage sometimes wraps a logical 404 in HTTP 400. A bare HTTP 404
            # may mean a missing bucket/route; only explicit object absence is safe.
            if (missing_ok and error.code in (400, 404) and isinstance(body, dict) and
                    (body.get("code") == "NoSuchKey" or
                     (not body.get("code") and body.get("error") == "not_found" and
                      body.get("message") == "Object not found"))):
                return None
            raise HostedArtifactStoreError("Hosted artifact operation failed.") from None
        except (HTTPException, URLError, OSError, ValueError):
            raise HostedArtifactTransportError("Hosted artifact transport failed.") from None

    def _list(self, prefix, *, search=None, offset=0):
        payload = {"prefix": prefix, "limit": 100, "offset": offset,
                   "sortBy": {"column": "name", "order": "asc"}}
        if search is not None:
            payload["search"] = search
        raw = self._request("POST", "/object/list/" + quote(self._bucket, safe=""), payload=payload)
        try:
            items = json.loads(raw)
            if not isinstance(items, list) or any(not isinstance(i, dict) or not isinstance(i.get("name"), str) for i in items):
                raise ValueError()
            return items
        except (ValueError, TypeError):
            raise HostedArtifactStoreError("Hosted artifact metadata is invalid.") from None

    def create_directory(self, path: Path) -> None:
        self.relative_locator(path)

    def status(self, path: Path):
        relative = self.relative_locator(path)
        if relative == Path("."):
            self._list(self._workspace_key)  # Validate access even for the logical root.
            return "other"
        key = self._key(path)
        parent, name = key.rsplit("/", 1)
        offset = 0
        found_prefix = False
        while True:
            items = self._list(parent, search=name, offset=offset)
            for item in items:
                if item["name"] == name:
                    if item.get("id") is not None:
                        return "artifact"
                    found_prefix = True
            if len(items) < 100:
                return "other" if found_prefix else "missing"
            offset += len(items)

    def exists(self, path: Path) -> bool:
        return self.status(path) != "missing"

    def write_text(self, path: Path, text: str) -> None:
        self._request("POST", self._object_route(path), data=text.encode("utf-8"))

    def read_text(self, path: Path, *, errors="strict") -> str:
        with self.open_binary_read(path) as artifact:
            with TextIOWrapper(artifact, encoding="utf-8", errors=errors, newline=None) as text:
                return text.read()

    @contextmanager
    def open_binary_write(self, path: Path):
        route = self._object_route(path)
        with TemporaryFile("w+b") as working:
            yield working
            working.seek(0)
            self._request("POST", route, data=working.read())

    @contextmanager
    def open_binary_read(self, path: Path):
        raw = self._request("GET", self._object_route(path), missing_ok=True)
        if raw is None:
            raise FileNotFoundError("Hosted artifact not found.")
        with TemporaryFile("w+b") as working:
            working.write(raw)
            working.seek(0)
            yield working

    @contextmanager
    def materialize(self, path: Path):
        relative = self.relative_locator(path)
        with TemporaryDirectory(prefix="ke-artifact-") as directory:
            local_path = Path(directory) / relative.name
            with self.open_binary_read(path) as artifact:
                local_path.write_bytes(artifact.read())
            yield local_path

    def replace(self, temporary: Path, destination: Path) -> None:
        source_route = self._object_route(temporary)
        target_route = self._object_route(destination)
        if source_route == target_route:
            if self.status(temporary) != "artifact":
                raise FileNotFoundError("Hosted artifact not found.")
            return
        with self.open_binary_read(temporary) as artifact:
            self._request("POST", target_route, data=artifact.read())
        self.remove(temporary)

    def remove(self, path: Path) -> None:
        self._request("DELETE", self._object_route(path), missing_ok=True)

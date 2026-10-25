#!/usr/bin/env python3
"""Fail-closed operator stages for a disk-backed hosted backup.

The preflight stage performs local checks only. Inventory uses Storage metadata
only. Download is an explicit separate command and streams one object at a time.
"""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler


SECRET_ENV = "SUPABASE_SECRET_KEY"
REFERENCE_KEYS = ("file_path", "extracted_text_path", "chunks_path")


class BackupError(RuntimeError):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def canonical(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise BackupError(f"Invalid JSON file: {path.name}") from None


def safe_locator(value: str) -> PurePosixPath:
    if not isinstance(value, str) or not value or "\\" in value:
        raise BackupError("Snapshot contains an unsafe artifact locator.")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or path == PurePosixPath("."):
        raise BackupError("Snapshot contains an unsafe artifact locator.")
    return path


def snapshot_references(snapshot: dict) -> tuple[list[str], int]:
    sources = snapshot.get("sources")
    if not isinstance(sources, list):
        raise BackupError("Snapshot sources are invalid.")
    references = set()
    for source in sources:
        if not isinstance(source, dict):
            raise BackupError("Snapshot source record is invalid.")
        for key in REFERENCE_KEYS:
            value = source.get(key)
            if value:
                references.add(safe_locator(value).as_posix())
    return sorted(references), len(sources)


def write_lines(path: Path, records: list[dict]) -> None:
    temporary = path.with_name(path.name + ".partial")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(canonical(record) + "\n")
    temporary.replace(path)


def read_lines(path: Path) -> list[dict]:
    try:
        records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    except (OSError, ValueError):
        raise BackupError(f"Invalid deterministic record file: {path.name}") from None
    return records


class StorageReader:
    def __init__(self, url: str, secret: str, bucket: str, workspace: str, opener=None):
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.path not in ("", "/"):
            raise BackupError("Storage URL must be an HTTPS origin.")
        if not secret:
            raise BackupError(f"{SECRET_ENV} is required for Storage access.")
        for label, value in (("bucket", bucket), ("workspace", workspace)):
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", value or ""):
                raise BackupError(f"Storage {label} must be one safe segment.")
        self.base = url.rstrip("/") + "/storage/v1"
        self.secret = secret
        self.bucket = bucket
        self.workspace = workspace
        self.opener = opener or build_opener(NoRedirect())

    def _open(self, request):
        try:
            return self.opener.open(request, timeout=60)
        except (HTTPError, URLError, OSError):
            raise BackupError("Storage request failed; no remote details were retained.") from None

    def list_exact(self, locator: str) -> dict:
        path = safe_locator(locator)
        parent = path.parent.as_posix()
        prefix = self.workspace + ("/" + parent if parent != "." else "")
        name = path.name
        matches = []
        offset = 0
        while True:
            payload = canonical({"prefix": prefix, "limit": 100, "offset": offset,
                                 "search": name, "sortBy": {"column": "name", "order": "asc"}}).encode()
            request = Request(
                self.base + "/object/list/" + quote(self.bucket, safe=""), data=payload,
                headers={"apikey": self.secret, "Content-Type": "application/json"}, method="POST")
            with closing(self._open(request)) as response:
                try:
                    items = json.loads(response.read())
                except (OSError, ValueError):
                    raise BackupError("Storage metadata response is invalid.") from None
            if not isinstance(items, list):
                raise BackupError("Storage metadata response is invalid.")
            for item in items:
                if isinstance(item, dict) and item.get("name") == name and item.get("id") is not None:
                    matches.append(item)
            if len(items) < 100:
                break
            offset += len(items)
        if len(matches) != 1:
            raise BackupError("Each snapshot locator must match exactly one Storage object.")
        item = matches[0]
        metadata = item.get("metadata")
        size = metadata.get("size") if isinstance(metadata, dict) else None
        if isinstance(size, bool) or not isinstance(size, (int, str)):
            raise BackupError("Storage object size metadata is missing.")
        try:
            size = int(size)
        except (TypeError, ValueError):
            raise BackupError("Storage object size metadata is invalid.") from None
        if (size < 0 or not isinstance(item.get("id"), str) or not item["id"] or
                not isinstance(item.get("updated_at"), str) or not item["updated_at"]):
            raise BackupError("Storage object identity or size is invalid.")
        return {"locator": path.as_posix(), "object_key": self.workspace + "/" + path.as_posix(),
                "object_id": item["id"], "size": size, "updated_at": item.get("updated_at")}

    def download(self, object_key: str, target: Path, expected_size: int) -> str:
        route = "/object/" + quote(self.bucket, safe="") + "/" + quote(object_key, safe="/")
        request = Request(self.base + route, headers={"apikey": self.secret}, method="GET")
        partial = target.with_name(target.name + ".partial")
        target.parent.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        count = 0
        try:
            with closing(self._open(request)) as response, partial.open("xb") as handle:
                while True:
                    block = response.read(1024 * 1024)
                    if not block:
                        break
                    handle.write(block)
                    digest.update(block)
                    count += len(block)
            if count != expected_size:
                raise BackupError("Downloaded artifact size does not match metadata.")
            partial.replace(target)
            return digest.hexdigest()
        except Exception:
            partial.unlink(missing_ok=True)
            raise


def inventory(snapshot_path: Path, output: Path, reader: StorageReader) -> dict:
    snapshot = load_json(snapshot_path)
    references, source_count = snapshot_references(snapshot)
    records = [reader.list_exact(locator) for locator in references]
    if (len({record["object_key"] for record in records}) != len(records) or
            len({record["object_id"] for record in records}) != len(records)):
        raise BackupError("Storage inventory contains duplicate object identities.")
    write_lines(output, records)
    return {"sources": source_count, "artifacts": len(records),
            "bytes": sum(record["size"] for record in records)}


def download(inventory_path: Path, package: Path, reader: StorageReader) -> dict:
    records = read_lines(inventory_path)
    artifacts = []
    for record in records:
        locator = safe_locator(record.get("locator")).as_posix()
        expected_key = reader.workspace + "/" + locator
        if record.get("object_key") != expected_key or not isinstance(record.get("size"), int):
            raise BackupError("Storage inventory identity is invalid.")
        target = package.joinpath("objects", *PurePosixPath(locator).parts)
        if target.exists() or target.with_name(target.name + ".partial").exists():
            raise BackupError("Download destination is not empty.")
        digest = reader.download(expected_key, target, record["size"])
        artifacts.append({"locator": locator, "object_key": expected_key,
                          "file": target.relative_to(package).as_posix(),
                          "size": record["size"], "sha256": digest})
    write_lines(package / "artifacts.ndjson", artifacts)
    return {"artifacts": len(artifacts), "bytes": sum(item["size"] for item in artifacts)}


def finalize(package: Path, deployed_commit: str) -> dict:
    before = load_json(package / "consistency-before.json")
    after = load_json(package / "consistency-after.json")
    if before != after:
        raise BackupError("Database consistency fence changed during backup.")
    if before.get("partition_marker") is not None:
        raise BackupError("Backup is not snapshot-authority state.")
    metadata_before = read_lines(package / "metadata-before.ndjson")
    metadata_after = read_lines(package / "metadata-after.ndjson")
    if (metadata_before != metadata_after or
            (package / "metadata-before.ndjson").read_bytes() !=
            (package / "metadata-after.ndjson").read_bytes()):
        raise BackupError("Storage object identity or metadata changed during backup.")
    snapshot = load_json(package / "snapshot.json")
    references, source_count = snapshot_references(snapshot)
    artifacts = read_lines(package / "artifacts.ndjson")
    if [item.get("locator") for item in metadata_before] != references:
        raise BackupError("Storage inventory does not match the fenced snapshot.")
    if [item.get("locator") for item in artifacts] != references:
        raise BackupError("Downloaded artifacts do not match the fenced snapshot.")
    if before.get("source_count") != source_count:
        raise BackupError("Snapshot count does not match the database consistency fence.")
    for item in artifacts:
        path = package.joinpath(*PurePosixPath(item["file"]).parts)
        if not path.is_file() or path.stat().st_size != item.get("size") or sha256(path) != item.get("sha256"):
            raise BackupError("Downloaded artifact checksum verification failed.")
    dump = package / "database.dump"
    snapshot_path = package / "snapshot.json"
    if not dump.is_file():
        raise BackupError("PostgreSQL dump is missing.")
    manifest = {
        "format_version": 1, "authority": "snapshot",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "deployed_commit": deployed_commit,
        "snapshot_revision": before.get("revision"),
        "expected_counts": {"sources": source_count, "artifacts": len(references),
                            "knowledge_assets": before.get("asset_count"),
                            "extraction_jobs": before.get("job_count"),
                            "outputs": before.get("output_count")},
        "snapshot": {"file": "snapshot.json", "sha256": sha256(snapshot_path)},
        "database_dump": {"file": "database.dump", "sha256": sha256(dump)},
        "allowance_ledger": {"included_in_database_dump": True},
        "artifacts": artifacts,
    }
    temporary = package / "manifest.json.partial"
    temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(package / "manifest.json")
    return manifest["expected_counts"]


def preflight(destination: Path, required_gib: int) -> dict:
    if destination.exists() and any(destination.iterdir()):
        raise BackupError("Backup destination must be new or empty.")
    parent = destination
    while not parent.exists():
        parent = parent.parent
    free = shutil.disk_usage(parent).free
    required = required_gib * 1024 ** 3
    if free < required:
        raise BackupError("Insufficient persistent disk space for backup and rehearsal.")
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    destination.chmod(0o700)
    return {"destination": str(destination.resolve()), "free_bytes": free,
            "required_bytes": required,
            "stop": "STOP: obtain approval before suspending Render or using production credentials."}


def storage_reader(args) -> StorageReader:
    return StorageReader(args.url, os.environ.get(SECRET_ENV, ""), args.bucket, args.workspace)


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("preflight")
    check.add_argument("destination", type=Path)
    check.add_argument("--required-free-gib", type=int, default=2)
    for name in ("inventory", "download"):
        command = commands.add_parser(name)
        command.add_argument("--url", required=True)
        command.add_argument("--bucket", required=True)
        command.add_argument("--workspace", required=True)
        if name == "inventory":
            command.add_argument("--snapshot", type=Path, required=True)
            command.add_argument("--output", type=Path, required=True)
        else:
            command.add_argument("--inventory", type=Path, required=True)
            command.add_argument("--package", type=Path, required=True)
    finish = commands.add_parser("finalize")
    finish.add_argument("--package", type=Path, required=True)
    finish.add_argument("--deployed-commit", required=True)
    args = parser.parse_args()
    try:
        if args.command == "preflight":
            result = preflight(args.destination, args.required_free_gib)
        elif args.command == "inventory":
            result = inventory(args.snapshot, args.output, storage_reader(args))
        elif args.command == "download":
            result = download(args.inventory, args.package, storage_reader(args))
        else:
            result = finalize(args.package, args.deployed_commit)
        print(json.dumps(result, sort_keys=True))
    except BackupError as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Verify a disk-backed hosted backup and prepare an isolated local restore.

This tool never connects to Supabase and never writes hosted data. Acquisition is
an operator procedure documented in docs/hosted_backup_restore.md.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import sqlite3


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def contained_file(root: Path, value, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise RuntimeError(f"Backup {label} path is invalid.")
    relative = PurePosixPath(value)
    if relative.is_absolute() or ".." in relative.parts or "\\" in value:
        raise RuntimeError(f"Backup {label} path is outside the package.")
    path = root.joinpath(*relative.parts)
    if not path.resolve().is_relative_to(root.resolve()):
        raise RuntimeError(f"Backup {label} path is outside the package.")
    return path


def load_and_verify(package: Path) -> tuple[dict, dict]:
    manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("format_version") != 1 or manifest.get("authority") != "snapshot":
        raise RuntimeError("Backup manifest is not the supported snapshot-authority format.")
    snapshot_entry = manifest.get("snapshot") or {}
    snapshot_path = contained_file(package, snapshot_entry.get("file"), "snapshot")
    dump_entry = manifest.get("database_dump") or {}
    dump_path = contained_file(package, dump_entry.get("file"), "database dump")
    for label, path, entry in (("snapshot", snapshot_path, snapshot_entry),
                               ("database dump", dump_path, dump_entry)):
        if not path.is_file() or sha256(path) != entry.get("sha256"):
            raise RuntimeError(f"Backup {label} is missing or has the wrong checksum.")
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    if snapshot.get("partition") is not None:
        raise RuntimeError("Backup unexpectedly declares partition authority.")

    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list):
        raise RuntimeError("Backup artifact manifest is missing.")
    locators = []
    keys = []
    for entry in artifacts:
        locator = entry.get("locator")
        object_key = entry.get("object_key")
        relative_file = entry.get("file")
        if not all(isinstance(value, str) and value for value in (locator, object_key, relative_file)):
            raise RuntimeError("Backup artifact identity is incomplete.")
        path = contained_file(package, relative_file, "artifact")
        locator_path = PurePosixPath(locator)
        if locator_path.is_absolute() or ".." in locator_path.parts or "\\" in locator:
            raise RuntimeError("Backup artifact locator is unsafe.")
        if (not path.is_file() or path.stat().st_size != entry.get("size") or
                sha256(path) != entry.get("sha256")):
            raise RuntimeError("Backup artifact is missing or has the wrong size or checksum.")
        locators.append(locator)
        keys.append(object_key)
    if len(locators) != len(set(locators)) or len(keys) != len(set(keys)):
        raise RuntimeError("Backup artifact identities are duplicated.")

    referenced = {
        source[key]
        for source in snapshot.get("sources", [])
        for key in ("file_path", "extracted_text_path", "chunks_path")
        if source.get(key)
    }
    if referenced != set(locators):
        raise RuntimeError("Backup artifacts do not exactly match active snapshot references.")
    expected = manifest.get("expected_counts")
    if expected is not None:
        observed = {
            "sources": len(snapshot.get("sources", [])),
            "artifacts": len(referenced),
            "knowledge_assets": len(snapshot.get("knowledge_assets", [])),
            "extraction_jobs": len(snapshot.get("extraction_jobs", [])),
            "outputs": len(snapshot.get("outputs", [])),
        }
        if expected != observed:
            raise RuntimeError("Backup manifest counts do not match the snapshot.")
    return manifest, snapshot


def restore_local(package: Path, destination: Path) -> dict:
    _manifest, snapshot = load_and_verify(package)
    if destination.exists() and any(destination.iterdir()):
        raise RuntimeError("Restore destination must be new or empty.")
    storage = destination / "storage"
    storage.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
    for entry in manifest["artifacts"]:
        target = storage.joinpath(*PurePosixPath(entry["locator"]).parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(package / entry["file"], target)

    portable = json.loads(json.dumps(snapshot))
    for source in portable.get("sources", []):
        for key in ("file_path", "extracted_text_path", "chunks_path"):
            if source.get(key):
                source[key] = "storage/" + source[key]
    (storage / "state.json").write_text(json.dumps(portable), encoding="utf-8")

    database = storage / "knowledge.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE state (id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL)")
        connection.execute("INSERT INTO state VALUES (1, ?)", (json.dumps(portable),))
    for source in portable.get("sources", []):
        for key in ("file_path", "extracted_text_path", "chunks_path"):
            value = source.get(key)
            if value and not (destination / value).is_file():
                raise RuntimeError("Restored snapshot contains a missing artifact.")
    return {"sources": len(portable.get("sources", [])), "artifacts": len(manifest["artifacts"])}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("package", type=Path)
    parser.add_argument("--restore-local", type=Path)
    args = parser.parse_args()
    if args.restore_local:
        result = restore_local(args.package, args.restore_local)
    else:
        manifest, snapshot = load_and_verify(args.package)
        result = {"sources": len(snapshot.get("sources", [])), "artifacts": len(manifest["artifacts"])}
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()

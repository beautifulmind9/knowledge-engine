"""Controlled, idempotent one-time manifest backfill (never invokes Gemini)."""
import json
from pathlib import Path

from app.db import mock_data
from app.db.persistence import StateMutationConflict
from app.persistence.factory import get_artifact_store
from app.services.chunk_manifest import manifest_from_chunks, valid_manifest


def backfill_chunk_manifests(*, source_records=None, store=None, persist=None, apply=True):
    records = mock_data.sources if source_records is None else source_records
    store = store or get_artifact_store()
    if persist is None:
        from app.services.knowledge_extraction import persist_state
        persist = persist_state

    eligible = [source for source in records if source.get("chunks_path")
                and not valid_manifest(source.get("id", ""), source.get("chunk_manifest"))]
    paths = [Path(source["chunks_path"]) for source in eligible]
    presence = store.status_many(paths)
    staged = []
    skipped = {"missing": [], "other": [], "malformed": [], "invalid_chunks": []}
    loaded = {}
    for path in dict.fromkeys(paths):
        status = presence[path]
        if status != "artifact":
            loaded[path] = ("missing" if status == "missing" else "other", None)
            continue
        try:
            raw = store.read_text(path)
        except FileNotFoundError:
            loaded[path] = ("missing", None)
            continue
        try:
            loaded[path] = ("chunks", json.loads(raw))
        except (json.JSONDecodeError, UnicodeDecodeError):
            loaded[path] = ("malformed", None)
    for source, path in zip(eligible, paths):
        state, chunks = loaded[path]
        if state != "chunks":
            skipped[state].append(source["id"])
            continue
        try:
            manifest = manifest_from_chunks(source["id"], chunks)
        except (TypeError, ValueError):
            skipped["invalid_chunks"].append(source["id"])
            continue
        staged.append((source, manifest))

    if staged and apply:
        previous = [(source, source.get("chunk_manifest")) for source, _ in staged]
        for source, manifest in staged:
            source["chunk_manifest"] = manifest
        try:
            persist()
        except StateMutationConflict:
            # The persistence layer refreshed these records to the latest
            # snapshot; never reapply the stale pre-backfill values locally.
            raise
        except Exception:
            for source, old_manifest in previous:
                if old_manifest is None:
                    source.pop("chunk_manifest", None)
                else:
                    source["chunk_manifest"] = old_manifest
            raise
    return {"updated_source_ids": [source["id"] for source, _ in staged],
            "skipped_source_ids": skipped,
            "updated_count": len(staged),
            "skipped_count": sum(map(len, skipped.values()))}

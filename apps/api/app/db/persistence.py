"""Whole-workspace snapshots with optimistic hosted writes and safe local rebasing.

The local store remains single-owner and migrates state.json without changing
the source file. Corruption fails loudly; it must never silently replace data.
"""
from copy import deepcopy
from pathlib import Path

from app.persistence.factory import (
    API_ROOT, STORAGE_ROOT, STATE_PATH, DB_PATH, get_state_store, get_artifact_store, PERSISTENCE_MODE,
)
from app.persistence.postgres import StaleStateWriteError
from app.persistence.reconciliation import StateReconciliationConflict, merge_state_snapshots


class StateMutationConflict(StaleStateWriteError):
    """A bounded rebase failed; the API's live collections were refreshed."""


def load_state():
    return get_state_store().load()


def save_state(libraries, sources, extraction_jobs, knowledge_assets):
    from app.db.mock_data import outputs, usage
    state = dict(libraries=libraries, sources=sources, extraction_jobs=extraction_jobs,
                 knowledge_assets=knowledge_assets, outputs=outputs, usage=usage, schema_version=2)
    if PERSISTENCE_MODE == "hosted":
        # Source locators are application data, not the StateStore's concern.
        # Persist portable root-relative locators without mutating live records.
        from pathlib import Path
        from app.persistence.artifact_paths import contained_locator
        store = get_artifact_store()
        portable_sources = []
        for source in sources:
            portable = dict(source)
            for key in ("file_path", "extracted_text_path", "chunks_path"):
                if portable.get(key):
                    path = contained_locator(store, Path(portable[key]), STORAGE_ROOT)
                    portable[key] = path.relative_to(STORAGE_ROOT).as_posix()
            portable_sources.append(portable)
        state["sources"] = portable_sources
    store = get_state_store()
    baseline = getattr(store, "loaded_snapshot", None)
    if baseline is None:
        baseline = {
            "schema_version": 2, "libraries": [], "sources": [],
            "extraction_jobs": [], "knowledge_assets": [], "outputs": [], "usage": {},
        }
    reconciliations = 0
    while True:
        try:
            store.save(state)
            if reconciliations:
                _restore_live_state(state, libraries, sources, extraction_jobs, knowledge_assets)
            return
        except StaleStateWriteError:
            # Only JSON snapshot persistence is repeated here. The route/service
            # mutation and any external upload, extraction, or provider work have
            # already happened and are never invoked by this reconciliation.
            if reconciliations >= 2:
                latest = store.load()
                if isinstance(latest, dict):
                    _restore_live_state(
                        latest, libraries, sources, extraction_jobs, knowledge_assets,
                        preserve_record_objects=False,
                    )
                raise StateMutationConflict(
                    "Hosted state changed repeatedly; this update could not be saved safely. Reload and try again."
                ) from None
            if not isinstance(baseline, dict):
                raise
            latest = store.load()
            if not isinstance(latest, dict):
                raise
            try:
                state = merge_state_snapshots(baseline, state, latest)
            except StateReconciliationConflict:
                _restore_live_state(
                    latest, libraries, sources, extraction_jobs, knowledge_assets,
                    preserve_record_objects=False,
                )
                raise StateMutationConflict(
                    "Hosted state changed concurrently; this update could not be reconciled safely. Reload and try again."
                ) from None
            baseline = getattr(store, "loaded_snapshot", None)
            reconciliations += 1


def _restore_live_state(state, libraries, sources, extraction_jobs, knowledge_assets,
                        preserve_record_objects=True):
    """Reflect a committed/rebased snapshot into module-level live collections."""
    from app.db import mock_data

    source_records = deepcopy(state.get("sources", []))
    if PERSISTENCE_MODE == "hosted":
        for source in source_records:
            for key in ("file_path", "extracted_text_path", "chunks_path"):
                value = source.get(key)
                if value and not Path(value).is_absolute():
                    source[key] = str(STORAGE_ROOT / value)

    for live, key, records in (
        (libraries, "libraries", state.get("libraries", [])),
        (sources, "sources", source_records),
        (extraction_jobs, "extraction_jobs", state.get("extraction_jobs", [])),
        (knowledge_assets, "knowledge_assets", state.get("knowledge_assets", [])),
        (mock_data.outputs, "outputs", state.get("outputs", [])),
    ):
        previous = {record.get("id"): record for record in live if isinstance(record, dict)}
        restored = []
        for value in records:
            record = previous.get(value.get("id")) if preserve_record_objects else None
            if record is None:
                record = deepcopy(value)
            else:
                record.clear()
                record.update(deepcopy(value))
            restored.append(record)
        live[:] = restored
    mock_data.usage.clear()
    mock_data.usage.update(deepcopy(state.get("usage", {})))

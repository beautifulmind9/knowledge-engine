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
from app.services.performance_timing import start as timing_start, emit as timing_emit, snapshot_utf8_size


class StateMutationConflict(StaleStateWriteError):
    """A bounded rebase failed; the API's live collections were refreshed."""


def load_state():
    return _load_store_state(get_state_store(), "application_load")


def _load_store_state(store, load_kind):
    started = timing_start() if PERSISTENCE_MODE == "hosted" else None
    result = "success"
    try:
        return store.load()
    except Exception:
        result = "error"
        raise
    finally:
        if PERSISTENCE_MODE == "hosted":
            timing_emit("hosted_state_load", started, result=result,
                        destination_category="state", load_kind=load_kind, payload_bytes=None,
                        payload_size_measurement="unavailable_without_reserializing")


def _snapshot_counts(state):
    try:
        state_sources = state.get("sources", [])
        state_jobs = state.get("extraction_jobs", [])
        state_assets = state.get("knowledge_assets", [])
        return dict(
            source_count=len(state_sources),
            extraction_job_count=len(state_jobs),
            interpreted_part_count=sum(1 for job in state_jobs if job.get("status") == "completed"),
            active_knowledge_asset_count=sum(1 for asset in state_assets if asset.get("active", True)),
        )
    except Exception:
        return dict(source_count=None, extraction_job_count=None,
                    interpreted_part_count=None, active_knowledge_asset_count=None)


def save_state(libraries, sources, extraction_jobs, knowledge_assets):
    persistence_started = timing_start()
    from app.db.request_state import request_mode
    if PERSISTENCE_MODE=='hosted' and request_mode.get() is not None and bool(getattr(get_state_store(),'partitioned',False))!=request_mode.get():
        raise StateMutationConflict('Persistence authority changed; reload before saving.')
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
    reconcile_started = None
    while True:
        snapshot_bytes = snapshot_utf8_size(state) if PERSISTENCE_MODE == "hosted" else None
        save_kind = "reconciliation" if reconciliations else "normal"
        snapshot_counts = _snapshot_counts(state)
        save_attempt_started = timing_start()
        try:
            store.save(state)
            timing_emit("state_persistence_attempt", save_attempt_started, result="success",
                        destination_category="state", mode=PERSISTENCE_MODE,
                        save_kind=save_kind, attempt_number=reconciliations + 1,
                        snapshot_utf8_bytes=snapshot_bytes, **snapshot_counts)
            timing_emit("state_persistence", persistence_started, result="success",
                        mode=PERSISTENCE_MODE,
                        source_count=len(sources),
                        active_knowledge_asset_count=snapshot_counts["active_knowledge_asset_count"],
                        reconciliation_count=reconciliations)
            if reconcile_started is not None:
                timing_emit("hosted_state_reconciliation", reconcile_started, result="success",
                            reconciliation_count=reconciliations)
            if reconciliations:
                _restore_live_state(state, libraries, sources, extraction_jobs, knowledge_assets)
            return
        except StaleStateWriteError:
            timing_emit("state_persistence_attempt", save_attempt_started, result="stale_revision",
                        destination_category="state", mode=PERSISTENCE_MODE,
                        save_kind=save_kind, attempt_number=reconciliations + 1,
                        snapshot_utf8_bytes=snapshot_bytes, **snapshot_counts)
            if reconcile_started is None:
                reconcile_started = timing_start()
            # Only JSON snapshot persistence is repeated here. The route/service
            # mutation and any external upload, extraction, or provider work have
            # already happened and are never invoked by this reconciliation.
            if reconciliations >= 2:
                latest = _load_store_state(store, "reconciliation")
                if isinstance(latest, dict):
                    _restore_live_state(
                        latest, libraries, sources, extraction_jobs, knowledge_assets,
                        preserve_record_objects=False,
                    )
                timing_emit("hosted_state_reconciliation", reconcile_started, result="exhausted",
                            reconciliation_count=reconciliations)
                raise StateMutationConflict(
                    "Hosted state changed repeatedly; this update could not be saved safely. Reload and try again."
                ) from None
            if not isinstance(baseline, dict):
                raise
            latest = _load_store_state(store, "reconciliation")
            if not isinstance(latest, dict):
                raise
            try:
                from app.persistence.phase3 import authority_version
                if authority_version(baseline)!=authority_version(latest):
                    _restore_live_state(latest,libraries,sources,extraction_jobs,knowledge_assets,preserve_record_objects=False)
                    raise StateMutationConflict('Persistence authority changed; retry the request after reload.')
                if getattr(store,'partitioned',False):
                    if getattr(store,'phase3',False):
                        from app.persistence.phase3 import rebase_projection
                    else:
                        from app.persistence.phase2 import rebase_projection
                    state = rebase_projection(baseline,state,latest)
                else:
                    state = merge_state_snapshots(baseline, state, latest)
            except StateReconciliationConflict:
                _restore_live_state(
                    latest, libraries, sources, extraction_jobs, knowledge_assets,
                    preserve_record_objects=False,
                )
                timing_emit("hosted_state_reconciliation", reconcile_started, result="conflict",
                            reconciliation_count=reconciliations)
                raise StateMutationConflict(
                    "Hosted state changed concurrently; this update could not be reconciled safely. Reload and try again."
                ) from None
            baseline = getattr(store, "loaded_snapshot", None)
            reconciliations += 1
        except Exception:
            timing_emit("state_persistence_attempt", save_attempt_started, result="error",
                        destination_category="state", mode=PERSISTENCE_MODE,
                        save_kind=save_kind, attempt_number=reconciliations + 1,
                        snapshot_utf8_bytes=snapshot_bytes, **snapshot_counts)
            raise


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

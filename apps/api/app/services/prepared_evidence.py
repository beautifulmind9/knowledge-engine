"""Short-lived server-owned Create previews for the single-process application.

Restart, expiry, or eviction requires an explicit new preparation, never retrieval
inside generation. No client-supplied knowledge is trusted or persisted here.
"""
from collections import OrderedDict
from copy import deepcopy
import secrets
from threading import Lock
import time

from fastapi import HTTPException
from app.models.workshop import WorkshopPrepareRequest
from app.services.evidence_safety import validate_preparation, check_json_budget, MAX_PREPARED_BYTES

TTL_SECONDS = 30 * 60
MAX_SNAPSHOTS = 128
MAX_CACHED_EVIDENCE_BYTES = 8 * 1024 * 1024
_snapshots = OrderedDict()
_snapshot_sizes = {}
_lock = Lock()


def _brief(payload):
    return WorkshopPrepareRequest.model_validate(payload.model_dump()).model_dump(mode="json")


def remember_preparation(payload, prepared):
    validate_preparation(prepared, payload)
    size = check_json_budget(prepared, MAX_PREPARED_BYTES,
                             message='This evidence preview is too large. Choose fewer materials or ideas.')
    snapshot_id = secrets.token_urlsafe(32)
    with _lock:
        now = time.monotonic()
        for key, entry in list(_snapshots.items()):
            if entry[0] <= now:
                del _snapshots[key]
                _snapshot_sizes.pop(key, None)
        _snapshots[snapshot_id] = (now + TTL_SECONDS, _brief(payload), deepcopy(prepared))
        _snapshot_sizes[snapshot_id] = size
        while len(_snapshots) > MAX_SNAPSHOTS or sum(_snapshot_sizes.get(key, 0) for key in _snapshots) > MAX_CACHED_EVIDENCE_BYTES:
            old_id, _ = _snapshots.popitem(last=False)
            _snapshot_sizes.pop(old_id, None)
    return {**prepared, "prepared_snapshot_id": snapshot_id,
            "interaction_revision": payload.interaction_revision}


def resolve_preparation(payload):
    with _lock:
        entry = _snapshots.get(payload.prepared_snapshot_id)
        if not entry or entry[0] <= time.monotonic():
            raise HTTPException(409, "Knowledge preview expired or is unavailable. Update knowledge before creating.")
        if entry[1] != _brief(payload):
            raise HTTPException(409, "Knowledge preview does not match this request. Update knowledge before creating.")
        from app.db.mock_data import sources, libraries
        source_ids = {s["id"] for s in sources}
        if any(sid not in source_ids for group in entry[2]["knowledge_units"] for sid in group["source_ids"]) or (
            payload.library_id and not any(l["id"] == payload.library_id for l in libraries)
        ):
            raise HTTPException(409, "A reviewed material is no longer available. Update knowledge before creating.")
        prepared = deepcopy(entry[2])
    validate_preparation(prepared, payload)
    return prepared

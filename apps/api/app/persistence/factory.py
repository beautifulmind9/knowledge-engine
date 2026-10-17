"""Process-wide persistence wiring, selected once at import/startup.

Construction does not load state or create directories. The existing database
facade remains responsible for load/save timing. Restart to change configuration.
"""
import os
from pathlib import Path

from app.persistence.contracts import ArtifactStore, StateStore, PartitionStore
from app.persistence.local_artifacts import LocalArtifactStore
from app.persistence.sqlite import SQLiteStateStore

MODE_ENV = "KNOWLEDGE_ENGINE_PERSISTENCE_MODE"
# Values are deliberately strict: only an unset variable defaults to local.
PERSISTENCE_MODE = os.environ.get(MODE_ENV, "local")
if PERSISTENCE_MODE not in ("local", "hosted"):
    raise RuntimeError(
        f"Invalid {MODE_ENV} value {PERSISTENCE_MODE!r}. Expected 'local' or 'hosted'."
    )

API_ROOT = Path(__file__).resolve().parents[2]
STORAGE_ROOT = Path(os.environ.get("KNOWLEDGE_ENGINE_STORAGE", API_ROOT / "storage")).expanduser().resolve()
STATE_PATH = STORAGE_ROOT / "state.json"
DB_PATH = STORAGE_ROOT / "knowledge.sqlite3"

if PERSISTENCE_MODE == "local":
    _state_store = SQLiteStateStore(STORAGE_ROOT, STATE_PATH, DB_PATH, API_ROOT)
    _artifact_store = LocalArtifactStore()
else:
    from app.persistence.postgres import PostgresStateStore

    _state_store = PostgresStateStore(
        os.environ.get("KNOWLEDGE_ENGINE_DATABASE_URL", ""),
        os.environ.get("KNOWLEDGE_ENGINE_WORKSPACE_KEY", ""),
    )
    from app.persistence.supabase_artifacts import SupabaseArtifactStore

    _artifact_store = SupabaseArtifactStore(
        STORAGE_ROOT, os.environ.get("SUPABASE_URL", ""),
        os.environ.get("SUPABASE_SECRET_KEY", ""),
        os.environ.get("KNOWLEDGE_ENGINE_STORAGE_BUCKET", ""),
        os.environ.get("KNOWLEDGE_ENGINE_WORKSPACE_KEY", ""),
    )
    _allowance_store = None


def get_state_store() -> StateStore:
    return _state_store


def get_artifact_store() -> ArtifactStore:
    return _artifact_store


def get_local_artifact_store() -> LocalArtifactStore:
    """Local-only containment and backup capabilities, outside the generic contract."""
    if not isinstance(_artifact_store, LocalArtifactStore):
        raise RuntimeError("Local artifact capabilities are unavailable in hosted mode.")
    return _artifact_store


def get_allowance_store():
    """Return the separate atomic allowance store in hosted mode only."""
    if PERSISTENCE_MODE != "hosted":
        raise RuntimeError("A separate allowance store is available only in hosted mode.")
    global _allowance_store
    if _allowance_store is None:
        from app.persistence.allowance import PostgresAllowanceStore

        _allowance_store = PostgresAllowanceStore(
            os.environ.get("KNOWLEDGE_ENGINE_DATABASE_URL", ""),
            os.environ.get("KNOWLEDGE_ENGINE_WORKSPACE_KEY", ""),
        )
    return _allowance_store


_partition_store = None


def get_partition_store() -> PartitionStore:
    """Dormant hosted primitives. No IO or authority switch until explicitly used."""
    if PERSISTENCE_MODE != "hosted":
        raise RuntimeError("Narrow partition storage is available only in hosted mode.")
    global _partition_store
    if _partition_store is None:
        from app.persistence.partitions import PostgresPartitionStore

        _partition_store = PostgresPartitionStore(
            os.environ.get("KNOWLEDGE_ENGINE_DATABASE_URL", ""),
            os.environ.get("KNOWLEDGE_ENGINE_WORKSPACE_KEY", ""),
        )
    return _partition_store


_phase2_coordinator = None


def get_phase2_coordinator():
    """No IO, backfill or activation on construction."""
    if PERSISTENCE_MODE != 'hosted':
        raise RuntimeError('Phase 2 coordination requires hosted persistence.')
    global _phase2_coordinator
    if _phase2_coordinator is None:
        from app.persistence.phase2 import Phase2Coordinator
        _phase2_coordinator = Phase2Coordinator(
            os.environ.get('KNOWLEDGE_ENGINE_DATABASE_URL', ''),
            os.environ.get('KNOWLEDGE_ENGINE_WORKSPACE_KEY', ''))
    return _phase2_coordinator


_phase3_coordinator = None


def get_phase3_coordinator():
    """No IO, backfill or activation on construction."""
    if PERSISTENCE_MODE != 'hosted':
        raise RuntimeError('Phase 3 coordination requires hosted persistence.')
    global _phase3_coordinator
    if _phase3_coordinator is None:
        from app.persistence.phase3 import Phase3Coordinator
        _phase3_coordinator = Phase3Coordinator(
            os.environ.get('KNOWLEDGE_ENGINE_DATABASE_URL', ''),
            os.environ.get('KNOWLEDGE_ENGINE_WORKSPACE_KEY', ''))
    return _phase3_coordinator

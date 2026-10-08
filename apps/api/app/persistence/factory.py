"""Process-wide persistence wiring, selected once at import/startup.

Construction does not load state or create directories. The existing database
facade remains responsible for load/save timing. Restart to change configuration.
"""
import os
from pathlib import Path

from app.persistence.contracts import ArtifactStore, StateStore
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


def get_state_store() -> StateStore:
    return _state_store


def get_artifact_store() -> ArtifactStore:
    return _artifact_store


def get_local_artifact_store() -> LocalArtifactStore:
    """Local-only containment and backup capabilities, outside the generic contract."""
    if not isinstance(_artifact_store, LocalArtifactStore):
        raise RuntimeError("Local artifact capabilities are unavailable in hosted mode.")
    return _artifact_store

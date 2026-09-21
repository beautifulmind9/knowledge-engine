"""Single-owner SQLite snapshots. Run one server process; requests are serialized.

The first launch migrates existing state.json without changing the source file.
Corruption fails loudly; it must never silently replace the owner's data.
"""
import os
from pathlib import Path

from app.persistence.contracts import StateStore
from app.persistence.sqlite import SQLiteStateStore

API_ROOT = Path(__file__).resolve().parents[2]
STORAGE_ROOT = Path(os.environ.get("KNOWLEDGE_ENGINE_STORAGE", API_ROOT / "storage")).expanduser().resolve()
STATE_PATH = STORAGE_ROOT / "state.json"
DB_PATH = STORAGE_ROOT / "knowledge.sqlite3"


def _state_store() -> StateStore:
    return SQLiteStateStore(STORAGE_ROOT, STATE_PATH, DB_PATH, API_ROOT)


def load_state():
    return _state_store().load()


def save_state(libraries, sources, extraction_jobs, knowledge_assets):
    from app.db.mock_data import outputs, usage
    state = dict(libraries=libraries, sources=sources, extraction_jobs=extraction_jobs,
                 knowledge_assets=knowledge_assets, outputs=outputs, usage=usage, schema_version=2)
    _state_store().save(state)

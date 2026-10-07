"""Single-owner SQLite snapshots. Run one server process; requests are serialized.

The first launch migrates existing state.json without changing the source file.
Corruption fails loudly; it must never silently replace the owner's data.
"""
from app.persistence.factory import (
    API_ROOT, STORAGE_ROOT, STATE_PATH, DB_PATH, get_state_store,
)


def load_state():
    return get_state_store().load()


def save_state(libraries, sources, extraction_jobs, knowledge_assets):
    from app.db.mock_data import outputs, usage
    state = dict(libraries=libraries, sources=sources, extraction_jobs=extraction_jobs,
                 knowledge_assets=knowledge_assets, outputs=outputs, usage=usage, schema_version=2)
    get_state_store().save(state)

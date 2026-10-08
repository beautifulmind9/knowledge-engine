"""Single-owner snapshots. Run one server process; requests are serialized.

Local first launch migrates state.json without changing the source file.
Corruption fails loudly; it must never silently replace the owner's data.
"""
from app.persistence.factory import (
    API_ROOT, STORAGE_ROOT, STATE_PATH, DB_PATH, get_state_store, get_artifact_store, PERSISTENCE_MODE,
)


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
    get_state_store().save(state)

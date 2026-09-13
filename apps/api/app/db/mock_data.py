from datetime import datetime, timezone
from uuid import uuid4

from app.db.persistence import load_state


_default_libraries = [
    {
        "id": "library_copywriting",
        "name": "Copywriting",
        "description": "Books and sources about writing, messaging, persuasion, and communication.",
        "created_at": datetime.now(timezone.utc).isoformat()
    },
    {
        "id": "library_product_strategy",
        "name": "Product Strategy",
        "description": "Sources about product building, validation, strategy, and user problems.",
        "created_at": datetime.now(timezone.utc).isoformat()
    }
]


_default_sources = [
    {
        "id": "source_made_to_stick",
        "library_id": "library_copywriting",
        "title": "Made to Stick",
        "author": "Chip Heath & Dan Heath",
        "source_type": "book",
        "processing_status": "prototype_imported",
        "created_at": datetime.now(timezone.utc).isoformat()
    }
]


_state = load_state()

if _state is not None:
    libraries = _state.get("libraries", _default_libraries)
    sources = _state.get("sources", _default_sources)
    extraction_jobs = _state.get("extraction_jobs", [])
    knowledge_assets = _state.get("knowledge_assets", [])
else:
    libraries = _default_libraries
    sources = []
    extraction_jobs = []
    knowledge_assets = []


outputs = _state.get("outputs", []) if _state is not None else []
usage = _state.get("usage", {}) if _state is not None else {}

def create_id(prefix):
    return f"{prefix}_{uuid4().hex[:8]}"

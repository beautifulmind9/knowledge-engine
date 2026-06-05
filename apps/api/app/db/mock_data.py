from datetime import datetime, timezone
from uuid import uuid4


libraries = [
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


sources = [
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


def create_id(prefix):
    return f"{prefix}_{uuid4().hex[:8]}"

from fastapi import APIRouter
from pydantic import BaseModel

from app.db.mock_data import create_id, sources

router = APIRouter(prefix="/sources", tags=["sources"])


class SourceCreate(BaseModel):
    library_id: str
    title: str
    author: str | None = None
    source_type: str = "book"


@router.get("")
def get_sources(library_id: str | None = None):
    if library_id:
        filtered_sources = [
            source for source in sources
            if source.get("library_id") == library_id
        ]

        return {
            "items": filtered_sources,
            "count": len(filtered_sources)
        }

    return {
        "items": sources,
        "count": len(sources)
    }


@router.post("")
def create_source(payload: SourceCreate):
    source = {
        "id": create_id("source"),
        "library_id": payload.library_id,
        "title": payload.title,
        "author": payload.author or "",
        "source_type": payload.source_type,
        "processing_status": "not_started",
        "created_at": None
    }

    sources.append(source)

    return source

from fastapi import APIRouter
from pydantic import BaseModel

from app.db.mock_data import (
    create_id,
    extraction_jobs,
    knowledge_assets,
    libraries,
    sources,
)
from app.db.persistence import save_state

router = APIRouter(prefix="/libraries", tags=["libraries"])


class LibraryCreate(BaseModel):
    name: str
    description: str | None = None


@router.get("")
def get_libraries():
    return {
        "items": libraries,
        "count": len(libraries)
    }


@router.post("")
def create_library(payload: LibraryCreate):
    library = {
        "id": create_id("library"),
        "name": payload.name,
        "description": payload.description or "",
        "created_at": None
    }

    libraries.append(library)
    save_state(libraries, sources, extraction_jobs, knowledge_assets)

    return library

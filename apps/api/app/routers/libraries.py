from fastapi import APIRouter
from pydantic import BaseModel

from app.db.mock_data import create_id, libraries

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

    return library

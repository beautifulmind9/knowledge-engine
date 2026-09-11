from fastapi import APIRouter
from pydantic import BaseModel, Field, ConfigDict
from app.db import store

router = APIRouter(prefix="/libraries", tags=["libraries"])


class LibraryCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)


@router.get("")
def get_libraries():
    items = store.all_records("library")
    return {"items": items, "count": len(items)}


@router.post("", status_code=201)
def create_library(payload: LibraryCreate):
    return store.save("library", {"id": store.create_id("library"), **payload.model_dump(), "created_at": store.now()})

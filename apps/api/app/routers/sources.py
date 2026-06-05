from pathlib import Path
from shutil import copyfileobj

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.db.mock_data import create_id, sources

router = APIRouter(prefix="/sources", tags=["sources"])

UPLOAD_FOLDER = Path("storage/uploads")

ALLOWED_FILE_EXTENSIONS = {
    ".pdf",
    ".epub",
    ".txt",
    ".md",
    ".docx",
    ".csv",
    ".json",
    ".html",
    ".htm"
}


class SourceCreate(BaseModel):
    library_id: str
    title: str
    author: str | None = None
    source_type: str = "book"


def find_source(source_id: str):
    for source in sources:
        if source.get("id") == source_id:
            return source

    return None


def get_file_extension(filename: str):
    return Path(filename).suffix.lower()


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
        "file_name": None,
        "file_path": None,
        "file_type": None,
        "created_at": None
    }

    sources.append(source)

    return source


@router.get("/{source_id}")
def get_source(source_id: str):
    source = find_source(source_id)

    if not source:
        raise HTTPException(
            status_code=404,
            detail="Source not found"
        )

    return source


@router.get("/{source_id}/status")
def get_source_status(source_id: str):
    source = find_source(source_id)

    if not source:
        raise HTTPException(
            status_code=404,
            detail="Source not found"
        )

    return {
        "source_id": source["id"],
        "title": source["title"],
        "processing_status": source["processing_status"],
        "file_name": source.get("file_name"),
        "file_type": source.get("file_type")
    }


@router.post("/{source_id}/process")
def request_source_processing(source_id: str):
    source = find_source(source_id)

    if not source:
        raise HTTPException(
            status_code=404,
            detail="Source not found"
        )

    if not source.get("file_path"):
        raise HTTPException(
            status_code=400,
            detail="Upload a source file before requesting processing."
        )

    source["processing_status"] = "processing_requested"

    return {
        "source_id": source["id"],
        "title": source["title"],
        "processing_status": source["processing_status"],
        "message": "Processing has been requested. Background processing will be connected later."
    }


@router.post("/{source_id}/upload")
def upload_source_file(source_id: str, file: UploadFile = File(...)):
    source = find_source(source_id)

    if not source:
        raise HTTPException(
            status_code=404,
            detail="Source not found"
        )

    file_extension = get_file_extension(file.filename)

    if file_extension not in ALLOWED_FILE_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type. Allowed types: {sorted(ALLOWED_FILE_EXTENSIONS)}"
        )

    UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)

    safe_file_name = f"{source_id}{file_extension}"
    file_path = UPLOAD_FOLDER / safe_file_name

    with file_path.open("wb") as buffer:
        copyfileobj(file.file, buffer)

    source["file_name"] = file.filename
    source["file_path"] = str(file_path)
    source["file_type"] = file_extension
    source["processing_status"] = "uploaded"

    return {
        "source_id": source["id"],
        "title": source["title"],
        "file_name": source["file_name"],
        "file_type": source["file_type"],
        "processing_status": source["processing_status"],
        "message": "File uploaded successfully."
    }


@router.get("/{source_id}/file")
def get_source_file(source_id: str):
    source = find_source(source_id)

    if not source:
        raise HTTPException(
            status_code=404,
            detail="Source not found"
        )

    file_path = source.get("file_path")

    if not file_path:
        raise HTTPException(
            status_code=404,
            detail="No file uploaded for this source."
        )

    path = Path(file_path)

    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail="Uploaded file not found on disk."
        )

    return FileResponse(
        path=path,
        filename=source.get("file_name") or path.name
    )

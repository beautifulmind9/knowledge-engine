from pathlib import Path
from shutil import copyfileobj

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel

from app.db.mock_data import create_id, sources
from app.services.text_extraction import (
    UnsupportedExtractionTypeError,
    extract_text_from_file,
    save_extracted_text
)

from app.services.text_chunking import chunk_text, load_chunks, save_chunks

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
        "extracted_text_path": None,
        "chunks_path": None,
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
        "file_type": source.get("file_type"),
        "extracted_text_path": source.get("extracted_text_path"),
        "chunks_path": source.get("chunks_path")
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
    source["extracted_text_path"] = None
    source["chunks_path"] = None
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


@router.post("/{source_id}/extract")
def extract_source_text(source_id: str):
    source = find_source(source_id)

    if not source:
        raise HTTPException(
            status_code=404,
            detail="Source not found"
        )

    file_path = source.get("file_path")
    file_type = source.get("file_type")

    if not file_path or not file_type:
        raise HTTPException(
            status_code=400,
            detail="Upload a source file before extracting text."
        )

    try:
        extracted_text = extract_text_from_file(
            file_path=file_path,
            file_type=file_type
        )
    except UnsupportedExtractionTypeError as error:
        source["processing_status"] = "extraction_not_supported"

        raise HTTPException(
            status_code=400,
            detail=str(error)
        )

    extracted_text_path = save_extracted_text(
        source_id=source_id,
        text=extracted_text
    )

    source["extracted_text_path"] = extracted_text_path
    source["processing_status"] = "text_extracted"

    return {
        "source_id": source["id"],
        "title": source["title"],
        "file_type": source["file_type"],
        "processing_status": source["processing_status"],
        "extracted_text_path": source["extracted_text_path"],
        "character_count": len(extracted_text),
        "message": "Text extracted successfully."
    }


@router.get("/{source_id}/extracted-text", response_class=PlainTextResponse)
def get_extracted_text(source_id: str):
    source = find_source(source_id)

    if not source:
        raise HTTPException(
            status_code=404,
            detail="Source not found"
        )

    extracted_text_path = source.get("extracted_text_path")

    if not extracted_text_path:
        raise HTTPException(
            status_code=404,
            detail="No extracted text found for this source."
        )

    path = Path(extracted_text_path)

    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail="Extracted text file not found on disk."
        )

    return path.read_text(encoding="utf-8", errors="ignore")

@router.post("/{source_id}/chunk")
def chunk_source_text(source_id: str):
    source = find_source(source_id)

    if not source:
        raise HTTPException(
            status_code=404,
            detail="Source not found"
        )

    extracted_text_path = source.get("extracted_text_path")

    if not extracted_text_path:
        raise HTTPException(
            status_code=400,
            detail="Extract text before chunking this source."
        )

    path = Path(extracted_text_path)

    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail="Extracted text file not found on disk."
        )

    extracted_text = path.read_text(encoding="utf-8", errors="ignore")
    chunks = chunk_text(
        source_id=source_id,
        text=extracted_text
    )

    chunks_path = save_chunks(
        source_id=source_id,
        chunks=chunks
    )

    source["chunks_path"] = chunks_path
    source["processing_status"] = "chunked"

    return {
        "source_id": source["id"],
        "title": source["title"],
        "processing_status": source["processing_status"],
        "chunks_path": source["chunks_path"],
        "chunk_count": len(chunks),
        "message": "Text chunked successfully."
    }


@router.get("/{source_id}/chunks")
def get_source_chunks(source_id: str):
    source = find_source(source_id)

    if not source:
        raise HTTPException(
            status_code=404,
            detail="Source not found"
        )

    chunks_path = source.get("chunks_path")

    if not chunks_path:
        raise HTTPException(
            status_code=404,
            detail="No chunks found for this source."
        )

    path = Path(chunks_path)

    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail="Chunks file not found on disk."
        )

    chunks = load_chunks(chunks_path)

    return {
        "source_id": source["id"],
        "title": source["title"],
        "items": chunks,
        "count": len(chunks)
    }
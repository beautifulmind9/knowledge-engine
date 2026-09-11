from pathlib import Path
from hashlib import sha256

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel, Field, ConfigDict

from app.db import store
from app.db.store import create_id
from app.services.text_extraction import (
    UnsupportedExtractionTypeError,
    extract_text_from_file,
    save_extracted_text
)

from app.services.text_chunking import chunk_text, load_chunks, save_chunks

router = APIRouter(prefix="/sources", tags=["sources"])

MAX_UPLOAD_BYTES = 25 * 1024 * 1024

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
    model_config = ConfigDict(str_strip_whitespace=True)
    library_id: str
    title: str = Field(min_length=1, max_length=500)
    author: str | None = None
    source_type: str = "book"


def find_source(source_id: str):
    return store.get("source", source_id)


def get_file_extension(filename: str):
    return Path(filename or "").suffix.lower()


@router.get("")
def get_sources(library_id: str | None = None):
    sources = store.all_records("source")
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
    if not store.get("library", payload.library_id):
        raise HTTPException(404, "Library not found")
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
        "created_at": store.now()
    }

    store.save("source", source)

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

    extract_source_text(source_id)
    return chunk_source_text(source_id)


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

    if source.get("file_path"):
        raise HTTPException(409, "This source already has a file. Add a new source for a revised file to preserve existing evidence.")
    upload_folder = store.storage_root() / "uploads"
    upload_folder.mkdir(parents=True, exist_ok=True)

    safe_file_name = f"{source_id}{file_extension}"
    file_path = upload_folder / safe_file_name

    data = file.file.read(MAX_UPLOAD_BYTES + 1)
    if not data:
        raise HTTPException(400, "The uploaded file is empty.")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "Please upload a file smaller than 25 MB.")
    file_path.write_bytes(data)
    source["file_sha256"] = sha256(data).hexdigest()

    source["file_name"] = file.filename
    source["file_path"] = str(file_path)
    source["file_type"] = file_extension
    source["processing_status"] = "uploaded"
    source["extracted_text_path"] = None
    source["chunks_path"] = None
    store.save("source", source)
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
    except Exception as error:
        source["processing_status"] = "extraction_failed"
        store.save("source", source)

        raise HTTPException(
            status_code=400,
            detail=str(error) if isinstance(error, (UnsupportedExtractionTypeError, ValueError)) else "Could not read this file. Check that it is valid and not encrypted."
        )

    if not extracted_text.strip():
        source["processing_status"] = "extraction_failed"
        store.save("source", source)
        raise HTTPException(422, "No readable text found. Scanned PDFs need OCR before upload.")

    extracted_text_path = save_extracted_text(
        source_id=source_id,
        text=extracted_text
    )

    source["extracted_text_path"] = extracted_text_path
    source["processing_status"] = "text_extracted"
    store.save("source", source)

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
    source["chunk_count"] = len(chunks)
    store.save("source", source)

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

@router.delete("/{source_id}", status_code=204)
def delete_source(source_id: str):
    source = find_source(source_id)
    if not source:
        raise HTTPException(404, "Source not found")
    used = any(source_id in w.get("source_ids", []) for w in store.all_records("workshop"))
    if used:
        raise HTTPException(409, "Delete workshops using this source first so saved evidence remains traceable.")
    for unit in store.all_records("knowledge"):
        if unit["source_id"] == source_id:
            store.delete("knowledge", unit["id"])
    for key in ("file_path", "extracted_text_path", "chunks_path"):
        if source.get(key):
            Path(source[key]).unlink(missing_ok=True)
    store.delete("source", source_id)

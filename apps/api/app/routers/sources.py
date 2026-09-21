from pathlib import Path
from shutil import copyfileobj

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from datetime import datetime, timezone

from app.db.mock_data import (
    create_id,
    extraction_jobs,
    knowledge_assets,
    libraries,
    sources,
)
from app.db.persistence import save_state
from app.persistence.contracts import ArtifactStore
from app.persistence.local_artifacts import LocalArtifactStore
from app.responses import ArtifactFileResponse
from app.services.text_extraction import (
    UnsupportedExtractionTypeError,
    extract_text_from_file,
    save_extracted_text
)
from app.services.text_chunking import chunk_text, load_chunks, save_chunks
from app.services.source_structure import annotate_pdf_chunks_with_outline

router = APIRouter(prefix="/sources", tags=["sources"])

from app.db.persistence import STORAGE_ROOT

UPLOAD_FOLDER = STORAGE_ROOT / "uploads"
_artifact_store: ArtifactStore = LocalArtifactStore()

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
    title: str = Field(min_length=1, max_length=500)
    author: str | None = None
    source_type: str = "book"


def persist_state():
    save_state(libraries, sources, extraction_jobs, knowledge_assets)


def find_source(source_id: str):
    for source in sources:
        if source.get("id") == source_id:
            return source

    return None


def get_file_extension(filename: str):
    return Path(filename).suffix.lower()


def _recover_pdf_structure(source: dict):
    if source.get("file_type") != ".pdf":
        raise HTTPException(400, "Chapter recovery currently uses embedded PDF outlines and is available only for PDF sources.")

    file_path = source.get("file_path")
    chunks_path = source.get("chunks_path")
    if not file_path or not _artifact_store.exists(Path(file_path)):
        raise HTTPException(404, "Uploaded PDF file not found on disk.")
    if not chunks_path or not Path(chunks_path).exists():
        raise HTTPException(400, "Chunk this source before recovering chapter structure.")

    chunks = load_chunks(chunks_path)
    try:
        with _artifact_store.materialize(Path(file_path)) as local_path:
            chunks, summary = annotate_pdf_chunks_with_outline(str(local_path), chunks)
    except Exception as error:
        raise HTTPException(400, f"PDF chapter structure could not be read: {error}") from error

    save_chunks(source["id"], chunks)
    chapter_by_chunk = {
        chunk["id"]: chunk.get("chapter_or_section")
        for chunk in chunks
        if chunk.get("chapter_or_section")
    }
    updated_assets = 0
    for asset in knowledge_assets:
        if asset.get("source_id") != source["id"]:
            continue
        chapter = chapter_by_chunk.get(asset.get("chunk_id"))
        if chapter and not asset.get("chapter_or_section"):
            asset["chapter_or_section"] = chapter
            updated_assets += 1

    source["structure_status"] = (
        "pdf_outline_recovered" if summary["outline_entry_count"] else "no_pdf_outline"
    )
    source["structure_section_count"] = summary["section_count"]
    source["structure_outline_entry_count"] = summary["outline_entry_count"]
    persist_state()

    return {
        "source_id": source["id"],
        **summary,
        "updated_asset_count": updated_assets,
        "structure_status": source["structure_status"],
        "message": (
            "PDF outline structure recovered without changing chunk text or making an AI call."
            if summary["outline_entry_count"]
            else "This PDF has no usable embedded outline. No chapter labels were added."
        ),
    }


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
    if not any(l["id"] == payload.library_id for l in libraries):
        raise HTTPException(404, "Library not found.")
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
        "created_at": datetime.now(timezone.utc).isoformat()
    }

    sources.append(source)
    persist_state()

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
        "chunks_path": source.get("chunks_path"),
        "structure_status": source.get("structure_status"),
        "structure_section_count": source.get("structure_section_count", 0),
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

    if not source.get("extracted_text_path"):
        extract_source_text(source_id)
    return chunk_source_text(source_id)


@router.post("/{source_id}/recover-structure")
def recover_source_structure(source_id: str):
    source = find_source(source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    return _recover_pdf_structure(source)


@router.post("/{source_id}/upload")
def upload_source_file(source_id: str, file: UploadFile = File(...)):
    source = find_source(source_id)

    if not source:
        raise HTTPException(
            status_code=404,
            detail="Source not found"
        )

    if any(j["source_id"] == source_id for j in extraction_jobs):
        raise HTTPException(409, "This source already has interpretation history. Add a new source for a replacement file.")
    file_extension = get_file_extension(file.filename or "")

    if file_extension not in ALLOWED_FILE_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type. Allowed types: {sorted(ALLOWED_FILE_EXTENSIONS)}"
        )

    _artifact_store.create_directory(UPLOAD_FOLDER)

    safe_file_name = f"{source_id}{file_extension}"
    file_path = UPLOAD_FOLDER / safe_file_name

    old_paths = [Path(source[key]).resolve() for key in ("file_path", "extracted_text_path", "chunks_path") if source.get(key)]
    if any(not path.is_relative_to(STORAGE_ROOT) for path in old_paths):
        raise HTTPException(409, "Move this source's legacy files into private storage before replacing its upload.")

    temporary = file_path.with_suffix(file_path.suffix + ".tmp")
    size = 0
    try:
        with _artifact_store.open_binary_write(temporary) as buffer:
            while data := file.file.read(1024 * 1024):
                size += len(data)
                if size > 25 * 1024 * 1024:
                    raise HTTPException(413, "Upload limit is 25 MB.")
                buffer.write(data)
        if not size:
            raise HTTPException(400, "The uploaded file is empty.")
        _artifact_store.replace(temporary, file_path)
    finally:
        _artifact_store.remove(temporary)

    for old_path in old_paths:
        if old_path != file_path.resolve():
            _artifact_store.remove(old_path)

    source["file_name"] = file.filename
    source["file_path"] = str(file_path)
    source["file_type"] = file_extension
    source["processing_status"] = "uploaded"
    source["extracted_text_path"] = None
    source["chunks_path"] = None
    source["structure_status"] = None
    source["structure_section_count"] = 0
    source["structure_outline_entry_count"] = 0
    persist_state()

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

    if not _artifact_store.exists(path):
        raise HTTPException(
            status_code=404,
            detail="Uploaded file not found on disk."
        )

    return ArtifactFileResponse(
        path=path,
        store=_artifact_store,
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

    if source.get("chunks_path"):
        raise HTTPException(409, "Chunks already exist; add a new source for changed content.")
    file_path = source.get("file_path")
    file_type = source.get("file_type")

    if not file_path or not file_type:
        raise HTTPException(
            status_code=400,
            detail="Upload a source file before extracting text."
        )

    try:
        with _artifact_store.materialize(Path(file_path)) as local_path:
            extracted_text = extract_text_from_file(
                file_path=str(local_path),
                file_type=file_type
            )
    except Exception as error:
        source["processing_status"] = "extraction_not_supported"
        persist_state()

        raise HTTPException(
            status_code=400,
            detail=str(error)
        )

    if not extracted_text.strip():
        source["processing_status"] = "extraction_failed"
        persist_state()
        raise HTTPException(400, "No readable text found in the file.")
    extracted_text_path = save_extracted_text(
        source_id=source_id,
        text=extracted_text
    )

    source["extracted_text_path"] = extracted_text_path
    source["processing_status"] = "text_extracted"
    persist_state()

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

    if source.get("chunks_path"):
        return {"source_id":source_id,"chunk_count":len(load_chunks(source["chunks_path"])),"processing_status":source["processing_status"],"message":"Existing chunks preserved."}
    extracted_text = path.read_text(encoding="utf-8", errors="ignore")
    chunks = chunk_text(
        source_id=source_id,
        text=extracted_text
    )

    structure_summary = None
    if source.get("file_type") == ".pdf" and source.get("file_path"):
        try:
            with _artifact_store.materialize(Path(source["file_path"])) as local_path:
                chunks, structure_summary = annotate_pdf_chunks_with_outline(str(local_path), chunks)
        except Exception:
            # Text extraction/chunking should still succeed when a PDF has no
            # usable outline or its bookmark metadata is malformed.
            structure_summary = None

    chunks_path = save_chunks(
        source_id=source_id,
        chunks=chunks
    )

    source["chunks_path"] = chunks_path
    source["processing_status"] = "chunked"
    if structure_summary is not None:
        source["structure_status"] = (
            "pdf_outline_recovered" if structure_summary["outline_entry_count"] else "no_pdf_outline"
        )
        source["structure_section_count"] = structure_summary["section_count"]
        source["structure_outline_entry_count"] = structure_summary["outline_entry_count"]
    persist_state()

    return {
        "source_id": source["id"],
        "title": source["title"],
        "processing_status": source["processing_status"],
        "chunks_path": source["chunks_path"],
        "chunk_count": len(chunks),
        "structure": structure_summary,
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

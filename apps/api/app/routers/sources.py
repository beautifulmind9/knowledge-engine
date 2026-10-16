from pathlib import Path
from shutil import copyfileobj

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from typing import Literal
from datetime import datetime, timezone

from app.db.mock_data import (
    create_id,
    extraction_jobs,
    knowledge_assets,
    libraries,
    sources,
)
from app.db.persistence import StateMutationConflict, save_state
from app.persistence.factory import get_artifact_store
from app.persistence.supabase_artifacts import HostedArtifactStoreError
from app.persistence.artifact_paths import contained_locator, upload_locator, cleanup_unpublished_or_superseded
from app.responses import ArtifactFileResponse
from app.services.text_extraction import (
    UnsupportedExtractionTypeError,
    OCRRequiredError,
    extract_text_from_file,
    save_extracted_text
)
from app.services.text_chunking import chunk_text, load_chunks, save_chunks
from app.services.source_structure import annotate_pdf_chunks_with_outline
from app.services.source_identity import resolve_identity
from app.services.chunk_manifest import manifest_from_chunks
from app.services.performance_timing import start as timing_start, emit as timing_emit, utf8_size

from app.models.source_summary import SourceSummary
from app.services.source_summary import source_summaries, source_file_replacement_allowed

router = APIRouter(prefix="/sources", tags=["sources"])

from app.db.persistence import STORAGE_ROOT

UPLOAD_FOLDER = STORAGE_ROOT / "uploads"
MAX_SOURCE_UPLOAD_BYTES = 50_000_000
_artifact_store = get_artifact_store()

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
    # Existing callers remain user-confirmed by default. Material-first Add
    # marks untouched filename suggestions explicitly as provisional.
    title_origin: Literal["filename", "user_confirmed"] = "user_confirmed"
    author_origin: Literal["unconfirmed", "user_confirmed"] = "user_confirmed"


class SourceIdentityUpdate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    author: str | None = Field(default=None, max_length=500)


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
    if not chunks_path or not _artifact_store.exists(Path(chunks_path)):
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
    # PDF outline annotation may enrich chunks but must retain the exact chunk
    # identity set used by progress and recovery calculations.
    source["chunk_manifest"] = manifest_from_chunks(source["id"], chunks)
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


@router.get("/summaries", response_model=list[SourceSummary])
def get_source_summaries(library_id: str | None = None):
    started = timing_start()
    try:
        result = source_summaries(library_id=library_id)
        timing_emit("library_source_summaries", started, source_count=len(result))
        return result
    except Exception:
        timing_emit("library_source_summaries", started, result="error")
        raise


@router.get("/{source_id}/summary", response_model=SourceSummary)
def get_source_summary(source_id: str):
    started = timing_start()
    try:
        result = source_summaries(source_id=source_id)[0]
        timing_emit("source_summary", started, source_id=source_id)
        return result
    except Exception:
        timing_emit("source_summary", started, result="error", source_id=source_id)
        raise


@router.post("")
def create_source(payload: SourceCreate):
    started = timing_start()
    if not any(l["id"] == payload.library_id for l in libraries):
        raise HTTPException(404, "Library not found.")
    source = {
        "id": create_id("source"),
        "library_id": payload.library_id,
        "title": payload.title,
        "author": payload.author or "",
        "title_origin": payload.title_origin,
        "author_origin": "user_confirmed" if (payload.author or "").strip() else payload.author_origin,
        "identity_conflict": False,
        "source_type": payload.source_type,
        "processing_status": "not_started",
        "file_name": None,
        "file_path": None,
        "file_type": None,
        "extracted_text_path": None,
        "chunks_path": None,
        "chunk_manifest": None,
        "created_at": datetime.now(timezone.utc).isoformat()
    }

    sources.append(source)
    persist_state()

    timing_emit("source_create", started, source_id=source["id"], source_count=len(sources))
    return source


@router.put("/{source_id}/identity")
def update_source_identity(source_id: str, payload: SourceIdentityUpdate):
    source = find_source(source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    if not payload.title.strip():
        raise HTTPException(status_code=422, detail="A material title is required.")
    source["title"] = payload.title.strip()
    source["author"] = (payload.author or "").strip()
    source["title_origin"] = "user_confirmed"
    # Saving the optional field also confirms that blank authorship should stay
    # blank; it must not be repopulated by a later deterministic read.
    source["author_origin"] = "user_confirmed"
    source["identity_conflict"] = False
    persist_state()
    return {"id": source["id"], "title": source["title"], "author": source["author"],
            "title_origin": source["title_origin"], "author_origin": source["author_origin"]}


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
    try:
        return chunk_source_text(source_id)
    except Exception as error:
        source["reading_failure"] = "read_failed"
        persist_state()
        raise HTTPException(400, "The file was uploaded, but reading could not finish. Your material and original file are saved; retry reading or choose another supported file.") from error


@router.post("/{source_id}/recover-structure")
def recover_source_structure(source_id: str):
    source = find_source(source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    return _recover_pdf_structure(source)


def _write_source_upload(file: UploadFile, path: Path) -> None:
    started = timing_start()
    size = 0
    try:
        with _artifact_store.open_binary_write(path) as buffer:
            while data := file.file.read(1024 * 1024):
                size += len(data)
                if size > MAX_SOURCE_UPLOAD_BYTES:
                    raise HTTPException(413, "Upload limit is 50 MB (50,000,000 bytes) per file.")
                buffer.write(data)
            if not size:
                raise HTTPException(400, "The uploaded file is empty.")
        timing_emit("artifact_write", started, source_id=path.stem, destination_category="artifact",
                    operation_category="source_upload", file_size_bytes=size)
    except Exception as error:
        timing_emit("artifact_write", started, result="upload_rejected" if isinstance(error, HTTPException) else "error",
                    source_id=path.stem, destination_category="artifact",
                    operation_category="source_upload", file_size_bytes=size)
        raise


@router.post("/{source_id}/upload")
def upload_source_file(source_id: str, file: UploadFile = File(...)):
    started = timing_start()
    source = find_source(source_id)

    if not source:
        raise HTTPException(
            status_code=404,
            detail="Source not found"
        )

    if not source_file_replacement_allowed(source_id):
        raise HTTPException(409, "This source already has interpretation history. Add a new source for a replacement file.")
    file_extension = get_file_extension(file.filename or "")

    if file_extension not in ALLOWED_FILE_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Unsupported file type. Choose PDF, EPUB, Word, TXT, Markdown, HTML, CSV or JSON."
        )

    _artifact_store.create_directory(UPLOAD_FOLDER)

    safe_file_name = f"{source_id}{file_extension}"
    stable_path = UPLOAD_FOLDER / safe_file_name
    file_path = upload_locator(_artifact_store, stable_path)

    try:
        old_paths = [contained_locator(_artifact_store, Path(source[key]), STORAGE_ROOT) for key in ("file_path", "extracted_text_path", "chunks_path") if source.get(key)]
    except ValueError:
        raise HTTPException(409, "Move this source's legacy files into private storage before replacing its upload.")

    updated_fields = dict(
        file_name=file.filename, file_path=str(file_path), file_type=file_extension,
        processing_status="uploaded", extracted_text_path=None, chunks_path=None,
        chunk_manifest=None,
        reading_failure=None, stopped_reason=None,
        structure_status=None, structure_section_count=0, structure_outline_entry_count=0,
    )
    if file_path != stable_path:
        # Write directly to a fresh locator. A lost response can affect only this
        # unpublished candidate, never the bytes referenced by the current source.
        try:
            _write_source_upload(file, file_path)
        except HostedArtifactStoreError:
            cleanup_unpublished_or_superseded(_artifact_store, [file_path])
            raise HTTPException(503, "The file could not be uploaded right now. Your material record is saved; try uploading again.") from None
        except Exception:
            cleanup_unpublished_or_superseded(_artifact_store, [file_path])
            raise
        previous = dict(source)
        source.update(updated_fields)
        try:
            persist_state()
        except Exception as error:
            if isinstance(error, StateMutationConflict):
                raise
            source.clear()
            source.update(previous)
            # A state commit may have succeeded before its response was lost.
            # Keep BOTH versions and derived files until state is reloaded.
            raise
        cleanup_unpublished_or_superseded(_artifact_store, old_paths)
    else:
        # Preserve legacy local filenames, replace ordering, and failure behavior.
        temporary = file_path.with_suffix(file_path.suffix + ".tmp")
        try:
            _write_source_upload(file, temporary)
            _artifact_store.replace(temporary, file_path)
        finally:
            _artifact_store.remove(temporary)
        for old_path in old_paths:
            if old_path != contained_locator(_artifact_store, file_path, STORAGE_ROOT):
                _artifact_store.remove(old_path)
        source.update(updated_fields)
        persist_state()

    timing_emit("source_upload", started, source_id=source_id,
                file_size_bytes=getattr(file, "size", None), receipt_boundary="handler_entry_to_response")
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
    started = timing_start()
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

    identity = None
    extraction_started = timing_start()
    try:
        with _artifact_store.materialize(Path(file_path)) as local_path:
            extracted_text = extract_text_from_file(
                file_path=str(local_path),
                file_type=file_type
            )
            identity = resolve_identity(local_path, file_type, extracted_text)
            timing_emit("text_extraction", extraction_started, source_id=source_id,
                        extracted_character_count=len(extracted_text))
    except Exception as error:
        category = "ocr_required" if isinstance(error, OCRRequiredError) else "unsupported_extraction" if isinstance(error, UnsupportedExtractionTypeError) else "read_failed"
        timing_emit("text_extraction", extraction_started, result=category, source_id=source_id)
        source["reading_failure"] = category
        source["processing_status"] = "extraction_not_supported" if category != "read_failed" else "extraction_failed"
        persist_state()
        from app.services.source_summary import MESSAGES
        raise HTTPException(400, MESSAGES[category]) from error

    if not extracted_text.strip():
        source["processing_status"] = "extraction_failed"
        source["reading_failure"] = "read_failed"
        persist_state()
        raise HTTPException(400, "No readable text found in the file.")
    write_started = timing_start()
    extracted_text_path = save_extracted_text(
        source_id=source_id,
        text=extracted_text
    )
    timing_emit("artifact_write", write_started, source_id=source_id, destination_category="artifact",
                operation_category="extracted_text", file_size_bytes=utf8_size(extracted_text))

    source["extracted_text_path"] = extracted_text_path
    # Legacy sources without origins are treated as user-owned. New Add flows
    # explicitly mark filename suggestions and blank authors as provisional.
    if identity and source.get("title_origin") == "filename" and identity.get("title"):
        source["title"] = identity["title"]
        source["title_origin"] = identity["title_origin"]
    if identity and source.get("author_origin") == "unconfirmed" and identity.get("author"):
        source["author"] = identity["author"]
        source["author_origin"] = identity["author_origin"]
    if identity and source.get("title_origin") in {"material_text", "document_metadata"}:
        source["identity_conflict"] = identity.get("title_conflict", False)
    source["reading_failure"] = None
    source["processing_status"] = "text_extracted"
    persist_state()

    timing_emit("source_extract_request", started, source_id=source_id,
                extracted_character_count=len(extracted_text))
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

    if not _artifact_store.exists(path):
        raise HTTPException(
            status_code=404,
            detail="Extracted text file not found on disk."
        )

    return _artifact_store.read_text(path, errors="ignore")


@router.post("/{source_id}/chunk")
def chunk_source_text(source_id: str):
    started = timing_start()
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

    if not _artifact_store.exists(path):
        raise HTTPException(
            status_code=404,
            detail="Extracted text file not found on disk."
        )

    if source.get("chunks_path"):
        return {"source_id":source_id,"chunk_count":len(load_chunks(source["chunks_path"])),"processing_status":source["processing_status"],"message":"Existing chunks preserved."}
    extracted_text = _artifact_store.read_text(path, errors="ignore")
    chunk_started = timing_start()
    chunks = chunk_text(
        source_id=source_id,
        text=extracted_text
    )
    timing_emit("chunk_construction", chunk_started, source_id=source_id, chunk_count=len(chunks),
                extracted_character_count=len(extracted_text))

    structure_summary = None
    if source.get("file_type") == ".pdf" and source.get("file_path"):
        try:
            with _artifact_store.materialize(Path(source["file_path"])) as local_path:
                chunks, structure_summary = annotate_pdf_chunks_with_outline(str(local_path), chunks)
        except Exception:
            # Text extraction/chunking should still succeed when a PDF has no
            # usable outline or its bookmark metadata is malformed.
            structure_summary = None

    write_started = timing_start()
    chunks_path = save_chunks(
        source_id=source_id,
        chunks=chunks
    )
    timing_emit("artifact_publication", write_started, source_id=source_id, destination_category="artifact",
                operation_category="chunks", chunk_count=len(chunks))

    source_fields = ("chunks_path", "chunk_manifest", "reading_failure", "processing_status",
                     "structure_status", "structure_section_count", "structure_outline_entry_count")
    previous_state = {key: source.get(key) for key in source_fields}
    source["chunks_path"] = chunks_path
    source["chunk_manifest"] = manifest_from_chunks(source_id, chunks)
    source["reading_failure"] = None
    source["processing_status"] = "chunked"
    if structure_summary is not None:
        source["structure_status"] = (
            "pdf_outline_recovered" if structure_summary["outline_entry_count"] else "no_pdf_outline"
        )
        source["structure_section_count"] = structure_summary["section_count"]
        source["structure_outline_entry_count"] = structure_summary["outline_entry_count"]
    # The artifact has been safely published, but the source reference and its
    # manifest become visible together at this durable snapshot boundary.
    try:
        persist_state()
    except StateMutationConflict:
        # Persistence has reconciled the live collections to the latest durable
        # state. Do not write the stale pre-checkpoint values back into it.
        raise
    except Exception:
        for key, value in previous_state.items():
            if value is None:
                source.pop(key, None)
            else:
                source[key] = value
        raise

    timing_emit("source_chunk_request", started, source_id=source_id, chunk_count=len(chunks))
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

    if not _artifact_store.exists(path):
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

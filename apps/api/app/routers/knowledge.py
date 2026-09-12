from fastapi import APIRouter, HTTPException, Query

from app.models.knowledge_extraction import (
    KnowledgeExtractionRequest,
    KnowledgeExtractionResultSubmission,
)
from app.services.knowledge_extraction import (
    complete_extraction_job,
    create_extraction_job,
    get_extraction_chunk,
    get_extraction_job,
    get_extraction_request,
    list_knowledge_assets,
)
from app.services.gemini_knowledge_extraction import run_gemini_knowledge_extraction
from app.services.source_interpretation import (
    get_source_interpretation_summary,
    interpret_source,
)

router = APIRouter(tags=["knowledge"])


def service_error(error: ValueError):
    message = str(error)
    status_code = 404 if "not found" in message.lower() else 400
    raise HTTPException(status_code=status_code, detail=message)


@router.post("/knowledge-extractions")
def start_knowledge_extraction(payload: KnowledgeExtractionRequest):
    try:
        job = create_extraction_job(
            source_id=payload.source_id,
            chunk_id=payload.chunk_id,
        )
    except ValueError as error:
        service_error(error)

    return {
        "job": job,
        "message": "Knowledge extraction job created. It is ready for the AI extraction step.",
    }


@router.get("/knowledge-extractions/{job_id}")
def read_knowledge_extraction(job_id: str):
    try:
        return get_extraction_job(job_id)
    except ValueError as error:
        service_error(error)


@router.get("/knowledge-extractions/{job_id}/chunk")
def read_knowledge_extraction_chunk(job_id: str):
    try:
        return get_extraction_chunk(job_id)
    except ValueError as error:
        service_error(error)


@router.get("/knowledge-extractions/{job_id}/request")
def read_knowledge_extraction_request(job_id: str):
    try:
        return get_extraction_request(job_id)
    except ValueError as error:
        service_error(error)


@router.post("/knowledge-extractions/{job_id}/run")
def run_knowledge_extraction(job_id: str):
    try:
        result = run_gemini_knowledge_extraction(job_id)
    except ValueError as error:
        service_error(error)
    except RuntimeError as error:
        raise HTTPException(status_code=400, detail=str(error))
    except Exception as error:
        raise HTTPException(
            status_code=502,
            detail=f"AI extraction failed: {error}",
        )

    return {
        **result,
        "message": "AI extraction completed and knowledge assets were stored.",
    }


@router.post("/knowledge-extractions/{job_id}/results")
def submit_knowledge_extraction_results(
    job_id: str,
    payload: KnowledgeExtractionResultSubmission,
):
    try:
        result = complete_extraction_job(
            job_id=job_id,
            assets=payload.assets,
        )
    except ValueError as error:
        service_error(error)

    return {
        **result,
        "message": "Knowledge assets validated and stored successfully.",
    }


@router.get("/knowledge-assets")
def read_knowledge_assets(
    source_id: str | None = None,
    chunk_id: str | None = None,
    asset_type: str | None = None,
):
    items = list_knowledge_assets(
        source_id=source_id,
        chunk_id=chunk_id,
        asset_type=asset_type,
    )

    return {
        "items": items,
        "count": len(items),
    }


@router.get("/sources/{source_id}/interpretation")
def read_source_interpretation(source_id: str):
    try:
        return get_source_interpretation_summary(source_id)
    except ValueError as error:
        service_error(error)


@router.post("/sources/{source_id}/interpret")
def interpret_source_knowledge(
    source_id: str,
    max_chunks: int = Query(
        default=1,
        ge=1,
        le=5,
        description=(
            "Maximum number of source chunks to interpret in this run. "
            "Small batches protect the free AI quota and make the workflow resumable."
        ),
    ),
):
    try:
        result = interpret_source(
            source_id=source_id,
            max_chunks=max_chunks,
        )
    except ValueError as error:
        service_error(error)

    return {
        **result,
        "message": (
            "Source interpretation run finished. Call this endpoint again later "
            "if chunks remain."
        ),
    }


@router.get("/sources/{source_id}/knowledge-assets")
def read_source_knowledge_assets(
    source_id: str,
    asset_type: str | None = None,
):
    items = list_knowledge_assets(
        source_id=source_id,
        asset_type=asset_type,
    )

    return {
        "source_id": source_id,
        "items": items,
        "count": len(items),
    }

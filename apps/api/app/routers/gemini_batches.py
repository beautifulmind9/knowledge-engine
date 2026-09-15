from fastapi import APIRouter, HTTPException

from app.services.gemini_source_batch import (
    refresh_source_batch,
    submit_source_batch,
)


router = APIRouter(tags=["knowledge"])


def _service_error(error: ValueError):
    message = str(error)
    status_code = 404 if "not found" in message.lower() else 400
    raise HTTPException(status_code=status_code, detail=message)


@router.post("/sources/{source_id}/interpret-batch")
def submit_source_interpretation_batch(source_id: str):
    """Submit unfinished chunks as independent asynchronous Gemini requests."""
    try:
        return submit_source_batch(source_id)
    except ValueError as error:
        _service_error(error)


@router.post("/sources/{source_id}/interpret-batch/refresh")
def refresh_source_interpretation_batch(source_id: str):
    """Perform one explicit status check and collect results if finished."""
    try:
        return refresh_source_batch(source_id)
    except ValueError as error:
        _service_error(error)

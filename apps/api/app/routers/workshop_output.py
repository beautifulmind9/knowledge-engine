import json
import logging
import os
from fastapi import APIRouter, HTTPException, Request

from app.models.workshop_generation import WorkshopGenerateRequest
from app.services.workshop_generation import DEFAULT_MODEL, GroundedAnswerValidationError, generate_workshop_output

router = APIRouter(prefix="/workshops", tags=["workshops"])
logger = logging.getLogger(__name__)


@router.post("/generate")
def generate_workshop(payload: WorkshopGenerateRequest, request: Request):
    try:
        result = generate_workshop_output(payload)
    except GroundedAnswerValidationError as error:
        logger.warning("Workshop answer rejected after provider success: %s", json.dumps({
            "request_id": getattr(request.state, "request_id", None),
            "validation_category": error.category,
            "model": os.getenv("GEMINI_MODEL", DEFAULT_MODEL),
            "result": "rejected_after_provider_success",
        }, sort_keys=True))
        raise HTTPException(502, "The AI response could not be validated. No answer was saved.") from error
    if payload.save:
        from app.services.outputs import save_output
        result["saved_output"] = save_output(result)
    return {
        **result,
        "message": ("Workshop draft has timing errors or unverified guidance. Review quality_report before use."
                    if result["quality_report"]["validation_status"] in {"failed", "needs_review"}
                    else "Output generated from retrieved knowledge. Human review is still required."),
    }

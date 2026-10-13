from fastapi import APIRouter, HTTPException

from app.models.workshop_generation import WorkshopGenerateRequest
from app.services.workshop_generation import GroundedAnswerValidationError, generate_workshop_output

router = APIRouter(prefix="/workshops", tags=["workshops"])


@router.post("/generate")
def generate_workshop(payload: WorkshopGenerateRequest):
    try:
        result = generate_workshop_output(payload)
    except GroundedAnswerValidationError as error:
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

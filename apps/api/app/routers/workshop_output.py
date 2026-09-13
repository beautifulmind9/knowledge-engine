from fastapi import APIRouter

from app.models.workshop_generation import WorkshopGenerateRequest
from app.services.workshop_generation import generate_workshop_output

router = APIRouter(prefix="/workshops", tags=["workshops"])


@router.post("/generate")
def generate_workshop(payload: WorkshopGenerateRequest):
    result = generate_workshop_output(payload)
    if payload.save:
        from app.services.outputs import save_output
        result["saved_output"] = save_output(result)
    return {
        **result,
        "message": ("Workshop draft has timing errors or unverified guidance. Review quality_report before use."
                    if result["quality_report"]["validation_status"] in {"failed", "needs_review"}
                    else "Output generated from retrieved knowledge. Human review is still required."),
    }

import json
import os

from google import genai
from pydantic import ValidationError

from app.models.knowledge_extraction import KnowledgeExtractionResultSubmission
from app.services.generated_content_integrity import ExtractionValidationError
from app.services.knowledge_extraction import (
    complete_extraction_job,
    get_extraction_request,
    mark_extraction_job_failed,
    mark_extraction_job_running,
    find_source,
    persist_interpretation_checkpoint,
)
from app.services.performance_timing import start as timing_start, emit as timing_emit, utf8_size


# Flash-Lite is a better fit for our current workload: short, structured
# extraction jobs where we want to stay within a free development setup.
DEFAULT_MODEL = "gemini-3.5-flash-lite"


def generate_structured_interaction(client, model: str, request: dict, payload: dict):
    from app.services.ai_gateway import generate
    return generate(model, payload, request["expected_output_schema"])


def _validation_summary(error: ValidationError, limit: int = 8) -> str:
    """Return useful schema diagnostics without persisting generated/source text."""
    details = error.errors(
        include_url=False,
        include_context=False,
        include_input=False,
    )
    parts = []
    for detail in details[:limit]:
        location = ".".join(str(part) for part in detail.get("loc", ())) or "result"
        parts.append(
            f"{location}: {detail.get('msg', 'validation error')} "
            f"[{detail.get('type', 'unknown')}]"
        )
    if len(details) > limit:
        parts.append(f"... plus {len(details) - limit} more validation error(s)")
    return "; ".join(parts) or "unknown schema validation error"


def validate_extraction_result(client, model: str, request: dict, interaction):
    started = timing_start()
    output_text = interaction.output_text
    if not output_text:
        raise RuntimeError("The AI returned no structured extraction output.")

    try:
        result = KnowledgeExtractionResultSubmission.model_validate_json(
            output_text
        )
        timing_emit("provider_response_adaptation_validation", started, source_id=request.get("source_id"),
                    chunk_id=request.get("chunk_id"), result="valid",
                    provider_response_utf8_bytes=utf8_size(output_text))
        return result, interaction
    except ValidationError as validation_error:
        timing_emit("provider_response_adaptation_validation", started, source_id=request.get("source_id"),
                    chunk_id=request.get("chunk_id"), result="invalid")
        validation_summary = _validation_summary(validation_error)
        raise ExtractionValidationError(
            "AI output failed validation: "
            f"{validation_summary}. No assets saved. "
            "Automatic repair is disabled; retry explicitly."
        ) from validation_error


def run_gemini_knowledge_extraction(job_id: str, *, coalesce_interpretation: bool = False,
                                   rollback_state=None, on_checkpoint=None,
                                   chunk_context=None):
    from app.services import partition_authority as authority
    initial_authority=bool(authority.coordinator())
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is not configured. Add a Gemini API key before running AI extraction."
        )

    model = os.getenv("GEMINI_MODEL", DEFAULT_MODEL)
    request = get_extraction_request(job_id, chunk_context=chunk_context)

    mark_extraction_job_running(
        job_id=job_id,
        provider="gemini",
        model=model,
        persist=not coalesce_interpretation,
    )

    if coalesce_interpretation:
        source = find_source(request["source_id"])
        source["processing_status"] = "knowledge_interpreting"
        source["stopped_reason"] = None
        durable_state = persist_interpretation_checkpoint(rollback_state)
        if on_checkpoint:
            on_checkpoint(durable_state)

    client = None

    model_input = {
        "instructions": request["instructions"],
        "source_id": request["source_id"],
        "chunk_id": request["chunk_id"],
        "chunk_text": request["chunk_text"],
    }

    if bool(authority.coordinator())!=initial_authority:
        from app.db.persistence import StateMutationConflict
        raise StateMutationConflict('Persistence authority changed before provider dispatch.')

    try:
        interaction = generate_structured_interaction(
            client=client,
            model=model,
            request=request,
            payload=model_input,
        )

        result, final_interaction = validate_extraction_result(
            client=client,
            model=model,
            request=request,
            interaction=interaction,
        )

        # Provenance and system metadata belong to Knowledge Engine, not the model.
        for asset in result.assets:
            asset.id = None
            asset.created_at = None
            asset.source_id = request["source_id"]
            asset.chunk_id = request["chunk_id"]

        return complete_extraction_job(
            job_id=job_id,
            assets=result.assets,
            model_response_id=getattr(final_interaction, "id", None),
            persist=not coalesce_interpretation,
            update_source=not coalesce_interpretation,
            chunk_context=chunk_context,
            generated_content=True,
        )

    except Exception as error:
        mark_extraction_job_failed(job_id=job_id, error=str(error),
                                   persist=not coalesce_interpretation)
        raise

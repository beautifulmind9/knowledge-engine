import json
import os

from google import genai
from pydantic import ValidationError

from app.models.knowledge_extraction import KnowledgeExtractionResultSubmission
from app.services.knowledge_extraction import (
    complete_extraction_job,
    get_extraction_request,
    mark_extraction_job_failed,
    mark_extraction_job_running,
)


# Flash-Lite is a better fit for our current workload: short, structured
# extraction jobs where we want to stay within a free development setup.
DEFAULT_MODEL = "gemini-3.1-flash-lite"


def generate_structured_interaction(client, model: str, request: dict, payload: dict):
    return client.interactions.create(
        model=model,
        input=json.dumps(payload, ensure_ascii=False),
        response_format={
            "type": "text",
            "mime_type": "application/json",
            "schema": request["expected_output_schema"],
        },
    )


def validate_or_repair_result(client, model: str, request: dict, interaction):
    if not interaction.output_text:
        raise RuntimeError("The AI returned no structured extraction output.")

    try:
        result = KnowledgeExtractionResultSubmission.model_validate_json(
            interaction.output_text
        )
        return result, interaction
    except ValidationError as validation_error:
        repair_payload = {
            "task": "Repair the previous knowledge extraction so it passes validation.",
            "rules": [
                "Use only information supported by the original chunk.",
                "Do not invent missing facts just to satisfy validation.",
                "If an asset cannot satisfy the rules from the source, change it to a better-fitting asset type or remove it.",
                "Every retained asset must include short source-grounded evidence and grounded keywords.",
                "For decision_rule assets, action must be a concrete behavior or choice supported by the chunk.",
                "Do not turn book scope, author credentials, publication details, or other source metadata into decision rules.",
                "For process assets, steps must contain at least one source-supported step.",
                "Return only the corrected structured result.",
            ],
            "validation_error": str(validation_error),
            "previous_output": interaction.output_text,
            "source_id": request["source_id"],
            "chunk_id": request["chunk_id"],
            "chunk_text": request["chunk_text"],
        }

        repaired_interaction = generate_structured_interaction(
            client=client,
            model=model,
            request=request,
            payload=repair_payload,
        )

        if not repaired_interaction.output_text:
            raise RuntimeError("The AI repair attempt returned no structured output.")

        repaired_result = KnowledgeExtractionResultSubmission.model_validate_json(
            repaired_interaction.output_text
        )
        return repaired_result, repaired_interaction


def run_gemini_knowledge_extraction(job_id: str):
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is not configured. Add a Gemini API key before running AI extraction."
        )

    model = os.getenv("GEMINI_MODEL", DEFAULT_MODEL)
    request = get_extraction_request(job_id)

    mark_extraction_job_running(
        job_id=job_id,
        provider="gemini",
        model=model,
    )

    client = genai.Client(api_key=api_key)

    model_input = {
        "instructions": request["instructions"],
        "source_id": request["source_id"],
        "chunk_id": request["chunk_id"],
        "chunk_text": request["chunk_text"],
    }

    try:
        interaction = generate_structured_interaction(
            client=client,
            model=model,
            request=request,
            payload=model_input,
        )

        result, final_interaction = validate_or_repair_result(
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
        )

    except Exception as error:
        mark_extraction_job_failed(job_id=job_id, error=str(error))
        raise

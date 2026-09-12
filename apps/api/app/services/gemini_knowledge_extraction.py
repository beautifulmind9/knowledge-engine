import json
import os

from google import genai

from app.models.knowledge_extraction import KnowledgeExtractionResultSubmission
from app.services.knowledge_extraction import (
    complete_extraction_job,
    get_extraction_request,
    mark_extraction_job_failed,
    mark_extraction_job_running,
)


DEFAULT_MODEL = "gemini-3.8-flash"


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
        interaction = client.interactions.create(
            model=model,
            input=json.dumps(model_input, ensure_ascii=False),
            response_format={
                "type": "text",
                "mime_type": "application/json",
                "schema": request["expected_output_schema"],
            },
        )

        if not interaction.output_text:
            raise RuntimeError("The AI returned no structured extraction output.")

        result = KnowledgeExtractionResultSubmission.model_validate_json(
            interaction.output_text
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
            model_response_id=getattr(interaction, "id", None),
        )

    except Exception as error:
        mark_extraction_job_failed(job_id=job_id, error=str(error))
        raise

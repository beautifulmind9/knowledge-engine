import json
import os

from openai import OpenAI

from app.models.knowledge_extraction import KnowledgeExtractionResultSubmission
from app.services.knowledge_extraction import (
    complete_extraction_job,
    get_extraction_request,
    mark_extraction_job_failed,
    mark_extraction_job_running,
)


DEFAULT_MODEL = "gpt-5.6-terra"


def run_openai_knowledge_extraction(job_id: str):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not configured. Add it to the Codespace environment before running AI extraction."
        )

    model = os.getenv("OPENAI_MODEL", DEFAULT_MODEL)
    request = get_extraction_request(job_id)

    mark_extraction_job_running(
        job_id=job_id,
        provider="openai",
        model=model,
    )

    client = OpenAI(api_key=api_key)

    model_input = {
        "source_id": request["source_id"],
        "chunk_id": request["chunk_id"],
        "chunk_text": request["chunk_text"],
    }

    try:
        response = client.responses.create(
            model=model,
            instructions=request["instructions"],
            input=json.dumps(model_input, ensure_ascii=False),
            text={
                "format": {
                    "type": "json_schema",
                    "name": "knowledge_extraction_result",
                    "description": "Reusable knowledge assets extracted from one source chunk.",
                    "schema": request["expected_output_schema"],
                    "strict": False,
                }
            },
        )

        if not response.output_text:
            raise RuntimeError("The AI returned no structured extraction output.")

        result = KnowledgeExtractionResultSubmission.model_validate_json(
            response.output_text
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
            model_response_id=response.id,
        )

    except Exception as error:
        mark_extraction_job_failed(job_id=job_id, error=str(error))
        raise

"""Whole-source extraction through Gemini Batch API.

Each source chunk is a separate GenerateContent request. Chunks never share a
model context, so batching provides throughput without weakening source
boundaries. Results are still validated independently against Knowledge
Engine's strict internal asset models before any replacement is committed.
"""
import json
import os
from datetime import datetime, timezone

from google.genai import types
from pydantic import ValidationError

from app.db.mock_data import extraction_jobs
from app.models.knowledge_extraction import (
    KnowledgeExtractionResultSubmission,
    gemini_batch_asset_schema,
)
from app.services import ai_gateway
from app.services.gemini_batch_gateway import (
    get_generate_content_batch,
    submit_generate_content_batch,
)
from app.services.gemini_knowledge_extraction import DEFAULT_MODEL, _validation_summary
from app.services.knowledge_extraction import (
    complete_extraction_job,
    create_extraction_job,
    get_extraction_request,
    mark_extraction_job_failed,
    mark_extraction_job_running,
    persist_state,
)
from app.services.source_interpretation import (
    get_source_chunks,
    get_source_interpretation_summary,
)


# Google documents inline Batch requests as suitable below 20 MB. Keep a
# conservative margin for request/config serialization overhead.
MAX_INLINE_BATCH_BYTES = 18 * 1024 * 1024
TERMINAL_BATCH_STATES = {
    "JOB_STATE_SUCCEEDED",
    "JOB_STATE_FAILED",
    "JOB_STATE_CANCELLED",
    "JOB_STATE_EXPIRED",
}


BATCH_ITEM_RESPONSE_RULES = """
Batch-API item response rules (these override output-format/provenance rules only):
- This request contains exactly one source chunk. Use only this chunk_text.
- Return exactly one JSON object with one key: assets.
- assets must be an array, or [] only when the entire chunk has no reusable knowledge.
- Every candidate asset must include asset_type, title, what_it_says, evidence, keywords, and confidence_score.
- Do not omit what_it_says or evidence because subtype-specific fields are present.
- decision_rule requires action; process requires steps; framework requires components.
- Use only subtype-specific fields valid for the chosen asset_type.
- Do not emit id, created_at, source_id, or chunk_id inside assets. Knowledge Engine assigns system provenance locally.
- Scan the entire chunk before returning an empty assets array.
""".strip()


def _provider_response_schema():
    return {
        "type": "object",
        "properties": {
            "assets": {
                "type": "array",
                "items": gemini_batch_asset_schema(),
            }
        },
        "required": ["assets"],
    }


def _model_payload(request: dict):
    return {
        "instructions": request["instructions"] + "\n\n" + BATCH_ITEM_RESPONSE_RULES,
        "source_id": request["source_id"],
        "chunk_id": request["chunk_id"],
        "chunk_text": request["chunk_text"],
    }


def _inline_request(job: dict, request: dict):
    schema = ai_gateway._gemini_response_schema(_provider_response_schema())
    return types.InlinedRequest(
        contents=[
            {
                "role": "user",
                "parts": [
                    {
                        "text": json.dumps(
                            _model_payload(request),
                            ensure_ascii=False,
                        )
                    }
                ],
            }
        ],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=schema,
        ),
        metadata={
            "job_id": job["id"],
            "chunk_id": job["chunk_id"],
        },
    )


def _state_name(batch_job) -> str:
    state = getattr(batch_job, "state", None)
    name = getattr(state, "name", None)
    if isinstance(name, str):
        return name
    value = getattr(state, "value", None)
    if isinstance(value, str):
        return value
    return str(state) if state is not None else "JOB_STATE_UNSPECIFIED"


def _response_text(response) -> str:
    try:
        text = getattr(response, "text", None)
    except Exception:
        text = None
    if isinstance(text, str) and text.strip():
        return text

    parts = []
    for candidate in getattr(response, "candidates", None) or []:
        content = getattr(candidate, "content", None)
        for part in getattr(content, "parts", None) or []:
            value = getattr(part, "text", None)
            if isinstance(value, str) and value:
                parts.append(value)
    return "".join(parts)


def _completed_chunk_ids(source_id: str):
    return {
        job.get("chunk_id")
        for job in extraction_jobs
        if job.get("source_id") == source_id and job.get("status") == "completed"
    }


def _active_source_batch(source_id: str):
    running = [
        job
        for job in extraction_jobs
        if job.get("source_id") == source_id
        and job.get("status") == "running"
        and job.get("provider_batch_name")
    ]
    if not running:
        return None
    names = {job["provider_batch_name"] for job in running}
    if len(names) != 1:
        raise ValueError("Source has multiple active provider batches; recover them explicitly before submitting another.")
    name = next(iter(names))
    return name, [job for job in running if job["provider_batch_name"] == name]


def _latest_source_batch(source_id: str):
    for job in reversed(extraction_jobs):
        if job.get("source_id") == source_id and job.get("provider_batch_name"):
            name = job["provider_batch_name"]
            return name, [
                item
                for item in extraction_jobs
                if item.get("source_id") == source_id
                and item.get("provider_batch_name") == name
            ]
    return None


def submit_source_batch(source_id: str):
    """Submit all unfinished source chunks as independent inline batch requests."""
    source, chunks = get_source_chunks(source_id)
    if not chunks:
        raise ValueError("This source has no chunks to interpret.")

    active = _active_source_batch(source_id)
    if active:
        name, jobs = active
        return {
            "submitted": False,
            "provider_batch_name": name,
            "provider_batch_state": jobs[0].get("provider_batch_state") or "JOB_STATE_PENDING",
            "chunk_count": len(jobs),
            "message": "This source already has an active Gemini Batch job.",
        }

    unowned_running = [
        job
        for job in extraction_jobs
        if job.get("source_id") == source_id
        and job.get("status") == "running"
        and not job.get("provider_batch_name")
    ]
    if unowned_running:
        raise ValueError("A synchronous extraction is already running for this source. Recover or finish it before batch submission.")

    completed = _completed_chunk_ids(source_id)
    remaining = [chunk for chunk in chunks if chunk.get("id") not in completed]
    if not remaining:
        return {
            "submitted": False,
            "provider_batch_name": None,
            "provider_batch_state": "LOCAL_COMPLETED",
            "chunk_count": 0,
            "message": "All source chunks are already completed.",
        }

    # Check inline size before creating or changing extraction jobs.
    estimated_bytes = sum(
        len(
            json.dumps(
                _model_payload(
                    {
                        **__import__(
                            "app.services.knowledge_extraction_prompt",
                            fromlist=["build_knowledge_extraction_request"],
                        ).build_knowledge_extraction_request(chunk)
                    }
                ),
                ensure_ascii=False,
            ).encode("utf-8")
        )
        for chunk in remaining
    )
    if estimated_bytes > MAX_INLINE_BATCH_BYTES:
        raise ValueError(
            "Source is too large for one safe inline Gemini Batch request. Split it into multiple source batches before submission."
        )

    jobs = [
        create_extraction_job(source_id=source_id, chunk_id=chunk["id"])
        for chunk in remaining
    ]
    model = os.getenv("GEMINI_MODEL", DEFAULT_MODEL)
    requests = [get_extraction_request(job["id"]) for job in jobs]
    inline_requests = [
        _inline_request(job, request)
        for job, request in zip(jobs, requests)
    ]

    started = []
    try:
        for job in jobs:
            mark_extraction_job_running(job["id"], "gemini_batch", model)
            started.append(job["id"])
        display_name = (
            f"knowledge-engine-{source_id[-12:]}-"
            f"{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
        )
        batch_job = submit_generate_content_batch(
            model=model,
            inline_requests=inline_requests,
            display_name=display_name,
        )
        batch_name = getattr(batch_job, "name", None)
        if not isinstance(batch_name, str) or not batch_name:
            raise RuntimeError("Gemini Batch submission returned no provider batch name.")
        state = _state_name(batch_job)
        for job in jobs:
            job["provider_batch_name"] = batch_name
            job["provider_batch_state"] = state
        source["processing_status"] = "knowledge_interpreting"
        source["stopped_reason"] = None
        persist_state()
        return {
            "submitted": True,
            "provider_batch_name": batch_name,
            "provider_batch_state": state,
            "chunk_count": len(jobs),
            "estimated_inline_bytes": estimated_bytes,
            "message": "Gemini Batch job submitted. Refresh explicitly later to collect completed results.",
        }
    except Exception as error:
        detail = str(getattr(error, "detail", error))
        for job_id in started:
            mark_extraction_job_failed(job_id, detail)
        source["stopped_reason"] = "Batch submission failed; no prior active assets were superseded."
        persist_state()
        raise


def _fail_running_jobs(jobs: list[dict], message: str):
    for job in jobs:
        if job.get("status") == "running":
            mark_extraction_job_failed(job["id"], message)


def refresh_source_batch(source_id: str):
    """Retrieve one provider status snapshot and collect results if complete."""
    source, _ = get_source_chunks(source_id)
    selected = _active_source_batch(source_id) or _latest_source_batch(source_id)
    if not selected:
        raise ValueError("This source has no Gemini Batch job to refresh.")
    batch_name, jobs = selected

    if all(job.get("status") in {"completed", "failed"} for job in jobs):
        return {
            "provider_batch_name": batch_name,
            "provider_batch_state": jobs[0].get("provider_batch_state") or "LOCAL_FINALIZED",
            "collected": True,
            "results": [],
            "failures": [],
            "progress": get_source_interpretation_summary(source_id),
            "message": "This provider batch was already collected locally.",
        }

    batch_job = get_generate_content_batch(batch_name)
    state = _state_name(batch_job)
    for job in jobs:
        job["provider_batch_state"] = state
    persist_state()

    if state not in TERMINAL_BATCH_STATES:
        return {
            "provider_batch_name": batch_name,
            "provider_batch_state": state,
            "collected": False,
            "results": [],
            "failures": [],
            "progress": get_source_interpretation_summary(source_id),
            "message": "Gemini Batch job is not finished yet. Refresh explicitly later.",
        }

    if state != "JOB_STATE_SUCCEEDED":
        message = f"Gemini Batch ended with {state}; no generated assets were saved."
        _fail_running_jobs(jobs, message)
        source["stopped_reason"] = message
        persist_state()
        return {
            "provider_batch_name": batch_name,
            "provider_batch_state": state,
            "collected": True,
            "results": [],
            "failures": [
                {"job_id": job["id"], "chunk_id": job["chunk_id"], "error": message}
                for job in jobs
            ],
            "progress": get_source_interpretation_summary(source_id),
            "message": message,
        }

    destination = getattr(batch_job, "dest", None)
    responses = getattr(destination, "inlined_responses", None)
    if not isinstance(responses, list) or len(responses) != len(jobs):
        message = "Gemini Batch succeeded but its inline response envelope could not be routed safely."
        _fail_running_jobs(jobs, message)
        source["stopped_reason"] = message
        persist_state()
        return {
            "provider_batch_name": batch_name,
            "provider_batch_state": state,
            "collected": True,
            "results": [],
            "failures": [
                {"job_id": job["id"], "chunk_id": job["chunk_id"], "error": message}
                for job in jobs
            ],
            "progress": get_source_interpretation_summary(source_id),
            "message": message,
        }

    by_job_id = {}
    routing_error = False
    for item in responses:
        metadata = getattr(item, "metadata", None) or {}
        job_id = metadata.get("job_id") if isinstance(metadata, dict) else None
        if not isinstance(job_id, str) or job_id in by_job_id:
            routing_error = True
            break
        by_job_id[job_id] = item
    expected_ids = {job["id"] for job in jobs}
    if routing_error or set(by_job_id) != expected_ids:
        message = "Gemini Batch response metadata did not map exactly once to every extraction job."
        _fail_running_jobs(jobs, message)
        source["stopped_reason"] = message
        persist_state()
        return {
            "provider_batch_name": batch_name,
            "provider_batch_state": state,
            "collected": True,
            "results": [],
            "failures": [
                {"job_id": job["id"], "chunk_id": job["chunk_id"], "error": message}
                for job in jobs
            ],
            "progress": get_source_interpretation_summary(source_id),
            "message": message,
        }

    results, failures = [], []
    for job in jobs:
        item = by_job_id[job["id"]]
        try:
            if getattr(item, "error", None) is not None:
                raise ValueError("Gemini Batch request failed for this chunk.")
            response = getattr(item, "response", None)
            if response is None:
                raise ValueError("Gemini Batch returned no response for this chunk.")
            text = _response_text(response)
            if not text:
                raise ValueError("Gemini Batch returned no structured extraction output for this chunk.")
            raw = json.loads(text)
            if not isinstance(raw, dict) or set(raw) != {"assets"} or not isinstance(raw["assets"], list):
                raise ValueError("Gemini Batch chunk output must contain only an assets array.")
            hydrated = {
                "assets": [
                    {
                        **asset,
                        "id": None,
                        "created_at": None,
                        "source_id": job["source_id"],
                        "chunk_id": job["chunk_id"],
                    }
                    if isinstance(asset, dict)
                    else asset
                    for asset in raw["assets"]
                ]
            }
            validated = KnowledgeExtractionResultSubmission.model_validate(hydrated)
            results.append(
                complete_extraction_job(
                    job["id"],
                    validated.assets,
                    getattr(response, "response_id", None),
                )
            )
        except (ValidationError, ValueError, json.JSONDecodeError) as error:
            if isinstance(error, ValidationError):
                detail = _validation_summary(error)
            else:
                detail = str(error)
            message = "AI batch chunk output failed validation: " + detail
            mark_extraction_job_failed(job["id"], message)
            failures.append(
                {"job_id": job["id"], "chunk_id": job["chunk_id"], "error": message}
            )

    source["stopped_reason"] = (
        f"{len(failures)} batch chunk result(s) failed validation; valid chunks were saved."
        if failures
        else None
    )
    persist_state()
    return {
        "provider_batch_name": batch_name,
        "provider_batch_state": state,
        "collected": True,
        "results": results,
        "failures": failures,
        "progress": get_source_interpretation_summary(source_id),
        "message": "Gemini Batch results collected and independently validated.",
    }

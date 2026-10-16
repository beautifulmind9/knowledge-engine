from fastapi import HTTPException
from pathlib import Path

from app.db.persistence import StateMutationConflict
from app.db.mock_data import extraction_jobs, knowledge_assets
from app.models.knowledge_extraction import KnowledgeExtractionStatus
from app.services.gemini_knowledge_extraction import ExtractionValidationError, run_gemini_knowledge_extraction
from app.services.knowledge_extraction import (
    InterpretationCheckpointError,
    capture_interpretation_state,
    create_extraction_job,
    find_source,
    persist_interpretation_checkpoint,
    restore_interpretation_state,
)
from app.services.text_chunking import load_chunks
from app.services.chunk_manifest import valid_manifest
from app.persistence.factory import get_artifact_store
from app.services.performance_timing import operation_context


# Source-level orchestration may process several chunks in one explicit run,
# but every chunk gets its own normal Gemini request. Chunks never share model
# context. The AI gateway still enforces the global daily free-tier call cap.
MAX_CHUNKS_PER_RUN = 10


def get_source_chunks(source_id: str):
    source = find_source(source_id)
    if not source:
        raise ValueError("Source not found.")

    chunks_path = source.get("chunks_path")
    if not chunks_path:
        raise ValueError("This source has not been chunked yet.")

    return source, load_chunks(chunks_path)


def _jobs_for_source(source_id: str):
    return [
        job
        for job in extraction_jobs
        if job.get("source_id") == source_id
    ]


def _completed_chunk_ids(source_id: str):
    return {
        job.get("chunk_id")
        for job in _jobs_for_source(source_id)
        if job.get("status") == KnowledgeExtractionStatus.COMPLETED.value
    }


def _pending_or_running_job(source_id: str, chunk_id: str):
    candidates = [
        job
        for job in _jobs_for_source(source_id)
        if job.get("chunk_id") == chunk_id
        and job.get("status")
        in {
            KnowledgeExtractionStatus.PENDING_AI.value,
            KnowledgeExtractionStatus.RUNNING.value,
        }
    ]

    return candidates[-1] if candidates else None


def get_source_interpretation_summary(source_id: str):
    source = find_source(source_id)
    if not source:
        raise ValueError("Source not found.")
    manifest = source.get("chunk_manifest")
    if source.get("chunks_path") and valid_manifest(source_id, manifest):
        # Metadata avoids downloading chunk contents, but never substitutes for
        # live artifact-presence verification.
        if get_artifact_store().status_many([Path(source["chunks_path"])])[Path(source["chunks_path"])] != "artifact":
            raise ValueError("Chunks file not found on disk. Restore the source data before continuing.")
        chunk_ids = set(manifest["chunk_ids"])
        total_chunks = manifest["total_parts"]
    else:
        source, chunks = get_source_chunks(source_id)
        chunk_ids = {chunk.get("id") for chunk in chunks}
        total_chunks = len(chunks)
    source_jobs = [
        job
        for job in _jobs_for_source(source_id)
        if job.get("chunk_id") in chunk_ids
    ]

    completed_chunk_ids = {
        job.get("chunk_id")
        for job in source_jobs
        if job.get("status") == KnowledgeExtractionStatus.COMPLETED.value
    }

    completed_count = len(completed_chunk_ids)
    remaining_count = max(total_chunks - completed_count, 0)

    if total_chunks == 0:
        status = "empty"
    elif remaining_count == 0:
        status = "completed"
    elif any(
        job.get("status") == KnowledgeExtractionStatus.RUNNING.value
        for job in source_jobs
    ):
        status = "running"
    elif completed_count:
        status = "partial"
    else:
        status = "ready"

    return {
        "source_id": source_id,
        "title": source.get("title"),
        "status": status,
        "total_chunks": total_chunks,
        "completed_chunks": completed_count,
        "remaining_chunks": remaining_count,
        "asset_count": len(
            [
                asset
                for asset in knowledge_assets
                if asset.get("source_id") == source_id and asset.get("active", True)
            ]
        ),
        "job_counts": {
            "pending_ai": len(
                [
                    job
                    for job in source_jobs
                    if job.get("status") == KnowledgeExtractionStatus.PENDING_AI.value
                ]
            ),
            "running": len(
                [
                    job
                    for job in source_jobs
                    if job.get("status") == KnowledgeExtractionStatus.RUNNING.value
                ]
            ),
            "completed": len(
                [
                    job
                    for job in source_jobs
                    if job.get("status") == KnowledgeExtractionStatus.COMPLETED.value
                ]
            ),
            "failed": len(
                [
                    job
                    for job in source_jobs
                    if job.get("status") == KnowledgeExtractionStatus.FAILED.value
                ]
            ),
        },
    }


def interpret_source(source_id: str, max_chunks: int = 1):
    if max_chunks < 1 or max_chunks > MAX_CHUNKS_PER_RUN:
        raise ValueError(
            f"max_chunks must be between 1 and {MAX_CHUNKS_PER_RUN}."
        )

    source, chunks = get_source_chunks(source_id)
    if not chunks:
        raise ValueError("This source has no chunks to interpret.")

    durable_state = capture_interpretation_state()

    completed_chunk_ids = _completed_chunk_ids(source_id)
    processed_results = []
    stopped_reason = None
    interruption_category = None

    selected_jobs = []
    for chunk in chunks:
        chunk_id = chunk.get("id")
        if chunk_id in completed_chunk_ids:
            continue

        existing_job = _pending_or_running_job(source_id, chunk_id)
        if existing_job and existing_job.get("status") == KnowledgeExtractionStatus.RUNNING.value:
            stopped_reason = "A chunk is already marked as running. Check its job before continuing."
            break

        job = existing_job or create_extraction_job(
            source_id=source_id,
            chunk_id=chunk_id,
            persist=False,
        )

        selected_jobs.append(job["id"])
        if len(selected_jobs) >= max_chunks:
            break

    # Each selected chunk is a separate provider request with the original
    # strict single-chunk response schema. Stop on the first failure so one bad
    # response cannot automatically spend the rest of the user's daily budget.
    for job_id in selected_jobs:
        job = next((item for item in extraction_jobs if item.get("id") == job_id), {})
        try:
            with operation_context(source_id=source_id, chunk_id=job.get("chunk_id"),
                                   operation_category="interpretation_part"):
                result = run_gemini_knowledge_extraction(
                    job_id, coalesce_interpretation=True,
                    rollback_state=durable_state,
                    on_checkpoint=lambda state: durable_state.update(state),
                )
                processed_results.append(result)
        except Exception as error:
            if isinstance(error, (InterpretationCheckpointError, StateMutationConflict)):
                raise
            if isinstance(error, HTTPException):
                stopped_reason="Interpretation stopped after an AI service interruption."
                interruption_category=(getattr(error,"headers",None) or {}).get("X-KE-Interruption-Category")
                if error.status_code==429:
                    interruption_category="allowance_exhausted"
                elif error.status_code==503 and not interruption_category:
                    interruption_category="ai_unavailable"
                elif error.status_code==502 and not interruption_category:
                    interruption_category="provider_unavailable"
            elif isinstance(error, ExtractionValidationError):
                stopped_reason="Interpretation stopped because the response could not be validated."
                interruption_category="validation_failed"
            else:
                stopped_reason = "Interpretation stopped after an unexpected preparation error."
                interruption_category="preparation_failed"
            break

    try:
        source["stopped_reason"] = stopped_reason
        summary = get_source_interpretation_summary(source_id)
        source["processing_status"] = "knowledge_interpreted" if summary["status"] == "completed" else "knowledge_interpreting"
        durable_state = persist_interpretation_checkpoint(durable_state)
    except StateMutationConflict:
        # save_state already refreshed the live collections from latest state.
        raise
    except Exception:
        # For other finalization failures restore the last durable checkpoint.
        restore_interpretation_state(durable_state)
        raise

    return {
        "source_id": source_id,
        "title": source.get("title"),
        "processed_this_run": len(processed_results),
        "stopped_reason": stopped_reason,
        "interruption_category": interruption_category,
        "progress": summary,
        "results": processed_results,
    }

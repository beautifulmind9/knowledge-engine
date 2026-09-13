from app.db.mock_data import extraction_jobs, knowledge_assets
from app.models.knowledge_extraction import KnowledgeExtractionStatus
from app.services.gemini_knowledge_extraction import run_gemini_knowledge_extraction
from app.services.knowledge_extraction import (
    create_extraction_job,
    find_source,
    persist_state,
)
from app.services.text_chunking import load_chunks


MAX_CHUNKS_PER_RUN = 5


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
    source, chunks = get_source_chunks(source_id)
    chunk_ids = {chunk.get("id") for chunk in chunks}
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
    total_chunks = len(chunks)
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

    source["processing_status"] = "knowledge_interpreting"
    source["stopped_reason"] = None
    persist_state()

    completed_chunk_ids = _completed_chunk_ids(source_id)
    processed_results = []
    stopped_reason = None

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
        )

        try:
            result = run_gemini_knowledge_extraction(job["id"])
        except Exception as error:
            message = str(getattr(error, "detail", error))
            lowered = message.lower()
            if "429" in message or "quota" in lowered or "too_many_requests" in lowered:
                stopped_reason = (
                    "Gemini free-tier rate limit reached. Progress was saved; "
                    "retry later to continue with the remaining chunks."
                )
            else:
                stopped_reason = f"Interpretation stopped after an extraction error: {message}"
            break

        processed_results.append(result)
        completed_chunk_ids.add(chunk_id)

        if len(processed_results) >= max_chunks:
            break

    source["stopped_reason"] = stopped_reason
    summary = get_source_interpretation_summary(source_id)

    if summary["status"] == "completed":
        source["processing_status"] = "knowledge_interpreted"
    else:
        source["processing_status"] = "knowledge_interpreting"

    persist_state()

    return {
        "source_id": source_id,
        "title": source.get("title"),
        "processed_this_run": len(processed_results),
        "stopped_reason": stopped_reason,
        "progress": summary,
        "results": processed_results,
    }

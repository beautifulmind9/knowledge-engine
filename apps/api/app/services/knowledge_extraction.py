from datetime import datetime, timezone

from app.db.mock_data import (
    create_id,
    extraction_jobs,
    knowledge_assets,
    libraries,
    sources,
)
from app.db.persistence import save_state
from app.models.knowledge_extraction import (
    KnowledgeExtractionJob,
    KnowledgeExtractionStatus,
)
from app.services.knowledge_extraction_prompt import build_knowledge_extraction_request
from app.services.text_chunking import load_chunks


def utc_now():
    return datetime.now(timezone.utc)


def persist_state():
    save_state(libraries, sources, extraction_jobs, knowledge_assets)


def find_source(source_id: str):
    for source in sources:
        if source.get("id") == source_id:
            return source
    return None


def find_chunk(source_id: str, chunk_id: str):
    source = find_source(source_id)
    if not source:
        raise ValueError("Source not found.")

    chunks_path = source.get("chunks_path")
    if not chunks_path:
        raise ValueError("This source has not been chunked yet.")

    for chunk in load_chunks(chunks_path):
        if chunk.get("id") == chunk_id:
            return chunk

    raise ValueError("Chunk not found for this source.")


def create_extraction_job(source_id: str, chunk_id: str):
    find_chunk(source_id=source_id, chunk_id=chunk_id)

    job = KnowledgeExtractionJob(
        id=create_id("extraction"),
        source_id=source_id,
        chunk_id=chunk_id,
        status=KnowledgeExtractionStatus.PENDING_AI,
        created_at=utc_now(),
    )

    job_data = job.model_dump(mode="json")
    extraction_jobs.append(job_data)
    persist_state()
    return job_data


def find_extraction_job(job_id: str):
    for job in extraction_jobs:
        if job.get("id") == job_id:
            return job
    return None


def get_extraction_job(job_id: str):
    job = find_extraction_job(job_id)
    if not job:
        raise ValueError("Knowledge extraction job not found.")
    return job


def get_extraction_chunk(job_id: str):
    job = get_extraction_job(job_id)
    return find_chunk(
        source_id=job["source_id"],
        chunk_id=job["chunk_id"],
    )


def get_extraction_request(job_id: str):
    chunk = get_extraction_chunk(job_id)
    return build_knowledge_extraction_request(chunk)


def mark_extraction_job_running(job_id: str, provider: str, model: str):
    job = get_extraction_job(job_id)

    if job.get("status") == KnowledgeExtractionStatus.COMPLETED.value:
        raise ValueError("This knowledge extraction job is already completed.")

    job["status"] = KnowledgeExtractionStatus.RUNNING.value
    job["provider"] = provider
    job["model"] = model
    job["error"] = None
    persist_state()
    return job


def mark_extraction_job_failed(job_id: str, error: str):
    job = get_extraction_job(job_id)
    job["status"] = KnowledgeExtractionStatus.FAILED.value
    job["error"] = error
    persist_state()
    return job


def complete_extraction_job(job_id: str, assets, model_response_id: str | None = None):
    job = get_extraction_job(job_id)

    if job.get("status") == KnowledgeExtractionStatus.COMPLETED.value:
        raise ValueError("This knowledge extraction job is already completed.")

    stored_assets = []

    for asset in assets:
        asset_data = asset.model_dump(mode="json")

        if asset_data["source_id"] != job["source_id"]:
            raise ValueError("Asset source_id must match the extraction job source_id.")

        if asset_data["chunk_id"] != job["chunk_id"]:
            raise ValueError("Asset chunk_id must match the extraction job chunk_id.")

        if not asset_data.get("id"):
            asset_data["id"] = create_id("asset")

        if not asset_data.get("created_at"):
            asset_data["created_at"] = utc_now().isoformat()

        asset_data["extraction_job_id"] = job_id
        knowledge_assets.append(asset_data)
        stored_assets.append(asset_data)

    job["status"] = KnowledgeExtractionStatus.COMPLETED.value
    job["asset_count"] = len(stored_assets)
    job["completed_at"] = utc_now().isoformat()
    job["model_response_id"] = model_response_id
    job["error"] = None
    persist_state()

    return {
        "job": job,
        "assets": stored_assets,
    }


def list_knowledge_assets(
    source_id: str | None = None,
    chunk_id: str | None = None,
    asset_type: str | None = None,
):
    items = knowledge_assets

    if source_id:
        items = [item for item in items if item.get("source_id") == source_id]

    if chunk_id:
        items = [item for item in items if item.get("chunk_id") == chunk_id]

    if asset_type:
        items = [item for item in items if item.get("asset_type") == asset_type]

    return items

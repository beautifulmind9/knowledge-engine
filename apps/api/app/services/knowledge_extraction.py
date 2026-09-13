from collections import Counter
from datetime import datetime, timezone
import re

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


STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "before", "by", "for",
    "from", "has", "have", "if", "in", "into", "is", "it", "its", "of",
    "on", "or", "that", "the", "their", "them", "they", "this", "to",
    "use", "using", "when", "where", "which", "with", "you", "your",
}


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


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def query_tokens(query: str) -> list[str]:
    return [token for token in normalize_text(query).split() if len(token) > 1]


def _meaningful_tokens(value: str | None) -> set[str]:
    return {
        token
        for token in normalize_text(value).split()
        if len(token) > 2 and token not in STOPWORDS
    }


def _asset_special_text(asset: dict) -> str:
    values = []
    for field in (
        "condition",
        "action",
        "rationale",
        "consequence",
        "prevention",
        "what_happened",
        "transferable_lesson",
        "concept_demonstrated",
        "adaptation_notes",
    ):
        value = asset.get(field)
        if value:
            values.append(str(value))

    for field in (
        "how_to_apply",
        "when_to_use",
        "when_not_to_use",
        "tradeoffs",
        "steps",
        "components",
    ):
        values.extend(str(value) for value in asset.get(field, []) if value)

    return " ".join(values)


def _asset_similarity_text(asset: dict) -> str:
    parts = [
        asset.get("title") or "",
        asset.get("what_it_says") or "",
        asset.get("why_it_matters") or "",
        " ".join(asset.get("keywords", [])),
        _asset_special_text(asset),
    ]
    return " ".join(parts)


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def knowledge_asset_similarity(left: dict, right: dict) -> float:
    if left.get("asset_type") != right.get("asset_type"):
        return 0.0

    left_evidence = normalize_text(left.get("evidence"))
    right_evidence = normalize_text(right.get("evidence"))
    if left_evidence and left_evidence == right_evidence:
        return 1.0

    left_title = normalize_text(left.get("title"))
    right_title = normalize_text(right.get("title"))
    if left_title and left_title == right_title:
        return 0.98

    title_similarity = _jaccard(
        _meaningful_tokens(left.get("title")),
        _meaningful_tokens(right.get("title")),
    )
    content_similarity = _jaccard(
        _meaningful_tokens(_asset_similarity_text(left)),
        _meaningful_tokens(_asset_similarity_text(right)),
    )

    if title_similarity >= 0.65 and content_similarity >= 0.35:
        return max(0.80, (title_similarity + content_similarity) / 2)

    return (title_similarity * 0.35) + (content_similarity * 0.65)


def _asset_quality_score(asset: dict) -> int:
    score = int(asset.get("confidence_score") or 0) * 10

    for field in (
        "why_it_matters",
        "evidence",
        "condition",
        "action",
        "rationale",
        "consequence",
        "prevention",
        "what_happened",
        "transferable_lesson",
        "concept_demonstrated",
        "adaptation_notes",
    ):
        if asset.get(field):
            score += 2

    for field in (
        "keywords",
        "how_to_apply",
        "when_to_use",
        "when_not_to_use",
        "tradeoffs",
        "steps",
        "components",
    ):
        score += min(len(asset.get(field, [])), 5)

    return score


def consolidate_knowledge_assets(items: list[dict], similarity_threshold: float = 0.78):
    clusters: list[list[dict]] = []

    for asset in items:
        matching_cluster = None

        for cluster in clusters:
            if any(
                knowledge_asset_similarity(asset, existing) >= similarity_threshold
                for existing in cluster
            ):
                matching_cluster = cluster
                break

        if matching_cluster is None:
            clusters.append([asset])
        else:
            matching_cluster.append(asset)

    consolidated = []

    for cluster in clusters:
        canonical = max(cluster, key=_asset_quality_score)
        evidence = []
        asset_ids = []
        chunk_ids = []

        for asset in cluster:
            if asset.get("id"):
                asset_ids.append(asset["id"])
            if asset.get("chunk_id") and asset["chunk_id"] not in chunk_ids:
                chunk_ids.append(asset["chunk_id"])
            if asset.get("evidence") and asset["evidence"] not in evidence:
                evidence.append(asset["evidence"])

        consolidated.append(
            {
                "canonical_asset": canonical,
                "support_count": len(cluster),
                "asset_ids": asset_ids,
                "chunk_ids": chunk_ids,
                "supporting_evidence": evidence,
                "duplicate_asset_ids": [
                    asset_id
                    for asset_id in asset_ids
                    if asset_id != canonical.get("id")
                ],
            }
        )

    consolidated.sort(
        key=lambda group: (
            group["support_count"],
            _asset_quality_score(group["canonical_asset"]),
        ),
        reverse=True,
    )
    return consolidated


def search_knowledge_assets(
    query: str,
    source_id: str | None = None,
    asset_type: str | None = None,
    limit: int = 20,
):
    tokens = query_tokens(query)
    if not tokens:
        return []

    normalized_query = normalize_text(query)
    candidates = list_knowledge_assets(
        source_id=source_id,
        asset_type=asset_type,
    )
    ranked = []

    for asset in candidates:
        title = normalize_text(asset.get("title"))
        what_it_says = normalize_text(asset.get("what_it_says"))
        why_it_matters = normalize_text(asset.get("why_it_matters"))
        evidence = normalize_text(asset.get("evidence"))
        keywords = [normalize_text(value) for value in asset.get("keywords", [])]
        special = normalize_text(_asset_special_text(asset))

        score = 0
        matched_terms = set()

        if normalized_query and normalized_query in title:
            score += 12
        if normalized_query and normalized_query in what_it_says:
            score += 8

        for token in tokens:
            token_matched = False
            if token in title.split():
                score += 5
                token_matched = True
            if any(token in keyword.split() for keyword in keywords):
                score += 4
                token_matched = True
            if token in what_it_says.split():
                score += 3
                token_matched = True
            if token in special.split():
                score += 2
                token_matched = True
            if token in why_it_matters.split():
                score += 1
                token_matched = True
            if token in evidence.split():
                score += 1
                token_matched = True

            if token_matched:
                matched_terms.add(token)

        if score <= 0:
            continue

        ranked.append(
            {
                **asset,
                "relevance_score": score,
                "matched_terms": sorted(matched_terms),
            }
        )

    ranked.sort(
        key=lambda item: (
            item["relevance_score"],
            item.get("confidence_score", 0),
            item.get("created_at") or "",
        ),
        reverse=True,
    )
    return ranked[:limit]


def search_consolidated_knowledge_assets(
    query: str,
    source_id: str | None = None,
    asset_type: str | None = None,
    limit: int = 20,
):
    raw_results = search_knowledge_assets(
        query=query,
        source_id=source_id,
        asset_type=asset_type,
        limit=max(limit * 3, 20),
    )
    groups = consolidate_knowledge_assets(raw_results)

    for group in groups:
        members = [
            item for item in raw_results if item.get("id") in group["asset_ids"]
        ]
        group["relevance_score"] = max(
            (item.get("relevance_score", 0) for item in members),
            default=0,
        )
        group["matched_terms"] = sorted(
            {
                term
                for item in members
                for term in item.get("matched_terms", [])
            }
        )

    groups.sort(
        key=lambda group: (
            group["relevance_score"],
            group["support_count"],
            _asset_quality_score(group["canonical_asset"]),
        ),
        reverse=True,
    )
    return groups[:limit]


def summarize_knowledge_assets(source_id: str):
    source = find_source(source_id)
    if not source:
        raise ValueError("Source not found.")

    items = list_knowledge_assets(source_id=source_id)
    type_counts = Counter(item.get("asset_type", "unknown") for item in items)
    keyword_counts = Counter()

    for item in items:
        for keyword in item.get("keywords", []):
            normalized = normalize_text(keyword)
            if normalized:
                keyword_counts[normalized] += 1

    consolidated = consolidate_knowledge_assets(items)
    overlap_groups = [group for group in consolidated if group["support_count"] > 1]

    return {
        "source_id": source_id,
        "title": source.get("title"),
        "asset_count": len(items),
        "knowledge_unit_count": len(consolidated),
        "overlapping_asset_count": len(items) - len(consolidated),
        "overlap_group_count": len(overlap_groups),
        "asset_types": dict(sorted(type_counts.items())),
        "top_keywords": [
            {"keyword": keyword, "count": count}
            for keyword, count in keyword_counts.most_common(15)
        ],
    }

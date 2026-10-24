from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
import re

from app.db.mock_data import (
    create_id,
    extraction_jobs,
    knowledge_assets,
    libraries,
    sources,
)
from app.services import partition_authority as authority
from app.db.persistence import save_state
from app.db.persistence import StateMutationConflict
from app.models.knowledge_extraction import (
    KnowledgeExtractionJob,
    KnowledgeExtractionStatus,
)
from app.services.knowledge_extraction_prompt import build_knowledge_extraction_request
from app.services.text_chunking import load_chunks
from app.services.evidence_safety import (
    INTERPRETATION_FIELDS, MAX_WORKSHOP_REQUEST_BYTES, check_candidate_budget,
    MAX_CANDIDATE_ASSETS, MAX_CANDIDATE_BYTES, check_json_budget,
    reject_candidate_capacity, validate_raw_sources, validate_units,
)
from app.persistence.partitions import PartitionCapacityExceeded


STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "before", "by", "for",
    "from", "has", "have", "if", "in", "into", "is", "it", "its", "of",
    "on", "or", "that", "the", "their", "them", "they", "this", "to",
    "use", "using", "when", "where", "which", "with", "you", "your",
}


class InterpretationCheckpointError(RuntimeError):
    """A durable interpretation boundary failed; provider work must not proceed."""


def utc_now():
    return datetime.now(timezone.utc)


def persist_state():
    save_state(libraries, sources, extraction_jobs, knowledge_assets)


def find_source(source_id: str):
    for source in sources:
        if source.get("id") == source_id:
            return authority.source(source)
    return None


def find_chunk(source_id: str, chunk_id: str, *, chunk_context=None):
    source = find_source(source_id)
    if not source:
        raise ValueError("Source not found.")

    chunks_path = source.get("chunks_path")
    if not chunks_path:
        raise ValueError("This source has not been chunked yet.")

    if chunk_context is not None:
        chunk = chunk_context.get(source_id, chunks_path, chunk_id, source.get("chunk_manifest"))
        if chunk is not None:
            return chunk
        raise ValueError("Chunk not found for this source.")

    for chunk in load_chunks(chunks_path):
        if chunk.get("id") == chunk_id:
            return chunk

    raise ValueError("Chunk not found for this source.")


def create_extraction_job(source_id: str, chunk_id: str, reprocess: bool = False, *, persist: bool = True,
                          chunk_context=None):
    find_chunk(source_id=source_id, chunk_id=chunk_id, chunk_context=chunk_context)

    if authority.coordinator():
        return authority.create_job(source_id,chunk_id,create_id('extraction'),reprocess)
    prior = [j for j in authority.jobs(source_id) if j["chunk_id"] == chunk_id]
    for existing in reversed(prior):
        if existing["status"] in ("pending_ai", "running"):
            return existing
    if any(j["status"] == "completed" for j in prior) and not reprocess:
        raise ValueError("Chunk already completed. Set reprocess=true to intentionally create a replacement extraction.")

    job = KnowledgeExtractionJob(
        id=create_id("extraction"),
        source_id=source_id,
        chunk_id=chunk_id,
        status=KnowledgeExtractionStatus.PENDING_AI,
        created_at=utc_now(),
    )

    job_data = job.model_dump(mode="json")
    job_data.update(schema_version=2, extraction_version=max((j.get("extraction_version", 1) for j in prior), default=0)+1)
    source=find_source(source_id)
    if 'generation' in source:job_data['generation']=source['generation']
    extraction_jobs.append(job_data)
    if persist:
        persist_state()
    return job_data


def find_extraction_job(job_id: str):
    if authority.coordinator():
        return authority.find_job(job_id)
    for job in extraction_jobs:
        if job.get("id") == job_id:
            return job
    return None


def get_extraction_job(job_id: str):
    job = find_extraction_job(job_id)
    if not job:
        raise ValueError("Knowledge extraction job not found.")
    return job


def get_extraction_chunk(job_id: str, *, chunk_context=None):
    job = get_extraction_job(job_id)
    if authority.coordinator():authority.guard_chunk_read(job_id)
    else:authority.legacy_generation_guard(job)
    return find_chunk(
        source_id=job["source_id"],
        chunk_id=job["chunk_id"],
        chunk_context=chunk_context,
    )


def get_extraction_request(job_id: str, *, chunk_context=None):
    chunk = get_extraction_chunk(job_id, chunk_context=chunk_context)
    return build_knowledge_extraction_request(chunk)


def mark_extraction_job_running(job_id: str, provider: str, model: str, *, persist: bool = True):
    if authority.coordinator():
        return authority.claim(job_id,provider,model)
    job = get_extraction_job(job_id)
    if not authority.coordinator():authority.legacy_mutation_guard(job)

    if job.get("status") == KnowledgeExtractionStatus.COMPLETED.value:
        raise ValueError("This knowledge extraction job is already completed.")

    if job.get("status") == "running":
        raise ValueError("Job is already running; recover it only after the stale timeout.")
    job["started_at"] = utc_now().isoformat()
    job["status"] = KnowledgeExtractionStatus.RUNNING.value
    job["provider"] = provider
    job["model"] = model
    job["error"] = None
    if persist:
        persist_state()
    return job


def mark_extraction_job_failed(job_id: str, error: str, *, persist: bool = True):
    if authority.coordinator():
        return authority.fail(job_id,error)
    job = get_extraction_job(job_id)
    authority.legacy_mutation_guard(job)
    job["status"] = KnowledgeExtractionStatus.FAILED.value
    job["error"] = error
    if persist:
        persist_state()
    return job


def complete_extraction_job(job_id: str, assets, model_response_id: str | None = None, *,
                            persist: bool = True, update_source: bool = True,
                            chunk_context=None, generated_content: bool = False):
    job = get_extraction_job(job_id)
    if not authority.coordinator():authority.legacy_mutation_guard(job)

    if job.get("status") == KnowledgeExtractionStatus.COMPLETED.value:
        raise ValueError("This knowledge extraction job is already completed.")

    chunk = get_extraction_chunk(job_id, chunk_context=chunk_context)
    if generated_content:
        from app.services.generated_content_integrity import check_generated_assets
        check_generated_assets(assets, job)
    stored_assets = []

    for asset in assets:
        asset_data = asset.model_dump(mode="json")

        if asset_data["source_id"] != job["source_id"]:
            raise ValueError("Asset source_id must match the extraction job source_id.")

        if asset_data["chunk_id"] != job["chunk_id"]:
            raise ValueError("Asset chunk_id must match the extraction job chunk_id.")

        asset_data["id"] = create_id("asset")

        if not asset_data.get("created_at"):
            asset_data["created_at"] = utc_now().isoformat()

        asset_data["extraction_job_id"] = job_id
        asset_data.update(schema_version=2, extraction_version=job.get("extraction_version", 1), active=True)
        asset_data["chapter_or_section"] = asset_data.get("chapter_or_section") or chunk.get("chapter_or_section")
        stored_assets.append(asset_data)

    if authority.coordinator():
        completed=authority.complete(job_id,stored_assets,model_response_id)
        coordinator=authority.coordinator()
        if getattr(coordinator,'version',2)<3:
            from app.persistence.factory import get_state_store
            knowledge_assets[:]=deepcopy(get_state_store().loaded_snapshot.get('knowledge_assets',[]))
        if update_source and getattr(coordinator,'version',2)<3:
            from app.services.source_interpretation import get_source_interpretation_summary
            summary=get_source_interpretation_summary(job['source_id'])
            authority.checkpoint_source(job['source_id'],'knowledge_interpreted' if summary['status']=='completed' else 'knowledge_interpreting',None)
        return {'job':completed,'assets':stored_assets}

    # Validate the entire batch first; only successful replacement supersedes prior assets.
    for old in knowledge_assets:
        if old["source_id"] == job["source_id"] and old["chunk_id"] == job["chunk_id"] and old.get("active", True):
            old.update(active=False, superseded_by_job_id=job_id)
    knowledge_assets.extend(stored_assets)
    job["status"] = KnowledgeExtractionStatus.COMPLETED.value
    job["asset_count"] = len(stored_assets)
    job["completed_at"] = utc_now().isoformat()
    job["model_response_id"] = model_response_id
    job["error"] = None
    source = find_source(job["source_id"])
    if update_source:
        from app.services.source_interpretation import get_source_interpretation_summary
        summary = get_source_interpretation_summary(job["source_id"])
        source["processing_status"] = "knowledge_interpreted" if summary["status"] == "completed" else "knowledge_interpreting"
        source["stopped_reason"] = None
    if persist:
        persist_state()

    return {
        "job": job,
        "assets": stored_assets,
    }


def capture_interpretation_state():
    """In-memory rollback point for a not-yet-durable interpretation checkpoint."""
    if authority.coordinator():
        return {'phase2':True}
    from app.db import mock_data
    return {
        "libraries": deepcopy(libraries), "sources": deepcopy(sources),
        "extraction_jobs": deepcopy(extraction_jobs),
        "knowledge_assets": deepcopy(knowledge_assets),
        "outputs": deepcopy(mock_data.outputs), "usage": deepcopy(mock_data.usage),
    }


def restore_interpretation_state(state):
    """Restore a pre-checkpoint view after a definite persistence failure."""
    if state.get('phase2'):
        return  # Active mutations are transactional; never undo committed narrow/core state.
    from app.db import mock_data
    for name, target in (("libraries", libraries), ("sources", sources),
                         ("extraction_jobs", extraction_jobs),
                         ("knowledge_assets", knowledge_assets), ("outputs", mock_data.outputs)):
        target[:] = deepcopy(state[name])
    mock_data.usage.clear()
    mock_data.usage.update(deepcopy(state["usage"]))


def persist_interpretation_checkpoint(rollback_state):
    """Persist once; CAS conflicts restore latest state, other failures roll back locally."""
    if authority.coordinator():
        return capture_interpretation_state()
    try:
        persist_state()
    except StateMutationConflict:
        # save_state already refreshed the live collections from the latest
        # committed snapshot on a fail-closed reconciliation conflict.
        raise
    except Exception:
        restore_interpretation_state(rollback_state)
        raise InterpretationCheckpointError("Interpretation progress could not be saved safely.") from None
    return capture_interpretation_state()


def list_knowledge_assets(
    source_id: str | None = None,
    chunk_id: str | None = None,
    asset_type: str | None = None,
    source_ids: list[str] | None = None,
):
    coordinator=authority.coordinator()
    if coordinator is not None and getattr(coordinator,'version',2)>=3:
        selected=source_ids if source_ids is not None else ([source_id] if source_id else None)
        if source_ids is not None and source_id:
            selected = [sid for sid in source_ids if sid == source_id]
        try:
            items = coordinator.active_assets(
                source_ids=selected, chunk_id=chunk_id, asset_type=asset_type,
                max_items=MAX_CANDIDATE_ASSETS, max_bytes=MAX_CANDIDATE_BYTES)
        except PartitionCapacityExceeded:
            reject_candidate_capacity()
        # PostgreSQL READ COMMITTED gives the aggregate and fetch statements
        # separate snapshots. Repeat the authoritative application budget so a
        # concurrent insert or payload update cannot bypass the preflight.
        check_candidate_budget(items)
        validate_raw_sources(items, None if selected is None else set(selected))
        return items
    items = [a for a in knowledge_assets if a.get("active", True)]

    if source_ids is not None:
        selected_ids = set(source_ids)
        items = [item for item in items if item.get("source_id") in selected_ids]

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


def _evidence_supported_by_text(evidence: str | None, chunk_text: str | None) -> bool:
    """Conservative deterministic evidence support used by source audits.

    Exact normalized excerpts are accepted. Evidence that joins multiple source
    excerpts with an ellipsis is also accepted when each meaningful fragment
    occurs in order. Close paraphrases remain reviewable rather than being
    automatically treated as verified.
    """
    evidence_text = normalize_text(evidence)
    source_text = normalize_text(chunk_text)
    if not evidence_text or not source_text:
        return False
    if evidence_text in source_text:
        return True

    parts = re.split(r"(?:\.{3,}|…)", evidence or "")
    fragments = [
        normalize_text(part)
        for part in parts
        if len(normalize_text(part).split()) >= 5
    ]
    if len(fragments) < 2:
        return False

    position = 0
    for fragment in fragments:
        found = source_text.find(fragment, position)
        if found == -1:
            return False
        position = found + len(fragment)
    return True


def query_tokens(query: str) -> list[str]:
    return [token for token in normalize_text(query).split() if len(token) > 1]


def lexical_variants(term: str) -> set[str]:
    """Return the original token plus a conservative English plural stem.

    This is deliberately narrower than stemming or synonym expansion: it only
    lets plural question wording meet an existing singular source term. The
    original request term remains the scored and displayed diagnostic identity.
    """
    variants = {term}
    if len(term) > 4 and term.endswith("ies"):
        variants.add(term[:-3] + "y")
    elif len(term) > 3 and term.endswith("s") and not term.endswith(("ss", "us", "is")):
        variants.add(term[:-1])
    return variants


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


@dataclass(frozen=True)
class _TensionFeatures:
    terms: frozenset[str]
    negated: bool
    numbers: frozenset[str]


def _tension_features(asset):
    text = normalize_text((asset.get("what_it_says") or "") + " " + (asset.get("action") or ""))
    tokens = set(text.split())
    return _TensionFeatures(
        frozenset(token for token in tokens if len(token) > 2 and token not in STOPWORDS),
        bool(tokens & {"not", "never", "avoid", "without", "stop", "don", "cannot"}),
        frozenset(re.findall(r"\b\d+\b", text)),
    )


def _features_tension(left, right):
    if _jaccard(left.terms, right.terms) < 0.35:
        return False
    return left.negated != right.negated or bool(left.numbers and right.numbers and left.numbers != right.numbers)


@dataclass(frozen=True)
class _SimilarityFeatures:
    asset_type: str | None
    evidence: str
    title: str
    title_terms: frozenset[str]
    content_terms: frozenset[str]
    tension: _TensionFeatures


def _similarity_features(asset):
    return _SimilarityFeatures(
        asset.get("asset_type"), normalize_text(asset.get("evidence")), normalize_text(asset.get("title")),
        frozenset(_meaningful_tokens(asset.get("title"))),
        frozenset(_meaningful_tokens(_asset_similarity_text(asset))), _tension_features(asset),
    )


def _features_similarity(left, right):
    if left.asset_type != right.asset_type or _features_tension(left.tension, right.tension):
        return 0.0
    if left.evidence and left.evidence == right.evidence:
        return 1.0
    if left.title and left.title == right.title:
        return 0.98
    title_similarity = _jaccard(left.title_terms, right.title_terms)
    content_similarity = _jaccard(left.content_terms, right.content_terms)
    if title_similarity >= 0.65 and content_similarity >= 0.35:
        return max(0.80, (title_similarity + content_similarity) / 2)
    return (title_similarity * 0.35) + (content_similarity * 0.65)


def knowledge_asset_similarity(left: dict, right: dict) -> float:
    return _features_similarity(_similarity_features(left), _similarity_features(right))


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
    check_candidate_budget(items)
    clusters: list[list[dict]] = []
    # Scope this cache to a single consolidation. Normalization must not run for
    # every pair in a full candidate pool, and no private text is cached globally.
    # Equal features can share comparison work while every original member stays
    # in the cluster and evidence trail.
    cluster_features: list[dict[_SimilarityFeatures, None]] = []

    for asset in items:
        matching_cluster = None
        features = _similarity_features(asset)

        for index, cluster in enumerate(clusters):
            comparisons = cluster_features[index]
            if all(
                not _features_tension(features.tension, existing.tension) for existing in comparisons
            ) and any(
                _features_similarity(features, existing) >= similarity_threshold
                for existing in comparisons
            ):
                matching_cluster = cluster
                comparisons[features] = None
                break

        if matching_cluster is None:
            clusters.append([asset])
            cluster_features.append({features: None})
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
                "source_ids": sorted({a["source_id"] for a in cluster}),
                "evidence_trail": [{"asset_id":a["id"],"source_id":a["source_id"],"chunk_id":a["chunk_id"],"evidence":a.get("evidence"),"chapter_or_section":a.get("chapter_or_section"),
                                    "interpretation": {key:deepcopy(a[key]) for key in INTERPRETATION_FIELDS if key in a}}
                                   for a in cluster],
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
    limit: int | None = 20,
    library_id: str | None = None,
    *,
    diagnostics=None,
):
    check_json_budget(query, MAX_WORKSHOP_REQUEST_BYTES,
                      message='This search request is too large. Shorten the question.')
    tokens = sorted(set(query_tokens(query)) - STOPWORDS - {"one", "approach"})
    diagnostic_scope_ids = sorted(source["id"] for source in sources
                                  if (source_id is None or source["id"] == source_id)
                                  and (library_id is None or source.get("library_id") == library_id))
    if diagnostics is not None:
        diagnostics.request("knowledge_search", query, scope={"source_id": source_id, "library_id": library_id,
                            "source_ids": diagnostic_scope_ids, "asset_type": asset_type}, limit=limit, terms=tokens,
                            acquisition="active in-scope assets; indexed mode may return only a lexical superset")
    if not tokens:
        return []

    normalized_query = normalize_text(query)
    coordinator=authority.coordinator()
    if coordinator is not None and getattr(coordinator,'version',2)>=3:
        selected_sources=None
        if library_id:
            if not any(l['id']==library_id for l in libraries):raise ValueError('Library not found.')
            allowed={s['id'] for s in sources if s.get('library_id')==library_id}
            if source_id and source_id not in allowed:
                raise ValueError('Selected source does not belong to this library.')
            selected_sources=sorted({source_id} if source_id else allowed)
        acquisition_tokens = sorted({variant for token in tokens for variant in lexical_variants(token)})
        try:
            candidates=coordinator.search_candidates(
                acquisition_tokens, normalized_query, source_ids=selected_sources,
                source_id=source_id, asset_type=asset_type,
                max_items=MAX_CANDIDATE_ASSETS, max_bytes=MAX_CANDIDATE_BYTES)
        except PartitionCapacityExceeded:
            reject_candidate_capacity()
    else:
        candidates = list_knowledge_assets(source_id=source_id,asset_type=asset_type)
    if source_id:
        validate_raw_sources(candidates, {source_id})
    if library_id:
        if not any(l["id"] == library_id for l in libraries):
            raise ValueError("Library not found.")
        allowed = {s["id"] for s in sources if s["library_id"] == library_id}
        if source_id and source_id not in allowed:
            raise ValueError("Selected source does not belong to this library.")
        if coordinator is not None and getattr(coordinator, 'version', 2) >= 3:
            validate_raw_sources(candidates, allowed)
        candidates = [a for a in candidates if a["source_id"] in allowed]
    validate_raw_sources(candidates, {source_id} if source_id else (allowed if library_id else None))
    check_candidate_budget(candidates)
    if diagnostics is not None:
        from app.services.source_summary import source_summaries
        for summary in source_summaries(source_ids=diagnostic_scope_ids):
            diagnostics.preparation(summary.source_id, readiness=summary.readiness,
                                    completed_parts=summary.completed_parts, total_parts=summary.total_parts,
                                    has_usable_knowledge=summary.has_usable_knowledge,
                                    attention_category=summary.attention_category,
                                    candidate_count=sum(item.get("source_id") == summary.source_id for item in candidates))
    ranked = []

    for asset in candidates:
        title = normalize_text(asset.get("title"))
        what_it_says = normalize_text(asset.get("what_it_says"))
        why_it_matters = normalize_text(asset.get("why_it_matters"))
        evidence = normalize_text(asset.get("evidence"))
        keywords = [normalize_text(value) for value in asset.get("keywords", [])]
        special = normalize_text(_asset_special_text(asset))

        contributions = []
        matched_terms = set()
        # The integer part measures distinct query-term coverage. The bounded
        # fractional part breaks ties using each term's strongest field and
        # exact-phrase matches. Repeating a word in many asset fields cannot
        # outrank broader overlap confined to the source evidence.
        denominator = (len(tokens) * 5) + 21
        for token in tokens:
            variants = lexical_variants(token)
            fields = (("title", title, 5), ("keywords", " ".join(keywords), 4),
                      ("what_it_says", what_it_says, 3), ("special", special, 2),
                      ("why_it_matters", why_it_matters, 1), ("evidence", evidence, 1))
            for field, text, weight in fields:
                matched = sorted(variants & set(text.split()))
                if not matched:
                    continue
                matched_terms.add(token)
                contributions.append({"term": token, "field": field, "weight": weight,
                                      "matched_variant": matched[0],
                                      "points": 1 + weight / denominator})
                break

        for field, text, weight in (("title", title, 12), ("what_it_says", what_it_says, 8)):
            if normalized_query and normalized_query in text:
                contributions.append({"field": field, "bonus": "exact_phrase", "weight": weight,
                                      "points": weight / denominator})

        score = sum(part["points"] for part in contributions)
        if diagnostics is not None:
            diagnostics.candidate(asset, score, matched_terms, contributions,
                                  reason="no_query_overlap" if score <= 0 else None)

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
    retained = ranked if limit is None else ranked[:limit]
    if diagnostics is not None:
        diagnostics.ranked(ranked, retained=retained)
        for source_id in diagnostic_scope_ids:
            diagnostics.preparation(source_id, positive_match_count=sum(item.get("source_id") == source_id for item in ranked))
    return retained


def search_consolidated_knowledge_assets(
    query: str,
    source_id: str | None = None,
    asset_type: str | None = None,
    limit: int = 20,
    library_id: str | None = None,
    *,
    diagnostics=None,
):
    raw_results = search_knowledge_assets(
        query=query,
        source_id=source_id,
        asset_type=asset_type,
        # Consolidate the full positive in-scope pool before applying a result
        # limit, retaining independent member evidence even in duplicate floods.
        limit=None,
        library_id=library_id,
        diagnostics=diagnostics,
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
    validate_units(groups, {source_id} if source_id else (
        {source['id'] for source in sources if source.get('library_id') == library_id} if library_id else None))
    if diagnostics is not None:
        diagnostics.groups(groups, limit=limit)
        for source_id in {sid for group in groups for sid in group["source_ids"]}:
            diagnostics.preparation(source_id, retained_group_count=sum(source_id in group["source_ids"] for group in groups[:limit]))
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


def potential_tension(left, right):
    """Conservative review flag, never an assertion of semantic contradiction."""
    return _features_tension(_tension_features(left), _tension_features(right))


def recovery_eligibility(job, now=None):
    """Shared by read models and mutation: the server owns the ten-minute rule."""
    from datetime import timedelta
    if job["status"] == "failed":
        return True, None
    if job["status"] != "running":
        return False, None
    started = datetime.fromisoformat(job.get("started_at") or job["created_at"])
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    eligible_at = started + timedelta(seconds=600)
    return (now or utc_now()) >= eligible_at, eligible_at


def recover_job(job_id):
    if authority.coordinator():
        return authority.job_dto(authority.coordinator().recover(job_id))
    job = get_extraction_job(job_id)
    authority.legacy_mutation_guard(job)
    allowed, _ = recovery_eligibility(job)
    if not allowed:
        if job["status"] == "running":
            raise ValueError("Job is still running. Recovery requires ten minutes without completion.")
        raise ValueError("Only failed or stale-running jobs can be recovered.")
    job.update(status="pending_ai", error=None, recovered_at=utc_now().isoformat())
    # A reset resolves the old stop, never invokes AI. Other failures still matter.
    latest = {}
    for candidate in authority.jobs(job["source_id"]):
        if candidate["source_id"] == job["source_id"]:
            latest[candidate["chunk_id"]] = candidate
    if not any(j["status"] in {"failed", "running"} for j in latest.values()):
        find_source(job["source_id"])["stopped_reason"] = None
    persist_state()
    return job


def audit_source(source_id):
    from app.services.source_interpretation import get_source_interpretation_summary
    overview=summarize_knowledge_assets(source_id)
    source=find_source(source_id)
    current=list_knowledge_assets(source_id=source_id)
    all_assets=authority.assets([source_id],history=True)
    chunks=load_chunks(source["chunks_path"]) if source.get("chunks_path") else []
    chunk_map={c["id"]:c for c in chunks}
    evidence_review=[]
    for a in current:
        evidence=a.get("evidence")
        chunk_text=chunk_map.get(a["chunk_id"],{}).get("text")
        if evidence and not _evidence_supported_by_text(evidence, chunk_text):
            evidence_review.append(a["id"])
    return {**overview, "interpretation":get_source_interpretation_summary(source_id) if source.get("chunks_path") else None,
        "jobs":authority.jobs(source_id,history=True),
        "missing_evidence":[a["id"] for a in current if not (a.get("evidence") or "").strip()],
        "missing_keywords":[a["id"] for a in current if not a.get("keywords")],
        "old_schema_assets":[a["id"] for a in all_assets if a.get("schema_version",1)<2],
        "superseded_assets":[a["id"] for a in all_assets if not a.get("active",True)],
        "confidence_distribution":dict(Counter(a.get("confidence_score",0) for a in current)),
        "evidence_needing_review":evidence_review,
        "overlap_rate":round(overview["overlapping_asset_count"]/max(len(current),1),3),
        "note":"Non-verbatim evidence may be a valid paraphrase. Review it for source support; automatic matching cannot establish faithfulness or false positives."}

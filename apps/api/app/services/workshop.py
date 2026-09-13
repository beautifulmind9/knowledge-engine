from collections import defaultdict

from app.models.workshop import WorkshopPrepareRequest
from app.services.knowledge_extraction import (
    STOPWORDS,
    consolidate_knowledge_assets,
    normalize_text,
    search_knowledge_assets,
)


def build_workshop_query(payload: WorkshopPrepareRequest) -> str:
    parts = [payload.situation, payload.goal, payload.audience or "", payload.output_type]
    parts.extend(payload.constraints)
    raw_query = " ".join(part.strip() for part in parts if part and part.strip())

    # Workshop inputs are full sentences, so remove common filler words and
    # repeated terms before retrieval. Otherwise words such as "and", "for",
    # "is", and repeated uses of "workshop" can overwhelm the useful signals
    # in the user's goal and constraints.
    tokens = []
    seen = set()
    for token in normalize_text(raw_query).split():
        if len(token) <= 1 or token in STOPWORDS or token in seen:
            continue
        seen.add(token)
        tokens.append(token)

    return " ".join(tokens)


def _retrieve_raw_assets(payload: WorkshopPrepareRequest, query: str) -> list[dict]:
    per_scope_limit = max(payload.limit * 4, 20)

    if not payload.source_ids:
        return search_knowledge_assets(query=query, limit=per_scope_limit)

    results = []
    seen_ids = set()

    for source_id in payload.source_ids:
        for item in search_knowledge_assets(
            query=query,
            source_id=source_id,
            limit=per_scope_limit,
        ):
            item_id = item.get("id")
            if item_id and item_id in seen_ids:
                continue
            if item_id:
                seen_ids.add(item_id)
            results.append(item)

    results.sort(
        key=lambda item: (
            item.get("relevance_score", 0),
            item.get("confidence_score", 0),
        ),
        reverse=True,
    )
    return results


def prepare_workshop(payload: WorkshopPrepareRequest) -> dict:
    query = build_workshop_query(payload)
    raw_assets = _retrieve_raw_assets(payload=payload, query=query)
    groups = consolidate_knowledge_assets(raw_assets)

    for group in groups:
        members = [
            item for item in raw_assets if item.get("id") in group["asset_ids"]
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
            group.get("relevance_score", 0),
            group.get("support_count", 0),
            group["canonical_asset"].get("confidence_score", 0),
        ),
        reverse=True,
    )
    groups = groups[: payload.limit]

    by_type = defaultdict(list)
    for group in groups:
        asset_type = group["canonical_asset"].get("asset_type", "unknown")
        by_type[asset_type].append(group)

    return {
        "brief": {
            "situation": payload.situation,
            "goal": payload.goal,
            "audience": payload.audience,
            "constraints": payload.constraints,
            "output_type": payload.output_type,
            "retrieval_query": query,
        },
        "source_ids": payload.source_ids,
        "knowledge_unit_count": len(groups),
        "knowledge_units": groups,
        "knowledge_by_type": dict(sorted(by_type.items())),
        "message": (
            "Workshop preparation complete. Relevant consolidated knowledge is ready "
            "for an output-generation step."
        ),
    }

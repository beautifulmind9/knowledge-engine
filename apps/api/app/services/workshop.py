from collections import defaultdict

from app.models.workshop import WorkshopPrepareRequest
from app.services.knowledge_extraction import (
    STOPWORDS,
    consolidate_knowledge_assets,
    list_knowledge_assets,
    normalize_text,
)


# These terms describe the Workshop interaction itself more than the user's
# actual problem. Excluding them prevents generic words such as "workshop" and
# "plan" from outranking specific constraints such as "breaks" or "cramming".
WORKSHOP_GENERIC_TERMS = {
    "avoid",
    "create",
    "design",
    "different",
    "educational",
    "include",
    "material",
    "much",
    "must",
    "need",
    "plan",
    "professionals",
    "total",
    "useful",
    "workshop",
}


# Small deterministic expansions help user language meet the terminology used
# by the source without requiring another AI call or embedding service.
TERM_EXPANSIONS = {
    "breaks": {"break", "rest"},
    "break": {"breaks", "rest"},
    "cramming": {"crammed", "overloaded", "overload"},
    "crammed": {"cramming", "overloaded", "overload"},
    "overloaded": {"crammed", "cramming", "overload"},
    "mixed": {"diverse", "varied"},
    "experience": {"level", "levels"},
    "levels": {"level", "experience"},
    "realistic": {"plausible", "timing"},
    "hours": {"hour", "time", "timing", "schedule", "scheduling"},
    "hour": {"hours", "time", "timing", "schedule", "scheduling"},
    "focused": {"focus", "sharp", "specific"},
}


def _meaningful_terms(value: str | None) -> list[str]:
    if not value:
        return []

    terms = []
    seen = set()
    for token in normalize_text(value).split():
        if (
            len(token) <= 1
            or token in STOPWORDS
            or token in WORKSHOP_GENERIC_TERMS
            or token in seen
        ):
            continue
        seen.add(token)
        terms.append(token)
    return terms


def build_workshop_query(payload: WorkshopPrepareRequest) -> str:
    parts = [payload.situation, payload.goal, payload.audience or "", payload.output_type]
    parts.extend(payload.constraints)

    terms = []
    seen = set()
    for part in parts:
        for term in _meaningful_terms(part):
            if term in seen:
                continue
            seen.add(term)
            terms.append(term)

    return " ".join(terms)


def _asset_fields(asset: dict) -> dict[str, set[str]]:
    special_values = []
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
            special_values.append(str(value))

    for field in (
        "how_to_apply",
        "when_to_use",
        "when_not_to_use",
        "tradeoffs",
        "steps",
        "components",
    ):
        special_values.extend(str(value) for value in asset.get(field, []) if value)

    return {
        "title": set(normalize_text(asset.get("title")).split()),
        "keywords": set(
            normalize_text(" ".join(asset.get("keywords", []))).split()
        ),
        "what_it_says": set(normalize_text(asset.get("what_it_says")).split()),
        "special": set(normalize_text(" ".join(special_values)).split()),
        "why_it_matters": set(normalize_text(asset.get("why_it_matters")).split()),
        "evidence": set(normalize_text(asset.get("evidence")).split()),
    }


def _term_match_strength(term: str, fields: dict[str, set[str]]) -> int:
    candidates = {term, *TERM_EXPANSIONS.get(term, set())}

    # Stronger fields are more intentional labels for the knowledge asset.
    weights = {
        "title": 5,
        "keywords": 5,
        "special": 4,
        "what_it_says": 3,
        "why_it_matters": 2,
        "evidence": 1,
    }

    best = 0
    for field, weight in weights.items():
        if candidates & fields[field]:
            best = max(best, weight)
    return best


def _workshop_relevance(asset: dict, payload: WorkshopPrepareRequest) -> tuple[int, list[str]]:
    fields = _asset_fields(asset)
    score = 0
    matched_terms = set()

    # Constraints and goals should drive selection more strongly than generic
    # situation wording. This keeps task-critical knowledge near the top.
    sections = [
        (payload.goal, 6),
        (payload.audience or "", 5),
        (payload.situation, 4),
        (payload.output_type, 2),
    ]
    sections.extend((constraint, 10) for constraint in payload.constraints)

    for text, section_weight in sections:
        section_matched = False
        for term in _meaningful_terms(text):
            strength = _term_match_strength(term, fields)
            if strength <= 0:
                continue
            score += section_weight * strength
            matched_terms.add(term)
            section_matched = True

        # Matching a stated constraint is more useful than accumulating several
        # weak matches from general prose.
        if section_weight == 10 and section_matched:
            score += 15

    return score, sorted(matched_terms)


def _retrieve_raw_assets(payload: WorkshopPrepareRequest) -> list[dict]:
    if payload.source_ids:
        candidates = []
        seen_ids = set()
        for source_id in payload.source_ids:
            for item in list_knowledge_assets(source_id=source_id):
                item_id = item.get("id")
                if item_id and item_id in seen_ids:
                    continue
                if item_id:
                    seen_ids.add(item_id)
                candidates.append(item)
    else:
        candidates = list_knowledge_assets()

    ranked = []
    for item in candidates:
        score, matched_terms = _workshop_relevance(item, payload)
        if score <= 0:
            continue
        ranked.append(
            {
                **item,
                "relevance_score": score,
                "matched_terms": matched_terms,
            }
        )

    ranked.sort(
        key=lambda item: (
            item.get("relevance_score", 0),
            item.get("confidence_score", 0),
        ),
        reverse=True,
    )

    return ranked[: max(payload.limit * 5, 30)]


def prepare_workshop(payload: WorkshopPrepareRequest) -> dict:
    query = build_workshop_query(payload)
    raw_assets = _retrieve_raw_assets(payload=payload)
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

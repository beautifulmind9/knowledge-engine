from collections import defaultdict
from math import ceil

from app.models.workshop import WorkshopPrepareRequest
from app.services.knowledge_extraction import (
    STOPWORDS,
    consolidate_knowledge_assets,
    list_knowledge_assets,
    normalize_text,
)


# These terms describe the Workshop interaction itself more than the user's
# actual problem. Excluding them prevents broad facilitation language and filler
# words from outranking specific task concepts such as timing, practice or Q&A.
WORKSHOP_GENERIC_TERMS = {
    "am",
    "avoid",
    "can",
    "could",
    "create",
    "design",
    "did",
    "different",
    "do",
    "does",
    "educational",
    "facilitation",
    "facilitator",
    "facilitators",
    "include",
    "just",
    "keep",
    "keeping",
    "little",
    "material",
    "me",
    "more",
    "most",
    "much",
    "must",
    "my",
    "need",
    "not",
    "only",
    "participant",
    "participants",
    "plan",
    "professionals",
    "selected",
    "session",
    "sessions",
    "should",
    "source",
    "total",
    "useful",
    "want",
    "would",
    "workshop",
    "workshops",
}


# Output-format wording can otherwise dominate retrieval even though it is not
# source subject matter. Keep these terms available in the user's situation,
# where they may be substantive, but suppress them in goals and structural
# constraints for the corresponding output mode.
MODE_CONSTRAINT_GENERIC_TERMS = {
    "study_guide": {
        "answer",
        "answers",
        "checking",
        "guidance",
        "question",
        "questions",
        "review",
    },
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
    "engaged": {"engagement", "attention", "participation"},
    "engagement": {"engaged", "attention", "participation"},
    "timing": {"time", "schedule", "scheduling"},
    "practice": {"exercise", "exercises", "activity", "activities", "application"},
    "practical": {"practice", "exercise", "exercises", "application"},
    "concepts": {"concept"},
    "concept": {"concepts"},
    "problems": {"problem"},
    "problem": {"problems"},
    "examples": {"example"},
    "example": {"examples"},
    "rules": {"rule", "decision"},
    "warnings": {"warning"},
    "patterns": {"pattern"},
    "frameworks": {"framework"},
    "chapters": {"chapter", "section"},
}


def _meaningful_terms(value: str | None, extra_generic_terms=None) -> list[str]:
    if not value:
        return []

    extra_generic_terms = extra_generic_terms or set()
    terms = []
    seen = set()
    for token in normalize_text(value).split():
        if (
            len(token) <= 1
            or token in STOPWORDS
            or token in WORKSHOP_GENERIC_TERMS
            or token in extra_generic_terms
            or token in seen
        ):
            continue
        seen.add(token)
        terms.append(token)
    return terms


def build_workshop_query(payload: WorkshopPrepareRequest) -> str:
    terms = []
    seen = set()
    mode_generic = MODE_CONSTRAINT_GENERIC_TERMS.get(payload.output_type, set())

    # Situation wording is the strongest signal for what the user is actually
    # working on, so retain potentially substantive terms there. Goal wording
    # often repeats output-format language (for example, "review" in a Study
    # Guide goal), so apply the mode-specific structural filter to the goal.
    for part, extra_generic in (
        (payload.situation, set()),
        (payload.goal, mode_generic),
        (payload.audience or "", set()),
    ):
        for term in _meaningful_terms(part, extra_generic):
            if term in seen:
                continue
            seen.add(term)
            terms.append(term)

    for constraint in payload.constraints:
        for term in _meaningful_terms(constraint, mode_generic):
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
        "asset_type": set(normalize_text(str(asset.get("asset_type", "")).replace("_", " ")).split()),
        "chapter_or_section": set(normalize_text(asset.get("chapter_or_section")).split()),
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
        "asset_type": 6,
        "chapter_or_section": 6,
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
    mode_generic = MODE_CONSTRAINT_GENERIC_TERMS.get(payload.output_type, set())

    # Situation wording stays unfiltered by output mode because it describes the
    # subject matter. Goals and constraints can contain format instructions, so
    # mode-specific structural terms are removed from those scoring sections.
    sections = [
        (payload.goal, 6, mode_generic),
        (payload.audience or "", 5, set()),
        (payload.situation, 4, set()),
    ]
    sections.extend((constraint, 10, mode_generic) for constraint in payload.constraints)

    for text, section_weight, extra_generic in sections:
        section_matched = False
        for term in _meaningful_terms(text, extra_generic):
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
    from app.db.mock_data import sources, libraries
    selected = set(payload.source_ids)
    known = {s["id"] for s in sources}
    if selected - known:
        raise ValueError("Selected source not found.")
    if payload.library_id:
        if not any(l["id"] == payload.library_id for l in libraries):
            raise ValueError("Library not found.")
        library_sources = {s["id"] for s in sources if s["library_id"] == payload.library_id}
        if selected - library_sources:
            raise ValueError("Selected sources do not belong to this library.")
        selected = selected or library_sources
        if not selected:
            return []
    if selected:
        candidates = []
        seen_ids = set()
        for source_id in sorted(selected):
            for item in list_knowledge_assets(source_id=source_id):
                item_id = item.get("id")
                if item_id and item_id in seen_ids:
                    continue
                if item_id:
                    seen_ids.add(item_id)
                candidates.append(item)
    else:
        candidates = list_knowledge_assets()

    if payload.asset_ids:
        available = {a["id"] for a in candidates}
        if set(payload.asset_ids) - available:
            raise ValueError("Selected knowledge asset not found in the current source scope.")
        # Selecting a consolidated unit must retain all its in-scope evidence,
        # not just the canonical asset displayed by the browser.
        selected_ids = set(payload.asset_ids)
        contributing_ids = {
            aid for group in consolidate_knowledge_assets(candidates)
            if selected_ids.intersection(group["asset_ids"])
            for aid in group["asset_ids"]
        }
        candidates = [a for a in candidates if a["id"] in contributing_ids]
    multi_source_scope = len({item.get("source_id") for item in candidates if item.get("source_id")}) > 1
    ranked = []
    for item in candidates:
        score, matched_terms = _workshop_relevance(item, payload)
        if score <= 0 and not payload.asset_ids:
            if payload.output_type == "knowledge_answer" and not multi_source_scope:
                # Broad source questions such as "What does this source teach?"
                # should still return a representative evidence-grounded set.
                score = 1
            else:
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

    pool_limit = max(payload.limit * 5, 30)
    if payload.output_type == "knowledge_answer" and multi_source_scope:
        source_ids = {item.get("source_id") for item in ranked if item.get("source_id")}
        per_source_limit = max(3, ceil(pool_limit / max(len(source_ids), 1)))
        source_counts = defaultdict(int)
        balanced_pool = []
        for item in ranked:
            source_id = item.get("source_id")
            if source_id and source_counts[source_id] >= per_source_limit:
                continue
            balanced_pool.append(item)
            if source_id:
                source_counts[source_id] += 1
            if len(balanced_pool) >= pool_limit:
                break
        ranked = balanced_pool

    return ranked[:pool_limit]


def _coverage_aware_group_selection(groups, raw_assets, payload):
    """Keep relevance primary while giving similarly relevant sources a chance to appear."""
    if payload.output_type != "knowledge_answer":
        return groups[: payload.limit]

    from app.db.mock_data import sources

    selected = set(payload.source_ids)
    if payload.library_id:
        selected = selected or {source["id"] for source in sources if source["library_id"] == payload.library_id}
    if not selected:
        selected = {item.get("source_id") for item in raw_assets if item.get("source_id")}
    if len(selected) < 2:
        return groups[: payload.limit]

    raw_by_id = {item.get("id"): item for item in raw_assets if item.get("id")}
    best_score = max((group.get("relevance_score", 0) for group in groups), default=0)
    if best_score <= 0:
        return groups[: payload.limit]

    # Only reserve a source when its own evidence has meaningful query overlap
    # and is at least half as relevant as the strongest candidate. This avoids
    # forcing every selected material into a comparison for the sake of breadth.
    threshold = best_score * 0.5
    source_candidates = []
    for source_id in sorted(selected):
        best = None
        for group in groups:
            member_scores = [
                raw_by_id.get(asset_id, {})
                for asset_id in group.get("asset_ids", [])
            ]
            own = [item for item in member_scores if item.get("source_id") == source_id and item.get("matched_terms")]
            source_score = max((item.get("relevance_score", 0) for item in own), default=0)
            if source_score < threshold:
                continue
            candidate = (source_score, group)
            if best is None or source_score > best[0]:
                best = candidate
        if best:
            source_candidates.append((best[0], source_id, best[1]))

    source_candidates.sort(key=lambda item: (-item[0], item[1], tuple(item[2].get("asset_ids", []))))
    chosen = []
    chosen_ids = set()
    for _, _, group in source_candidates:
        marker = tuple(group.get("asset_ids", []))
        if marker in chosen_ids:
            continue
        chosen.append(group)
        chosen_ids.add(marker)
        if len(chosen) >= payload.limit:
            break
    for group in groups:
        marker = tuple(group.get("asset_ids", []))
        if marker in chosen_ids:
            continue
        chosen.append(group)
        chosen_ids.add(marker)
        if len(chosen) >= payload.limit:
            break
    # Preserve the relevance ordering for presentation and provider context.
    return sorted(chosen, key=lambda group: (
        group.get("relevance_score", 0), group.get("support_count", 0),
        group["canonical_asset"].get("confidence_score", 0),
    ), reverse=True)


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
    groups = _coverage_aware_group_selection(groups, raw_assets, payload)

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
            "output_format": payload.output_format,
            "retrieval_query": query,
            "source_ids": payload.source_ids,
            "library_id": payload.library_id,
            "asset_ids": payload.asset_ids,
            "limit": payload.limit,
            "tone_or_style": getattr(payload, "tone_or_style", None),
        },
        "source_ids": payload.source_ids,
        "knowledge_unit_count": len(groups),
        "knowledge_units": groups,
        "knowledge_by_type": dict(sorted(by_type.items())),
        "synthesis_context": synthesis_context(groups),
        "source_coverage": source_coverage(groups),
        "message": (
            "Workshop preparation complete. Relevant consolidated knowledge is ready "
            "for an output-generation step."
        ),
    }



def source_coverage(groups):
    """Preparation progress, distinct from lexical relevance or adequacy."""
    from app.db.mock_data import sources
    from app.services.source_interpretation import get_source_interpretation_summary
    counts = defaultdict(int)
    for group in groups:
        for source_id in set(group["source_ids"]):
            counts[source_id] += 1
    coverage = []
    for source in sources:
        if source["id"] not in counts:
            continue
        item = {"source_id": source["id"], "title": source["title"],
                "relevant_idea_count": counts[source["id"]],
                "prepared_sections": None, "total_sections": None}
        if source.get("chunks_path"):
            try:
                progress = get_source_interpretation_summary(source["id"])
                item.update(prepared_sections=progress["completed_chunks"], total_sections=progress["total_chunks"])
            except (ValueError, FileNotFoundError, OSError):
                # Unknown coverage must never be presented as complete.
                pass
        coverage.append(item)
    return coverage


def evidence_base_state(source_ids, library_id=None):
    """Summarize only selected-material readiness for a grounded answer."""
    from app.db.mock_data import sources
    from app.services.source_summary import source_summaries

    chosen_ids = set(source_ids or [])
    chosen = [source for source in sources
              if (not chosen_ids or source["id"] in chosen_ids)
              and (library_id is None or source["library_id"] == library_id)]
    state = {"selected_count": len(chosen), "selected_source_ids": [source["id"] for source in chosen], "ready_count": 0, "preparing_count": 0,
             "attention_count": 0, "unavailable_count": 0}
    for source in chosen:
        try:
            summary = source_summaries(source_id=source["id"])[0]
        except Exception:
            state["unavailable_count"] += 1
            continue
        if summary.readiness == "ready":
            state["ready_count"] += 1
        elif summary.readiness == "unknown":
            state["unavailable_count"] += 1
        elif summary.attention_category:
            state["attention_count"] += 1
        else:
            state["preparing_count"] += 1
    return state


def synthesis_context(groups):
    from itertools import combinations
    from app.services.knowledge_extraction import potential_tension
    agreements=[{"asset_ids":g["asset_ids"],"source_ids":g["source_ids"],"idea":g["canonical_asset"]["what_it_says"],"status":"candidate agreement; inspect evidence"}
                for g in groups if len(g["source_ids"])>1]
    tensions=[]
    for left,right in combinations(groups,2):
        if any(a != b for a in left["source_ids"] for b in right["source_ids"]) and potential_tension(left["canonical_asset"],right["canonical_asset"]):
            tensions.append({"asset_ids":[left["canonical_asset"]["id"],right["canonical_asset"]["id"]],
                "source_ids":sorted(set(left["source_ids"]+right["source_ids"])),
                "reason":"Potential difference in polarity or numeric guidance; inspect scope before resolving.","status":"needs review"})
    return {"agreements":agreements, "tensions":tensions,
        "distinct_contributions":[{"asset_ids":g["asset_ids"],"source_ids":g["source_ids"],"idea":g["canonical_asset"]["what_it_says"]} for g in groups if len(g["source_ids"])==1],
        "limitations":"Deterministic lexical signals only. No flag does not imply no contradiction. Never infer consensus just from overlap."}

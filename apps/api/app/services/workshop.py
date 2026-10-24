from collections import defaultdict

from app.models.workshop import WorkshopPrepareRequest
from app.services.evidence_safety import (
    MAX_WORKSHOP_REQUEST_BYTES, check_candidate_budget, check_json_budget,
    request_scope, validate_preparation, validate_raw_sources, validate_units,
)
from app.services.knowledge_extraction import (
    STOPWORDS,
    consolidate_knowledge_assets,
    lexical_variants,
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
    candidates = lexical_variants(term) | TERM_EXPANSIONS.get(term, set())

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


def _workshop_relevance(asset: dict, payload: WorkshopPrepareRequest, *, diagnostics=None) -> tuple[float, list[str]]:
    fields = _asset_fields(asset)
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
    # Each request term contributes once at its strongest stated priority.
    # Repeating the brief or constraints cannot manufacture extra relevance.
    priorities = {}
    for index, (text, section_weight, extra_generic) in enumerate(sections):
        for term in _meaningful_terms(text, extra_generic):
            previous = priorities.get(term)
            if previous is None or section_weight > previous[0]:
                priorities[term] = (section_weight, "constraint" if index >= 3 else ("goal", "audience", "situation")[index])
    denominator = len(priorities) * 60 + 1  # max section weight 10 × max field weight 6
    contributions = []
    field_weights = {"asset_type": 6, "chapter_or_section": 6, "title": 5, "keywords": 5,
                     "special": 4, "what_it_says": 3, "why_it_matters": 2, "evidence": 1}
    for term, (section_weight, section) in priorities.items():
        variants = lexical_variants(term) | TERM_EXPANSIONS.get(term, set())
        matches = [(weight, field, sorted(variants & fields[field]))
                   for field, weight in field_weights.items() if variants & fields[field]]
        if not matches:
            continue
        strength, field, matched = max(matches, key=lambda part: part[0])
        matched_terms.add(term)
        contributions.append({"term": term, "section": section, "section_weight": section_weight,
                              "field": field, "strength": strength, "matched_variant": matched[0],
                              "points": 1 + section_weight * strength / denominator})
    score = sum(part["points"] for part in contributions)
    if diagnostics is not None:
        diagnostics.candidate(asset, score, matched_terms, contributions)
    return score, sorted(matched_terms)


def _retrieve_raw_assets(payload: WorkshopPrepareRequest, *, diagnostics=None) -> list[dict]:
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
    scope_ids = sorted(selected if payload.library_id else selected or known)
    if diagnostics is not None:
        diagnostics.request("workshop", build_workshop_query(payload), scope={"source_ids": scope_ids},
                            library_id=payload.library_id, asset_ids=payload.asset_ids,
                            limit=payload.limit, output_type=payload.output_type,
                            terms=build_workshop_query(payload).split(), acquisition="all active in-scope assets")
        from app.services.source_summary import source_summaries
        for summary in source_summaries(source_ids=scope_ids):
            diagnostics.preparation(summary.source_id, readiness=summary.readiness,
                                    attention_category=summary.attention_category,
                                    has_usable_knowledge=summary.has_usable_knowledge,
                                    completed_parts=summary.completed_parts, total_parts=summary.total_parts)
    if payload.library_id and not selected:
        return []
    if selected:
        candidates = list_knowledge_assets(source_ids=sorted(selected))
    else:
        candidates = list_knowledge_assets()
    validate_raw_sources(candidates, set(scope_ids) if selected or payload.library_id else None)
    check_candidate_budget(candidates)
    if diagnostics is not None:
        for source_id in scope_ids:
            diagnostics.preparation(source_id, candidate_count=sum(item.get("source_id") == source_id for item in candidates))

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
        if diagnostics is not None:
            for asset in candidates:
                if asset["id"] not in contributing_ids:
                    diagnostics.candidate(asset, reason="not_selected_idea")
        candidates = [a for a in candidates if a["id"] in contributing_ids]
    multi_source_scope = len({item.get("source_id") for item in candidates if item.get("source_id")}) > 1
    ranked = []
    for item in candidates:
        score, matched_terms = _workshop_relevance(item, payload, diagnostics=diagnostics)
        if score <= 0 and not payload.asset_ids:
            if payload.output_type == "knowledge_answer" and not multi_source_scope:
                # Broad source questions such as "What does this source teach?"
                # should still return a representative evidence-grounded set.
                score = 1
                if diagnostics is not None:
                    diagnostics.candidate(item, score, contributions=[{"bonus": "single_source_representative_fallback", "points": 1}])
            else:
                if diagnostics is not None:
                    diagnostics.candidate(item, reason="no_query_overlap")
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

    # Raw limits and hard source quotas lose independent evidence and distinct
    # findings before consolidation. Apply the limit to complete groups below.
    if diagnostics is not None:
        diagnostics.ranked(ranked)
        for source_id in scope_ids:
            diagnostics.preparation(source_id, positive_match_count=sum(
                item.get("source_id") == source_id and bool(item.get("matched_terms")) for item in ranked))
    return ranked


def _coverage_aware_group_selection(groups, raw_assets, payload):
    """Use source diversity only to choose between equal-relevance candidates."""
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

    chosen = []
    seen_sources = set()
    pending = list(groups)
    while pending and len(chosen) < payload.limit:
        best_score = pending[0].get("relevance_score", 0)
        tied = [group for group in pending if group.get("relevance_score", 0) == best_score]
        # Original ordering remains the tie-breaker after unseen-source count.
        group = max(tied, key=lambda item: len(set(item.get("source_ids", [])) - seen_sources))
        chosen.append(group)
        seen_sources.update(group.get("source_ids", []))
        pending.remove(group)
    return chosen


def prepare_workshop(payload: WorkshopPrepareRequest, *, diagnostics=None) -> dict:
    check_json_budget(payload.model_dump(mode='json'), MAX_WORKSHOP_REQUEST_BYTES,
                      message='This request is too large. Shorten the request or attached instructions.')
    query = build_workshop_query(payload)
    # Keep the normal retrieval invocation unchanged when capture is disabled.
    if diagnostics is None:
        raw_assets = _retrieve_raw_assets(payload=payload)
    else:
        raw_assets = _retrieve_raw_assets(payload=payload, diagnostics=diagnostics)
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
    selected_groups = _coverage_aware_group_selection(groups, raw_assets, payload)
    validate_units(selected_groups, request_scope(payload), selected_assets=payload.asset_ids)
    from app.db.mock_data import sources
    scope_ids = [source["id"] for source in sources
                 if (not payload.source_ids or source["id"] in payload.source_ids)
                 and (payload.library_id is None or source["library_id"] == payload.library_id)]
    retrieval_coverage = {
        "candidate_idea_count": len(groups), "retained_idea_count": len(selected_groups),
        "lexically_matched_asset_count": sum(bool(item.get("matched_terms")) for item in raw_assets),
        "candidate_without_word_matches_asset_count": sum(not item.get("matched_terms") for item in raw_assets),
        "sources": [{"source_id": source_id,
                     "candidate_idea_count": sum(source_id in group["source_ids"] for group in groups),
                     "retained_idea_count": sum(source_id in group["source_ids"] for group in selected_groups),
                     "lexically_matched_asset_count": sum(item.get("source_id") == source_id and bool(item.get("matched_terms")) for item in raw_assets)}
                    for source_id in scope_ids],
    }
    if diagnostics is not None:
        diagnostics.groups(groups, limit=payload.limit, selected_groups=selected_groups)
        for row in retrieval_coverage["sources"]:
            diagnostics.preparation(row["source_id"], retained_group_count=row["retained_idea_count"],
                                    retained_asset_count=sum(item.get("source_id") == row["source_id"]
                                                             for group in selected_groups
                                                             for item in group.get("evidence_trail", [])))
    groups = selected_groups

    by_type = defaultdict(list)
    for group in groups:
        asset_type = group["canonical_asset"].get("asset_type", "unknown")
        by_type[asset_type].append(group)

    prepared = {
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
        "source_coverage": source_coverage(groups, source_ids=scope_ids),
        "retrieval_coverage": retrieval_coverage,
        "evidence_base": evidence_base_state(payload.source_ids, payload.library_id),
        "message": (
            "Workshop preparation complete. Relevant consolidated knowledge is ready "
            "for an output-generation step."
        ),
    }
    validate_preparation(prepared, payload)
    return prepared



def source_coverage(groups, source_ids=None):
    """Preparation progress, distinct from lexical relevance or adequacy."""
    from app.db.mock_data import sources
    from app.services.source_interpretation import get_source_interpretation_summary
    counts = defaultdict(int)
    for group in groups:
        for source_id in set(group["source_ids"]):
            counts[source_id] += 1
    coverage = []
    for source in sources:
        if (source_ids is None and source["id"] not in counts) or (source_ids is not None and source["id"] not in source_ids):
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
    summaries=source_summaries(source_ids=[source['id'] for source in chosen])
    summary_by_id={item.source_id:item for item in summaries}
    for source in chosen:
        try:
            summary = summary_by_id[source['id']]
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

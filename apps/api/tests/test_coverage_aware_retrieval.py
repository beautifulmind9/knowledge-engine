from app.db import mock_data
from app.models.workshop import WorkshopPrepareRequest
from app.services import workshop


def _asset(asset_id, source_id, text, score, terms):
    return {
        "id": asset_id,
        "source_id": source_id,
        "title": text,
        "what_it_says": text,
        "keywords": [],
        "confidence_score": 0.8,
        "relevance_score": score,
        "matched_terms": terms,
        "canonical_asset": {"id": asset_id, "source_id": source_id, "confidence_score": 0.8},
        "asset_ids": [asset_id],
        "source_ids": [source_id],
        "support_count": 1,
    }


def test_multisource_raw_pool_preserves_relevant_candidates_without_importing_irrelevant_sources(monkeypatch):
    source_ids = ["source_a", "source_b", "source_c", "source_irrelevant"]
    monkeypatch.setattr(mock_data, "sources", [
        {"id": source_id, "library_id": "library_test", "title": source_id}
        for source_id in source_ids
    ])
    monkeypatch.setattr(mock_data, "libraries", [{"id": "library_test"}])
    assets = [
        {"id": f"a_{index}", "source_id": "source_a", "title": "Audience positioning", "what_it_says": "Audience positioning and customer choice"}
        for index in range(100)
    ]
    assets += [
        {"id": "b_1", "source_id": "source_b", "title": "Audience positioning", "what_it_says": "Audience positioning and customer choice"},
        {"id": "c_1", "source_id": "source_c", "title": "Audience positioning", "what_it_says": "Audience positioning and customer choice"},
        {"id": "i_1", "source_id": "source_irrelevant", "title": "Garden soil", "what_it_says": "Watering garden soil"},
    ]
    def list_assets(source_id=None, source_ids=None):
        selected = set(source_ids) if source_ids is not None else None
        return [item for item in assets
                if (selected is None and (source_id is None or item["source_id"] == source_id))
                or (selected is not None and item["source_id"] in selected)]

    monkeypatch.setattr(workshop, "list_knowledge_assets", list_assets)
    payload = WorkshopPrepareRequest(
        situation="Audience positioning for customer choice",
        goal="Compare audience positioning and customer choice",
        output_type="knowledge_answer",
        source_ids=source_ids,
        library_id="library_test",
        limit=8,
    )

    candidates = workshop._retrieve_raw_assets(payload)
    candidate_sources = {item["source_id"] for item in candidates}
    assert "source_a" in candidate_sources
    assert "source_b" in candidate_sources
    assert "source_c" in candidate_sources
    assert "source_irrelevant" not in candidate_sources
    assert len(candidates) <= 40


def test_multi_source_selection_diversifies_comparable_evidence_but_not_irrelevant_material():
    payload = WorkshopPrepareRequest(
        situation="Audience positioning",
        goal="Compare audience positioning",
        output_type="knowledge_answer",
        source_ids=["source_a", "source_b", "source_c", "source_irrelevant"],
        limit=3,
    )
    raw = [
        {"id": f"a_{index}", "source_id": "source_a", "relevance_score": 100, "matched_terms": ["audience"]}
        for index in range(5)
    ] + [
        {"id": "b_1", "source_id": "source_b", "relevance_score": 70, "matched_terms": ["audience"]},
        {"id": "c_1", "source_id": "source_c", "relevance_score": 60, "matched_terms": ["audience"]},
        {"id": "i_1", "source_id": "source_irrelevant", "relevance_score": 0, "matched_terms": []},
    ]
    groups = [
        {"asset_ids": [item["id"]], "source_ids": [item["source_id"]], "relevance_score": item["relevance_score"], "support_count": 1, "canonical_asset": {"id": item["id"], "confidence_score": 0.8}}
        for item in raw
    ]
    selected = workshop._coverage_aware_group_selection(groups, raw, payload)
    selected_sources = {group["source_ids"][0] for group in selected}
    assert selected_sources == {"source_a", "source_b", "source_c"}


def test_single_source_retrieval_keeps_existing_global_ranking():
    payload = WorkshopPrepareRequest(
        situation="A broad source question",
        goal="What does this source teach?",
        output_type="knowledge_answer",
        source_ids=["source_a"],
        limit=2,
    )
    raw = [_asset(f"a_{index}", "source_a", f"Idea {index}", 100-index, ["idea"]) for index in range(4)]
    groups = [
        {"asset_ids": item["asset_ids"], "source_ids": item["source_ids"], "relevance_score": item["relevance_score"], "support_count": 1, "canonical_asset": item["canonical_asset"]}
        for item in raw
    ]
    selected = workshop._coverage_aware_group_selection(groups, raw, payload)
    assert [group["asset_ids"] for group in selected] == [["a_0"], ["a_1"]]

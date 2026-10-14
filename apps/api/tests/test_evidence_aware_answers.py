import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.models.workshop_generation import WorkshopGenerateRequest
from app.services import ai_gateway, workshop, workshop_generation


def _prepared(source_ids=("source_a", "source_b")):
    units = []
    for index, source_id in enumerate(source_ids):
        asset_id = f"asset_{index + 1}"
        units.append({
            "asset_id": asset_id,
            "asset_ids": [asset_id],
            "source_id": source_id,
            "source_ids": [source_id],
            "chunk_ids": [f"chunk_{index + 1}"],
            "title": f"Idea {index + 1}",
            "what_it_says": "Give customers a clear reason to join.",
            "canonical_asset": {
                "id": asset_id, "source_id": source_id, "asset_type": "principle",
                "title": f"Idea {index + 1}", "what_it_says": "Give customers a clear reason to join.",
                "evidence": "Offer a meaningful reason to join.",
            },
            "evidence_trail": [{"source_id": source_id, "chunk_id": f"chunk_{index + 1}", "evidence": "Offer a meaningful reason to join."}],
        })
    return {
        "brief": {"situation": "Prepare a launch strategy", "goal": "Attract cinnamon-roll buyers", "source_ids": list(source_ids), "constraints": []},
        "knowledge_unit_count": len(units),
        "knowledge_units": units,
        "synthesis_context": {"agreements": [], "tensions": [], "limitations": "No deterministic contradiction was found."},
    }


def _answer():
    return {
        "title": "A grounded launch direction",
        "introduction": "Use the available sources as evidence, not a fixed recipe.",
        "sections": [
            {"kind": "source_principle", "heading": "Give a meaningful reason to join", "content": "A clear benefit can support list growth.", "evidence_refs": ["asset_1"]},
            {"kind": "source_tactic", "heading": "The source example", "content": "One source describes a three-email sequence.", "evidence_refs": ["asset_1"]},
            {"kind": "mechanism", "heading": "The mechanism", "content": "The sequence develops interest over time; email is the source's delivery choice.", "evidence_refs": ["asset_1"]},
            {"kind": "interpretation", "heading": "A launch-specific interpretation", "content": "Early access to limited preorder drops may fit this business better than a generic newsletter.", "evidence_refs": ["asset_1"]},
            {"kind": "assumption", "heading": "What remains uncertain", "content": "Local customers may value early access enough to share contact details.", "evidence_refs": []},
            {"kind": "experiment", "heading": "A small test", "content": "Compare a list invitation with an early-access invitation.", "evidence_refs": []},
            {"kind": "disagreement", "heading": "A source tension", "content": "The sources emphasize different starting points; preserve that difference and test what fits the audience.", "evidence_refs": ["asset_1", "asset_2"]},
        ],
        "applied_knowledge": [
            {"asset_id": "asset_1", "usage_note": "Supports the source principle and tactic."},
            {"asset_id": "asset_2", "usage_note": "Provides a contrasting source perspective."},
        ],
        "design_choices": ["Early access is a contextual option, not a source-prescribed tactic."],
    }


def _payload():
    return WorkshopGenerateRequest(
        situation="A pre-launch cinnamon-roll business wants to attract buyers.",
        goal="Build an audience of likely customers before preorder drops.",
        audience="Local cinnamon-roll buyers in Jamaica",
        output_type="knowledge_answer",
        source_ids=["source_a", "source_b"],
        save=False,
    )


def test_grounded_answer_uses_dedicated_schema_and_keeps_reasoning_claims_distinct(monkeypatch):
    calls = []
    monkeypatch.setattr(ai_gateway, "generate", lambda model, data, schema: (calls.append((data, schema)) or SimpleNamespace(output_text=json.dumps(_answer()), id="synthetic-response")))
    monkeypatch.setattr(workshop, "evidence_base_state", lambda *_: {"selected_count": 2, "selected_source_ids": ["source_a", "source_b"], "ready_count": 1, "preparing_count": 1, "attention_count": 0, "unavailable_count": 0})

    result = workshop_generation.generate_workshop_output(_payload(), prepared=_prepared())

    assert len(calls) == 1
    instructions = calls[0][0]["instructions"]
    assert "source_principle or source_tactic" in instructions
    assert "objective, intended audience and operating context" in instructions
    assert "Do not manufacture consensus" in instructions
    assert "delivery channel" in instructions
    assert "Selection alone is not evidence" in instructions
    assert "Avoid unsupported exact counts" in instructions
    assert result["output"]["reasoning_sections"][0]["kind"] == "source_principle"
    assert result["output"]["reasoning_sections"][4]["supporting_asset_ids"] == []
    assert "**Source principle:**" in result["output"]["content"]
    assert "**KE interpretation:**" in result["output"]["content"]
    assert result["evidence_base"] == {"selected_count": 2, "selected_source_ids": ["source_a", "source_b"], "ready_count": 1, "preparing_count": 1, "attention_count": 0, "unavailable_count": 0}
    assert result["evidence_coverage"]["retrieved_source_ids"] == ["source_a", "source_b"]
    assert result["evidence_coverage"]["used_source_ids"] == ["source_a", "source_b"]
    assert result["evidence_coverage"]["selected_count"] == 2


def test_selected_retrieved_and_cited_source_coverage_are_distinct(monkeypatch):
    answer = _answer()
    answer["sections"] = [{
        "kind": "source_principle", "heading": "One source finding",
        "content": "A clear invitation can support customer interest.", "evidence_refs": ["asset_1"],
    }]
    answer["applied_knowledge"] = [{"asset_id": "asset_1", "usage_note": "Supports this finding."}]
    monkeypatch.setattr(ai_gateway, "generate", lambda *args: SimpleNamespace(output_text=json.dumps(answer), id="synthetic-response"))
    monkeypatch.setattr(workshop, "evidence_base_state", lambda *_: {
        "selected_count": 11, "selected_source_ids": [f"source_{index}" for index in range(11)],
        "ready_count": 9, "preparing_count": 2, "attention_count": 0, "unavailable_count": 0,
    })

    result = workshop_generation.generate_workshop_output(_payload(), prepared=_prepared())

    coverage = result["evidence_coverage"]
    assert coverage["selected_count"] == 11
    assert set(coverage["retrieved_source_ids"]) == {"source_a", "source_b"}
    assert coverage["used_source_ids"] == ["source_a"]
    assert coverage["used_idea_count"] == 1
    assert coverage["retrieved_source_count"] == 2
    assert coverage["used_source_count"] == 1


def test_broad_corpus_claim_is_rejected_when_citations_cover_only_part_of_scope(monkeypatch):
    answer = _answer()
    answer["introduction"] = "Across the available materials, the corpus supports this direction."
    calls = []
    monkeypatch.setattr(ai_gateway, "generate", lambda *args: (calls.append(args) or SimpleNamespace(output_text=json.dumps(answer), id="synthetic-response")))
    monkeypatch.setattr(workshop, "evidence_base_state", lambda *_: {
        "selected_count": 11, "selected_source_ids": [f"source_{index}" for index in range(11)],
        "ready_count": 11, "preparing_count": 0, "attention_count": 0, "unavailable_count": 0,
    })

    with pytest.raises(workshop_generation.GroundedAnswerValidationError, match="broader source coverage"):
        workshop_generation.generate_workshop_output(_payload(), prepared=_prepared())
    assert len(calls) == 1


def test_broad_claim_is_allowed_when_complete_selected_scope_is_cited(monkeypatch):
    answer = _answer()
    answer["introduction"] = "Across the selected sources, both support a clear invitation."
    monkeypatch.setattr(ai_gateway, "generate", lambda *args: SimpleNamespace(output_text=json.dumps(answer), id="synthetic-response"))
    monkeypatch.setattr(workshop, "evidence_base_state", lambda *_: {
        "selected_count": 2, "selected_source_ids": ["source_a", "source_b"],
        "ready_count": 2, "preparing_count": 0, "attention_count": 0, "unavailable_count": 0,
    })

    result = workshop_generation.generate_workshop_output(_payload(), prepared=_prepared())

    assert result["evidence_coverage"]["used_source_ids"] == ["source_a", "source_b"]


def test_single_source_broad_question_keeps_representative_retrieval():
    from app.models.workshop import WorkshopPrepareRequest

    payload = WorkshopPrepareRequest(
        situation="Explain this",
        goal="What is here?",
        output_type="knowledge_answer",
        source_ids=["source_a"],
    )
    asset = {"id": "asset_single", "source_id": "source_a", "title": "Reflection", "what_it_says": "Reflection can help."}
    monkeypatch = pytest.MonkeyPatch()
    try:
        from app.db import mock_data
        monkeypatch.setattr(mock_data, "sources", [{"id": "source_a", "library_id": "library_a", "title": "Material"}])
        monkeypatch.setattr(mock_data, "libraries", [{"id": "library_a"}])
        monkeypatch.setattr(workshop, "list_knowledge_assets", lambda source_id=None: [asset])
        result = workshop._retrieve_raw_assets(payload)
    finally:
        monkeypatch.undo()
    assert len(result) == 1
    assert result[0]["relevance_score"] == 1


def test_answer_rejects_unprovided_asset_reference_without_retry(monkeypatch):
    answer = _answer()
    answer["sections"][0]["evidence_refs"] = ["asset_not_supplied"]
    calls = []
    monkeypatch.setattr(ai_gateway, "generate", lambda *args: (calls.append(args) or SimpleNamespace(output_text=json.dumps(answer), id="synthetic-response")))

    with pytest.raises(RuntimeError, match="not supplied"):
        workshop_generation.generate_workshop_output(_payload(), prepared=_prepared())
    assert len(calls) == 1


def test_answer_rejects_cross_source_disagreement_without_two_distinct_sources(monkeypatch):
    answer = _answer()
    answer["sections"][-1]["evidence_refs"] = ["asset_1"]
    calls = []
    monkeypatch.setattr(ai_gateway, "generate", lambda *args: (calls.append(args) or SimpleNamespace(output_text=json.dumps(answer), id="synthetic-response")))

    with pytest.raises(RuntimeError, match="distinct materials"):
        workshop_generation.generate_workshop_output(_payload(), prepared=_prepared(("source_a", "source_a")))
    assert len(calls) == 1


def test_cross_source_agreement_is_accepted_only_with_distinct_material_evidence(monkeypatch):
    answer = _answer()
    answer["sections"][-1] = {
        "kind": "agreement", "heading": "Both sources value a clear invitation",
        "content": "Each source supports making the next step understandable.",
        "evidence_refs": ["asset_1", "asset_2"],
    }
    calls = []
    monkeypatch.setattr(ai_gateway, "generate", lambda *args: (calls.append(args) or SimpleNamespace(output_text=json.dumps(answer), id="synthetic-response")))

    result = workshop_generation.generate_workshop_output(_payload(), prepared=_prepared())

    assert len(calls) == 1
    assert result["output"]["reasoning_sections"][-1]["kind"] == "agreement"


def test_invalid_structured_answer_fails_locally_after_one_attempt(monkeypatch):
    malformed = {"title": "Incomplete", "introduction": "", "sections": [{"kind": "invented_kind", "heading": "Unsupported", "content": "This should fail.", "evidence_refs": []}], "applied_knowledge": [], "design_choices": []}
    calls = []
    monkeypatch.setattr(ai_gateway, "generate", lambda *args: (calls.append(args) or SimpleNamespace(output_text=json.dumps(malformed), id="synthetic-response")))
    with pytest.raises(Exception):
        workshop_generation.generate_workshop_output(_payload(), prepared=_prepared())
    assert len(calls) == 1


def test_invalid_grounded_answer_has_safe_http_response_and_is_not_saved(monkeypatch):
    from app.routers.workshop_output import generate_workshop
    from app.services import outputs

    invalid = _answer()
    invalid["sections"][0]["kind"] = "invented_kind"
    calls = []
    saves = []
    monkeypatch.setattr(ai_gateway, "generate", lambda *args: (calls.append(args) or SimpleNamespace(output_text=json.dumps(invalid), id="synthetic")))
    monkeypatch.setattr(workshop_generation, "prepare_workshop", lambda *_: _prepared())
    monkeypatch.setattr(outputs, "save_output", lambda result: saves.append(result))

    with pytest.raises(HTTPException) as response:
        generate_workshop(_payload().model_copy(update={"save": True}))
    assert response.value.status_code == 502
    assert response.value.detail == "The AI response could not be validated. No answer was saved."
    assert len(calls) == 1
    assert saves == []


def test_evidence_base_state_counts_ready_preparing_attention_and_unknown(monkeypatch):
    from app.db import mock_data
    from app.services import source_summary

    monkeypatch.setattr(mock_data, "sources", [*mock_data.sources,
        {"id": "s_ready", "library_id": "lib", "title": "Ready"},
        {"id": "s_preparing", "library_id": "lib", "title": "Preparing"},
        {"id": "s_attention", "library_id": "lib", "title": "Attention"},
        {"id": "s_unknown", "library_id": "lib", "title": "Unknown"},
    ])
    states = {
        "s_ready": SimpleNamespace(readiness="ready", attention_category=None),
        "s_preparing": SimpleNamespace(readiness="partly_ready", attention_category=None),
        "s_attention": SimpleNamespace(readiness="partly_ready", attention_category="build_stopped"),
        "s_unknown": SimpleNamespace(readiness="unknown", attention_category="artifact_unavailable"),
    }
    monkeypatch.setattr(source_summary, "source_summaries", lambda source_id: [states[source_id]])

    assert workshop.evidence_base_state([], "lib") == {
        "selected_count": 4, "selected_source_ids": ["s_ready", "s_preparing", "s_attention", "s_unknown"], "ready_count": 1, "preparing_count": 1,
        "attention_count": 1, "unavailable_count": 1,
    }

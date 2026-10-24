"""Verified coverage is context, never an offline semantic sufficiency verdict."""
from copy import deepcopy
import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.models.workshop_generation import WorkshopGenerateRequest
from app.services import ai_gateway, workshop, workshop_generation


def snapshot():
    return {
        "brief": {"situation": "Compare audience research", "goal": "Understand the evidence", "constraints": []},
        "knowledge_unit_count": 2,
        "knowledge_units": [
            {
                "canonical_asset": {"id": "asset_a", "source_id": "source_a", "asset_type": "principle",
                                    "title": "Audience relationships", "what_it_says": "Relationships depend on context.",
                                    "evidence": "Relationships depend on context."},
                "asset_ids": ["asset_a", "asset_b"], "source_ids": ["source_a", "source_b"],
                "support_count": 2, "chunk_ids": ["chunk_a", "chunk_b"],
                "evidence_trail": [
                    {"asset_id": "asset_a", "source_id": "source_a", "chunk_id": "chunk_a", "evidence": "Relationships depend on context."},
                    {"asset_id": "asset_b", "source_id": "source_b", "chunk_id": "chunk_b", "evidence": "The relationship is contextual."},
                ],
            },
            {
                "canonical_asset": {"id": "asset_c", "source_id": "source_c", "asset_type": "principle",
                                    "title": "A separate finding", "what_it_says": "A separate finding has limitations.",
                                    "evidence": "A separate finding has limitations."},
                "asset_ids": ["asset_c"], "source_ids": ["source_c"], "chunk_ids": ["chunk_c"],
                "evidence_trail": [{"asset_id": "asset_c", "source_id": "source_c", "chunk_id": "chunk_c", "evidence": "A separate finding has limitations."}],
            },
        ],
        "evidence_base": {
            "selected_count": 4, "selected_source_ids": ["source_a", "source_b", "source_c", "source_d"],
            "ready_count": 1, "preparing_count": 1, "attention_count": 1, "unavailable_count": 1,
        },
    }


def request(mode):
    return WorkshopGenerateRequest(
        situation="Compare audience research", goal="Understand the evidence",
        output_type=mode, source_ids=["source_a", "source_b", "source_c", "source_d"], save=False,
    )


def response(mode):
    output = {"title": "A limited finding", "applied_knowledge": [{"asset_id": "asset_a", "usage_note": "Frames one contextual finding."}], "design_choices": []}
    if mode == "knowledge_answer":
        output.update(introduction="", sections=[{"kind": "source_principle", "heading": "A contextual finding", "content": "Relationships depend on context.", "evidence_refs": ["asset_b"]}])
    else:
        output.update(output_type=mode, content="Synthesis: relationships depend on context. Supporting ideas: one finding. Gaps: context and causal evidence remain unknown.")
    return SimpleNamespace(output_text=json.dumps(output), id="synthetic-response")


@pytest.mark.parametrize("mode", ["knowledge_answer", "research_synthesis"])
def test_research_context_exposes_preparation_without_claiming_sufficiency(monkeypatch, mode):
    prepared = snapshot()
    original_units = deepcopy(prepared["knowledge_units"])
    calls = []
    monkeypatch.setattr(ai_gateway, "generate", lambda *args: (calls.append(args) or response(mode)))
    monkeypatch.setattr(workshop, "evidence_base_state", lambda *_: prepared["evidence_base"])

    result = workshop_generation.generate_workshop_output(request(mode), prepared=prepared)

    assert len(calls) == 1
    provider_input, provider_schema = calls[0][1:]
    assert provider_input["evidence_base"] == prepared["evidence_base"]
    assert provider_input["evidence_base_basis"] == "preparation_snapshot"
    assert provider_input["retrieval_coverage"]["retained_source_ids"] == ["source_a", "source_b", "source_c"]
    assert provider_input["retrieval_coverage"]["retained_idea_count"] == 2
    assert "do not infer empirical quality or independent studies" in provider_input["instructions"]
    assert "evidence_base" not in provider_schema["properties"]
    assert result["evidence_base"] == prepared["evidence_base"]
    assert result["evidence_base_basis"] == "preparation_snapshot"
    coverage = result["evidence_coverage"]
    assert coverage["selected_count"] == 4
    assert coverage["retrieved_source_count"] == 3
    assert coverage["applied_source_count"] == coverage["applied_idea_count"] == 1
    assert coverage["applied_source_ids"] == ["source_a"]
    if mode == "knowledge_answer":
        assert coverage["section_cited_source_ids"] == coverage["used_source_ids"] == ["source_b"]
    else:
        assert "section_cited_source_count" not in coverage
        assert "used_source_count" not in coverage
    assert "do not establish relevance" in result["research_limitations"]
    assert "unprepared material is unknown" in result["research_limitations"]
    assert result["retrieval_coverage"]["retained_match_status_unknown_idea_count"] == 2
    assert prepared["knowledge_units"] == original_units == result["knowledge_snapshot"]


def test_legacy_synthesis_snapshot_collects_only_requested_scope(monkeypatch):
    prepared = snapshot()
    base = prepared.pop("evidence_base")
    scopes = []
    monkeypatch.setattr(workshop, "evidence_base_state", lambda *args: (scopes.append(args) or base))
    monkeypatch.setattr(ai_gateway, "generate", lambda *_: response("research_synthesis"))

    result = workshop_generation.generate_workshop_output(request("research_synthesis"), prepared=prepared)

    assert scopes == [(["source_a", "source_b", "source_c", "source_d"], None)]
    assert result["evidence_base"] == base
    assert result["evidence_base_basis"] == "generation_preflight"
    assert "sufficient" not in result["evidence_coverage"]


@pytest.mark.parametrize("mode", ["knowledge_answer", "research_synthesis"])
def test_retained_word_match_status_is_not_reconstructed_for_legacy_units(monkeypatch, mode):
    prepared = snapshot()
    prepared["knowledge_units"][0]["matched_terms"] = ["audience"]
    prepared["knowledge_units"][1]["matched_terms"] = []
    prepared["retrieval_coverage"] = {
        "candidate_idea_count": 5,
        "sources": [{"source_id": "source_d", "candidate_idea_count": 0, "retained_idea_count": 0}],
    }
    calls = []
    monkeypatch.setattr(ai_gateway, "generate", lambda *args: (calls.append(args) or response(mode)))
    monkeypatch.setattr(workshop, "evidence_base_state", lambda *_: prepared["evidence_base"])

    result = workshop_generation.generate_workshop_output(request(mode), prepared=prepared)

    coverage = result["retrieval_coverage"]
    assert coverage["candidate_idea_count"] == 5
    assert coverage["retained_word_matched_idea_count"] == 1
    assert coverage["retained_without_word_matches_idea_count"] == 1
    assert coverage["retained_match_status_unknown_idea_count"] == 0
    assert coverage["sources"] == prepared["retrieval_coverage"]["sources"]
    assert calls[0][1]["retrieval_coverage"] == coverage
    assert "rather than evidence of relevance" in coverage["limitations"]


def test_ask_reports_snapshot_readiness_separately_from_validation_readiness(monkeypatch):
    prepared = snapshot()
    changed = {**prepared["evidence_base"], "ready_count": 4,
               "preparing_count": 0, "attention_count": 0, "unavailable_count": 0}
    monkeypatch.setattr(ai_gateway, "generate", lambda *_: response("knowledge_answer"))
    monkeypatch.setattr(workshop, "evidence_base_state", lambda *_: changed)

    result = workshop_generation.generate_workshop_output(request("knowledge_answer"), prepared=prepared)

    assert result["evidence_base"] == prepared["evidence_base"]
    assert result["evidence_base_at_validation"] == changed
    assert result["evidence_base"]["ready_count"] == 1
    assert result["evidence_base_at_validation"]["ready_count"] == 4


@pytest.mark.parametrize("changed_scope", [False, True])
def test_inconsistent_prepared_scope_is_rejected_before_later_readiness_can_hide_it(monkeypatch, changed_scope):
    prepared = snapshot()
    prepared["evidence_base"] = {
        "selected_count": 1, "selected_source_ids": ["source_b"],
        "ready_count": int(changed_scope), "preparing_count": int(not changed_scope),
        "attention_count": 0, "unavailable_count": 0,
    }
    live = {**prepared["evidence_base"], "ready_count": 1, "preparing_count": 0}
    if changed_scope:
        live["selected_source_ids"] = ["source_new"]
    generated = json.loads(response("knowledge_answer").output_text)
    generated["introduction"] = "Across the selected sources, the evidence is contextual."
    calls = []
    monkeypatch.setattr(ai_gateway, "generate", lambda *args: (calls.append(args) or SimpleNamespace(output_text=json.dumps(generated))))
    monkeypatch.setattr(workshop, "evidence_base_state", lambda *_: live)

    # The retained groups include A/B/C, while this supplied snapshot declares
    # only B selected. Reject before dispatch, even if later readiness is ready.
    with pytest.raises(HTTPException) as error:
        workshop_generation.generate_workshop_output(request("knowledge_answer"), prepared=prepared)
    assert error.value.status_code == 409
    assert calls == []


class Unavailable(Exception):
    status_code = code = 503


@pytest.mark.parametrize("mode", ["knowledge_answer", "research_synthesis"])
def test_workshop_provider_503_stops_after_one_attempt_and_restores_default(monkeypatch, caplog, mode):
    """Exercise the real gateway against a fake SDK, including context cleanup."""
    monkeypatch.setenv("GEMINI_API_KEY", "synthetic-key")
    monkeypatch.setenv("GEMINI_FREE_TIER_CONFIRMED", "true")
    monkeypatch.setattr("app.services.knowledge_extraction.persist_state", lambda: None)
    calls, sleeps = [], []
    outcomes = iter([Unavailable(), Unavailable(), SimpleNamespace(output_text="ok")])
    monkeypatch.setattr(ai_gateway.time, "sleep", sleeps.append)
    caplog.set_level("INFO", logger=ai_gateway.__name__)

    class FakeClient:
        def __init__(self, **kwargs):
            assert kwargs["http_options"]["retry_options"]["attempts"] == 1
            self.interactions = self
            self.sdk_configuration = SimpleNamespace(retry_config=SimpleNamespace(strategy="default"))

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def create(self, **kwargs):
            assert self.sdk_configuration.retry_config.strategy == "none"
            calls.append(kwargs)
            outcome = next(outcomes)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

    monkeypatch.setattr(ai_gateway.genai, "Client", FakeClient)
    with pytest.raises(HTTPException) as error:
        workshop_generation.generate_workshop_output(request(mode), prepared=snapshot())
    assert error.value.status_code == 502
    assert error.value.headers["X-KE-Interruption-Category"] == "provider_unavailable"
    assert len(calls) == ai_gateway.status()["calls_today"] == 1
    assert sleeps == []
    first = [json.loads(record.getMessage().split(": ", 1)[1]) for record in caplog.records
             if record.getMessage().startswith("Gemini provider attempt admitted: ")]
    assert first[0]["max_attempts"] == 1
    assert ai_gateway.generate("synthetic-model", {}, {"type": "object"}).output_text == "ok"
    assert len(calls) == ai_gateway.status()["calls_today"] == 3
    assert sleeps == [ai_gateway._TRANSIENT_503_RETRY_DELAY_SECONDS]

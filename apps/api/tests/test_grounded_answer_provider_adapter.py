import json
from typing import get_args

import pytest
from pydantic import ValidationError

from app.models.grounded_answer_provider import grounded_answer_provider_schema
from app.models.workshop_generation import GroundedAnswerDocument, GroundedAnswerSection
from app.services.workshop_generation import _adapt_grounded_answer_provider_json


def _provider_answer(**overrides):
    answer = {
        "title": "A supported answer",
        "introduction": "",
        "sections": [{
            "kind": "source_principle",
            "heading": "The principle",
            "content": "A grounded explanation.",
            "evidence_refs": ["asset_a"],
        }],
        "applied_knowledge": [{"asset_id": "asset_a", "usage_note": "Supports the explanation."}],
        "design_choices": [],
    }
    answer.update(overrides)
    return answer


def test_every_internal_reasoning_kind_maps_through_plain_provider_string():
    kinds = get_args(GroundedAnswerSection.model_fields["kind"].annotation)
    sections = [{
        "kind": kind,
        "heading": f"Section for {kind}",
        "content": "Synthetic content for local adapter coverage.",
        "evidence_refs": [],
    } for kind in kinds]
    result = _adapt_grounded_answer_provider_json(
        json.dumps(_provider_answer(sections=sections)), {"asset_a"}, {"asset_a"},
    )
    assert [section.kind for section in result.reasoning_sections] == list(kinds)
    assert all(section.supporting_asset_ids == [] for section in result.reasoning_sections)


def test_empty_introduction_and_optional_reasoning_categories_are_valid():
    result = _adapt_grounded_answer_provider_json(json.dumps(_provider_answer()), {"asset_a"}, {"asset_a"})
    assert result.introduction is None
    assert len(result.reasoning_sections) == 1
    assert result.design_choices == []


def test_unknown_kind_is_rejected_locally():
    answer = _provider_answer(sections=[{
        "kind": "invented_kind", "heading": "Unsupported", "content": "Synthetic content.", "evidence_refs": [],
    }])
    with pytest.raises(RuntimeError, match="unsupported answer section"):
        _adapt_grounded_answer_provider_json(json.dumps(answer), {"asset_a"}, {"asset_a"})


def test_unavailable_evidence_and_noncanonical_applied_references_are_rejected():
    answer = _provider_answer(sections=[{
        "kind": "source_principle", "heading": "Unsupported evidence", "content": "Synthetic content.",
        "evidence_refs": ["asset_other"],
    }])
    with pytest.raises(RuntimeError, match="knowledge that was not supplied"):
        _adapt_grounded_answer_provider_json(json.dumps(answer), {"asset_a"}, {"asset_a"})

    with pytest.raises(RuntimeError, match="not supplied to the Workshop"):
        _adapt_grounded_answer_provider_json(json.dumps(_provider_answer(
            applied_knowledge=[{"asset_id": "asset_other", "usage_note": "Unresolvable."}],
        )), {"asset_a"}, {"asset_a"})


def test_provider_identity_text_is_not_part_of_the_contract():
    properties = grounded_answer_provider_schema()["properties"]
    assert set(properties) == {"title", "introduction", "sections", "applied_knowledge", "design_choices"}
    assert "author" not in properties and "source_title" not in properties and "location" not in properties


def test_internal_answer_model_still_rejects_unknown_fields_after_adapter():
    with pytest.raises(ValidationError):
        GroundedAnswerDocument.model_validate({
            "title": "A supported answer",
            "introduction": None,
            "reasoning_sections": [{
                "kind": "analysis", "heading": "Analysis", "content": "A grounded explanation.",
                "supporting_asset_ids": [],
            }],
            "applied_knowledge": [{"asset_id": "asset_a", "usage_note": "Supports the explanation."}],
            "design_choices": [],
            "unexpected": "rejected",
        })

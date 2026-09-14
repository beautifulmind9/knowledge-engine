import json

import pytest
from pydantic import ValidationError

from app.models.knowledge_extraction import (
    KnowledgeExtractionBatchGroup,
    KnowledgeExtractionBatchResponse,
    gemini_batch_response_schema,
)
from app.services.batch_knowledge_extraction import (
    _candidate_assets_for_group,
    gemini_batch_schema_size,
)


def test_gemini_batch_schema_is_minimal_and_has_no_asset_grammar():
    provider_schema = gemini_batch_response_schema()
    encoded = json.dumps(provider_schema, ensure_ascii=False)
    strict_encoded = json.dumps(
        KnowledgeExtractionBatchResponse.model_json_schema(), ensure_ascii=False
    )

    assert len(encoded) == gemini_batch_schema_size()
    assert len(encoded) <= 800, (
        f"Provider batch schema grew to {len(encoded)} chars; expected a minimal routing envelope."
    )
    assert len(encoded) < len(strict_encoded) / 10
    for keyword in ("$defs", "$ref", "oneOf", "anyOf", "discriminator"):
        assert keyword not in encoded

    item_schema = provider_schema["properties"]["results"]["items"]
    assert item_schema["required"] == ["chunk_id", "assets_json"]
    assert set(item_schema["properties"]) == {"chunk_id", "assets_json"}
    assert item_schema["properties"]["assets_json"]["type"] == "string"
    # Asset fields belong to Knowledge Engine's local validator, not Gemini's
    # serving grammar.
    for field in ("asset_type", "action", "steps", "components", "source_id"):
        assert field not in encoded


def test_assets_json_is_decoded_before_strict_validation():
    candidate = {
        "asset_type": "principle",
        "title": "A principle",
        "what_it_says": "Use a supported practice.",
        "evidence": "Use a supported practice.",
        "keywords": ["practice"],
        "confidence_score": 4,
    }
    decoded = _candidate_assets_for_group(
        {"chunk_id": "chunk_1", "assets_json": json.dumps([candidate])}
    )
    assert decoded == [candidate]


@pytest.mark.parametrize("raw", ["not json", "{}", "null", '"string"'])
def test_assets_json_must_decode_to_an_array(raw):
    with pytest.raises(ValueError):
        _candidate_assets_for_group({"chunk_id": "chunk_1", "assets_json": raw})


def test_minimal_provider_schema_does_not_weaken_strict_internal_asset_validation():
    invalid_concept = {
        "chunk_id": "chunk_1",
        "assets": [
            {
                "asset_type": "concept",
                "source_id": "source_1",
                "chunk_id": "chunk_1",
                "title": "A concept",
                "what_it_says": "A source-supported concept.",
                "evidence": "A source-supported concept.",
                "keywords": ["concept"],
                "action": "This subtype-only decision-rule field must be rejected.",
            }
        ],
    }

    with pytest.raises(ValidationError):
        KnowledgeExtractionBatchGroup.model_validate(invalid_concept)


def test_minimal_provider_schema_leaves_subtype_requirements_to_strict_validation():
    missing_decision_action = {
        "chunk_id": "chunk_1",
        "assets": [
            {
                "asset_type": "decision_rule",
                "source_id": "source_1",
                "chunk_id": "chunk_1",
                "title": "A rule",
                "what_it_says": "Choose based on a condition.",
                "evidence": "Choose based on a condition.",
                "keywords": ["choice"],
            }
        ],
    }

    with pytest.raises(ValidationError):
        KnowledgeExtractionBatchGroup.model_validate(missing_decision_action)

import json

import pytest
from pydantic import ValidationError

from app.models.knowledge_extraction import (
    GEMINI_BATCH_ASSET_TYPES,
    GEMINI_BATCH_REQUIRED_ASSET_FIELDS,
    KnowledgeExtractionBatchGroup,
    KnowledgeExtractionBatchResponse,
    gemini_batch_response_schema,
)
from app.services.batch_knowledge_extraction import (
    _candidate_assets_for_group,
    gemini_batch_schema_size,
)


def test_gemini_batch_schema_is_flat_superset_without_discriminated_union():
    provider_schema = gemini_batch_response_schema()
    encoded = json.dumps(provider_schema, ensure_ascii=False)
    strict_encoded = json.dumps(
        KnowledgeExtractionBatchResponse.model_json_schema(), ensure_ascii=False
    )

    assert len(encoded) == gemini_batch_schema_size()
    assert len(encoded) <= 5000, (
        f"Provider batch schema grew to {len(encoded)} chars; expected a flat compatibility schema."
    )
    assert len(encoded) < len(strict_encoded)
    for keyword in ("$defs", "$ref", "oneOf", "anyOf", "discriminator"):
        assert keyword not in encoded

    item_schema = provider_schema["properties"]["results"]["items"]
    assert item_schema["required"] == ["chunk_id", "assets"]
    assert set(item_schema["properties"]) == {"chunk_id", "assets"}

    asset_schema = item_schema["properties"]["assets"]["items"]
    assert asset_schema["required"] == GEMINI_BATCH_REQUIRED_ASSET_FIELDS
    assert asset_schema["properties"]["asset_type"]["enum"] == GEMINI_BATCH_ASSET_TYPES

    for field in GEMINI_BATCH_REQUIRED_ASSET_FIELDS:
        assert field in asset_schema["properties"]

    # Subtype-specific fields are visible to Gemini but optional in the flat
    # transport contract; the strict local discriminated models decide whether
    # each one is valid/required for the selected asset_type.
    for field in (
        "action",
        "condition",
        "rationale",
        "steps",
        "components",
        "consequence",
        "prevention",
        "what_happened",
    ):
        assert field in asset_schema["properties"]
        assert field not in asset_schema["required"]

    # Provenance remains system-owned and must never be model-generated at the
    # asset level.
    for field in ("source_id", "chunk_id", "id", "created_at"):
        assert field not in asset_schema["properties"]


def test_provider_assets_are_read_directly_before_strict_validation():
    candidate = {
        "asset_type": "principle",
        "title": "A principle",
        "what_it_says": "Use a supported practice.",
        "evidence": "Use a supported practice.",
        "keywords": ["practice"],
        "confidence_score": 4,
    }
    decoded = _candidate_assets_for_group(
        {"chunk_id": "chunk_1", "assets": [candidate]}
    )
    assert decoded == [candidate]


@pytest.mark.parametrize("raw", ["not json", "{}", "null", '"string"'])
def test_legacy_assets_json_must_decode_to_an_array(raw):
    with pytest.raises(ValueError):
        _candidate_assets_for_group({"chunk_id": "chunk_1", "assets_json": raw})


def test_legacy_assets_json_compatibility_is_local_only():
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

    encoded_provider_schema = json.dumps(gemini_batch_response_schema())
    assert "assets_json" not in encoded_provider_schema


def test_flat_provider_schema_does_not_weaken_strict_internal_asset_validation():
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


def test_flat_provider_schema_leaves_subtype_requirements_to_strict_validation():
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

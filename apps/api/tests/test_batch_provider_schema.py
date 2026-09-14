import json

import pytest
from pydantic import ValidationError

from app.models.knowledge_extraction import (
    KnowledgeExtractionBatchGroup,
    KnowledgeExtractionBatchResponse,
    gemini_batch_response_schema,
)
from app.services.batch_knowledge_extraction import gemini_batch_schema_size


def test_gemini_batch_schema_is_flat_compact_and_has_no_discriminated_union():
    provider_schema = gemini_batch_response_schema()
    encoded = json.dumps(provider_schema, ensure_ascii=False)
    strict_encoded = json.dumps(
        KnowledgeExtractionBatchResponse.model_json_schema(), ensure_ascii=False
    )

    assert len(encoded) == gemini_batch_schema_size()
    assert len(encoded) <= 2000, (
        f"Provider batch schema grew to {len(encoded)} chars; baseline is about 1,603."
    )
    assert len(encoded) < len(strict_encoded) / 5
    for keyword in ("$defs", "$ref", "oneOf", "anyOf", "discriminator"):
        assert keyword not in encoded

    asset_schema = provider_schema["properties"]["results"]["items"]["properties"]["assets"]["items"]
    assert asset_schema["required"] == [
        "asset_type", "title", "what_it_says", "evidence", "keywords"
    ]
    assert "action" in asset_schema["properties"]
    assert "steps" in asset_schema["properties"]
    assert "components" in asset_schema["properties"]
    for system_field in ("id", "created_at", "source_id", "chunk_id"):
        assert system_field not in asset_schema["properties"]


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

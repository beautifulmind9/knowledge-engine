import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.models.knowledge_extraction import KnowledgeExtractionResultSubmission
from app.services.gemini_knowledge_extraction import validate_or_repair_result


def test_invalid_extraction_reports_schema_locations_without_raw_input(monkeypatch):
    monkeypatch.delenv("GEMINI_ALLOW_REPAIR", raising=False)
    raw = json.dumps(
        {
            "assets": [
                {
                    "asset_type": "decision_rule",
                    "title": "Incomplete rule",
                    "what_it_says": "A rule without required grounded fields.",
                    "source_id": "source_test",
                    "chunk_id": "chunk_test",
                }
            ]
        }
    )

    with pytest.raises(RuntimeError) as exc:
        validate_or_repair_result(
            client=None,
            model="test-model",
            request={},
            interaction=SimpleNamespace(output_text=raw),
        )

    message = str(exc.value)
    assert "AI output failed validation:" in message
    assert "assets.0" in message
    assert "No assets saved" in message
    assert "A rule without required grounded fields." not in message


def test_knowledge_asset_schema_is_discriminated_by_asset_type():
    schema = KnowledgeExtractionResultSubmission.model_json_schema()
    asset_schema = schema["properties"]["assets"]["items"]
    assert asset_schema["discriminator"]["propertyName"] == "asset_type"
    assert "warning" in asset_schema["discriminator"]["mapping"]
    assert "decision_rule" in asset_schema["discriminator"]["mapping"]


def test_subtype_fields_do_not_bleed_between_asset_types():
    common = {
        "title": "Keep the schedule realistic",
        "what_it_says": "Avoid overloading the schedule.",
        "source_id": "source_test",
        "chunk_id": "chunk_test",
        "evidence": "Do not cram too much into the schedule.",
        "keywords": ["schedule", "workshop"],
    }

    warning = KnowledgeExtractionResultSubmission.model_validate(
        {
            "assets": [
                {
                    **common,
                    "asset_type": "warning",
                    "consequence": "The workshop becomes rushed.",
                    "prevention": "Cut material before adding more.",
                }
            ]
        }
    )
    assert warning.assets[0].asset_type == "warning"

    with pytest.raises(ValidationError):
        KnowledgeExtractionResultSubmission.model_validate(
            {
                "assets": [
                    {
                        **common,
                        "asset_type": "decision_rule",
                        "action": "Cut material before adding more.",
                        "consequence": "This belongs only on warnings.",
                    }
                ]
            }
        )

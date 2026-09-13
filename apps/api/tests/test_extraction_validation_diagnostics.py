import json
from types import SimpleNamespace

import pytest

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

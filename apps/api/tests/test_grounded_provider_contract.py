import json
from types import SimpleNamespace

from app.models.workshop_generation import (
    GroundedAnswerDocument,
    WorkshopGenerateRequest,
    WorkshopGeneratedOutput,
)
from app.services import knowledge_extraction
from app.services import ai_gateway, workshop, workshop_generation


def _prepared():
    source_id = "source_synthetic"
    asset_id = "asset_synthetic"
    asset = {
        "id": asset_id,
        "source_id": source_id,
        "asset_type": "principle",
        "title": "Synthetic principle",
        "what_it_says": "A synthetic principle for contract testing.",
        "evidence": "Synthetic evidence text only.",
    }
    group = {
        "canonical_asset": asset,
        "asset_id": asset_id,
        "asset_ids": [asset_id],
        "source_id": source_id,
        "source_ids": [source_id],
        "chunk_ids": ["chunk_synthetic"],
        "evidence_trail": [{"source_id": source_id, "chunk_id": "chunk_synthetic", "evidence": "Synthetic evidence text only."}],
    }
    return {
        "brief": {
            "situation": "A synthetic request.",
            "goal": "A synthetic goal.",
            "audience": None,
            "constraints": [],
            "output_type": "general",
            "output_format": None,
            "retrieval_query": "synthetic request goal",
            "source_ids": [source_id],
            "library_id": None,
            "asset_ids": [],
            "limit": 8,
            "tone_or_style": None,
        },
        "knowledge_unit_count": 1,
        "knowledge_units": [group],
        "synthesis_context": {"agreements": [], "tensions": [], "limitations": "Synthetic fixture."},
    }


def _request(output_type):
    return WorkshopGenerateRequest(
        situation="A synthetic request.",
        goal="A synthetic goal.",
        output_type=output_type,
        source_ids=["source_synthetic"],
        save=False,
    )


def _schema_keywords(value):
    schema_keys = {
        "$defs", "$ref", "additionalProperties", "anyOf", "description", "enum",
        "items", "maxItems", "minItems", "properties", "required", "title", "type",
    }
    found = set()

    def visit(item):
        if isinstance(item, dict):
            found.update(key for key in item if key in schema_keys)
            for child in item.values():
                visit(child)
        elif isinstance(item, list):
            for child in item:
                visit(child)

    visit(value)
    return found


def test_service_keeps_ordinary_and_grounded_provider_contracts_distinct(monkeypatch):
    captured = []

    def fake_generate(model, payload, schema):
        captured.append((model, payload, schema))
        if payload["brief"]["output_type"] == "knowledge_answer":
            response = {
                "title": "Synthetic grounded answer",
                "reasoning_sections": [{
                    "kind": "source_principle",
                    "heading": "Synthetic principle",
                    "content": "A synthetic claim supported by the fixture.",
                    "supporting_asset_ids": ["asset_synthetic"],
                }],
                "applied_knowledge": [{"asset_id": "asset_synthetic", "usage_note": "Supports the synthetic claim."}],
                "design_choices": [],
            }
        else:
            response = {
                "title": "Synthetic output",
                "output_type": "general",
                "content": "A synthetic output long enough for local validation.",
                "applied_knowledge": [{"asset_id": "asset_synthetic", "usage_note": "Supports the synthetic output."}],
                "design_choices": [],
            }
        return SimpleNamespace(output_text=json.dumps(response), id="synthetic")

    monkeypatch.setattr(ai_gateway, "generate", fake_generate)
    monkeypatch.setattr(workshop, "evidence_base_state", lambda *_: {"selected_count": 1, "ready_count": 1})

    for output_type in ("general", "knowledge_answer"):
        prepared = _prepared()
        prepared["brief"]["output_type"] = output_type
        workshop_generation.generate_workshop_output(_request(output_type), prepared=prepared)

    assert len(captured) == 2
    assert captured[0][2] == WorkshopGeneratedOutput.model_json_schema()
    assert captured[1][2] == GroundedAnswerDocument.model_json_schema()
    assert "Grounded reasoning requirements" not in captured[0][1]["instructions"]
    assert "Grounded reasoning requirements" in captured[1][1]["instructions"]
    assert captured[0][1]["knowledge_units"] == captured[1][1]["knowledge_units"]


def test_normalized_grounded_schema_contains_only_supported_keywords_and_internal_model_stays_strict():
    schema = ai_gateway._gemini_response_schema(GroundedAnswerDocument.model_json_schema())

    assert _schema_keywords(schema) <= {
        "$defs", "$ref", "additionalProperties", "anyOf", "description", "enum",
        "items", "maxItems", "minItems", "properties", "required", "title", "type",
    }
    serialized = json.dumps(schema)
    assert '"$defs"' in serialized and '"$ref"' in serialized
    assert '"anyOf"' in serialized and '"null"' in serialized
    assert '"enum"' in serialized and '"maxItems"' in serialized
    assert "minLength" not in serialized and "maxLength" not in serialized
    assert "default" not in serialized and "discriminator" not in serialized

    assert GroundedAnswerDocument.model_config["extra"] == "forbid"
    try:
        GroundedAnswerDocument.model_validate({
            "title": "Synthetic",
            "reasoning_sections": [{"kind": "analysis", "heading": "Analysis", "content": "Synthetic."}],
            "applied_knowledge": [{"asset_id": "asset_synthetic", "usage_note": "Synthetic grounding."}],
            "provider_private_field": "rejected",
        })
    except Exception as error:
        assert "provider_private_field" in str(error)
    else:
        raise AssertionError("The internal grounded answer model must reject unexpected fields.")


def test_gateway_builds_documented_interactions_response_format_without_network(monkeypatch):
    calls = []

    class FakeInteractions:
        def __init__(self):
            self.sdk_configuration = SimpleNamespace(retry_config=SimpleNamespace(strategy="none"))

        def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(output_text="{}")

    class FakeClient:
        def __init__(self, **kwargs):
            self.interactions = FakeInteractions()

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    monkeypatch.setattr(ai_gateway.genai, "Client", FakeClient)
    monkeypatch.setattr(knowledge_extraction, "persist_state", lambda: None)
    monkeypatch.setenv("GEMINI_API_KEY", "synthetic-not-a-key")
    monkeypatch.setenv("GEMINI_FREE_TIER_CONFIRMED", "true")
    monkeypatch.setenv("GEMINI_DAILY_CALL_LIMIT", "450")

    synthetic_input = {"instructions": "Synthetic only", "brief": {"question": "placeholder"}}
    normalized = ai_gateway._gemini_response_schema(GroundedAnswerDocument.model_json_schema())
    ai_gateway.generate("synthetic-model", synthetic_input, GroundedAnswerDocument.model_json_schema())

    assert calls == [{
        "model": "synthetic-model",
        "input": json.dumps(synthetic_input, ensure_ascii=False),
        "store": False,
        "response_format": {"type": "text", "mime_type": "application/json", "schema": normalized},
    }]

import json
from types import SimpleNamespace

from app.models.workshop_generation import WorkshopGenerateRequest
from app.services.workshop_generation import (
    build_authorship_guidance,
    generate_workshop_output,
)


def _request(**overrides):
    data = {
        "situation": "Create a short video concept",
        "goal": "Make the piece feel intentional",
        "output_type": "social_content",
        "source_ids": [],
        "asset_ids": [],
        "save": False,
    }
    data.update(overrides)
    return WorkshopGenerateRequest(**data)


def test_authorship_guidance_uses_creator_signals_when_available():
    payload = _request(
        creative_intent="nostalgic and intimate",
        creator_context="personal birthday memory",
        preserve=["handheld movement", "long pause before the final line"],
        avoid=["overly polished commercial pacing"],
    )

    guidance = build_authorship_guidance(payload)

    assert "creator-direction signals are authoritative" in guidance
    assert "Respect explicit preserve and avoid instructions" in guidance
    assert "silently overriding the creator" in guidance


def test_authorship_guidance_does_not_invent_style_without_creator_signals():
    payload = _request()

    guidance = build_authorship_guidance(payload)

    assert "Do not invent one" in guidance
    assert "do not silently collapse the task to a single generic aesthetic or voice" in guidance
    assert "preserve meaningful optionality" in guidance


def test_creator_context_fields_are_optional():
    payload = _request()

    assert payload.creative_intent is None
    assert payload.creator_context is None
    assert payload.preserve == []
    assert payload.avoid == []


def test_creator_direction_reaches_generation_brief(monkeypatch):
    payload = _request(
        creative_intent="nostalgic and intimate",
        creator_context="personal birthday memory",
        preserve=["handheld movement", "long pause before the final line"],
        avoid=["overly polished commercial pacing"],
        tone_or_style="conversational",
    )
    prepared = {
        "brief": {
            "situation": payload.situation,
            "goal": payload.goal,
            "audience": None,
            "constraints": [],
            "output_type": payload.output_type,
            "output_format": None,
        },
        "knowledge_unit_count": 1,
        "knowledge_units": [
            {
                "canonical_asset": {
                    "id": "asset-1",
                    "asset_type": "principle",
                    "title": "Use contrast intentionally",
                    "what_it_says": "Contrast can direct attention.",
                    "why_it_matters": "It changes emphasis.",
                    "chapter_or_section": "Color",
                    "keywords": ["contrast", "attention"],
                    "evidence": "Contrast directs the eye.",
                    "source_id": "source-1",
                },
                "support_count": 1,
                "chunk_ids": ["chunk-1"],
                "source_ids": ["source-1"],
                "asset_ids": ["asset-1"],
                "evidence_trail": [],
            }
        ],
        "synthesis_context": {},
    }
    captured = {}

    def fake_generate(model, model_input, schema):
        captured["model_input"] = model_input
        return SimpleNamespace(
            output_text=json.dumps(
                {
                    "title": "Birthday video direction",
                    "output_type": "social_content",
                    "content": "One possible direction is to preserve the handheld intimacy while using contrast selectively.",
                    "applied_knowledge": [
                        {"asset_id": "asset-1", "usage_note": "Used contrast as an option for directing attention."}
                    ],
                    "design_choices": ["Preserved handheld movement because the creator explicitly asked to keep it."],
                }
            ),
            id="test-response",
        )

    monkeypatch.setattr("app.services.ai_gateway.generate", fake_generate)
    monkeypatch.setattr(
        "app.services.output_modes.quality_report",
        lambda output, brief, knowledge: {"validation_status": "not_evaluated"},
    )

    result = generate_workshop_output(payload, prepared=prepared)
    brief = captured["model_input"]["brief"]

    assert brief["creative_intent"] == "nostalgic and intimate"
    assert brief["creator_context"] == "personal birthday memory"
    assert brief["preserve"] == ["handheld movement", "long pause before the final line"]
    assert brief["avoid"] == ["overly polished commercial pacing"]
    assert brief["tone_or_style"] == "conversational"
    assert result["brief"] == brief

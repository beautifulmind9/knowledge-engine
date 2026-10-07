from app.models.workshop_generation import WorkshopGenerateRequest
from app.services.workshop_generation import build_authorship_guidance


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

import json
import os

from google import genai

from app.models.workshop import WorkshopGenerateRequest, WorkshopGeneratedOutput
from app.services.workshop import prepare_workshop


DEFAULT_MODEL = "gemini-3.1-flash-lite"


def _compact_knowledge_unit(group: dict) -> dict:
    asset = group["canonical_asset"]
    compact = {
        "asset_id": asset.get("id"),
        "asset_type": asset.get("asset_type"),
        "title": asset.get("title"),
        "what_it_says": asset.get("what_it_says"),
        "why_it_matters": asset.get("why_it_matters"),
        "evidence": asset.get("evidence"),
        "support_count": group.get("support_count", 1),
        "source_id": asset.get("source_id"),
        "chunk_ids": group.get("chunk_ids", []),
    }

    for field in (
        "condition",
        "action",
        "rationale",
        "consequence",
        "prevention",
        "steps",
        "components",
        "how_to_apply",
        "when_to_use",
        "when_not_to_use",
        "tradeoffs",
    ):
        value = asset.get(field)
        if value:
            compact[field] = value

    return compact


def generate_workshop_output(payload: WorkshopGenerateRequest) -> dict:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is not configured. Add the existing Gemini API key before generating a Workshop output."
        )

    prepared = prepare_workshop(payload)
    knowledge_units = [
        _compact_knowledge_unit(group)
        for group in prepared["knowledge_units"]
    ]

    if not knowledge_units:
        raise RuntimeError(
            "No relevant knowledge was retrieved for this Workshop request."
        )

    instructions = """You are the output-generation layer for Knowledge Engine.

Turn the user's Workshop brief into the requested useful output using the retrieved knowledge units as the primary knowledge base.

Rules:
1. Produce the requested output, not a summary of the knowledge units.
2. Respect the user's situation, goal, audience, constraints, and output type.
3. Apply the retrieved knowledge where it is relevant; do not force every unit into the output.
4. Do not invent source claims that are absent from the supplied knowledge.
5. You may make ordinary connective or organizational choices needed to assemble the output, but do not introduce unsupported factual claims.
6. Keep the output practical and ready to use.
7. Do not copy long evidence passages. Transform the knowledge into the requested output.
8. Return the IDs of the knowledge assets that materially influenced the output.
9. For each applied asset, briefly state how it shaped the output.
10. If the requested output is a plan, structure it so the user can act on it directly.
"""

    model_input = {
        "instructions": instructions,
        "brief": prepared["brief"],
        "knowledge_units": knowledge_units,
        "output_preferences": {
            "tone_or_style": payload.tone_or_style,
        },
    }

    model = os.getenv("GEMINI_MODEL", DEFAULT_MODEL)
    client = genai.Client(api_key=api_key)
    interaction = client.interactions.create(
        model=model,
        input=json.dumps(model_input, ensure_ascii=False),
        response_format={
            "type": "text",
            "mime_type": "application/json",
            "schema": WorkshopGeneratedOutput.model_json_schema(),
        },
    )

    if not interaction.output_text:
        raise RuntimeError("The AI returned no Workshop output.")

    generated = WorkshopGeneratedOutput.model_validate_json(interaction.output_text)

    available_asset_ids = {
        unit.get("asset_id")
        for unit in knowledge_units
        if unit.get("asset_id")
    }
    for applied in generated.applied_knowledge:
        if applied.asset_id not in available_asset_ids:
            raise RuntimeError(
                "The generated output referenced a knowledge asset that was not supplied to the Workshop."
            )

    return {
        "brief": prepared["brief"],
        "knowledge_unit_count": prepared["knowledge_unit_count"],
        "output": generated.model_dump(mode="json"),
        "provider": "gemini",
        "model": model,
        "model_response_id": getattr(interaction, "id", None),
    }

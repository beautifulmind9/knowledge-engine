"""Conservative Gemini-facing response contract for grounded answers.

This DTO is an external serialization boundary, not a domain model. The
strict GroundedAnswerDocument remains the authoritative internal contract.
"""
from pydantic import BaseModel, ConfigDict


class GroundedAnswerProviderSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Plain text keeps the provider schema free of enums/unions. The adapter
    # validates this value against GroundedAnswerSection's strict Literal.
    kind: str
    heading: str
    content: str
    evidence_refs: list[str]


class GroundedAnswerProviderAppliedKnowledge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    asset_id: str
    usage_note: str


class GroundedAnswerProviderResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    # Empty string represents no introduction, avoiding a nullable union.
    introduction: str
    sections: list[GroundedAnswerProviderSection]
    applied_knowledge: list[GroundedAnswerProviderAppliedKnowledge]
    design_choices: list[str]


def grounded_answer_provider_schema() -> dict:
    """Return a shallow, inline schema using only simple JSON Schema types."""
    section = {
        "type": "object",
        "properties": {
            "kind": {"type": "string"},
            "heading": {"type": "string"},
            "content": {"type": "string"},
            "evidence_refs": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["kind", "heading", "content", "evidence_refs"],
    }
    applied_knowledge = {
        "type": "object",
        "properties": {
            "asset_id": {"type": "string"},
            "usage_note": {"type": "string"},
        },
        "required": ["asset_id", "usage_note"],
    }
    return {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "introduction": {"type": "string"},
            "sections": {"type": "array", "items": section},
            "applied_knowledge": {"type": "array", "items": applied_knowledge},
            "design_choices": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["title", "introduction", "sections", "applied_knowledge", "design_choices"],
    }

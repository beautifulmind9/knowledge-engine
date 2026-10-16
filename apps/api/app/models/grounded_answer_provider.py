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


def grounded_answer_provider_schema(evidence_asset_ids=None, canonical_asset_ids=None) -> dict:
    """Return a shallow schema constrained to this request's supplied asset IDs."""
    evidence_reference = {"type": "string"}
    if evidence_asset_ids is not None:
        evidence_reference["enum"] = sorted(set(evidence_asset_ids))
    applied_reference = {"type": "string"}
    if canonical_asset_ids is not None:
        applied_reference["enum"] = sorted(set(canonical_asset_ids))
    section = {
        "type": "object",
        "properties": {
            "kind": {"type": "string"},
            "heading": {"type": "string"},
            "content": {"type": "string"},
            "evidence_refs": {"type": "array", "items": evidence_reference},
        },
        "required": ["kind", "heading", "content", "evidence_refs"],
    }
    applied_knowledge = {
        "type": "object",
        "properties": {
            "asset_id": applied_reference,
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

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

from app.models.workshop import WorkshopPrepareRequest


class WorkshopGenerateRequest(WorkshopPrepareRequest):
    prepared_snapshot_id: str | None = Field(default=None, min_length=20, max_length=100)
    tone_or_style: str | None = None
    save: bool = True


class AppliedKnowledgeReference(BaseModel):
    asset_id: str
    usage_note: str = Field(min_length=2)


class WorkshopGeneratedOutput(BaseModel):
    title: str = Field(min_length=2)
    output_type: str = Field(min_length=2)
    content: str = Field(min_length=20)
    applied_knowledge: list[AppliedKnowledgeReference] = Field(
        min_length=1,
        description="Knowledge assets that materially grounded the generated output.",
    )
    design_choices: list[str] = Field(
        default_factory=list,
        description=(
            "Generator-created choices or derived recommendations that are useful for "
            "the requested output but are not direct claims from a supplied knowledge asset."
        ),
    )
class GroundedAnswerSection(BaseModel):
    """A readable, evidence-aware section in an Ask & Explore answer."""
    model_config = ConfigDict(extra="forbid")
    kind: Literal[
        "source_principle", "source_tactic", "mechanism", "interpretation",
        "assumption", "experiment", "challenge", "agreement", "disagreement",
        "applicability", "open_question", "analysis",
    ]
    heading: str = Field(min_length=2, max_length=180)
    content: str = Field(min_length=2, max_length=20000)
    supporting_asset_ids: list[str] = Field(default_factory=list, max_length=20)


class GroundedAnswerDocument(BaseModel):
    """Dedicated response shape for grounded questions; never a KnowledgeAsset."""
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=2, max_length=500)
    introduction: str | None = Field(default=None, max_length=4000)
    reasoning_sections: list[GroundedAnswerSection] = Field(min_length=1, max_length=16)
    applied_knowledge: list[AppliedKnowledgeReference] = Field(min_length=1, max_length=20)
    design_choices: list[str] = Field(default_factory=list, max_length=30)

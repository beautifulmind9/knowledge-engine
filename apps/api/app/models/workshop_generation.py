from pydantic import BaseModel, Field

from app.models.workshop import WorkshopPrepareRequest


class WorkshopGenerateRequest(WorkshopPrepareRequest):
    tone_or_style: str | None = None


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

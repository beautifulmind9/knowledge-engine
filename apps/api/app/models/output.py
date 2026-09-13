from datetime import datetime
from pydantic import BaseModel, Field
from app.models.workshop_generation import WorkshopGenerateRequest, WorkshopGeneratedOutput


class OutputRecord(WorkshopGeneratedOutput):
    id: str
    brief: dict
    source_ids: list[str]
    applied_asset_ids: list[str]
    knowledge_snapshot: list[dict]
    provider: str
    model: str | None = None
    created_at: datetime
    updated_at: datetime
    root_output_id: str
    parent_output_id: str | None = None
    version: int = Field(ge=1)
    revision_instruction: str | None = None
    generation_metadata: dict = Field(default_factory=dict)


class RevisionRequest(BaseModel):
    instruction: str = Field(min_length=2, max_length=4000)
    content: str | None = Field(default=None, min_length=20, max_length=100000)
    title: str | None = Field(default=None, min_length=2, max_length=500)
    design_choices: list[str] | None = None


class ManualOutputRequest(BaseModel):
    brief: WorkshopGenerateRequest
    output: WorkshopGeneratedOutput

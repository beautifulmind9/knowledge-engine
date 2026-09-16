from pydantic import BaseModel, Field


class WorkshopPrepareRequest(BaseModel):
    situation: str = Field(min_length=2)
    goal: str = Field(min_length=2)
    audience: str | None = None
    constraints: list[str] = Field(default_factory=list)
    output_type: str = Field(default="general")
    output_format: str | None = None
    source_ids: list[str] = Field(default_factory=list)
    library_id: str | None = None
    asset_ids: list[str] = Field(default_factory=list)
    limit: int = Field(default=8, ge=1, le=20)


class WorkshopBrief(BaseModel):
    situation: str
    goal: str
    audience: str | None = None
    constraints: list[str] = Field(default_factory=list)
    output_type: str
    output_format: str | None = None
    retrieval_query: str

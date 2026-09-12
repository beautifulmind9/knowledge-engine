from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, model_validator


class KnowledgeAssetType(str, Enum):
    """The kinds of reusable knowledge Knowledge Engine can extract."""

    CONCEPT = "concept"
    PROBLEM = "problem"
    PRINCIPLE = "principle"
    INSIGHT = "insight"
    DECISION_RULE = "decision_rule"
    PATTERN = "pattern"
    EXAMPLE = "example"
    WARNING = "warning"
    FRAMEWORK = "framework"
    MENTAL_MODEL = "mental_model"
    PROCESS = "process"


class KnowledgeAsset(BaseModel):
    """A reusable piece of knowledge extracted from a source chunk.

    The common fields preserve the useful structure learned from the
    Made to Stick prototype while keeping each asset small enough to
    retrieve and reuse independently in the Workshop later.
    """

    id: str | None = None
    asset_type: KnowledgeAssetType
    title: str
    what_it_says: str
    why_it_matters: str | None = None

    # Provenance: where this knowledge came from.
    source_id: str
    chunk_id: str
    chapter_or_section: str | None = None
    evidence: str | None = None

    # Application guidance learned from the original prototype.
    how_to_apply: list[str] = Field(default_factory=list)
    when_to_use: list[str] = Field(default_factory=list)
    when_not_to_use: list[str] = Field(default_factory=list)
    tradeoffs: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)

    # Type-specific fields. Only populate the ones that fit the asset.
    condition: str | None = None
    action: str | None = None
    rationale: str | None = None

    consequence: str | None = None
    prevention: str | None = None

    what_happened: str | None = None
    transferable_lesson: str | None = None
    concept_demonstrated: str | None = None

    steps: list[str] = Field(default_factory=list)
    adaptation_notes: str | None = None

    # Confidence remains useful from the prototype. Importance and novelty
    # are intentionally left out for now because they are more subjective.
    confidence_score: int = Field(default=3, ge=1, le=5)

    # System-owned metadata. The application can fill this later.
    created_at: datetime | None = None

    @model_validator(mode="after")
    def validate_type_specific_content(self):
        if self.asset_type == KnowledgeAssetType.DECISION_RULE and not self.action:
            raise ValueError("decision_rule assets must include an action")

        if self.asset_type == KnowledgeAssetType.PROCESS and not self.steps:
            raise ValueError("process assets must include at least one step")

        return self

from datetime import datetime
from typing import Literal, Union

from pydantic import BaseModel, ConfigDict, Field


class BaseKnowledgeAsset(BaseModel):
    """Fields shared by every reusable knowledge asset."""

    model_config = ConfigDict(extra="forbid")

    id: str | None = None
    title: str
    what_it_says: str
    why_it_matters: str | None = None

    # Provenance: where this knowledge came from.
    source_id: str
    chunk_id: str
    chapter_or_section: str | None = None
    evidence: str = Field(
        min_length=1,
        description=(
            "Short source-grounded excerpt or close paraphrase that supports the asset."
        ),
    )

    # Application guidance learned from the Made to Stick prototype.
    how_to_apply: list[str] = Field(default_factory=list)
    when_to_use: list[str] = Field(default_factory=list)
    when_not_to_use: list[str] = Field(default_factory=list)
    tradeoffs: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(
        min_length=1,
        max_length=8,
        description="Grounded retrieval terms for this asset.",
    )

    confidence_score: int = Field(default=3, ge=1, le=5)
    created_at: datetime | None = None


class ConceptKnowledgeAsset(BaseKnowledgeAsset):
    asset_type: Literal["concept"]


class ProblemKnowledgeAsset(BaseKnowledgeAsset):
    asset_type: Literal["problem"]


class PrincipleKnowledgeAsset(BaseKnowledgeAsset):
    asset_type: Literal["principle"]


class InsightKnowledgeAsset(BaseKnowledgeAsset):
    asset_type: Literal["insight"]


class DecisionRuleKnowledgeAsset(BaseKnowledgeAsset):
    """A decision rule says when a choice applies and what to do."""

    asset_type: Literal["decision_rule"]
    condition: str | None = None
    action: str = Field(
        min_length=1,
        description="Concrete behavior or choice recommended by the rule.",
    )
    rationale: str | None = None


class PatternKnowledgeAsset(BaseKnowledgeAsset):
    asset_type: Literal["pattern"]
    steps: list[str] = Field(default_factory=list)
    adaptation_notes: str | None = None


class ExampleKnowledgeAsset(BaseKnowledgeAsset):
    asset_type: Literal["example"]
    what_happened: str | None = None
    transferable_lesson: str | None = None
    concept_demonstrated: str | None = None


class WarningKnowledgeAsset(BaseKnowledgeAsset):
    asset_type: Literal["warning"]
    consequence: str | None = None
    prevention: str | None = None


class FrameworkKnowledgeAsset(BaseKnowledgeAsset):
    asset_type: Literal["framework"]
    steps: list[str] = Field(default_factory=list)
    adaptation_notes: str | None = None


class MentalModelKnowledgeAsset(BaseKnowledgeAsset):
    asset_type: Literal["mental_model"]


class ProcessKnowledgeAsset(BaseKnowledgeAsset):
    asset_type: Literal["process"]
    steps: list[str] = Field(
        min_length=1,
        description="Ordered source-supported actions that make up the process.",
    )
    adaptation_notes: str | None = None


# Each type has its own structure. This prevents a generic concept from
# carrying decision-rule fields such as condition, action, and rationale.
KnowledgeAsset = Union[
    DecisionRuleKnowledgeAsset,
    ProcessKnowledgeAsset,
    WarningKnowledgeAsset,
    ExampleKnowledgeAsset,
    PatternKnowledgeAsset,
    FrameworkKnowledgeAsset,
    ConceptKnowledgeAsset,
    ProblemKnowledgeAsset,
    PrincipleKnowledgeAsset,
    InsightKnowledgeAsset,
    MentalModelKnowledgeAsset,
]

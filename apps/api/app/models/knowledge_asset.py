from datetime import datetime
from enum import Enum
from typing import Literal, Union

from pydantic import BaseModel, Field


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


class BaseKnowledgeAsset(BaseModel):
    """Fields shared by every reusable knowledge asset."""

    id: str | None = None
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

    # Type-specific fields. They stay optional unless a subtype requires them.
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

    confidence_score: int = Field(default=3, ge=1, le=5)
    created_at: datetime | None = None


class GeneralKnowledgeAsset(BaseKnowledgeAsset):
    """Asset types that do not currently require extra mandatory fields."""

    asset_type: Literal[
        "concept",
        "problem",
        "principle",
        "insight",
        "pattern",
        "example",
        "warning",
        "framework",
        "mental_model",
    ]


class DecisionRuleKnowledgeAsset(BaseKnowledgeAsset):
    """A decision rule must say what action or choice it recommends."""

    asset_type: Literal["decision_rule"]
    action: str = Field(
        min_length=1,
        description="Concrete behavior or choice recommended by the rule.",
    )


class ProcessKnowledgeAsset(BaseKnowledgeAsset):
    """A process must contain at least one repeatable step."""

    asset_type: Literal["process"]
    steps: list[str] = Field(
        min_length=1,
        description="Ordered source-supported actions that make up the process.",
    )


# A union makes the requirement visible to Gemini's JSON schema, rather than
# relying only on validation after the model has already generated its output.
KnowledgeAsset = Union[
    DecisionRuleKnowledgeAsset,
    ProcessKnowledgeAsset,
    GeneralKnowledgeAsset,
]

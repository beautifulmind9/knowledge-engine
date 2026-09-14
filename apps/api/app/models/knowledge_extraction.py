from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from app.models.knowledge_asset import KnowledgeAsset


class KnowledgeExtractionStatus(str, Enum):
    PENDING_AI = "pending_ai"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class KnowledgeExtractionRequest(BaseModel):
    source_id: str
    chunk_id: str
    reprocess: bool = False


class KnowledgeExtractionJob(BaseModel):
    id: str
    source_id: str
    chunk_id: str
    status: KnowledgeExtractionStatus = KnowledgeExtractionStatus.PENDING_AI
    asset_count: int = 0
    provider: str | None = None
    model: str | None = None
    model_response_id: str | None = None
    created_at: datetime
    completed_at: datetime | None = None
    error: str | None = None


class KnowledgeExtractionResultSubmission(BaseModel):
    assets: list[KnowledgeAsset] = Field(default_factory=list)


class KnowledgeExtractionBatchGroup(BaseModel):
    model_config = {"extra": "forbid"}
    chunk_id: str
    assets: list[KnowledgeAsset]


class KnowledgeExtractionBatchResponse(BaseModel):
    model_config = {"extra": "forbid"}
    results: list[KnowledgeExtractionBatchGroup] = Field(min_length=1, max_length=10)


GEMINI_BATCH_ASSET_TYPES = [
    "concept",
    "problem",
    "principle",
    "insight",
    "decision_rule",
    "pattern",
    "example",
    "warning",
    "framework",
    "mental_model",
    "process",
]


def gemini_batch_response_schema():
    """Minimal provider contract; all asset structure is validated locally.

    Gemini's structured-output compiler only has to route one string payload per
    chunk. ``assets_json`` contains a JSON-encoded array of candidate asset
    objects. Knowledge Engine parses that string and validates every candidate
    against the unchanged strict discriminated ``KnowledgeAsset`` models before
    anything is persisted.
    """

    return {
        "type": "object",
        "properties": {
            "results": {
                "type": "array",
                "minItems": 1,
                "maxItems": 10,
                "items": {
                    "type": "object",
                    "properties": {
                        "chunk_id": {"type": "string"},
                        "assets_json": {
                            "type": "string",
                            "description": (
                                "JSON-encoded array of candidate knowledge asset objects "
                                "for this chunk; use [] when none are supported."
                            ),
                        },
                    },
                    "required": ["chunk_id", "assets_json"],
                },
            }
        },
        "required": ["results"],
    }

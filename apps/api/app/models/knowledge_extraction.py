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
    """Small provider-facing schema; strict KnowledgeAsset validation stays local.

    Gemini only needs a flat formatting contract. Conditional subtype rules and
    provenance ownership are intentionally enforced after the response returns.
    """

    string_array = {"type": "array", "items": {"type": "string"}}
    asset_schema = {
        "type": "object",
        "properties": {
            "asset_type": {"type": "string", "enum": GEMINI_BATCH_ASSET_TYPES},
            "title": {"type": "string"},
            "what_it_says": {"type": "string"},
            "why_it_matters": {"type": "string"},
            "chapter_or_section": {"type": "string"},
            "evidence": {"type": "string"},
            "how_to_apply": string_array,
            "when_to_use": string_array,
            "when_not_to_use": string_array,
            "tradeoffs": string_array,
            "keywords": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
                "maxItems": 8,
            },
            "confidence_score": {"type": "integer", "minimum": 1, "maximum": 5},
            "condition": {"type": "string"},
            "action": {"type": "string"},
            "rationale": {"type": "string"},
            "steps": string_array,
            "adaptation_notes": {"type": "string"},
            "what_happened": {"type": "string"},
            "transferable_lesson": {"type": "string"},
            "concept_demonstrated": {"type": "string"},
            "consequence": {"type": "string"},
            "prevention": {"type": "string"},
            "components": string_array,
        },
        "required": ["asset_type", "title", "what_it_says", "evidence", "keywords"],
    }
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
                        "assets": {"type": "array", "items": asset_schema},
                    },
                    "required": ["chunk_id", "assets"],
                },
            }
        },
        "required": ["results"],
    }

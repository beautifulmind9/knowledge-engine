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

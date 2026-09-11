from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from app.models.knowledge_asset import KnowledgeAsset


class KnowledgeExtractionStatus(str, Enum):
    PENDING_AI = "pending_ai"
    COMPLETED = "completed"
    FAILED = "failed"


class KnowledgeExtractionRequest(BaseModel):
    source_id: str
    chunk_id: str


class KnowledgeExtractionJob(BaseModel):
    id: str
    source_id: str
    chunk_id: str
    status: KnowledgeExtractionStatus = KnowledgeExtractionStatus.PENDING_AI
    asset_count: int = 0
    created_at: datetime
    completed_at: datetime | None = None
    error: str | None = None


class KnowledgeExtractionResultSubmission(BaseModel):
    assets: list[KnowledgeAsset] = Field(default_factory=list)

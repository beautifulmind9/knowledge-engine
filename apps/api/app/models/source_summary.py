"""Factual source readiness; deliberately independent of relevance or quality."""
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict


class RecoverySummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: str  # Internal action identity, never ordinary display copy.
    category: Literal["failed_build", "unconfirmed_build"]
    allowed: bool
    eligible_at: datetime | None = None


class SourceSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_id: str
    readiness: Literal["added", "ready_to_build", "partly_ready", "ready", "unknown"]
    completed_parts: int | None
    total_parts: int | None
    coverage_text: str | None
    has_usable_knowledge: bool
    operation: Literal["idle", "build_unconfirmed"]
    attention_category: Literal["missing_file", "artifact_unavailable", "unsupported_extraction", "read_failed", "ocr_required", "build_stopped", "build_unconfirmed"] | None
    attention_message: str | None
    file_state: Literal["unattached", "available", "missing", "unknown"]
    read_state: Literal["not_read", "read", "unsupported_extraction", "read_failed", "ocr_required", "unavailable"]
    next_action: Literal["attach_file", "read_source", "build_knowledge", "continue_building", "wait_or_reset", "restore_source", "use_knowledge", "supply_readable_file"]
    recovery: list[RecoverySummary]

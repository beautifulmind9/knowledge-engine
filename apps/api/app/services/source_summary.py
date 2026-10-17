"""Compact inventory facts. No audit, consolidation, retrieval or provider IO."""
from app.services import partition_authority as authority
from collections import defaultdict
import json
from pathlib import Path

from app.db.mock_data import sources, extraction_jobs, knowledge_assets
from app.models.source_summary import SourceSummary, RecoverySummary
from app.persistence.factory import get_artifact_store
from app.services.knowledge_extraction import recovery_eligibility
from app.services.chunk_manifest import valid_manifest

MESSAGES = {
    "missing_file": "Attach a file to this material.",
    "artifact_unavailable": "Source data is unavailable. Restore the source data to continue.",
    "unsupported_extraction": "This file cannot be read in its current format.",
    "read_failed": "This file could not be read. Try reading again or supply a readable file.",
    "ocr_required": "This PDF has no extractable text. OCR is not supported; supply a PDF with selectable text or another supported file.",
    "build_stopped": "The previous knowledge-building attempt stopped before completion.",
    "build_unconfirmed": "Previous build has not reported completion.",
}


def source_file_replacement_allowed(source_id: str) -> bool:
    """A source file can be replaced only before interpretation history exists."""
    return not authority.has_history(source_id)


def source_summaries(library_id=None, source_id=None, now=None, source_ids=None):
    chosen = [s for s in sources if (library_id is None or s["library_id"] == library_id)
              and (source_id is None or s["id"] == source_id)
              and (source_ids is None or s["id"] in set(source_ids))]
    if source_id is not None and not chosen:
        raise ValueError("Source not found.")
    jobs = defaultdict(list)
    usable = set()
    coordinator=authority.coordinator()
    summary_state=(coordinator.summary_state([s['id'] for s in chosen])
                   if coordinator is not None and getattr(coordinator,'version',2)>=3 else None)
    selected=(summary_state['jobs'] if summary_state is not None else
              authority.jobs_many([s['id'] for s in chosen]) if coordinator else authority.jobs())
    for job in selected:
        jobs[job["source_id"]].append(job)
    if not authority.coordinator():
        for asset in knowledge_assets:
            if asset.get("active", True):
                usable.add(asset["source_id"])
    history={j['source_id'] for j in extraction_jobs}
    if summary_state is not None:
        usable=set(summary_state['asset_counts'])
        history=summary_state['history_sources']
    elif coordinator:
        usable=set(coordinator.asset_counts([s['id'] for s in chosen]))
        history=coordinator.history_sources([s['id'] for s in chosen])
    store = get_artifact_store()
    paths = [Path(s[key]) for s in chosen for key in ("file_path", "chunks_path") if s.get(key)]
    try:
        presence = store.status_many(paths)
    except Exception:
        # A failed inventory is unknown, never evidence that artifacts are absent.
        presence = {}
    return [_summarize(s, jobs[s["id"]], s["id"] in usable, now, store, presence, s['id'] not in history) for s in chosen]


def _summarize(source, jobs, usable, now, store, presence, replacement_allowed):
    attention = None
    file_state = "unattached"
    if source.get("file_path"):
        checked = presence.get(Path(source["file_path"]))
        file_state = "available" if checked == "artifact" else "unknown" if checked is None else "missing"
        if file_state != "available":
            attention = "artifact_unavailable"
    else:
        attention = "missing_file"
    read_state = "not_read"
    completed = total = 0
    current_ids = set()
    if source.get("chunks_path"):
        try:
            chunks_path = Path(source["chunks_path"])
            checked = presence.get(chunks_path)
            if checked != "artifact":
                raise OSError("Chunk artifact is unavailable.")
            manifest = source.get("chunk_manifest")
            if valid_manifest(source["id"], manifest):
                current_ids = set(manifest["chunk_ids"])
                total = manifest["total_parts"]
            else:
                raw = store.read_text(chunks_path)
                chunks = json.loads(raw)
                if not isinstance(chunks, list) or any(not isinstance(c, dict) or not isinstance(c.get("id"), str) or not c["id"] for c in chunks):
                    raise ValueError("Invalid processing parts.")
                current_ids = {c["id"] for c in chunks}
                if len(current_ids) != len(chunks):
                    raise ValueError("Duplicate processing parts.")
                total = len(current_ids)
            completed = len({j["chunk_id"] for j in jobs if j["chunk_id"] in current_ids and j["status"] == "completed"})
            read_state = "read" if total else "read_failed"
            if not total:
                attention = attention or "read_failed"
        except Exception:
            current_ids = set()
            completed = total = None
            read_state = "unavailable"
            attention = "artifact_unavailable"
    else:
        category = source.get("reading_failure")
        if category not in {"unsupported_extraction", "read_failed", "ocr_required"}:
            # Old records cannot distinguish parser failures from unsupported formats.
            # Never guess OCR from stored raw exception text.
            category = "read_failed" if source.get("processing_status") in {"extraction_failed", "extraction_not_supported"} else None
        if category:
            read_state = category
            attention = attention or category
    # Missing references cannot prove a zero-part lifecycle after parts/knowledge existed.
    if not source.get("chunks_path") and (jobs or usable or source.get("processing_status") in {"chunked", "knowledge_interpreting", "knowledge_interpreted"}):
        completed = total = None
        read_state = "unavailable"
        attention = "artifact_unavailable"
    readiness = "unknown" if total is None else "added"
    if total:
        readiness = "ready" if completed == total else "partly_ready" if completed else "ready_to_build"
    latest = {}
    for job in jobs:
        if job["chunk_id"] in current_ids:
            latest[job["chunk_id"]] = job
    recovery = []
    for job in latest.values():
        if job["status"] not in {"failed", "running"}:
            continue
        try:
            allowed, eligible_at = recovery_eligibility(job, now)
        except (ValueError, KeyError, TypeError):
            allowed, eligible_at = False, None
        recovery.append(RecoverySummary(job_id=job["id"], category="failed_build" if job["status"] == "failed" else "unconfirmed_build", allowed=allowed, eligible_at=eligible_at))
    running = any(j["status"] == "running" for j in latest.values())
    failed = any(j["status"] == "failed" for j in latest.values())
    # Completed/recovered latest attempts resolve historical source-level prose.
    stopped_pending = source.get("stopped_reason") and any(j["status"] == "pending_ai" and not j.get("recovered_at") for j in latest.values())
    if failed or stopped_pending:
        attention = attention or "build_stopped"
    elif any(r.category == "unconfirmed_build" and r.allowed for r in recovery):
        attention = attention or "build_unconfirmed"
    action = "attach_file" if file_state == "unattached" else "read_source"
    if total:
        action = {"ready": "use_knowledge", "partly_ready": "continue_building", "ready_to_build": "build_knowledge"}[readiness]
    if running:
        action = "wait_or_reset"
    if read_state in {"ocr_required", "unsupported_extraction"}:
        action = "supply_readable_file"
    if attention == "artifact_unavailable":
        action = "restore_source"
    return SourceSummary(
        source_id=source["id"], readiness=readiness, completed_parts=completed, total_parts=total,
        coverage_text=f"{completed} of {total} parts ready" if total else None,
        has_usable_knowledge=usable, operation="build_unconfirmed" if running else "idle",
        attention_category=attention, attention_message=MESSAGES.get(attention), file_state=file_state,
        file_replacement_allowed=replacement_allowed,
        read_state=read_state, next_action=action, recovery=recovery,
    )

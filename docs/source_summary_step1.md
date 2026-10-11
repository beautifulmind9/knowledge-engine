# Slice 2B Step 1: source facts and recovery

This step supplies factual readiness without changing the Add interaction, Library rows, or accepted Create/Home/Ask flows. Source detail uses the summary and loads audit/chunks only when Advanced opens.

## API

- `GET /sources/summaries?library_id=…`: array of summaries, optional library filter.
- `GET /sources/{source_id}/summary`: one summary, 404 for unknown source.

Each strict response contains:

```json
{
  "source_id": "internal-source-identity",
  "readiness": "partly_ready",
  "completed_parts": 12,
  "total_parts": 20,
  "coverage_text": "12 of 20 parts ready",
  "has_usable_knowledge": true,
  "operation": "idle",
  "attention_category": "build_stopped",
  "attention_message": "The previous knowledge-building attempt stopped before completion.",
  "file_state": "available",
  "read_state": "read",
  "next_action": "continue_building",
  "recovery": [{"job_id": "internal-action-identity", "category": "failed_build", "allowed": true, "eligible_at": null}]
}
```

Readiness is independent of attention, operation and knowledge availability:

| Facts | Readiness |
| --- | --- |
| Reliably known no current parts (valid empty part list, or no part reference and no evidence parts previously existed) | `added` |
| Current-part coverage cannot be established | `unknown` |
| Current parts exist, none completed | `ready_to_build` |
| Some but not all current parts completed | `partly_ready` |
| All current parts completed, total greater than zero | `ready` |

Known zero parts have zero counts and no coverage text. Unknown counts are null, never inferred as zero or complete. Missing/corrupt/unreadable part artifacts and missing references after parts/knowledge existed produce unknown readiness. Completed parts are distinct current part IDs with completed jobs. Active idea availability is a separate boolean, consistent with existing retrieval. Ready with zero ideas is valid. Parts are processing windows; counts do not establish page, chapter, semantic, relevance or quality coverage. Mixed PDFs have no page-completeness claim.

Attention categories: `missing_file`, `artifact_unavailable`, `unsupported_extraction`, `read_failed`, `ocr_required`, `build_stopped`, `build_unconfirmed`, or null. Messages are fixed safe copy; source/parser/provider prose is not returned in the summary.

Readiness is exactly `added | ready_to_build | partly_ready | ready | unknown`. Operation is `idle` or `build_unconfirmed`. Persisted running markers cannot prove live computation. Reading/building activity in the current tab is represented by the explicit pending request, not inferred from old `processing_status` values. `ready_to_build` is a preparation fact; an unconfirmed operation overrides its next action to `wait_or_reset`.

File states: `unattached`, `available`, `missing`, `unknown`. Read states: `not_read`, `read`, `unsupported_extraction`, `read_failed`, `ocr_required`, `unavailable`.

Next actions: `attach_file`, `read_source`, `build_knowledge`, `continue_building`, `wait_or_reset`, `restore_source`, `use_knowledge`, `supply_readable_file`. These are presentation hints, not permission to bypass existing mutation checks.

## Recovery and historical state

Only latest attempts for current parts are offered. Failed jobs can reset immediately. Running jobs use the existing server rule: started_at (created_at fallback), plus 600 seconds. Summary and reset share the same predicate. A latest persisted running job produces build_unconfirmed operation immediately. Before server recovery eligibility it does not create build_unconfirmed attention; unrelated failures still can. At or after eligibility it can create that attention category. Invalid timestamps leave operation unconfirmed with no actionable running attention. Running entries include the exact eligible_at timestamp; invalid legacy timestamps fail closed. A summary is a point-in-time observation; reset always checks again.

Reset only sets pending_ai, clears the job error and records recovered_at. It never invokes AI or continues building. It clears the source stop reason when no latest failed/running attempts remain. The summary ignores stale stopped_reason text after completed/recovered attempts; unresolved pending attempts with a stopped reason remain attention. Successful later attempts resolve historical failures. A failed replacement may retain Ready coverage and usable old knowledge while still showing independent attention for that attempt.

## Reading and backward compatibility

One optional source-record field is added: `reading_failure`, with `unsupported_extraction`, `read_failed`, `ocr_required`, or null. Existing flexible source persistence requires no migration. New failures persist only the category; parser prose is replaced by safe response copy. Upload and successful reading clear the category. Existing extraction_failed/extraction_not_supported records without it map conservatively to read_failed; old text is not mined to guess OCR.

No unattached file is reported as read. Missing/corrupt chunk artifacts produce unknown coverage and an artifact attention state without hiding stored active knowledge. Original artifact absence or unavailable storage is independent of available knowledge. The summary reads current chunk artifacts internally for exact IDs/counts, but returns no chunk text. There is no full audit, consolidation, knowledge-unit loading, provider call or per-row diagnostic payload. Batch requests group jobs/assets once; chunk IO remains per source, with no speculative cached counters.

## Safeguards and boundary

Empty Add files fail locally before source creation, using the backend's empty-file message. Later upload failure still retains the known source identity. The active extraction validator has no repair branch or configuration lookup; malformed output fails after the explicit attempt. SDK retries/quota controls remain unchanged. Historical documentation proposing automatic repair has been corrected.

Material-first capture, filename suggestions, default destination creation, combined Add/read, normal recovery placement, Manage and Library-row redesign remain for Steps 2/3. Existing Library badges remain unchanged in this step. Source detail changes only readiness/coverage truth and diagnostic loading.

Verification: frontend regression suite; backend regression suite including test_source_summary.py; synthetic Create and Slice 2A browser acceptance. All provider behavior in tests uses mocks.

## Final semantic examples

These full-shape synthetic examples assume server time `2026-10-11T12:00:00Z`. Eligibility always comes from the server predicate.

### 1. Added

```json
{
  "source_id": "source_example",
  "readiness": "added",
  "completed_parts": 0,
  "total_parts": 0,
  "coverage_text": null,
  "has_usable_knowledge": false,
  "operation": "idle",
  "attention_category": "missing_file",
  "attention_message": "Attach a file to this material.",
  "file_state": "unattached",
  "read_state": "not_read",
  "next_action": "attach_file",
  "recovery": []
}
```

### 2. Unknown + artifact attention

```json
{
  "source_id": "source_example",
  "readiness": "unknown",
  "completed_parts": null,
  "total_parts": null,
  "coverage_text": null,
  "has_usable_knowledge": true,
  "operation": "idle",
  "attention_category": "artifact_unavailable",
  "attention_message": "Source data is unavailable. Restore it before continuing preparation.",
  "file_state": "available",
  "read_state": "unavailable",
  "next_action": "restore_source",
  "recovery": []
}
```

### 3. Ready to build

```json
{
  "source_id": "source_example",
  "readiness": "ready_to_build",
  "completed_parts": 0,
  "total_parts": 3,
  "coverage_text": "0 of 3 parts ready",
  "has_usable_knowledge": false,
  "operation": "idle",
  "attention_category": null,
  "attention_message": null,
  "file_state": "available",
  "read_state": "read",
  "next_action": "build_knowledge",
  "recovery": []
}
```

### 4. Partly ready

```json
{
  "source_id": "source_example",
  "readiness": "partly_ready",
  "completed_parts": 1,
  "total_parts": 3,
  "coverage_text": "1 of 3 parts ready",
  "has_usable_knowledge": true,
  "operation": "idle",
  "attention_category": null,
  "attention_message": null,
  "file_state": "available",
  "read_state": "read",
  "next_action": "continue_building",
  "recovery": []
}
```

### 5. Partly ready + failed build

```json
{
  "source_id": "source_example",
  "readiness": "partly_ready",
  "completed_parts": 1,
  "total_parts": 3,
  "coverage_text": "1 of 3 parts ready",
  "has_usable_knowledge": true,
  "operation": "idle",
  "attention_category": "build_stopped",
  "attention_message": "The previous knowledge-building attempt stopped before completion.",
  "file_state": "available",
  "read_state": "read",
  "next_action": "continue_building",
  "recovery": [
    {
      "job_id": "job_failed",
      "category": "failed_build",
      "allowed": true,
      "eligible_at": null
    }
  ]
}
```

### 6. Unconfirmed below threshold

```json
{
  "source_id": "source_example",
  "readiness": "partly_ready",
  "completed_parts": 1,
  "total_parts": 3,
  "coverage_text": "1 of 3 parts ready",
  "has_usable_knowledge": true,
  "operation": "build_unconfirmed",
  "attention_category": null,
  "attention_message": null,
  "file_state": "available",
  "read_state": "read",
  "next_action": "wait_or_reset",
  "recovery": [
    {
      "job_id": "job_running",
      "category": "unconfirmed_build",
      "allowed": false,
      "eligible_at": "2026-10-11T12:05:00Z"
    }
  ]
}
```

### 7. Unconfirmed after threshold

```json
{
  "source_id": "source_example",
  "readiness": "partly_ready",
  "completed_parts": 1,
  "total_parts": 3,
  "coverage_text": "1 of 3 parts ready",
  "has_usable_knowledge": true,
  "operation": "build_unconfirmed",
  "attention_category": "build_unconfirmed",
  "attention_message": "Previous build has not reported completion.",
  "file_state": "available",
  "read_state": "read",
  "next_action": "wait_or_reset",
  "recovery": [
    {
      "job_id": "job_running",
      "category": "unconfirmed_build",
      "allowed": true,
      "eligible_at": "2026-10-11T11:59:00Z"
    }
  ]
}
```

### 8. Ready with zero ideas

```json
{
  "source_id": "source_example",
  "readiness": "ready",
  "completed_parts": 3,
  "total_parts": 3,
  "coverage_text": "3 of 3 parts ready",
  "has_usable_knowledge": false,
  "operation": "idle",
  "attention_category": null,
  "attention_message": null,
  "file_state": "available",
  "read_state": "read",
  "next_action": "use_knowledge",
  "recovery": []
}
```

# Remaining sprint status — 2026-09-15

This document records the current state of the active `feature/knowledge-assets` implementation. **Verified** means implemented and exercised by automated checks and/or the stated real-source acceptance work. **Implemented** means code exists but a material acceptance check remains. **Pending** means the original acceptance criterion is not yet satisfied.

A mocked provider response proves software behavior, not real-world output usefulness. Real-provider evidence is called out explicitly below.

## R1 — Save outputs

| ID | Status | Evidence / remaining work |
|---|---|---|
| R1-01 | Verified | Output records store brief, provenance snapshot, mode, provider/model, and timestamps. |
| R1-02 | Verified | SQLite persistence survives restart. |
| R1-03 | Verified | Generation can save by default; `save=false` remains available. |
| R1-04 | Verified | Compact saved-output list exists. |
| R1-05 | Verified | Full saved records preserve brief and evidence snapshot. |
| R1-06 | Verified | Type, source, and creation-date filters exist. |
| R1-07 | Verified | Generated fixture persistence and saved-demo restart retrieval are covered. |

## R2 — Revisions

| ID | Status | Evidence / remaining work |
|---|---|---|
| R2-01 | Verified | Root/parent IDs, versions, and timestamps are stored. |
| R2-02 | Verified | Revision instructions/manual edits are bounded and validated. |
| R2-03 | Verified | Revisions create new records; originals remain unchanged. |
| R2-04 | Verified | Knowledge snapshots and applied IDs are validated. |
| R2-05 | Verified | Grounding prompt and design-choice separation exist; semantic human review remains necessary. |
| R2-06 | Verified | Chronological history is available. |
| R2-07 | Verified | Changed fields/content diff are available within one history. |
| R2-08 | Verified | One explicit provider request per AI revision; no automatic repair call. |

## R3 — Interpretation and audit

| ID | Status | Evidence / remaining work |
|---|---|---|
| R3-01 | Verified | Intentional replacement supersedes old assets only after the complete replacement validates. Failed replacements preserve the prior active set. |
| R3-02 | Verified | Schema/extraction versions plus active/superseded history are stored. |
| R3-03 | Verified | Audit reports jobs, active assets, overlap/evidence/keyword issues, and historical schema state. |
| R3-04 | Verified | Failed and stale-running jobs can be explicitly recovered. |
| R3-05 | Verified | Markdown/HTML/EPUB/DOCX structure hints and reading order are tested. PDF chapter inference remains limited. |
| R3-06 | **Verified** | Real *Workshop Survival Guide* source is complete at **46/46 chunks**. |
| R3-07 | **Verified** | Full-source audit and targeted qualitative review completed: **121 active assets**, **0 missing evidence**, **0 missing keywords**, confidence **83×5 / 38×3**, and **13 evidence-review items** retained as a manual review queue rather than known defects. Historical provenance defects were repaired. |
| R3-08 | Verified | TXT, Markdown, HTML, EPUB, and DOCX pipeline behavior is covered; PDF with selectable text is supported. |

### R3 architecture decision

Production extraction is **one chunk per Gemini request**. Source-level orchestration may select multiple chunks, but each chunk receives an independent model context and provider attempt.

This decision is based on live provider testing:

- shared-context multi-chunk extraction showed under-extraction and cross-chunk evidence leakage;
- simplifying the Gemini-facing schema fixed missing common-field enforcement but did not eliminate shared-context routing/coverage problems;
- a strict isolated single-chunk control on chunk 007 returned **5 valid assets**, matching its historical active count, all at confidence 5;
- Gemini asynchronous Batch API submission was rejected with `FAILED_PRECONDITION` on the billing-disabled/free-tier setup, consistent with Batch not being available on the current Developer API free tier, so Batch is not part of the production path.

The known chunk-025 compound crowd-recovery asset was repaired deterministically with zero Gemini calls. Chunk 025 now has `Talking in circles to recover attention`; chunk 026 separately retains `Borrowing goodwill to reclaim attention`. The active source count remained 121.

## R4 — Output modes

| ID | Status | Evidence / remaining work |
|---|---|---|
| R4-01 | Verified | Explicit output mode is persisted with each record and revision. |
| R4-02 | Verified | Six mode-specific prompt instruction sets exist. |
| R4-03 | Implemented | Structural quality checks and workshop timing validation exist; they do not prove semantic correctness. |
| R4-04 | Implemented | Writing workflow is implemented; real-provider usefulness review remains. |
| R4-05 | Implemented | Decision-brief workflow is implemented; real-provider usefulness review remains. |
| R4-06 | Implemented | Study/playbook workflows are implemented; real-provider usefulness review remains. |
| R4-07 | Verified | Mode metadata contains structural guidance. |
| R4-08 | Verified | All six modes exercise generate/save/revise in automated tests. |

**R4 exit gate remains open** until at least four materially different real-provider outputs are reviewed for usefulness, grounding, and structure, including real revisions.

## R5 — Multi-source synthesis

| ID | Status | Evidence / remaining work |
|---|---|---|
| R5-01 | Verified | Source-list and library-scoped retrieval exist. |
| R5-02 | Verified | Consolidated units preserve source, asset, chunk, and evidence trails. |
| R5-03 | Implemented | Lexical candidate agreements exist; semantic agreement still requires review. |
| R5-04 | Implemented | Polarity/numeric tension checks prevent some unsafe merges; contradiction detection is not comprehensive. |
| R5-05 | Verified | Agreement, distinct-contribution, and tension context is supplied to generation/revisions. |
| R5-06 | Verified | Two-source fixtures validate materially applied IDs and provenance. |
| R5-07 | Verified | Library scope is enforced in Workshop and knowledge search. |
| R5-08 | Pending | A meaningful **real** two-source comparison and quality judgment is still required. |

## R6 — Web interface

| ID | Status | Evidence / remaining work |
|---|---|---|
| R6-01 | Implemented | Active HTML/CSS/JS browser app is served by FastAPI. |
| R6-02 | Implemented | Shared request helper handles JSON/uploads/errors. |
| R6-03 | Implemented | Library/source creation, upload, processing, and source view exist. |
| R6-04 | Implemented | Interpretation progress, audit, recovery, and quota messages exist. |
| R6-05 | Implemented | Knowledge search, evidence, explicit selection, and library scope exist. |
| R6-06 | Implemented | Workshop brief captures situation/goal/audience/constraints/mode/tone/scope. |
| R6-07 | Implemented | Output, applied evidence, and design choices are displayed separately. |
| R6-08 | Implemented | Saved outputs, revisions, history, and comparison exist. |
| R6-09 | Implemented | Busy/live feedback, disabled submit actions, errors, and empty states exist. |

Full desktop/mobile/keyboard acceptance is still pending.

## R7 — Storage and control

| ID | Status | Evidence / remaining work |
|---|---|---|
| R7-01 | Verified | Local SQLite architecture is documented; no paid infrastructure is required. |
| R7-02 | Verified | Core records, outputs, and usage state survive restart. |
| R7-03 | Verified | Source files/assets/jobs and selected dependent output histories can be deleted safely. |
| R7-04 | Verified | Whole output histories can be deleted explicitly. |
| R7-05 | Verified | Markdown provenance export and portable private backup/restore exist. |
| R7-06 | Verified | Quota pause/resume and local budget exist; no paid fallback. |
| R7-07 | Implemented | Private data is git-ignored; localhost/origin protections exist; provider-wide privacy remains a separate policy consideration. |
| R7-08 | Verified | Covered integrity failures such as missing files and broken links are detected. |

## R8 — Hardening and release

| ID | Status | Evidence / remaining work |
|---|---|---|
| R8-01 | Verified | Automated workflow/persistence/revision/backup tests exist. |
| R8-02 | Verified | Original synthetic snippets and mode/two-source fixtures exist. |
| R8-03 | Verified | Quota, missing configuration/files, invalid AI output, recovery, and corruption paths are covered. |
| R8-04 | Verified | Synthetic public-safe demo is idempotent. |
| R8-05 | Verified | README, product vision, architecture, sprint status, and release documents describe the active product. |
| R8-06 | Verified | Setup/launcher and dependency lock are exercised; platform-specific acceptance may still reveal issues. |
| R8-07 | Implemented | Accessibility/responsive foundations exist; manual browser/mobile pass remains. |
| R8-08 | Pending | External tester must complete the workflow and provide feedback. |
| R8-09 | Verified | Release decision and remaining gates are explicit. |

## Current automated verification

Latest local suite on 2026-09-15: **153 passed, 2 upstream deprecation warnings**. The warnings are from Starlette/AnyIO and `google.genai` type internals and are unrelated to Knowledge Engine behavior.

The automated suite uses fake/in-memory provider responses and consumes no Gemini quota. Real-provider extraction validation was run separately within the explicit free-tier budget.

## Remaining release blockers

1. Review real Gemini outputs across at least four materially different modes and revise at least two of them.
2. Run one meaningful real two-source task and compare it with the corresponding single-source results.
3. Complete desktop/mobile/keyboard browser acceptance.
4. Have at least one external tester complete the core workflow and record feedback.

The real-book interpretation/audit is **no longer a release blocker**.

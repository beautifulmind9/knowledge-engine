# Remaining sprint status — 2026-09-13

The checkout on `codex/remaining-sprints` already contained substantial uncommitted implementation across R1–R8 when this pass began. That work was preserved, tested, and extended. This report reflects the combined working tree; it does not claim all of it was newly written during this pass.

**Verified** means implemented and exercised by relevant local automated checks. **Implemented** means code exists but a material acceptance check remains. **Pending** means the original acceptance criterion is not satisfied. A mocked provider response does not establish real-world AI output quality.

## R1 — Save outputs

| ID | Status | Evidence / remaining work |
|---|---|---|
| R1-01 | Verified | OutputRecord stores brief, provenance snapshot, mode, provider/model and timestamps. |
| R1-02 | Verified | SQLite persistence; fresh-process and live server restart tests. |
| R1-03 | Verified | Generate saves by default; `save=false` remains available. Provider output uses fixtures in tests. |
| R1-04 | Verified | Compact saved-output list. |
| R1-05 | Verified | Full saved record with brief and evidence snapshot. |
| R1-06 | Verified | Type, source and creation-date filters implemented. |
| R1-07 | Verified | Generated fixture persistence plus saved demo restart retrieval; original records preserved. |

## R2 — Revisions

| ID | Status | Evidence / remaining work |
|---|---|---|
| R2-01 | Verified | Root/parent IDs, monotonically increasing version, created/updated timestamps. |
| R2-02 | Verified | Bounded revision instruction and manual edit schema. |
| R2-03 | Verified | New records for manual or model-assisted revisions; original unchanged. |
| R2-04 | Verified | Immutable knowledge snapshot and validated applied IDs. |
| R2-05 | Verified | Grounding prompt, design-choice separation and manual-review annotation; semantic review remains required. |
| R2-06 | Verified | Chronological history endpoint and UI. |
| R2-07 | Verified | Changed fields and content diff within one history. |
| R2-08 | Verified | One explicit model request per revision; no automatic repair call. |

## R3 — Interpretation and audit

| ID | Status | Evidence / remaining work |
|---|---|---|
| R3-01 | Verified | Intentional replacement supersedes old assets only after full batch validation. |
| R3-02 | Verified | Schema/extraction versions and active/superseded records. |
| R3-03 | Verified | Audit endpoint and UI report jobs, active assets, overlap, evidence/keywords and old schema. |
| R3-04 | Verified | Failed jobs and running jobs older than the stale threshold can be explicitly recovered. |
| R3-05 | Verified | Markdown/HTML/EPUB/DOCX heading hints, EPUB reading order and DOCX table order tested. PDF chapter inference remains limited. |
| R3-06 | Pending | Full Workshop Survival Guide source/run not available in this checkout; no live provider calls made. |
| R3-07 | Pending | Audit tooling exists; actual full-book duplicate/evidence/false-positive review is not complete. |
| R3-08 | Verified | TXT, Markdown and HTML pipeline coverage, plus EPUB/DOCX structure tests and a live two-format demo. |

## R4 — Output modes

| ID | Status | Evidence / remaining work |
|---|---|---|
| R4-01 | Verified | Explicit output mode persisted with each record and revision. |
| R4-02 | Verified | Six mode-specific prompt instruction sets; requests exercised using fixtures. |
| R4-03 | Implemented | Lightweight structure hints and human-review criteria; not semantic validation. |
| R4-04 | Implemented | Distinct writing fixture generated/saved/revised; live output review pending. |
| R4-05 | Implemented | Distinct decision-brief fixture generated/saved/revised; live review pending. |
| R4-06 | Implemented | Study/playbook fixtures and manually authored demo; live review pending. |
| R4-07 | Verified | Lightweight heading templates in mode metadata. |
| R4-08 | Verified | All six modes exercise generate/save/revise with fixture responses. |

Exit gate remains open until at least four real model outputs meet usefulness and grounding acceptance.

## R5 — Multi-source synthesis

| ID | Status | Evidence / remaining work |
|---|---|---|
| R5-01 | Verified | Source-list and library-scoped retrieval. |
| R5-02 | Verified | Each consolidated unit preserves source, asset, chunk and evidence trails. |
| R5-03 | Implemented | Lexical candidate agreements; semantic agreement requires review. |
| R5-04 | Implemented | Polarity/numeric tension flags prevent some unsafe merges; not comprehensive contradiction detection. |
| R5-05 | Verified | Agreement, distinct-contribution and tension context supplied to generation and revisions. |
| R5-06 | Verified | Two-source generated fixture validates materially applied IDs and source provenance. |
| R5-07 | Verified | Library scope in Workshop and knowledge search, including empty/out-of-scope cases. |
| R5-08 | Pending | Synthetic scenario demonstrates complementary guidance; real-task comparison and quality judgment still needed. |

## R6 — Web interface

| ID | Status | Evidence / remaining work |
|---|---|---|
| R6-01 | Implemented | Active HTML/CSS/JS app in apps/web; served by FastAPI. |
| R6-02 | Implemented | Shared request helper for JSON, uploads and readable errors. |
| R6-03 | Implemented | Library/source creation, upload, process and source view. |
| R6-04 | Implemented | Chunk progress, audit, recovery, batch stop and quota messages. |
| R6-05 | Implemented | Knowledge search, evidence and explicit selection; library scope corrected. |
| R6-06 | Implemented | Situation/goal/audience/constraints/mode/tone/library/source form. |
| R6-07 | Implemented | Output content, applied evidence and design choices shown separately. |
| R6-08 | Implemented | Saved outputs, manual/AI revision, history and comparison. |
| R6-09 | Implemented | Busy/live feedback, disabled submit actions, errors and empty states. |

Static routes and JS syntax are checked. The cloud browser could not access localhost, so the full visual/browser acceptance gate is pending.

## R7 — Storage and control

| ID | Status | Evidence / remaining work |
|---|---|---|
| R7-01 | Verified | Local SQLite decision and trade-offs in storage_and_privacy.md; no paid infrastructure. |
| R7-02 | Verified | Core records, outputs and usage survive restart; legacy migration/corruption covered. |
| R7-03 | Verified | Source files/assets/jobs and intentionally selected dependent output histories removed. |
| R7-04 | Verified | Explicit whole-output-history deletion. |
| R7-05 | Verified | Markdown provenance export and portable private ZIP; restore into renamed folder tested. |
| R7-06 | Verified | Quota pause/resume and local budget; provider failures do not trigger paid fallbacks. |
| R7-07 | Implemented | Private data ignored by git, local host/origin checks, synthetic public examples, store=false on AI interactions. Provider-wide privacy requires separate review. |
| R7-08 | Verified | Missing files, orphan sources and broken output links detected in covered cases. |

Local durability is verified; hosting, multi-user access and encrypted storage remain out of scope.

## R8 — Hardening and release

| ID | Status | Evidence / remaining work |
|---|---|---|
| R8-01 | Verified | Automated API workflow, persistence, revision, backup restore and live-server demo tests. |
| R8-02 | Verified | Small original snippets, distinct mode responses and two-source fixtures. |
| R8-03 | Verified | Quota, missing configuration/source/files, unsupported/empty files, invalid AI output, stale recovery and corruption cases. |
| R8-04 | Verified | Original synthetic MD/HTML sources and idempotent no-API demo seed. |
| R8-05 | Verified | Root, API and web docs describe the active architecture. |
| R8-06 | Verified | Dependencies installed in a clean venv; setup/launcher and live-demo path exercised. macOS-specific install still needs user-machine acceptance. |
| R8-07 | Implemented | Labels, skip link, busy/live feedback, responsive CSS and focus styling; browser/mobile pass pending. |
| R8-08 | Pending | External tester must complete the workflow and provide feedback; nobody was contacted. |
| R8-09 | Verified | Explicit internal-candidate decision and remaining release gates in beta_test_checklist.md. |

## Changes added in this pass

- Preserved tone and retrieval limit in saved briefs; rebuilt synthesis context during revisions.
- Scoped knowledge search to libraries and cleared incompatible browser selections.
- Removed redundant trailing chunks while preserving full text coverage.
- Updated source completion status after manual imports.
- Corrected backup restoration into renamed storage folders.
- Cleaned up superseded files when replacing uninterpreted uploads.
- Added setup, launcher, original demo sources, idempotent demo seeding and release documentation.
- Preserved all contributing source evidence when a consolidated unit is explicitly selected; retained tensions even when both groups share the same source set.
- Preserved HTML/EPUB/DOCX section hints and document reading order.
- Made exhausted daily budgets visibly paused and prevented resume from bypassing them.
- Disabled the pinned SDK’s hidden retry behavior; actual-SDK tests cover success, quota errors, server errors and transport timeouts without external calls.
- Expanded regression coverage and pinned the tested dependency set.

## Release blockers

1. Complete and audit the real-book interpretation.
2. Review real Gemini outputs and revisions across four modes, then compare a real two-source task.
3. Complete desktop/mobile/keyboard browser acceptance and one external beta test.

No production deployment, paid API call, or public source upload was performed. See the test run record below for exact verification results.

## Verification record

Final local run on 2026-09-13: **44 tests passed**, with two upstream Starlette/AnyIO deprecation warnings. No external AI requests were made.

- `bash scripts/setup.sh` completed in a fresh local virtual environment using the locked dependency set.
- `.venv/bin/python -m pytest apps/api/tests -q` passed, including live-server demo/restart, backup relocation, all six mode fixtures, selected-unit provenance, quota/timeout behavior through the installed SDK, and EPUB/DOCX structure.
- `node --check apps/web/app.js`, shell syntax checks, Python compilation, dependency consistency, and `git diff --check` passed.
- Browser verification remains blocked by the cloud browser's localhost restriction. No visual, mobile or external-user acceptance result is claimed.

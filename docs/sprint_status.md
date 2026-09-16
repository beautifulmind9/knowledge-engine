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
| R2-03 | Verified with live evidence | Revisions create new records; two real Workshop revisions preserved their original Version 1 records unchanged. |
| R2-04 | Verified with live evidence | Knowledge snapshots and applied IDs are preserved across the two real manual revisions. |
| R2-05 | Verified | Grounding prompt and design-choice separation exist; semantic human review remains necessary. |
| R2-06 | Verified with live evidence | Chronological history is available and displayed for both real revision cases. |
| R2-07 | Verified with live evidence | Changed fields/content diff is available; both real cases exposed `content` and `design_choices` differences through v2→v1 comparison. |
| R2-08 | Verified | One explicit provider request per AI revision; no automatic repair call. The two accepted real revisions were manual and consumed zero Gemini calls. |

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
| R4-03 | Implemented with live evidence | Structural quality checks, workshop timing validation, and a deterministic grounding-review heuristic exist. A live 90-minute Workshop output passed timing while being correctly downgraded to `needs review` for an unsupported SOP component list. These checks still do not prove semantic correctness. |
| R4-04 | Implemented | Writing workflow is implemented; real-provider usefulness review remains. |
| R4-05 | Implemented | Decision-brief workflow is implemented; real-provider usefulness review remains. |
| R4-06 | Implemented | Study/playbook workflows are implemented; real-provider usefulness review remains. |
| R4-07 | Verified | Mode metadata contains structural guidance. |
| R4-08 | Verified | All six modes exercise generate/save/revise in automated tests. |

### Live Workshop-mode acceptance evidence

A single-source SOP-writing task was run twice with the real Gemini provider against the same eight retrieved Knowledge Units from *The Workshop Survival Guide*.

- Retrieval was stable across both runs.
- First run: useful 90-minute plan, but a 25-minute practice block conflicted with the retrieved 20-minute format-switch rule; the old parser also produced a false-positive Markdown table-header warning; Gemini introduced unsupported SOP-domain content.
- After prompt and validator fixes, the second run produced a clean 90-minute agenda with 15-minute independent practice plus 15-minute peer review and passed the timing check.
- The second run still invented the unsupported component list `Title; Scope; Steps; Troubleshooting`.
- The new grounding validator detected that exact unsupported list and changed the saved output's live quality status from `checks passed` to **`needs review`** while keeping `agenda total: passed`.
- The generation prompt now explicitly requires neutral placeholders when domain knowledge is absent and traceable `applied_knowledge` IDs for material source guidance.
- Both live outputs were preserved unchanged as first-pass acceptance evidence; no automatic repair call was used.

### Live revision acceptance evidence

The two real Workshop outputs were both revised manually through the browser with no provider call.

- **Case 1:** the unsupported `Title; Scope; Steps; Troubleshooting` list was replaced with neutral wording about the SOP format or requirements participants are expected to use. Version 2 reported `checks passed` with **90/90 minutes**, Version 1 remained unchanged, and the v2→v1 comparison showed the content/design-choice difference.
- **Case 2:** the unsupported `Objective; Prerequisites; Steps; Troubleshooting` list was removed and the 25-minute drafting block was restructured into 15-minute drafting plus 10-minute peer review while keeping the full agenda at **90/90 minutes**. Version 2 reported `checks passed`, Version 1 remained unchanged, and the comparison showed the agenda/activity/design-choice changes.
- Both Version 2 records are explicitly labeled manually supplied or edited; the source Knowledge Asset provenance remains visible.

This completes the real-revision acceptance requirement for **A2-04 (2 of 2)**. It also provides live evidence for R2 history and comparison behavior.

**R4 exit gate remains open** until at least four materially different real-provider outputs are reviewed for usefulness, grounding, and structure. The required two real revisions are now complete, but only the Workshop mode has received real-provider output review so far, and the latest first-pass Gemini Workshop sample itself still needed a grounding correction.

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
| R6-04 | Implemented | Interpretation progress, audit, recovery, and quota messages exist. Completed sources no longer show an unnecessary Gemini interpretation action, and historical failed jobs are filtered out of the recovery UI when a newer resolved job exists. |
| R6-05 | Implemented | Knowledge search, evidence, explicit selection, and library scope exist. |
| R6-06 | Implemented | Workshop brief captures situation/goal/audience/constraints/mode/tone/scope. |
| R6-07 | Implemented | Output, applied evidence, design choices, and live quality review are displayed separately. |
| R6-08 | Implemented with live evidence | Saved outputs, manual revisions, history, and comparison have now been exercised twice with real generated outputs. |
| R6-09 | Implemented | Busy/live feedback, disabled submit actions, errors, and empty states exist. |

Desktop browser inspection has now covered completed-source status, knowledge browsing/provenance, Workshop retrieval preview, generation, saved-output display, dynamic quality re-evaluation, manual revision, version preservation, and output comparison. Full create/upload/export acceptance plus mobile and keyboard acceptance remain pending.

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
| R8-03 | Verified | Quota, missing configuration/files, invalid AI output, recovery, corruption, timing, and supported grounding-review paths are covered. |
| R8-04 | Verified | Synthetic public-safe demo is idempotent. |
| R8-05 | Verified | README, product vision, architecture, sprint status, and release documents describe the active product. |
| R8-06 | Verified | Setup/launcher and dependency lock are exercised; platform-specific acceptance may still reveal issues. |
| R8-07 | Implemented | Accessibility/responsive foundations exist; manual browser/mobile pass remains. |
| R8-08 | Pending | External tester must complete the workflow and provide feedback. |
| R8-09 | Verified | Release decision and remaining gates are explicit. |

## Current automated verification

Latest local suite on 2026-09-15: **157 passed, 2 upstream deprecation warnings**. The warnings are from Starlette/AnyIO and `google.genai` type internals and are unrelated to Knowledge Engine behavior.

The automated suite uses fake/in-memory provider responses and consumes no Gemini quota. Real-provider extraction and Workshop-output acceptance were run separately within the explicit free-tier budget.

## Remaining release blockers

1. Review real Gemini outputs across at least three additional materially different modes.
2. Produce a fully grounded first-pass live Workshop sample or otherwise close/document the remaining generation-grounding limitation.
3. Run one meaningful real two-source task and compare it with the corresponding single-source results.
4. Complete the remaining desktop happy-path steps plus mobile/keyboard browser acceptance.
5. Have at least one external tester complete the core workflow and record feedback.

The required **two real output revisions are complete** and are no longer a release blocker. The real-book interpretation/audit is also **no longer a release blocker**.


## 2026-09-16 — Knowledge page structure and state cleanup

Search and Ask now precede a secondary, collapsed Browse knowledge section. Browse loads on demand, shows 10 units initially, supports Show more and type/chapter filters, and retains evidence/provenance and Workshop selection. The shared source selector scopes both Search and Ask; question labels adapt for multiple sources. Chapter questions require one source and chapter context. Search input edits and source changes clear stale results, and late search/answer responses cannot overwrite a newer scope. Answer-to-Workshop handoff retains the answered question and source scope.

Audit finding: the previous page left browse-all cards visible while a query was typed and did not refresh on source changes. Search also scored common query words. Deterministic search now excludes stopwords and generic “one”/“approach” terms; a specific “One-on-one facilitation approach” fixture excludes unrelated economic prioritization. This is lexical retrieval, not proof of semantic relevance on the private inventory.

Verification: **180 Python tests passed**, including a runner for **7 executable JavaScript state/view regressions**; JavaScript syntax and patch checks passed. Zero Gemini calls. Visual desktop/mobile checks remain pending: this environment's cloud browser cannot open localhost (`ERR_BLOCKED_BY_CLIENT`). Existing `test_source.txt` was not touched. Older unfinished schema work was preserved separately and was not applied to the current one-chunk extraction architecture.

A2 remains open: next preview a materially different real output (Decision brief or refreshed Study guide) before generating, and complete a meaningful two-real-source task. The private acceptance source inventory is in the user's local environment; these synthetic checks do not replace that evidence. Release status remains internal local candidate.

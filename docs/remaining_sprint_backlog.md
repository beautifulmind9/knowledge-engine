# Knowledge Engine — Remaining Sprint Backlog

## Execution status

Implementation and verification were reviewed through **2026-09-20**. See [item-level sprint status](sprint_status.md), [release acceptance backlog](release_acceptance_backlog.md), and [beta test checklist](beta_test_checklist.md) for the current evidence. The original acceptance criteria below remain authoritative; this file now also records which historical Remaining Sprints are complete versus which still have release-acceptance work.

## Purpose

This backlog starts from the point where the first end-to-end Knowledge Engine workflow has been validated:

```text
Source
→ Extracted Text
→ Chunks
→ Knowledge Extraction Jobs
→ Knowledge Assets
→ Consolidation
→ Retrieval
→ Workshop
→ Grounded Useful Output
```

The remaining work is no longer about proving whether the core idea works. The goal is to turn the validated backend vertical slice into a usable, persistent, testable v1 beta.

### Current execution status — 2026-09-20

| Remaining Sprint | Current status | Evidence / remaining work |
|---|---|---|
| R1 — Save outputs | **Complete** | Saved outputs persist with provenance and survive restart. |
| R2 — Revisions | **Complete** | Real manual revisions preserve Version 1, lineage, provenance, history, comparison, and consume zero AI calls when edited manually. |
| R3 — Interpretation hardening | **Complete for v1 candidate** | *The Workshop Survival Guide* is complete at 46/46 chunks and audited; production extraction is one chunk per Gemini request. |
| R4 — Output modes | **Complete for A2** | Four materially different real-provider modes were accepted after human grounding review: Workshop Plan, Decision Brief, Study Guide, and Research / Synthesis. Shared grounding review is at version 8. |
| R5 — Multi-source synthesis | **Complete for A2** | Same-task single-source and two-source synthesis was completed with *The Workshop Survival Guide* and a partial current-pipeline interpretation of *Made to Stick*. Human review corrected overclaimed agreement and unsupported cross-source additions. |
| R6 — Web app MVP | **Implemented; final acceptance still open** | Core browser flow, saved outputs, revisions, provenance, export, mobile-width, and keyboard checks have been exercised. Fresh clean-state/full desktop happy-path acceptance and a few remaining error states are still A3 work. |
| R7 — Durable storage/privacy/control | **Complete for v1 candidate** | Local SQLite persistence, deletion, export, backup/restore, integrity checks, and zero-cost quota controls are implemented and tested. |
| R8 — Beta hardening/release candidate | **In progress** | Automated baseline is 205 passed with 2 unchanged upstream warnings. Remaining A3 work: fresh setup, remaining desktop/error-state checks, external tester, critical-defect resolution/deferral, and final v1 beta decision. |

**Current execution point:** A1 and A2 acceptance are complete. The project is now in **A3 / Remaining Sprint 8 release acceptance**, not feature expansion.

Because the repository does not currently preserve a reliable historical sprint number, the sequence below uses **Remaining Sprint 1–8** rather than guessing prior sprint numbers.

---

## v1 Beta Definition of Done

Knowledge Engine v1 beta is ready when a user can:

1. Create or choose a Library.
2. Add a Source and upload a supported file.
3. Extract and chunk the source.
4. Interpret the source into validated Knowledge Assets.
5. Retrieve consolidated Knowledge Units for a real goal.
6. Generate a grounded output from selected knowledge.
7. Save that output.
8. Revise it without losing the original version or provenance.
9. Use more than one source when needed.
10. Complete the main workflow through a real web interface rather than terminal commands.
11. Delete/export their own data and understand processing/quota status.
12. Run the project without paid API billing or automatic paid upgrades.

### Product rules that apply to every remaining sprint

- Development cost target: **$0**.
- Paid API billing: **off**.
- If a free quota is exhausted, stop safely and resume later.
- Preserve source, chunk, asset, and output provenance.
- Raw Knowledge Assets remain preserved even when consolidated views are created.
- Do not add new work to the legacy Streamlit prototype.
- Prefer simple, inspectable systems before adding embeddings, vector databases, or extra AI calls.
- User-facing flows should not expose giant raw JSON responses.

---

# Remaining Sprint 1 — Save Outputs as First-Class Records

## Sprint goal

Turn generated Workshop outputs from temporary API responses into persistent Knowledge Engine records.

## Backlog

| ID | Priority | Work item | Acceptance criteria |
|---|---|---|---|
| R1-01 | Must | Create `OutputRecord` model | Stores output ID, title, output type, content, brief, source IDs, applied Knowledge Asset IDs, design choices, provider/model, timestamps, and generation metadata. |
| R1-02 | Must | Add output persistence | Saved outputs survive Uvicorn/API restart using the current development persistence layer. |
| R1-03 | Must | Save generated Workshop output | `/workshops/generate` can save the generated result rather than returning an ephemeral result only. |
| R1-04 | Must | List saved outputs | User can retrieve a compact list of saved outputs. |
| R1-05 | Must | Get one saved output | One endpoint returns the saved output with its brief and provenance. |
| R1-06 | Should | Filter outputs | Filter by output type, source ID, or creation date where practical. |
| R1-07 | Must | Persistence regression test | Generate → save → restart API → retrieve the same output successfully. |

## Sprint exit criteria

A generated output can be saved, survives restart, and can be retrieved later with the exact knowledge provenance that grounded it.

---

# Remaining Sprint 2 — Revision and Version History

## Sprint goal

Make Workshop outputs editable over time without destroying the original work or its provenance.

## Backlog

| ID | Priority | Work item | Acceptance criteria |
|---|---|---|---|
| R2-01 | Must | Add output lineage fields | Records support root output ID, parent output ID, version number, and revision timestamp. |
| R2-02 | Must | Revision request model | User can provide a revision instruction such as “make this shorter” or “adapt this for executives.” |
| R2-03 | Must | Revision endpoint | Creates a new version rather than overwriting the original. |
| R2-04 | Must | Preserve provenance | Revised output retains or updates the applied Knowledge Asset IDs intentionally; the prior version remains unchanged. |
| R2-05 | Must | Revision grounding rules | The same source-grounded vs `design_choices` distinction applies to revisions. |
| R2-06 | Should | Version history endpoint | User can view all versions in chronological order. |
| R2-07 | Should | Compare versions | Return a compact summary of what changed between two output versions. |
| R2-08 | Must | Free-tier protection | One revision uses at most one Gemini generation call unless explicit repair is required. |

## Sprint exit criteria

Create v1 → revise to v2 → retrieve both → see lineage and knowledge provenance for each version.

---

# Remaining Sprint 3 — Interpretation Hardening and Source Audit

## Sprint goal

Make full-source interpretation trustworthy and manageable beyond the initial six real-book chunks.

## Backlog

| ID | Priority | Work item | Acceptance criteria |
|---|---|---|---|
| R3-01 | Must | Chunk reprocessing rules | A completed chunk can be intentionally reprocessed without silently duplicating active knowledge. |
| R3-02 | Must | Extraction versioning | New extraction results can be distinguished from older pre-schema or superseded results. |
| R3-03 | Must | Source audit view | Source view reports chunks, completed/failed jobs, current assets, overlap groups, missing evidence/keywords, and stale/old-version assets. |
| R3-04 | Must | Failed/stale job recovery | Failed or stale-running jobs can be safely retried. |
| R3-05 | Should | Chapter/section provenance | Preserve section metadata where source structure makes it available. |
| R3-06 | Must | Finish real-book interpretation test | Process the remaining chunks of *The Workshop Survival Guide* gradually within free-tier limits until the source reaches a complete interpretation state. |
| R3-07 | Must | Full-source quality review | Inspect duplicate rate, asset-type balance, evidence quality, confidence distribution, and false-positive knowledge extraction. |
| R3-08 | Should | Cross-format regression | Run at least one additional source format such as EPUB/TXT/HTML through the current pipeline. |

## Sprint exit criteria

One complete real book can move from upload to `knowledge_interpreted` with recoverable failures, auditable quality, and no uncontrolled duplicate accumulation.

---

# Remaining Sprint 4 — Generalize Workshop Output Modes

## Sprint goal

Prove that Knowledge Engine is not only a workshop-plan generator.

## Target output modes

| Mode | Example |
|---|---|
| Writing / editing | LinkedIn post, email, article section |
| Decision brief | Compare choices and recommend a path |
| Study guide | Structured learning notes and review questions |
| Product messaging | Value proposition, positioning, launch copy |
| Playbook / process | Practical step-by-step operating guide |

## Backlog

| ID | Priority | Work item | Acceptance criteria |
|---|---|---|---|
| R4-01 | Must | Output-mode metadata | Requested output mode is explicit and persisted with the output. |
| R4-02 | Must | Mode-sensitive generation instructions | Generator produces the requested artifact rather than a generic essay. |
| R4-03 | Must | Mode-sensitive quality checks | Each tested mode has simple acceptance criteria for structure, usefulness, provenance, and design-choice separation. |
| R4-04 | Must | Writing/editing test | Produce a grounded writing output from source knowledge. |
| R4-05 | Must | Decision-brief test | Produce a grounded decision-oriented output. |
| R4-06 | Must | Study/playbook test | Produce at least one learning or procedural artifact. |
| R4-07 | Should | Output templates | Add lightweight structured templates only where they materially improve consistency. |
| R4-08 | Must | Save + revise each tested mode | The persistence/version system works across modes, not just workshop plans. |

## Sprint exit criteria

At least four materially different output modes work end to end with saved outputs, revisions, provenance, and design choices.

---

# Remaining Sprint 5 — Multi-Source Synthesis

## Sprint goal

Move from “apply one source” to “reason across a body of knowledge.”

## Backlog

| ID | Priority | Work item | Acceptance criteria |
|---|---|---|---|
| R5-01 | Must | Multi-source retrieval | Workshop can retrieve relevant Knowledge Units across multiple selected sources. |
| R5-02 | Must | Cross-source provenance | Consolidated/synthesized units retain all contributing source IDs, asset IDs, chunk IDs, and evidence trails. |
| R5-03 | Must | Agreement detection | System can identify when multiple sources support substantially the same reusable idea. |
| R5-04 | Must | Contradiction/tension detection | System does not flatten conflicting source guidance into a fake consensus. |
| R5-05 | Must | Synthesis context | Workshop receives a compact context that separates agreements, distinct contributions, and tensions. |
| R5-06 | Must | Multi-source generated output | Generated answer can use several sources while returning the asset IDs that materially influenced it. |
| R5-07 | Should | Library-scoped retrieval | User can retrieve across an entire selected Library without manually listing every source ID. |
| R5-08 | Must | Two-source validation scenario | Demonstrate a real task where two sources produce a better output than either source alone. |

## Sprint exit criteria

A user can ask one real question across at least two sources and receive a useful synthesis with visible agreement/tension and traceable evidence.

---

# Remaining Sprint 6 — Web App MVP

## Sprint goal

Remove the need for curl/terminal commands for the core happy path.

## Core screens

| Screen | Minimum capability |
|---|---|
| Libraries | View/create libraries and enter one |
| Sources | Add source metadata and upload a file |
| Source detail | See extraction/chunk/interpretation progress and knowledge overview |
| Knowledge view | Browse/search consolidated Knowledge Units with provenance |
| Workshop | Enter situation, goal, audience, constraints, sources, output type, and tone |
| Output | Read generated result, applied knowledge, and design choices |
| Saved outputs | Open prior outputs and revision history |

## Backlog

| ID | Priority | Work item | Acceptance criteria |
|---|---|---|---|
| R6-01 | Must | Establish active web app | Build in `apps/web`; do not revive Streamlit. |
| R6-02 | Must | API client layer | Frontend calls the existing FastAPI endpoints cleanly with reusable request helpers. |
| R6-03 | Must | Library/source flow | User can create/select a library, add a source, and upload a file. |
| R6-04 | Must | Processing status UI | Extraction, chunking, interpretation, partial progress, failures, and quota stops are understandable. |
| R6-05 | Must | Knowledge exploration | Search/browse consolidated units without exposing raw giant JSON. |
| R6-06 | Must | Workshop form | Main brief inputs are usable from the browser. |
| R6-07 | Must | Output viewer | Shows content, provenance, and `design_choices` separately. |
| R6-08 | Must | Saved output history | User can reopen and revise earlier outputs. |
| R6-09 | Should | Loading/error states | Clear feedback for long processing, rate limits, missing keys, and validation failures. |

## Sprint exit criteria

A non-technical user can complete the validated end-to-end workflow from the browser without using the terminal.

---

# Remaining Sprint 7 — Durable Storage, Privacy, and Control

## Sprint goal

Replace prototype-only persistence assumptions and give the user control over their data.

## Backlog

| ID | Priority | Work item | Acceptance criteria |
|---|---|---|---|
| R7-01 | Must | Choose zero-cost durable storage path | Select the simplest no-paid-billing storage approach appropriate for v1 beta; document trade-offs before migration. |
| R7-02 | Must | Migrate core records | Libraries, sources, jobs, Knowledge Assets, outputs, and revisions survive normal app restarts reliably. |
| R7-03 | Must | Source deletion | User can delete a source and intentionally handle derived chunks/assets. |
| R7-04 | Must | Output deletion | User can delete generated outputs and revision history intentionally. |
| R7-05 | Must | Export | Export a saved output with its provenance in a user-friendly format. |
| R7-06 | Must | Usage/quota visibility | UI/API shows when interpretation/generation is paused due to free-tier constraints. |
| R7-07 | Must | Copyright/privacy safeguards | Uploaded copyrighted source files remain private/local to the user workflow and are never committed to the public repository. |
| R7-08 | Should | Data integrity checks | Detect missing source files, orphaned records, or broken provenance links. |

## Sprint exit criteria

User data is durable, deletable, exportable, and controlled without introducing paid infrastructure.

---

# Remaining Sprint 8 — Beta Hardening and Release Candidate

## Sprint goal

Turn the working product into a coherent v1 beta that another person can actually test.

## Backlog

| ID | Priority | Work item | Acceptance criteria |
|---|---|---|---|
| R8-01 | Must | End-to-end automated tests | Cover the main API happy path and critical persistence/provenance rules. |
| R8-02 | Must | Regression test set | Keep small known source snippets and expected retrieval/generation behaviors for repeatable checks. |
| R8-03 | Must | Error-path testing | Validate quota exhaustion, failed extraction, unsupported files, invalid AI output, restart recovery, and missing sources. |
| R8-04 | Must | Public-safe demo | Demo uses public-domain, licensed, or synthetic material rather than copyrighted uploaded books. |
| R8-05 | Must | Documentation refresh | Root README and active app docs describe the FastAPI/web architecture rather than the legacy prototype. |
| R8-06 | Must | Setup script/checklist | A fresh environment can install dependencies, configure the free Gemini key, and run API/web apps. |
| R8-07 | Should | Basic accessibility/responsive pass | Core web flow is usable on common desktop/mobile widths and with keyboard navigation where practical. |
| R8-08 | Must | External beta test | At least one person other than the builder can complete the core workflow and provide feedback. |
| R8-09 | Must | Release decision | Record what is in v1 beta, what is deliberately deferred, and the known limitations. |

## Sprint exit criteria

Knowledge Engine can be handed to a beta tester with setup instructions and public-safe sample material, and the tester can complete the core workflow without developer intervention.

---

# Explicitly Deferred Until After v1 Beta

These are valuable, but they should not block the first usable beta unless a sprint uncovers a genuine dependency:

| Deferred item | Reason |
|---|---|
| Paid model/API integrations | Violates the current zero-cost development rule. |
| Vector database / embeddings | Deterministic retrieval is already working; add only if evaluation proves it necessary. |
| Autonomous web research | Different product surface; not required for the core source-to-knowledge engine. |
| Team collaboration / permissions | Single-user beta should be proven first. |
| Enterprise SSO | Premature for v1. |
| Complex analytics | Usage evidence should exist before building analytics dashboards. |
| Native mobile apps | Responsive web flow first. |
| Marketplace/shared copyrighted library | Conflicts with privacy/copyright direction. |

---

# Recommended Execution Order

```text
R1  Save outputs
↓
R2  Revisions + version history
↓
R3  Full-source interpretation hardening
↓
R4  Multiple output modes
↓
R5  Multi-source synthesis
↓
R6  Web app MVP
↓
R7  Durable storage + privacy controls
↓
R8  Beta hardening + release candidate
```

The order is intentional: persistence and revision come before more generation features; interpretation quality is hardened before multi-source synthesis; and the frontend is built after the backend workflows it must expose are stable enough to avoid repeatedly redesigning the interface.

### Current position in that sequence

R1–R5 and R7 are complete for the current v1 candidate. R6 is implemented and has substantial internal browser evidence, while its remaining acceptance checks are being closed under A3. The active release work is therefore **R8 / A3**, specifically:

1. fresh-machine/local setup acceptance;
2. remaining full desktop happy-path and error-state checks;
3. external beta tester completion;
4. resolution or explicit deferral of critical defects;
5. final evidence-based v1 beta release decision.

No additional Gemini output-mode testing is required to close A2.

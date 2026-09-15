# Knowledge Engine — Release Acceptance Backlog

## Current release decision

**Internal local candidate; not yet an externally validated v1 beta.**

The original Remaining Sprint 1–8 backlog remains the historical feature scope. Implementation now exists across those areas, and the real-book extraction/audit acceptance work has been completed. The focus is no longer on rebuilding the extraction architecture; it is on proving output usefulness, browser usability, and external-user readiness.

## Product rules

- Development cost target: **$0**.
- Paid API billing and automatic paid fallback: **off**.
- Stop safely when free quota is exhausted.
- One extraction chunk per Gemini request; no shared source context across chunks.
- No automatic repair call.
- Preserve source, chunk, Knowledge Asset, Knowledge Unit, and output provenance.
- Do not commit private/copyrighted source material, generated backups, or API keys.
- Automated fixtures prove behavior, not real-model usefulness.
- Lexical agreement/tension checks assist review; they do not prove semantic correctness.

---

# Acceptance Sprint A1 — Real-Source Completion and Knowledge Quality

**Status: Complete for the current v1 candidate.**

The real *Workshop Survival Guide* source is restored and fully interpreted at **46/46 chunks**. The latest active state contains **121 Knowledge Assets**, with **0 missing evidence**, **0 missing keywords**, and confidence distribution **83 at 5 / 38 at 3**. Thirteen evidence items remain in the manual review queue; inspection found them source-supported compressed or near-exact evidence rather than known defects.

Historical cross-chunk provenance defects were identified and reprocessed. The known chunk-025 compound crowd-recovery asset was also repaired deterministically: `Talking in circles to recover attention` now belongs to chunk 025, while `Borrowing goodwill to reclaim attention` remains a separate chunk-026 process.

A live strict single-chunk provider control on chunk 007 returned **5 valid assets**, matching its historical active count and validating the production extraction contract.

| ID | Status | Result |
|---|---|---|
| A1-01 | Complete | Real source, chunks, jobs, and asset history restored without losing provenance. |
| A1-02 | Complete | Free-tier/billing-disabled operating rule confirmed by the owner; no paid fallback exists. |
| A1-03 | Complete | Source reached 46/46 interpreted chunks. |
| A1-04 | Complete | Full audit performed; current active counts documented. |
| A1-05 | Complete | Evidence, confidence, duplicates/provenance, and known false-positive/atomicity issues reviewed and repaired where necessary. |
| A1-06 | Complete with limitation | Section hints remain useful where available; PDF chapter inference is still limited. |
| A1-07 | Complete | R3-06/R3-07 status updated with real-source evidence. |

### Architecture conclusion from A1

Shared-context multi-chunk extraction is not used in production. Live probes showed under-extraction and cross-chunk evidence leakage. Source-level orchestration may select multiple chunks, but each chunk is processed as its own strict Gemini request and consumes its own provider attempt.

Gemini's asynchronous Batch API is also not used because the current Gemini Developer API free tier does not include Batch processing.

---

# Acceptance Sprint A2 — Real-Model Output and Multi-Source Quality

## Goal

Prove that generated artifacts are useful and grounded with the real provider, not only with mocked responses.

## Live acceptance evidence so far

A real-provider **Workshop plan** test was run twice against the same brief and the same eight retrieved Knowledge Units from *The Workshop Survival Guide*. Retrieval was stable across both runs.

The task was to design a **90-minute beginner SOP-writing workshop** for junior operations staff, with hands-on practice, Q&A time, a participant-created draft SOP, and no long lecture blocks.

### Run 1

- Retrieval returned eight relevant Knowledge Units, including schedule design, short-lecture guidance, format switching, immediate practice, exercise design, and Q&A guidance.
- The generated agenda totaled 90 minutes and was practically useful, but the local validator initially surfaced a false-positive unparsed Markdown table header.
- A 25-minute drafting block also conflicted with the retrieved 20-minute format-switch guidance.
- Gemini introduced an unsupported domain framework for SOP components rather than keeping missing domain content neutral.
- The output was correctly retained as acceptance evidence rather than overwritten.

### Run 2 after fixes

- Retrieval returned the same eight Knowledge Units in the same order.
- The generated agenda passed the local timing check at **Requested: 90 min / Calculated: 90 min**.
- The prior 25-minute practice block was split into 15-minute independent practice plus 15-minute peer review, so the timed structure complied with the retrieved format-switch rule.
- The model still introduced an unsupported SOP component list: `Title; Scope; Steps; Troubleshooting`.
- A new deterministic grounding validator correctly changed the saved output from `checks passed` to **`needs review`** while leaving the timing check passed.
- The generation prompt was tightened to prefer neutral placeholders when required domain knowledge is absent and to require traceable `applied_knowledge` IDs for material source guidance.
- Regression coverage was added for the live agenda-header and unsupported-component-list failures.

### Real revision acceptance

Both real Workshop outputs were then corrected manually through the product's revision workflow with **zero additional Gemini calls**.

- **Revision case 1:** the second live output's unsupported `Title; Scope; Steps; Troubleshooting` list was replaced with neutral wording referring to the SOP format or requirements participants are expected to use. Version 2 revalidated at **90/90 minutes** with `checks passed`; Version 1 remained unchanged; the comparison view showed the content and design-choice changes.
- **Revision case 2:** the first live output's unsupported `Objective; Prerequisites; Steps; Troubleshooting` list was removed and its 25-minute drafting block was restructured into separately timed 15-minute drafting and 10-minute peer-review segments while preserving the 90-minute total. Version 2 revalidated at **90/90 minutes** with `checks passed`; Version 1 remained unchanged; the comparison view showed the agenda, activity, and design-choice changes.
- Both revisions preserved the original knowledge snapshot/provenance while clearly marking the new versions as manually supplied or edited.

**A2 conclusion so far:** retrieval quality and workshop timing behavior are promising, the quality layer catches the observed unsupported-list failure class, and the revision/history/compare workflow has now been validated twice with real outputs. The Workshop mode is **not yet fully accepted for first-pass generation** because the latest real Gemini sample still required a grounding correction before it was acceptable.

## Backlog

| ID | Priority | Work item | Acceptance criteria | Current status |
|---|---|---|---|---|
| A2-01 | Must | Test four materially different output modes | Generate real-provider outputs for at least four modes such as workshop plan, writing, decision brief, study guide/playbook, or product messaging. | In progress — Workshop plan tested; three additional modes remain. |
| A2-02 | Must | Review grounding | For every tested output, verify source claims, applied Knowledge Asset IDs, design-choice separation, and absence of unsupported factual claims. | In progress — live Workshop tests exposed unsupported domain content; validator flagged it and both saved outputs were corrected through manual revisions. |
| A2-03 | Must | Review usefulness and structure | Each tested mode meets its intended structure and is practically usable without major rewriting. | In progress — revised Workshop outputs are structurally usable and pass 90/90 timing; three additional modes remain. |
| A2-04 | Must | Revise real outputs | Revise at least two generated outputs and verify lineage, provenance, and original-version preservation. | **Complete — two real Workshop outputs were manually revised; both preserved Version 1, revalidated Version 2, retained provenance, and exposed v2→v1 comparisons.** |
| A2-05 | Must | Run one meaningful two-source task | Compare a multi-source result against each single-source result using the same task. | Pending. |
| A2-06 | Must | Record agreements/tensions honestly | Confirm whether candidate agreement/tension flags are useful; record missed semantic conflicts or false positives instead of treating lexical checks as proof. | Pending real two-source test. |
| A2-07 | Must | Close R4 and R5 quality gates | Update sprint status with actual real-model results and the two-source comparison. | In progress. |

## Exit criteria

At least four real-model outputs and one real two-source task are judged useful, grounded, and traceable, with known limitations documented.

---

# Acceptance Sprint A3 — Browser, External Tester and Beta Release Decision

## Goal

Prove that a non-technical person can use the product through the browser and make the final v1 beta decision.

## Backlog

| ID | Priority | Work item | Acceptance criteria |
|---|---|---|---|
| A3-01 | Must | Fresh-machine/local setup acceptance | Follow `README.md` setup from a clean environment and run the test suite successfully. Record any platform-specific fixes. |
| A3-02 | Must | Desktop browser happy path | Create/select library → add/process source → interpret → search/select knowledge → Workshop → save → revise → compare → export without terminal API calls. |
| A3-03 | Must | Error-state browser checks | Missing key, quota pause, invalid/unsupported input, and stale/failed job states produce understandable messages without losing completed work. |
| A3-04 | Must | Mobile-width visual pass | Check narrow screen widths for clipping, unreadable text, horizontal overflow, and unusable forms. |
| A3-05 | Should | Keyboard/accessibility pass | Complete the main flow with keyboard navigation; verify visible focus and meaningful labels. |
| A3-06 | Must | External beta test | At least one person other than the builder completes the core workflow and provides structured feedback. |
| A3-07 | Must | Resolve critical defects | Fix or explicitly defer any issue that prevents setup, core workflow completion, provenance understanding, or safe quota handling. |
| A3-08 | Must | Final release decision | Update `docs/beta_test_checklist.md`, `docs/sprint_status.md`, and README readiness language to either `v1 beta` or `not ready`, with reasons. |

## Exit criteria

Another person can complete the intended workflow through the browser, critical defects are resolved, and the repository contains an explicit evidence-based v1 beta release decision.

---

# Current verification baseline

Latest local automated verification on 2026-09-15: **157 tests passed**, with two upstream deprecation warnings. The suite uses fake/in-memory provider behavior and does not consume Gemini quota.

The real-provider extraction and Workshop output validation were performed separately under the project's explicit free-tier call budget. Live evidence is documented in `docs/sprint_status.md` and `docs/build_log.md`.

---

# What is no longer a development backlog

The following areas have implementation and regression coverage and should not be rebuilt from scratch unless acceptance testing exposes a new defect:

- saved outputs and persistent provenance;
- output revisions, history, and comparisons;
- reprocessing/versioning and source audit tooling;
- strict single-chunk Gemini interpretation;
- six output-mode instruction sets;
- multi-source retrieval and synthesis context;
- browser UI for the core workflow;
- local SQLite persistence, backup/export, and deletion controls;
- zero-cost quota guardrails;
- synthetic demo, setup scripts, and automated regression tests.

The focus from here is **A2 output quality and A3 release acceptance**, not more extraction batching experiments.

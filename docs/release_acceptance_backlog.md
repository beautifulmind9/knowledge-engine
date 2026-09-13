# Knowledge Engine — Release Acceptance Backlog

## Why this backlog exists

The original Remaining Sprint 1–8 backlog remains the authoritative feature scope. The implementation pass published in commit `b1ed3277b3c3abf22ccd0b65cfef9bed932818b8` now covers all eight sprint areas, so the execution plan should no longer treat R1–R8 as eight untouched development sprints.

This backlog contains only the material acceptance work still required before Knowledge Engine can be called an externally validated v1 beta.

Current release decision: **internal local candidate; not yet externally validated v1 beta**.

## Product rules

- Development cost target: **$0**.
- Paid API billing and automatic paid fallback: **off**.
- Stop safely when free quota is exhausted.
- Preserve source, chunk, Knowledge Asset, Knowledge Unit and output provenance.
- Do not commit private/copyrighted source material, generated backups or API keys.
- Automated fixtures prove behavior, not real-model usefulness.
- Lexical agreement/tension checks assist review; they do not prove semantic correctness.

---

# Acceptance Sprint A1 — Real-Source Completion and Knowledge Quality

## Goal

Prove that the hardened interpretation pipeline can complete and audit the real book already used to validate Knowledge Engine.

## Backlog

| ID | Priority | Work item | Acceptance criteria |
|---|---|---|---|
| A1-01 | Must | Safely restore the existing Workshop Survival Guide source and jobs | Existing source, chunk, job and asset history is available in the current candidate without losing provenance. |
| A1-02 | Must | Confirm free-tier Gemini setup | `GEMINI_FREE_TIER_CONFIRMED=true` is used only after confirming the project has billing disabled; no paid fallback exists. |
| A1-03 | Must | Complete remaining interpretation | Process remaining chunks gradually within the local/free-tier limits until the source reaches complete interpretation or documented provider quota pauses. |
| A1-04 | Must | Run source audit | Record total chunks, completed/failed jobs, active assets, overlap groups, old/superseded assets and missing evidence/keywords. |
| A1-05 | Must | Perform qualitative knowledge review | Inspect a representative spread across the book for evidence faithfulness, false positives, asset typing, confidence, duplicates and missed knowledge. Record concrete examples. |
| A1-06 | Should | Review chapter/section hints | Confirm where heading metadata is useful and record the known PDF chapter-inference limitation. |
| A1-07 | Must | Close R3-06 and R3-07 | Update `docs/sprint_status.md` with actual full-book results rather than fixture evidence. |

## Exit criteria

One real full book reaches an auditable completed state, and there is enough evidence to say the extracted knowledge is trustworthy enough for beta use.

---

# Acceptance Sprint A2 — Real-Model Output and Multi-Source Quality

## Goal

Prove that the generated artifacts are useful and grounded with the real provider, not only with mocked responses.

## Backlog

| ID | Priority | Work item | Acceptance criteria |
|---|---|---|---|
| A2-01 | Must | Test four materially different output modes | Generate real-provider outputs for at least four modes such as workshop plan, writing, decision brief, study guide/playbook or product messaging. |
| A2-02 | Must | Review grounding | For every tested output, verify source claims, applied Knowledge Asset IDs, design-choice separation and absence of unsupported factual claims. |
| A2-03 | Must | Review usefulness and structure | Each tested mode meets its intended structure and is practically usable without major rewriting. |
| A2-04 | Must | Revise real outputs | Revise at least two generated outputs and verify lineage, provenance and original-version preservation. |
| A2-05 | Must | Run one meaningful two-source task | Compare a multi-source result against each single-source result using the same task. |
| A2-06 | Must | Record agreements/tensions honestly | Confirm whether candidate agreement/tension flags are useful; record missed semantic conflicts or false positives instead of treating lexical checks as proof. |
| A2-07 | Must | Close R4 and R5 quality gates | Update sprint status with actual real-model results and the two-source comparison. |

## Exit criteria

At least four real-model outputs and one real two-source task are judged useful, grounded and traceable, with known limitations documented.

---

# Acceptance Sprint A3 — Browser, External Tester and Beta Release Decision

## Goal

Prove that a non-technical person can use the product through the browser and make the final v1 beta decision.

## Backlog

| ID | Priority | Work item | Acceptance criteria |
|---|---|---|---|
| A3-01 | Must | Fresh-machine/local setup acceptance | Follow `README.md` setup from a clean environment and run the test suite successfully. Record any platform-specific fixes. |
| A3-02 | Must | Desktop browser happy path | Create/select library → add/process source → interpret → search/select knowledge → Workshop → save → revise → compare → export without terminal API calls. |
| A3-03 | Must | Error-state browser checks | Missing key, quota pause, invalid/unsupported input and stale/failed job states produce understandable messages without losing completed work. |
| A3-04 | Must | Mobile-width visual pass | Check narrow screen widths for clipping, unreadable text, horizontal overflow and unusable forms. |
| A3-05 | Should | Keyboard/accessibility pass | Complete the main flow with keyboard navigation; verify visible focus and meaningful labels. |
| A3-06 | Must | External beta test | At least one person other than the builder completes the core workflow and provides structured feedback. |
| A3-07 | Must | Resolve critical defects | Fix or explicitly defer any issue that prevents setup, core workflow completion, provenance understanding or safe quota handling. |
| A3-08 | Must | Final release decision | Update `docs/beta_test_checklist.md`, `docs/sprint_status.md` and README readiness language to either `v1 beta` or `not ready`, with reasons. |

## Exit criteria

Another person can complete the intended workflow through the browser, critical defects are resolved, and the repository contains an explicit evidence-based v1 beta release decision.

---

# Pre-flight verification before A1

Before doing more feature work, pull the published implementation and confirm the candidate baseline locally:

```bash
cd /workspaces/knowledge-engine
git pull --ff-only
bash scripts/setup.sh
.venv/bin/python -m pytest apps/api/tests -q
```

Expected implementation-pass baseline: **44 passing tests**. If the local result differs, investigate before running paid-or-quota-sensitive acceptance steps.

The synthetic demo can be exercised without an AI key:

```bash
bash scripts/run.sh
# in another terminal
.venv/bin/python scripts/seed_demo.py
```

Open `http://127.0.0.1:8000` and use the demo to smoke-test the browser workflow before restoring the real source.

---

# What is no longer a development backlog

The following areas now have implementation and regression coverage and should not be rebuilt from scratch unless acceptance testing exposes a defect:

- Saved outputs and persistent provenance
- Output revisions, history and comparisons
- Reprocessing/versioning and source audit tooling
- Six output-mode instruction sets
- Multi-source retrieval and synthesis context
- Browser UI for the core workflow
- Local SQLite persistence, backup/export and deletion controls
- Zero-cost quota guardrails
- Synthetic demo, setup scripts and automated regression tests

The focus from here is **acceptance, quality evidence and release readiness**, not adding more architecture.
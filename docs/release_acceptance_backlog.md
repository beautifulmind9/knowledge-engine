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

**Status: Complete for the current v1 candidate (2026-09-20).**

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

### Decision Brief grounding acceptance evidence — 2026-09-20

Three controlled real-provider Decision Brief runs used the same *Workshop Survival Guide* brief and the same stable eight-unit retrieval set. The runs exposed a recurring cross-mode grounding pattern: Gemini can preserve a source-backed idea while adding unsupported quantities, renamed concepts, source-sounding method names, or invented taxonomies.

- The first run introduced a derived 15-minute Q&A allocation, an unsupported K/S/W taxonomy, and a coined “Iterative Pass Approach.” The saved output was later reclassified to **needs review** after the shared grounding layer was expanded.
- The second run removed K/S/W but still coined labels including “20-Minute Variation Rule,” “Interleaved Design,” “Buffer-Responsive Design,” and “Iterative Pass method,” and presented the 15-minute Q&A allocation too prescriptively. Shared prompt and validator rules were tightened rather than patching Decision Brief specifically.
- The controlled post-fix run saved as **needs review** during generation, proving the shared validator now catches real-provider grounding defects before acceptance. It exposed additional forms: K/S/W (Knowledge/Skill/Wisdom), a false claim that the taxonomy was referenced in supplied knowledge, and a quoted lowercase ‘iterative pass’ method formalization.
- Grounding report version **8** now reviews three-or-more slash taxonomies when paired with matching expansions or explicit taxonomy language, conservative unsupported source-attribution phrases, and quoted lowercase formalized method names. Ordinary slash notation, exact names present in the brief/retrieved knowledge, and locally disclosed/tracked generator-created labels remain allowed.

No further Decision Brief provider rerun is required for A2. The repeated real outputs are retained as acceptance evidence; the remaining Gemini calls should increase mode coverage and complete the meaningful two-source task.

### A2 completion evidence — 2026-09-20

A2 was completed with four materially different real-provider modes ending in grounded, useful, traceable accepted artifacts after human review and, where necessary, manual revision with zero additional provider calls:

- **Workshop Plan:** two real Gemini runs plus two manual revision cases. Timing, provenance, version preservation, and comparison were exercised.
- **Decision Brief:** repeated real runs exposed renamed concepts, unsupported quantities, invented taxonomies, and false source attribution. Grounding review was hardened through report version 8; the accepted Version 2 removed unsupported K/S/W and generator-created framework names, preserved exact source terminology, and retained traceable applied knowledge.
- **Study Guide:** the real output was structurally useful and traceable but coined the unsupported label `Iterative Design`. The accepted manual Version 2 removed the label and tightened several practice/checking statements to the retrieved evidence.
- **Research / Synthesis Brief:** single-source baselines were created for *The Workshop Survival Guide* and *Made to Stick*. Both were reviewed and manually tightened where necessary before the combined task.

The meaningful two-source task used the same workshop-attention/retention question for both single-source baselines and the combined result. *Made to Stick* contributed message-design concepts such as the Curse of Knowledge, Unexpectedness/knowledge gaps, and the Inverted Pyramid. *The Workshop Survival Guide* contributed teaching formats, multiple-pass workshop design, lecture construction, and attention-recovery techniques.

The first combined output incorrectly claimed direct agreement between the sources and introduced unsupported K/S/W and a 20-minute rule that were not in the explicitly selected evidence. The accepted Version 2 removed those claims, preserved source-specific attribution, described the sources as **complementary with different scopes**, and labeled the combined six-step workflow as a cross-source synthesis rather than a source-provided framework.

The lexical preview reported **0 candidate agreements / 0 possible tensions** for the combined task. Human review still found a useful complementary relationship and scope difference. This confirms that lexical agreement/tension flags remain advisory and must not be treated as semantic proof.

For the second real source, *Made to Stick* was processed through the current production pipeline for **10 of 91 chunks**, producing **38 active assets / 35 consolidated Knowledge Units**. That partial interpretation is sufficient for this A2 comparison but is not a claim that the full book has been interpreted or audited. Twenty-nine evidence items in the partial source remained in the human-review queue.

### Known A2 limitations

- Deterministic grounding checks are conservative review signals, not semantic certification.
- Gemini can still rename source concepts, introduce plausible specificity, or overstate cross-source relationships; human review remains required.
- Manual revision is an accepted safety path and preserves the original model output for audit.
- Lexical agreement/tension detection can miss meaningful complementary relationships and scope differences.
- The *Made to Stick* production interpretation used for A2 is intentionally partial (10/91 chunks).

## Backlog

| ID | Priority | Work item | Acceptance criteria | Current status |
|---|---|---|---|---|
| A2-01 | Must | Test four materially different output modes | Generate real-provider outputs for at least four modes such as workshop plan, writing, decision brief, study guide/playbook, or product messaging. | **Complete — Workshop Plan, Decision Brief, Study Guide, and Research / Synthesis were exercised with the real provider and ended in accepted grounded artifacts after review/revision.** |
| A2-02 | Must | Review grounding | For every tested output, verify source claims, applied Knowledge Asset IDs, design-choice separation, and absence of unsupported factual claims. | **Complete — all accepted A2 artifacts were human-reviewed against retained evidence; known grounding failure classes are documented and shared deterministic review is at version 8.** |
| A2-03 | Must | Review usefulness and structure | Each tested mode meets its intended structure and is practically usable without major rewriting. | **Complete — accepted artifacts are structurally usable for their intended mode; some required targeted manual grounding cleanup rather than regeneration.** |
| A2-04 | Must | Revise real outputs | Revise at least two generated outputs and verify lineage, provenance, and original-version preservation. | **Complete — two real Workshop outputs were manually revised; both preserved Version 1, revalidated Version 2, retained provenance, and exposed v2→v1 comparisons.** |
| A2-05 | Must | Run one meaningful two-source task | Compare a multi-source result against each single-source result using the same task. | **Complete — same research/synthesis task run against Workshop Survival Guide only, Made to Stick only, and both sources together.** |
| A2-06 | Must | Record agreements/tensions honestly | Confirm whether candidate agreement/tension flags are useful; record missed semantic conflicts or false positives instead of treating lexical checks as proof. | **Complete — lexical preview showed 0/0 while human review found complementary scopes; the combined first pass also overclaimed agreement and was manually corrected.** |
| A2-07 | Must | Close R4 and R5 quality gates | Update sprint status with actual real-model results and the two-source comparison. | **Complete — release docs updated with real-model and two-source acceptance evidence.** |

## Exit criteria

At least four real-model outputs and one real two-source task are judged useful, grounded, and traceable, with known limitations documented.

---

# Acceptance Sprint A3 — Browser, External Tester and Beta Release Decision

## Goal

Prove that a non-technical person can use the product through the browser and make the final v1 beta decision.

## Evidence completed so far

- **A3-04 mobile-width pass:** Workshop, Saved outputs, and Knowledge were exercised at 393×852 without blocking horizontal page overflow; layouts stacked correctly. The navigation remains horizontally scrollable and discoverability polish is deferred.
- **A3-05 core keyboard pass:** the main source/search/Ask/Browse/filter/selection/Workshop handoff flow was exercised in Safari. Safari may require Option+Tab or the browser keyboard-navigation setting for buttons.
- Several error states were exercised with zero provider calls: missing-key Knowledge generation, missing-key Data & usage messaging, blank chapter/idea validation, and duplicate-storage server locking.
- Markdown export, manual revision, version preservation, comparison, applied evidence, and provenance display were exercised repeatedly during A2.
- Still open: fresh setup, the remaining complete desktop happy path, quota-pause and any still-unverified stale/failed-job states, external tester acceptance, critical-defect resolution/deferral, and the final release decision.

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

Latest local automated verification on 2026-09-20: **205 tests passed**, with two unchanged upstream deprecation warnings. The suite uses fake/in-memory provider behavior and does not consume Gemini quota.

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

The focus from here is **A3 release acceptance**, not more extraction batching experiments or additional A2 provider calls.


## Knowledge-page cleanup evidence — 2026-09-16

Implemented scope-aware question wording, separate Search/Ask results, lazy Browse with 10-unit pages and type/chapter filters, and stale-response safeguards. Evidence/provenance and Workshop selection remain available. Full local suite: 180 Python tests, including 7 executable JavaScript state/view regressions. Zero Gemini calls. Desktop/mobile visual acceptance remains pending because the cloud preview could not reach localhost. A2 real-output/two-source acceptance and external beta acceptance remain open; this change does not close them.

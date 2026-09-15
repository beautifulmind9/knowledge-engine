# Build Log

## 2026-09-15

### Milestone

Real-source extraction architecture and audit stabilized, followed by first real-model output acceptance work and completion of the required real revision acceptance cases.

### Completed

- Finished the real *Workshop Survival Guide* interpretation at 46/46 chunks.
- Reprocessed historical old-schema and provenance-defective chunks without losing prior history.
- Added and validated stricter evidence provenance checks.
- Calibrated confidence guidance without broad destructive reprocessing.
- Simplified the Gemini-facing structured-output schema while preserving strict internal Knowledge Asset models.
- Tested shared-context extraction at multiple sizes and found non-deterministic under-extraction plus cross-chunk evidence leakage.
- Investigated Gemini asynchronous Batch API; live submission returned `FAILED_PRECONDITION` on the billing-disabled/free-tier project, so Batch API was removed from the production path.
- Standardized production extraction on **one chunk per Gemini request**, with no shared chunk context.
- Ran a live strict single-chunk control on chunk 007: 5 valid assets, matching the historical active count, all confidence 5.
- Repaired the known compound chunk-025 crowd-recovery asset deterministically with zero Gemini calls.
- Verified final real-source state: 121 active assets, 0 missing evidence, 0 missing keywords, confidence distribution 83×5 / 38×3, and 13 evidence-review items retained as a manual review queue.
- Cleaned the completed-source browser state so completed sources no longer invite another Gemini interpretation and old resolved failures do not clutter recovery actions.
- Ran the first real-provider A2 retrieval test for a 90-minute SOP-writing workshop; the same eight relevant Knowledge Units were retrieved consistently across repeated previews.
- Ran two real-provider Workshop-plan generations against the same brief and retrieved knowledge.
- First live output exposed three useful defects: a false-positive Markdown agenda-header warning, a 25-minute practice block that conflicted with the retrieved 20-minute format-switch rule, and unsupported SOP-domain content.
- Fixed the agenda-header parser regression and tightened the Workshop generation prompt to require explicit timed format changes and avoid unsupported domain frameworks.
- Second live output produced a valid 90-minute agenda with separate 15-minute independent-practice and peer-review blocks; timing checks passed.
- The second output still invented an unsupported SOP component list: `Title; Scope; Steps; Troubleshooting`.
- Added a deterministic grounding-review heuristic so the saved output is now correctly reported as **needs review** while its agenda timing remains **passed**.
- Tightened generation guidance again to use neutral placeholders when required domain knowledge is not supplied and require traceable applied Knowledge Asset IDs for material source guidance.
- Preserved both first-pass live outputs unchanged as acceptance evidence; no automatic repair call was used.
- Completed **two real manual revision acceptance cases** with zero additional Gemini calls:
  - Revision 1 removed the unsupported `Title; Scope; Steps; Troubleshooting` list from the second live output, revalidated Version 2 at 90/90 minutes with checks passed, preserved Version 1, and verified the v2→v1 comparison.
  - Revision 2 removed the unsupported `Objective; Prerequisites; Steps; Troubleshooting` list from the first live output and restructured its 25-minute drafting block into 15-minute drafting plus 10-minute peer review, revalidated Version 2 at 90/90 minutes with checks passed, preserved Version 1, and verified the v2→v1 comparison.
- Confirmed that both manual Version 2 records are labeled as manually supplied or edited while retaining the original Knowledge Asset provenance and visible source evidence.
- Brought the full local suite to **157 passing tests** with two unrelated upstream deprecation warnings.

### Key learning

Provider-call efficiency is not the same thing as extraction quality. Putting several chunks in one model context reduced structural reliability and created provenance risk even when token limits were not the bottleneck.

The safer extraction architecture is to treat the chunk as the unit of AI interpretation and the source-level run as orchestration only.

The first output-quality acceptance run produced a second lesson: **passing structural/timing checks is not the same thing as being grounded**. A useful-looking plan can still smuggle in plausible domain knowledge that was never supplied. Quality review therefore needs separate checks for timing/structure and grounding, with human review still required.

The revision acceptance work added a third lesson: preserving the flawed first-pass output is valuable. The product can turn a detected grounding/timing problem into a traceable corrected Version 2 without erasing what the model originally produced, and the comparison view makes the intervention auditable.

### Product decision

Knowledge Engine's current definition is:

> Knowledge Engine transforms source material into structured, reusable knowledge assets that can be connected, retrieved, and assembled into useful outputs.

Short form: **Knowledge in. Useful outputs out.**

The current quality posture is intentionally conservative: when an output is structurally valid but introduces unsupported domain detail, the system should surface **needs review** rather than treating the artifact as approved.

The required A2 revision acceptance criterion is now complete: **2 of 2 real outputs revised with lineage, provenance, original-version preservation, revalidation, and comparison verified.**

### Next acceptance work

- Test at least three additional materially different real-provider output modes.
- Produce or otherwise document the remaining limitation around a fully grounded first-pass Workshop generation.
- Run one meaningful real two-source comparison.
- Complete the remaining desktop happy path plus mobile/keyboard browser acceptance.
- Run one external beta test.

---

## 2026-06-02

### Milestone

First Streamlit application running.

### Completed

- Built PDF extraction pipeline
- Built chunking pipeline
- Built graph storage model
- Built graph validation
- Built graph cleaning
- Built source explorer
- Built concept explorer
- Built chapter explorer
- Built chapter group explorer
- Built problem search
- Built progress tracker
- Built knowledge audit
- Built first Streamlit interface

### Key Learning

The most valuable use case discovered so far is not book exploration.

It is applying knowledge from multiple sources to real-world problems.

Example:

Using concepts from Made to Stick to improve a message asking a friend for help.

### Product Insight

Users do not necessarily want to read more books.

Users want to apply knowledge from books to decisions, communication, learning, and work.

### Next Steps at that time

- Improve Apply Knowledge workflow
- Build Example Explorer
- Build Decision Rule Explorer
- Add normalization layer
- Improve portfolio documentation
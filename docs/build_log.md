# Build Log

## 2026-09-15

### Milestone

Real-source extraction architecture and audit stabilized.

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
- Brought the full local suite back to **153 passing tests** after the architecture change.

### Key learning

Provider-call efficiency is not the same thing as extraction quality. Putting several chunks in one model context reduced structural reliability and created provenance risk even when token limits were not the bottleneck.

The safer architecture is to treat the chunk as the unit of AI interpretation and the source-level run as orchestration only.

### Product decision

Knowledge Engine's current definition is:

> Knowledge Engine transforms source material into structured, reusable knowledge assets that can be connected, retrieved, and assembled into useful outputs.

Short form: **Knowledge in. Useful outputs out.**

### Next acceptance work

- Review real Gemini outputs across at least four materially different modes.
- Revise at least two real outputs and verify lineage/grounding.
- Run one meaningful real two-source comparison.
- Complete desktop/mobile/keyboard browser acceptance.
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

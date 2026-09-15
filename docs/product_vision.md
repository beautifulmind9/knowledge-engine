# Product Vision

## Product definition

**Knowledge Engine transforms source material into structured, reusable knowledge assets that can be connected, retrieved, and assembled into useful outputs.**

Short form: **Knowledge in. Useful outputs out.**

## What the product is for

People often read books, reports, articles, notes, and research but struggle to retrieve the right idea later and apply it to a real task. Knowledge Engine is designed to reduce that gap between consuming information and using it.

The product is not primarily a summarizer or a chat-with-PDF tool. It creates a reusable knowledge layer that can support writing, decisions, study, planning, messaging, playbooks, workshops, and other practical outputs.

## Core product model

```text
Private Library
↓
Sources
↓
Chunks
↓
Validated Knowledge Assets
↓
Consolidated Knowledge Units
↓
Retrieval / Selection
↓
Knowledge Workshop
↓
Saved Outputs + Revisions
```

Knowledge Assets retain source and chunk provenance, evidence, retrieval keywords, confidence, and type-specific structure. Current asset types include concepts, problems, principles, insights, decision rules, patterns, examples, warnings, frameworks, mental models, and processes.

## Main workflow

1. Add a source to a private library.
2. Extract and chunk the source while preserving useful section hints where possible.
3. Interpret each chunk into structured Knowledge Assets.
4. Validate the result locally before storing or superseding existing assets.
5. Search or retrieve relevant knowledge across one source or a library.
6. Consolidate overlapping raw assets into Knowledge Units while preserving evidence trails.
7. Use selected knowledge in the Workshop to create a useful output.
8. Save, revise, compare, and export outputs with provenance.

## AI role

AI is used as an interpretation and generation layer, not as the system of record.

For source interpretation, each chunk is sent to Gemini independently. Chunks do not share model context. The returned structure is validated against strict internal Pydantic models before it can become active knowledge.

For Workshop generation, the model receives the task brief plus retrieved knowledge and must distinguish source-grounded claims from design choices. Saved records retain the applied Knowledge Asset references.

## Reliability rules

The current architecture deliberately favors isolation and auditability over provider-call efficiency:

- one source chunk per Gemini extraction request;
- no shared multi-chunk model context;
- no automatic repair calls;
- no automatic paid fallback;
- one provider attempt per explicit extraction/generation request;
- strict local schema validation before replacement;
- failed replacements do not supersede good active assets;
- local daily call cap for zero-cost use.

Shared-context multi-chunk extraction was tested and produced under-extraction and cross-chunk provenance leakage. Gemini's asynchronous Batch API is not used because it is not available on the current Gemini Developer API free tier.

## Current interface

The active product is a local single-owner FastAPI application with a browser interface in `apps/web`. The earlier Streamlit implementation is archived under `legacy/streamlit_prototype` and is no longer the active application.

The browser currently supports library/source management, uploads, extraction/chunking, Gemini interpretation, knowledge browsing and search, Workshop generation, saved outputs, revisions, comparison, export, quota controls, audit views, and data backup.

## Current validation state

The real *Workshop Survival Guide* source has been fully interpreted at 46/46 chunks. The latest audited active set contains 121 Knowledge Assets, with no missing evidence and no missing keywords. The remaining 13 evidence-review items are retained as a manual review queue rather than classified defects; they were inspected as source-supported compressed or near-exact evidence.

A live strict single-chunk control on chunk 007 returned five valid assets, matching its historical active count. A known compound crowd-recovery asset in chunk 025 was repaired deterministically so `Talking in circles` and `Borrowing goodwill` are now separate atomic assets with correct provenance.

This closes the real-source extraction/audit acceptance area, but it does not close the overall v1 beta. Real-output usefulness across multiple modes, a meaningful real two-source comparison, browser/mobile acceptance, and an external tester are still required.

## Long-term direction

The product can expand from a private local workspace into a broader Knowledge Application Engine: richer library organization, stronger semantic retrieval and relationship modeling, more output types, and eventually multi-user/private-account infrastructure if that becomes a product requirement.

The central principle should remain the same: source material is converted into traceable reusable knowledge first, and outputs are assembled from that knowledge rather than treating every task as a fresh unstructured chat.

# Knowledge Engine Roadmap

## Product direction

Knowledge Engine transforms source material into structured, reusable knowledge assets that can be connected, retrieved, and assembled into useful outputs.

Short version:

> Knowledge in. Useful outputs out.

The current product is no longer the original Streamlit prototype. The prototype remains in `legacy/` as reference material while the active build uses a FastAPI backend and a new Knowledge Asset model.

---

## Phase 1: Source Processing Foundation

### Completed

- Library records
- Source records
- Multi-format source upload
- Text extraction, including text-based PDFs
- Text retrieval
- Chunking with chunk IDs and provenance
- Chunk retrieval
- Development-state persistence across API reloads

Core workflow:

```text
Library
↓
Source
↓
Upload
↓
Extract Text
↓
Chunks
```

---

## Phase 2: Knowledge Interpretation Pipeline

### Completed

- Canonical Knowledge Asset schema
- Separate asset types for concepts, problems, principles, insights, decision rules, patterns, examples, warnings, frameworks, mental models, and processes
- Type-specific validation
- Required evidence and grounded keywords for new extraction
- Explicit framework components and process steps
- Knowledge Extraction Job lifecycle
- Structured model request generation
- Gemini free-tier integration behind a provider service
- Structured JSON validation
- One repair attempt for invalid model output
- Asset provenance back to source and chunk
- Persistent extraction jobs and Knowledge Assets
- Asset retrieval by source, chunk, and type
- Resumable source-level interpretation workflow
- Source interpretation progress reporting
- Free-tier-safe batching and graceful rate-limit stopping
- Real multi-chunk book validation using *The Workshop Survival Guide*
- Prompt and schema refinement based on real extraction failures and overlap

Current interpretation workflow:

```text
Source
↓
Chunks
↓
Source Interpretation
↓
Knowledge Extraction Jobs
↓
Validated Knowledge Assets
```

### Next

- Add explicit reprocessing/versioning rules for a chunk
- Preserve chapter/section metadata during extraction and chunking where possible
- Add source-level quality/audit views
- Continue testing extraction quality across different source types

---

## Phase 3: Retrieval and Knowledge Relationships

Goal:

Make extracted assets easy to find, connect, and reuse.

### Completed

- Deterministic keyword and field-weighted Knowledge Asset search
- Retrieval by source and asset type
- Source-level knowledge overview
- Deterministic same-type similarity scoring
- Cross-chunk overlap detection
- Consolidation of overlapping raw assets into Knowledge Units
- Canonical asset selection while preserving all supporting asset IDs, chunk IDs, and evidence
- Consolidated source search
- Raw Knowledge Assets remain intact as the provenance layer

### Next

- Add library-scoped retrieval
- Add confidence and quality filters
- Improve relationship discovery beyond duplicate/overlap consolidation
- Link concepts to decision rules, examples, warnings, frameworks, and processes where useful
- Evaluate richer semantic retrieval only if deterministic retrieval proves insufficient

---

## Phase 4: Workshop

Goal:

Use knowledge, not merely browse it.

Core workflow:

```text
User situation or goal
↓
Relevant Knowledge Units
↓
Workshop preparation
↓
Grounded output generation
↓
Useful output
```

Example outputs:

- Cover letters
- LinkedIn posts
- Product strategies
- Workshop designs
- Proposals
- Lesson plans
- Business cases
- Decision briefs
- Communication plans

### Completed

- Workshop brief model
- Situation, goal, audience, constraints, and output-type inputs
- Deterministic, constraint-weighted knowledge selection
- Small deterministic terminology expansions for user language vs source language
- Consolidated Knowledge Units used as Workshop context
- One-call Gemini free-tier output generation
- Structured generated output
- Required references to the Knowledge Asset IDs that materially influenced the output
- Validation that generated references point only to supplied assets
- Separation of source-grounded knowledge from generator-created design choices and derived assumptions
- End-to-end validation using a 3-hour mixed-experience workshop-planning scenario

### Next

- Save generated outputs as first-class records
- Revise outputs while preserving the original brief, applied Knowledge Asset IDs, and provenance
- Add output history/versioning
- Generalize and test multiple output modes beyond workshop plans
- Add stronger grounding checks for numerical claims and derived recommendations where needed

---

## Phase 5: Multi-Source Synthesis

Goal:

Combine useful knowledge across multiple sources and libraries.

Examples:

- How do I validate a startup idea?
- How should I prioritize this product backlog?
- How do I communicate strategy clearly?
- What do several sources agree or disagree on?

Planned work:

- Cross-source retrieval
- Agreement and contradiction detection
- Multi-source evidence trails
- Synthesis into recommendations, playbooks, and briefs

---

## Phase 6: Productization

Planned work:

- User accounts
- Private libraries
- Production database
- Production file storage
- Background processing workers
- Source retention and deletion controls
- Reprocessing controls
- Export
- Public-safe demo data
- Usage and quota controls

Privacy and copyright direction:

- Users upload materials they are entitled to use.
- Private sources remain private to the user.
- The product should not create a shared public repository of copyrighted books.
- Users should be able to delete source files and generated knowledge.
- Public demos should use public-domain, licensed, or synthetic material.

---

## Current milestone

The first end-to-end Knowledge Engine workflow is now validated:

```text
Source
→ Extracted Text
→ Chunks
→ Knowledge Extraction Jobs
→ Knowledge Assets
→ Consolidation
→ Retrieval
→ Workshop
→ Useful Output
```

The next milestone is to make Workshop outputs durable and revisable: **save outputs, preserve their knowledge provenance, and support revision/version history before moving into broader multi-source synthesis.**

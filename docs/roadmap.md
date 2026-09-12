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
- Text extraction
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

- Test source-level interpretation on richer multi-chunk material
- Improve extraction quality across different source types
- Add explicit reprocessing/versioning rules for a chunk
- Add deduplication across chunks from the same source
- Preserve chapter/section metadata during extraction and chunking where possible
- Add source-level quality/audit views

---

## Phase 3: Retrieval and Knowledge Relationships

Goal:

Make extracted assets easy to find, connect, and reuse.

Planned work:

- Search Knowledge Assets by meaning and keywords
- Retrieve by asset type
- Retrieve by source and library
- Link related assets
- Link concepts to decision rules, examples, warnings, frameworks, and processes
- Identify repeated or supporting ideas across chunks
- Add source and asset provenance views
- Add confidence and quality filters

---

## Phase 4: Workshop

Goal:

Use knowledge, not merely browse it.

Core workflow:

```text
User situation or goal
↓
Relevant Knowledge Assets
↓
Selected / assembled knowledge
↓
Workshop
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

Planned work:

- Workshop brief model
- Knowledge selection for a goal
- Explain why each asset was selected
- Draft generation from selected assets
- Save outputs
- Revise outputs while preserving provenance

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

The current milestone is to prove **source-level knowledge interpretation on richer, multi-chunk material** before building retrieval and the Workshop on top of the assets.

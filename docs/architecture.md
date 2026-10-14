# Architecture

## Active application

Knowledge Engine is currently a **local, single-owner FastAPI application with a browser interface**. The active backend lives in `apps/api/app`, the browser client lives in `apps/web`, and persistent state is stored in SQLite plus source/chunk files under the configured storage directory.

The archived Streamlit prototype under `legacy/streamlit_prototype` is historical and is not part of the active runtime.

## Data flow

```text
Library
↓
Source
↓
Extracted text
↓
Chunks
↓
Gemini interpretation (one isolated request per chunk)
↓
Strict local Knowledge Asset validation
↓
Active / superseded Knowledge Asset history
↓
Consolidated Knowledge Units
↓
Search / retrieval / explicit selection
↓
Knowledge Workshop
↓
Saved Output
↓
Revision history / comparison / export
```

## Interaction boundary

Create uses a browser-owned `InteractionDraft` in `apps/web/interaction-draft.js`. It retains the original request, versioned interpreted values, provenance (`explicit`, `inferred`, `suggested`, `user-corrected`), resolution, clarification, confirmation snapshots and prepared-evidence identity. It does not replace Workshop, KnowledgeAsset or saved-output domain models.

One `workshopRequest` adapter maps this presentation state into existing prepare/generate/manual-save contracts. It preserves the complete original request in the stored situation, carries reviewed corrections with explicit precedence, and resolves scope against application data. Creator direction and output format are no longer reconstructed by independent fetch decorators. Unknown IDs and unresolved material scope are blocked before execution, with backend validation remaining authoritative.

Interpretation in this slice is deterministic and local. Request edits, navigation and corrections cause no provider attempts. Continue prepares knowledge without Gemini; explicit Create uses the exact server-owned prepared snapshot and the existing one-attempt generation pipeline. Revisions and request identities invalidate stale evidence and suppress late UI updates. Unsaved state is in memory within the current tab, not durable storage. Create supplies an opaque prepared-snapshot reference and InteractionDraft revision. The server binds that reference to the full preparation request, deep-copies the evidence, and rejects mismatched or missing references before provider IO; it never re-retrieves for an InteractionDraft generation. The bounded single-process cache expires after 30 minutes and is cleared on restart; expiry/eviction requires an explicit Update knowledge action. Existing API clients without an interaction revision retain their original retrieval behavior. Source preparation counts come from completed extraction jobs against actual source sections, separate from retrieval relevance. Committed local edits prepare automatically; keystrokes only invalidate evidence.

The longer-term **read → understand → interrogate → compare → apply → specify → build/test → reflect** vision grows around this validated knowledge boundary. No agents, generic chat replacement, semantic graph or learning-environment expansion is introduced in this slice.

## Knowledge model

A Source is broken into Chunks. Each chunk can produce zero or more Knowledge Assets. Every active Knowledge Asset retains provenance to its source and chunk plus evidence, keywords, confidence, and type-specific fields.

Current Knowledge Asset types are:

- concept
- problem
- principle
- insight
- decision_rule
- pattern
- example
- warning
- framework
- mental_model
- process

Overlapping raw assets may be consolidated into Knowledge Units for retrieval and synthesis, but their individual source/chunk/evidence trails remain available.

## Extraction architecture

### One chunk, one model context

The production extraction path sends **exactly one source chunk per Gemini request**. A source-level API action may orchestrate several chunks, but each selected chunk is processed independently and consumes its own provider attempt.

This isolation is intentional. Live probes showed that shared-context multi-chunk requests could under-extract knowledge and, in some cases, attach evidence from a neighboring chunk. The strict isolated path produced healthier results; a live control on chunk 007 returned five valid assets, matching its historical active count.

### Strict internal schema

The provider response is not trusted directly. Returned content is validated against the strict internal discriminated Knowledge Asset models before storage. Type-specific requirements remain enforced locally, for example:

- `decision_rule` requires `action`;
- `process` requires `steps`;
- `framework` requires `components`.

Intentional reprocessing is atomic at the chunk level: a replacement must validate before the previous active assets are superseded. A failed replacement leaves the old active assets intact.

### Provider constraints

The application is designed around the zero-cost rule:

- no paid fallback;
- no automatic semantic retries, repair calls, model fallbacks or prompt mutation;
- one additional identical provider attempt is permitted only for an explicitly transient HTTP 503 within a user-authorized operation;
- each actual provider attempt is separately allowance-gated and counted; uncertain transport outcomes are never automatically retried;
- local daily Gemini cap;
- free-tier confirmation must be explicitly enabled by the owner/admin;
- Gemini asynchronous Batch API is not part of the production path because the current Developer API free tier does not provide Batch processing.

### AI access and quota policy

KE owns the server-side provider integration; ordinary users do not supply keys or need AI Studio accounts. The current hosted shared-password beta supports one trusted external acceptance tester at a time in a shared workspace, with 20 admitted attempts per Pacific day and no per-user isolation claim. See [AI access and quota policy](ai_access_and_quota_policy.md) for invitation checks, current accounting, the known `max_chunks` API contract gap, and the settled future identity/ownership and quota hierarchy. Future multi-user architecture is not implemented or authorized by that policy checkpoint.

## Storage and process ownership

Core records persist as a SQLite snapshot; uploaded files, extracted text, and chunks live beside the database. The runtime is deliberately single-owner:

- exactly one server worker should use a storage directory;
- a filesystem lock prevents simultaneous servers;
- HTTP requests are serialized;
- direct maintenance scripts should run only while the server is stopped.

This is appropriate for the current private local beta, not for public multi-user hosting.

## Output generation

The Workshop retrieves structured knowledge based on source/library scope and the user's brief. Generation prompts receive selected or retrieved knowledge rather than entire source books. Saved outputs retain applied Knowledge Asset references and separate source-grounded material from model design choices.

Supported output modes currently include writing, decision brief, study guide, product messaging, playbook, and workshop plan. Outputs can be saved, revised, compared, reviewed, and exported.

## Validation state

The real *Workshop Survival Guide* source is complete at 46/46 interpreted chunks. After the latest deterministic repair, the source has 121 active Knowledge Assets, zero missing evidence, zero missing keywords, and a 13-item evidence-review queue retained for manual attention. The confidence distribution is 83 assets at 5 and 38 at 3.

The known crowd-recovery atomicity defect was repaired so chunk 025 contains the `Talking in circles` rule while chunk 026 retains the separate `Borrowing goodwill` process.

## Future architecture

Likely future work includes stronger semantic retrieval, richer relationship modeling, optional embeddings, better multi-source contradiction analysis, and—only if needed—authenticated multi-user/private-workspace infrastructure. Those are extensions to the current structured-knowledge architecture rather than prerequisites for the local beta.

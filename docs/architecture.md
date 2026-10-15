# Architecture

## Active application

Knowledge Engine is a **single-owner FastAPI application with a dependency-free browser interface**. The active backend lives in `apps/api/app`, the browser client lives in `apps/web`, and the archived Streamlit prototype under `legacy/streamlit_prototype` is historical only.

Two persistence modes are active:

- **Local:** transactionally replaced SQLite state plus private source/chunk artifacts under the configured storage directory.
- **Hosted private beta:** Supabase Postgres for whole-workspace state snapshots plus private Supabase Storage for source artifacts, served through the Render-hosted FastAPI application.

The hosted beta remains a shared private workspace, not a multi-user account system.

## Data flow

```text
Library
↓
Source
↓
Uploaded artifact
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
Knowledge Exploration + Create / Workshop
↓
Saved Output
↓
Revision history / comparison / export
```

## Interaction boundary

Create uses a browser-owned `InteractionDraft` in `apps/web/interaction-draft.js`. It retains the original request, versioned interpreted values, provenance (`explicit`, `inferred`, `suggested`, `user-corrected`), resolution, clarification, confirmation snapshots and prepared-evidence identity. It does not replace Workshop, KnowledgeAsset or saved-output domain models.

One `workshopRequest` adapter maps presentation state into the existing prepare/generate/manual-save contracts. It preserves the complete original request in the stored situation, carries reviewed corrections with explicit precedence, and resolves scope against application data. Creator direction and output format are not reconstructed by independent decorators. Unknown IDs and unresolved material scope are blocked before execution, with backend validation remaining authoritative.

Interpretation of the user's Create request is deterministic and local in the current slice. Request edits, navigation and corrections cause no provider attempts. Continue prepares knowledge without Gemini; explicit Create uses the server-owned prepared snapshot and the existing generation path. Revisions and request identities invalidate stale evidence and suppress late UI updates. Unsaved interaction state remains in the current tab rather than durable storage.

The longer-term **read → understand → interrogate → compare → apply → specify → build/test → reflect** vision grows around this validated knowledge boundary. It is not an authorization to replace the structured knowledge model with generic chat or to expand the MVP indiscriminately.

## Knowledge model

A Source is broken into Chunks. Each chunk can produce zero or more Knowledge Assets. Every active Knowledge Asset retains provenance to its source and chunk plus evidence, retrieval keywords, confidence and type-specific fields.

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

Overlapping raw assets may be consolidated into Knowledge Units for retrieval and synthesis, while their individual source/chunk/evidence trails remain available.

## Extraction architecture

### One chunk, one model context

The production extraction path sends **exactly one source chunk per Gemini request**. A source-level API action may orchestrate several chunks, but each selected chunk is processed independently and consumes its own provider attempt.

This isolation is intentional. Live probes showed that shared-context multi-chunk requests could under-extract knowledge and attach evidence from neighboring chunks. The strict isolated path produced healthier results, so provider-call efficiency is not allowed to weaken source isolation or provenance.

### Strict internal schema

Provider responses are not trusted directly. Returned content is adapted where necessary and validated against strict internal discriminated Knowledge Asset models before storage. Type-specific requirements remain enforced locally, for example:

- `decision_rule` requires `action`;
- `process` requires `steps`;
- `framework` requires `components`.

Intentional reprocessing is atomic at the chunk level: a replacement must validate before prior active assets are superseded. A failed replacement leaves the good active set intact.

### Provider constraints and retry boundary

The application is designed around the current zero-cost rule:

- no paid fallback;
- no automatic semantic retries, repair calls, model fallbacks or prompt mutation;
- a confirmed transient Gemini HTTP 503 may receive **one additional identical attempt**, for at most two provider attempts total;
- each actual provider attempt is separately allowance-gated and counted;
- HTTP 400, 429, validation failures, timeouts and uncertain transport outcomes are not automatically retried;
- local/hosted daily call limits remain enforced;
- free-tier confirmation must be explicitly enabled by the owner/admin;
- Gemini asynchronous Batch API is not part of the production path because it is not available on the current Developer API free tier used by the project.

The bounded 503 retry has been observed successfully in the hosted beta: a first-attempt provider 503 was followed by a successful second attempt while Render health remained 200, after which the source interpretation and summary requests completed normally.

## Material preparation lifecycle

Adding material saves and deterministically reads each selected file independently before any eligible foreground AI preparation. Preparation then runs one source at a time and one part per interpretation request. Completed knowledge is progressively saved so earlier progress survives later provider, validation or navigation failures.

Preparation is currently **foreground/tab-owned**, not a durable background worker. Leaving the preparation context, refreshing, or closing the tab stops further dispatch; saved progress remains. Explicit **Continue preparing** resumes remaining work.

See [Automatic material preparation](automatic_material_preparation.md) for the detailed lifecycle and [Performance plan](performance_plan.md) for the current latency investigation.

## Hosted state persistence and concurrency

Hosted state is persisted as a **whole-workspace snapshot** with an optimistic revision compare-and-swap. That protects against silent last-write-wins data loss, but independent requests can legitimately race—for example, preparation saving progress while the user adds another source.

A stale revision therefore enters a bounded persistence-only reconciliation path:

1. keep the original loaded snapshot as the merge baseline;
2. reload the newest persisted snapshot;
3. conservatively three-way merge only independent JSON changes;
4. retry the snapshot save;
5. after at most two rebases (three persistence-save attempts total), reload the latest state and fail safely if the mutation still cannot be saved.

This loop **does not re-enter route or service code**. It cannot repeat Gemini calls, extraction, uploads, artifact publication or allowance admission.

Record collections merge by ID. Independent field changes can coexist; identical changes are accepted; divergent writes to the same field, delete-vs-update of the same record, conflicting duplicate additions, and incompatible concurrent reorders fail closed rather than choosing a winner. Concurrent same-day allowance increments are combined so one writer cannot erase another writer's count.

Hosted production acceptance confirmed the original race: Book A continued preparing while Book B was added, both records survived, Book A retained its progress, and the stale-revision failure did not recur.

## Deletion safety

Source deletion is **state-first**:

1. dependent-output and path-safety checks run;
2. the logical source/asset/job/output deletion is persisted;
3. only after that durable state commit are source artifacts removed.

If state persistence fails or cannot be reconciled, artifacts are untouched and the latest live state is restored. If artifact cleanup fails after a successful logical deletion, the source stays deleted and the response may include `artifact_cleanup_pending: true`. An orphaned private artifact is preferable to a live source record pointing at a missing file.

The normal browser flow first requests ordinary source deletion. Destructive deletion of dependent saved output histories is only requested after the backend explicitly reports that dependency and the user confirms it.

## Local storage and process ownership

In local mode, records persist as a SQLite snapshot and artifacts live under the configured private storage root. Local runtime remains deliberately single-owner:

- exactly one server worker should use a storage directory;
- a filesystem/process lock prevents simultaneous local servers;
- local requests are serialized;
- direct maintenance scripts should run only while the server is stopped.

Hosted mode uses Supabase persistence and the conservative reconciliation rules above. Neither mode constitutes a public multi-user authorization model.

## Output generation

Knowledge answers and Create/Workshop generation receive the task plus selected/retrieved structured knowledge rather than whole source books. Saved outputs retain applied Knowledge Asset references and distinguish source-grounded material from generated design choices.

Current product behavior includes grounded questions, multi-source coverage reporting, output generation, saved work, manual or AI revisions, version comparison, quality review and export. Deterministic grounding checks remain conservative review signals, not semantic proof.

## Current validation state

The original real-source extraction acceptance remains complete for *The Workshop Survival Guide*: 46/46 chunks, 121 active Knowledge Assets, zero missing evidence, zero missing keywords, and 13 evidence-review items retained as a manual review queue rather than known defects.

Since then, the hosted beta has additionally validated material add/delete lifecycle safety, optimistic hosted-state reconciliation under real concurrent use, and successful recovery from a real Gemini first-attempt HTTP 503. The latest reliability checkpoint reported **950 backend tests passed** and **172 frontend tests passed** before deployment; the production concurrency workflow subsequently passed.

Performance is the next technical concern to characterize. The current architecture intentionally favors correctness, recoverability and provenance, and its foreground/sequential preparation path can be slow for large books.

## Future architecture

Likely future work includes measured performance improvements, stronger semantic retrieval, richer relationship modeling, optional embeddings, better contradiction analysis and—only if product evidence justifies it—authenticated multi-user/private-workspace infrastructure.

Performance changes should first address measured bottlenecks. Possible future directions include limited concurrency across independent one-chunk provider requests, durable background preparation, more granular persistence, cached/incremental summaries and lazy rendering. Paid infrastructure should follow evidence rather than substitute for application-level optimization.

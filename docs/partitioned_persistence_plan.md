# Narrow hosted interpretation persistence — proposed, not implemented

Date: 2026-10-16. Scope: the next bounded persistence slice, after beta model
acceptance. No schema, migration, or runtime persistence changes in this pass.

## Evidence and current paths

Operator-reported current production measurements: approximately 5.6 MB per full
workspace snapshot, roughly two full-state writes per completed interpreted
chunk (11.2 MB), or about 560 MB for a 50-chunk source before other traffic.
Render previously suspended the workspace after bandwidth overage;
Service-Initiated traffic overwhelmingly drove cost. These are payload estimates,
not a guarantee of billed transfer, and were not remeasured in this pass.

`db/persistence.py:save_state` serializes libraries, sources, extraction_jobs,
knowledge_assets, outputs and legacy usage into one schema-version-2 snapshot.
`persistence/postgres.py` replaces JSONB under a workspace revision CAS.
`db/persistence.py` permits at most two three-way reconciliation attempts after
stale writes, refreshes live collections on conflict, and never repeats provider
work. `db/mock_data.py` loads process-wide collections at startup.

`source_interpretation.interpret_source` selects pending jobs in memory. For each
part, `run_gemini_knowledge_extraction` checkpoints running state before the
provider call; completion/failure is persisted at the next running checkpoint or
at finalization. Thus current batching can durably finalize the previous part and
start the next in the same snapshot. Preserve explicit resume and stale-recovery rules; the proposed immediate
completion commit below is a deliberate durability improvement over deferred
checkpoints, requiring crash acceptance tests.

State that changes during interpretation:

- Jobs: newly selected pending jobs; status, started_at, provider, model, error;
  completion asset_count, completed_at, model_response_id, extraction_version.
- Assets: new validated assets with generated IDs, timestamps, source/chunk/job
  provenance and extraction_version; prior active assets for the same chunk
  become inactive with superseded_by_job_id only after full batch validation.
- Source: processing_status and stopped_reason, including final run outcome.
- Allowance: each actual attempt is independently reserved in the existing
  authoritative hosted allowance ledger. Legacy snapshot usage is not the hosted
  admission authority; no per-part snapshot mirroring is needed.
- Libraries and saved Workshop outputs do not change merely because a part runs,
  but are retransmitted along with every other source, job and asset.

## Proposed ownership boundary

Keep the existing Postgres snapshot adapter and CAS for libraries, stable source
metadata/artifact locators/chunk manifest, and saved output histories. Keep local
SQLite mode unchanged initially. Avoid a general ORM or full entity rewrite.

Add narrow server-only records in the existing private knowledge_engine schema:

| Record | Contents and concurrency boundary |
| --- | --- |
| Source interpretation state | workspace/source identity, source generation, processing_status, stopped_reason, revision, active/deleted lifecycle fence |
| Extraction job | existing job JSON, workspace/source/chunk identity, revision, source generation; unique job ID and guarded running transition |
| Knowledge asset | existing asset JSON and stable ID, source/chunk/job identity, active/supersession fields and revision |

Use workspace-scoped composite keys and indexed source/chunk/job lookups. Preserve
all historical assets, IDs, extraction versions, ordering and provenance. Keep
allowance_state authoritative and separate. Source existence/generation is the
small fence needed to coordinate with snapshot lifecycle operations, not a
second editable source catalog. Tables must not acquire public Data API access;
retain backend-only privileges (review RLS if exposed schema settings differ).

Asset records must move with job completion: moving progress alone would still
resend the growing asset corpus on completion. Manual asset revisions and recovery
must use the same narrow ownership boundary. Output histories remain snapshots
of evidence so historical Workshop provenance does not change.

## Single authoritative ownership after migration

| State/domain | Current authority | Proposed authority | Write frequency | Read path | Concurrency/version | In core snapshot? | Rollback source |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Sources/source metadata | Workspace snapshot | Core snapshot excluding interpretation fields | Create/edit/process/lifecycle | Core records composed with narrow interpretation fields | Core revision CAS; lifecycle transaction | Yes | Current core snapshot |
| Extraction jobs | Workspace snapshot | Narrow job records | Claim/complete/fail/recover | Scoped job queries/composed API | Job revision, claim token, generation | No | Narrow jobs |
| Per-chunk interpretation progress | Snapshot job statuses | Job records; derived progress, no second writable counter | Job transitions | Derive from authoritative jobs | Job revision/claim | No | Narrow jobs |
| Source interpretation status/reason | Snapshot source fields | Narrow source interpretation record | Claim/finalization/interruption | Composed source response | Source revision/short row lock | No | Narrow source record |
| Active knowledge assets | Workspace snapshot | Narrow asset records | Valid completion/manual revision | Scoped retrieval/request view | Asset revision; chunk replacement transaction | No | Narrow assets |
| Superseded/replacement assets | Snapshot asset fields | Same narrow asset records, including active/supersession fields | Successful replacement | Same asset queries | Atomic replacement with completion | No | Narrow assets/jobs |
| Chunk/artifact metadata | Snapshot locators/manifests; Storage bytes | Same division | Upload/extract/chunk/backfill | Core metadata/request-scoped artifact access | Core CAS; lifecycle generation | Yes, metadata only | Core plus artifacts |
| Outputs/revisions | Workspace snapshot with historical evidence | Core snapshot | Every saved output/revision/history deletion | Core records | Core CAS/conservative conflicts | Yes | Current core snapshot |
| Libraries | Workspace snapshot | Core snapshot | Create/edit/delete | Core records | Core CAS | Yes | Current core snapshot |
| Usage/allowance | Hosted allowance ledger; legacy snapshot copy is non-authoritative | Existing ledger | Actual provider attempt/pause/resume | Ledger operations | Atomic reservation/unique reservation ID | No live counter; any retained legacy copy is non-authoritative | Current ledger |
| Deletion/rechunk fencing | No dedicated generation fence today | Narrow source lifecycle record | Create/delete/rechunk | Claim/completion/lifecycle checks | Source lock/generation/deleted marker | No | Narrow lifecycle records; drain in-flight work for rollback |

Job state alone determines per-chunk progress. Source interpretation fields are
presentation/run outcomes, not a competing completed-chunk counter. The narrow
source record owns generation and interpretation fields; the core owns descriptive
metadata/manifests/locators. Do not duplicate generation as independently writable
core state. Job generation is an immutable reference to its claimed generation.
Assets own both active and superseded state. Historical evidence inside outputs
is immutable historical context, not authority for current active assets.
Process-wide collections are caches/API projections only. Strip partition-owned
fields from core saves; never dual-write or merge competing live copies. The
allowance ledger remains authoritative regardless of any frozen legacy copy.

## Transaction-boundary rule

Inspection of `persistence/factory.py` and `persistence/postgres.py` confirms the
core snapshot is a Postgres row. The proposed narrow records use that same
transactional database/schema. No impossible cross-store atomicity is required:
lifecycle operations must use one shared connection/transaction, rather than
calling adapters that independently commit. Artifacts remain a separate store.

Whenever core and narrow records share a transactional datastore, their lifecycle
mutation MUST occur in one database transaction, including core revision CAS,
fence/generation updates and affected record changes. This applies to deletion,
rechunk publication, migration activation and rollback authority changes.

If participants do not share a transaction boundary, do not assume cross-store
atomicity. Use generation fencing and explicit durable staged ordering: first
fence/block new claims and invalidate the old generation; prepare new artifacts
under distinct locators (or record deletion intent); publish core changes with
CAS; then activate the new generation only after verifying publication, or finish
logical deletion; clean obsolete artifacts last. Persist operation identity,
stage and pending cleanup so interruption recovery can resume/verify each step.
During an incomplete stage, reads/mutations must fail closed rather than expose
mismatched manifests/assets. Never restore an old generation after its artifacts
may have been removed. This is a safety rule, not a proposal to split Postgres
state across stores. No transaction is held across artifact I/O or provider calls.

## Write and read integration

1. Introduce a hosted interpretation repository beside StateStore with explicit
   claim/checkpoint/complete/fail/recover/read operations. Persist explicit changed
   records, not a diff reconstructed from stale process-wide lists. Stable IDs
   and operation tokens make persistence acknowledgements verifiable after an
   uncertain commit; they must never trigger an automatic provider retry.
2. Claim running state atomically, locking the source fence and checking the job
   revision/status and current source generation. Persist selected pending jobs
   at the same boundary as today. Do not hold a database transaction across AI
   calls or artifact I/O. A durable running job still requires existing explicit
   stale recovery after restart; do not automatically spend allowance again.
3. Commit a validated completion in one short transaction: verify fence/job
   claim, insert the complete asset batch, supersede prior active chunk assets,
   complete the job and update interpretation state. Validation or persistence
   failure leaves prior assets active. Guard against two replacements of the
   same chunk with a chunk-scoped lock and expected active extraction version.
   Moving completion to an immediate narrow commit is a deliberate durability
   improvement; add crash tests before changing current deferred checkpoints.
4. Failures only write the affected job/progress records; do not invalidate old
   assets. Finalization updates source progress without a full snapshot save.
   Keep at most two bounded persistence reconciliations; overlapping changes
   fail closed and reload relevant records. Reconciliation never invokes AI.
5. On startup, hydrate the existing list/dict API view from the core snapshot plus
   partition records in one consistent database read. Refresh authoritative
   job/source/chunk scope before claims, resume and mutations; global in-memory
   collections cannot serve as concurrency authority. For list/search/Workshop/
   audit/backup, read a consistent partition view once per request, not per asset.
   Avoid a new full-workspace load on every interpreted part. Preserve public
   response shapes by composing source progress into source DTOs.
6. Update direct extraction results, manual revisions, recovery, source summary,
   Library summary, retrieval, Workshop evidence selection, integrity/audit,
   backup/export/restore and all generic persist_state callers. Core saves must
   strip partition-owned collections/fields and never overwrite newer narrow
   state. Inventory all writers before cutover; mixed ownership is unsafe.
7. Source deletion (`routers/control.py`) currently persists logical deletion
   before removing artifacts, retains output-history consent, and reports
   cleanup_pending. Preserve that order. In one DB transaction CAS the core
   snapshot removal, advance/mark the source fence deleted, remove its narrow
   jobs/assets/progress, and delete affected output histories when authorized.
   Fence retained long enough to reject in-flight completions; never resurrect
   deleted data. Clean artifacts only after commit, preserving pending cleanup.
   Source rechunk/replacement must advance the generation under that same fence.

## Completion order and race protection

Validate the entire response first. In one short database transaction, lock the
source lifecycle row, then chunk coordination, then affected jobs/assets in fixed
order. Check live source, generation, running job, claim token/revision and expected
active extraction version. Insert the full validated asset batch with stable
operation/asset IDs and provenance; supersede the old active chunk assets; complete
the job; update source interpretation status/reason where appropriate. Commit all
changes together, then refresh affected cache entries. Any failed check or write
rolls back the entire batch and preserves prior active assets. Resolve uncertain
acknowledgements by operation ID, never by rerunning the provider.

- Delete during interpretation: take the same source lock, CAS-remove core data,
  mark the fence deleted and remove narrow data/output histories as authorized in
  one shared transaction. Retain the deleted fence. Only then remove artifacts.
  Completion after deletion fails; completion before deletion is included in it.
- Rechunk during interpretation: prepare new artifacts at distinct locators first;
  atomically publish core manifest/locators and advance the source generation
  under the same lock. Reject old-generation completions; clean old artifacts
  after publication. Apply the staged rule above across the artifact boundary.
- Same chunk: use a chunk-scoped transaction lock plus database uniqueness for a
  live claim, guarded status transition and claim token. Only the successful
  claimant may dispatch; stale recovery is explicit. No semantic retry/fallback.
- Independent chunks: distinct claims/asset batches; source-row transactions
  serialize briefly for lifecycle/progress coordination. Provider calls run
  without those locks. Never hold a workspace lock across interpretation.

## Migration, concurrency and rollback

Use a versioned per-workspace partition marker with preparing/active states in
the core snapshot. With writers paused/drained, backfill jobs/assets/progress with exact IDs/defaults and validate
counts, ordering, provenance and active replacement sets against the source
snapshot, including exact record equivalence, not counts alone. Invalid records
stop migration; do not drop them. Create source fences for every source. Migration must be idempotent and restartable, and flip authority
only after verification in the same transaction as the CAS-protected compact
snapshot. Preserve a private pre-migration backup; do not leave duplicate active
copies that readers merge or writers can accidentally reimport.

Backfill staging records against a fixed source snapshot revision with durable
batch checkpoints and original IDs. On interruption, recheck the source revision
and resume verified missing batches idempotently; revision drift blocks activation.
Until activation, staged records are not live authority. Atomically activate the
version and compact the core only after full composed-state verification.

Start behind an explicit hosted feature/version gate. Unmigrated workspaces use
the original path; migrated workspaces require compatible code and fail closed
if support is absent. Deploy compatible readers before migration; do not run old
and new writers concurrently. Deployment controls must prevent an old binary
without version checks from accessing migrated state. No per-chunk dual full-
snapshot writes, which would defeat the goal. Backups export the composed legacy-compatible state plus the
current authoritative allowance and restore into a new empty workspace.

Primary races: concurrent claim of one chunk; two replacements; source deletion
or rechunk during provider work; manual revision during completion; core CAS
reconciliation overlooking partition updates; cross-worker stale cached reads;
uncertain commit acknowledgements. Use fixed lock order (workspace migration/core
when needed, source fence, chunk, jobs/assets), row revision checks and operation
IDs. No long workspace lock for normal part writes. Preserve conservative
conflict behavior rather than last-writer-wins or unbounded merges. Verify
source-to-library membership and evidence/output relationships during lifecycle
transactions.

Rollback requires maintenance mode, drained requests and a consistent composed
read, then one CAS-protected rehydration into the legacy schema-version-2
snapshot with exact jobs/assets/progress. Copy current allowance via the existing
controlled ledger rollback mechanism; never restore an old counter or reset the
ledger. Verify composed export equivalence before changing authority and starting
old code. Keep narrow tables for diagnosis until rollback acceptance; they are
not read as an alternate authority. A flag flip alone after partition writes is
not a safe rollback. Do not restore the initial backup over newer user work.

## Remaining core writes and request budget

### Phase 2 SQL-budget decision

The disposable fixture measured interpretation at 9 transactions / 57
client-issued SQL statements and source summary at 4 transactions / 7
statements. No per-asset SQL loop or correctness issue was found; cosmetic
statement-count reduction is deferred. These fixture counts do not establish
production wire or billing equivalence. Phase 3 settlement must keep statement
count O(1) in N assets through batched/set-based writes, batch multi-source
Workshop and evidence-base reads, and avoid repeated full-corpus Explore
retrieval.

Full core snapshots remain for library mutations; source creation/identity edits;
upload, extraction, structure and chunk-manifest publication/backfill; saved
Workshop/manual/imported outputs; output revisions/history deletion; source/library
deletion; migration activation and controlled rollback. Interpretation, job
recovery and manual asset mutations use narrow records. Read-only export does not
write state. Output revisions still embed historical evidence and save the whole
remaining core; they and other core routes can still cause multi-megabyte writes.
Measure this residual cost before proposing any output partition.

Steady-state target per successful chunk: one narrow claim transaction (including
scoped checks) and one narrow completion transaction (batch assets/progress), plus
the existing two allowance transactions per provider attempt (migration/read
check and reservation). At most one extra progress finalization transaction per
run; prefer folding it into final completion. Fifty successful chunks without
provider retries therefore require approximately 100 interpretation transactions
plus 100 existing allowance transactions, with bounded request-level reads and
finalization. A confirmed 503 retry adds the existing allowance operations for its
second attempt. Conflicts and uncertain acknowledgements are counted separately.

These are transaction budgets, not SQL statement/round-trip counts. Record actual
transactions, statements, connections and wire round trips separately. Batch
asset inserts/updates; never issue one remote request per asset. Do not reload
the full corpus per chunk or perform routine reconciliation. No ledger redesign
is included in this slice. A backend read of a consistent request view must not
become an unconditional full-corpus reload for every downstream request: scope
queries to the request and retain only safely versioned reusable caches.

## Expected savings and acceptance tests

Current baseline: 2 × 5.6 MB × 50 = 560 MB. Proposed per-part transfer is job/progress
metadata plus that part's new assets and small supersession updates, independent
of unrelated workspace size. With two narrow checkpoints averaging 25 KB each,
50 parts would write about 2.5 MB (~99.6% less than 560 MB); at 100 KB each,
about 10 MB (~98.2% less). These are illustrative budgets, not measured promises.
Measure actual UTF-8 outbound bytes, result sizes, statement counts and database
reads separately, including end-of-run and conflicts. Core writes, artifacts,
provider payloads, reads, TLS overhead and database replication remain outside
this comparison. No scheduled full snapshot flush after every part/run.

Required focused tests before implementation acceptance:

- Adapter CAS, atomic claim, two-worker same/different chunk updates, bounded
  conflict reconciliation, commit-ack uncertainty/idempotency and lock order.
- Full-batch invalid result, empty valid replacement, failed transaction and
  supersession preserve correct prior active assets and provenance.
- Crash before/after claim, allowance reservation, provider result, completion
  commit and finalization; resumed work skips completed parts and requires
  explicit stale recovery, without a duplicate model call or allowance refund.
- Delete/rechunk vs in-flight completion, library deletion, output-history consent,
  logical commit failure before artifact removal and cleanup_pending afterward.
- Migration interruptions/idempotency, malformed legacy rows, concurrent writer
  rejection, composed read equivalence, backups/restores, downgrade rejection,
  rollback after new writes and authoritative allowance preservation.
- Request-level refresh across workers, manual revision/search/Workshop evidence
  consistency, and no stale cached state overwriting partition records.
- Instrumented hosted fake with a 5.6 MB corpus and 50 parts: zero monolithic
  writes from interpretation, payload scales with changed part data, bounded
  reads (no per-part corpus reload), conflict/failure byte counts included.

Run existing interpretation-checkpoint, independent-source, hosted-publication,
reconciliation, Postgres, allowance, beta/control deletion, artifact, provenance,
manual revision, retrieval, Workshop and performance timing regressions, then the
full backend suite. Use offline fakes first, then explicit disposable database
integration tests; no real provider calls are needed. Hosted rollout/measurement
requires separate approval and is not part of this pass.

## Post-implementation production acceptance

Use a representative existing corpus and an explicitly approved bounded canary;
this document does not authorize production writes or provider calls. Run race
and fault-injection scenarios with synthetic providers and a disposable database
before hosted acceptance. Record comparable baseline and migrated observations.

| Measurement | Required evidence |
| --- | --- |
| State bytes per interpreted chunk | Total/median/p95/max outbound UTF-8 state payload, including failures and reconciliation; zero monolithic interpretation writes |
| Hosted persistence requests per chunk | Transactions, queries/statements, connections and wire round trips separately; bounded claim/completion budget, no per-asset growth |
| Artifact traffic | GET/HEAD/list/write counts and bytes; no new artifact I/O per checkpoint; separate from state/provider traffic |
| End-to-end chunk duration | Median/p95 total and persistence duration; separate provider latency and compare equivalent workloads |
| Reconciliation frequency | Conflict rate, attempts, bytes and outcomes; at most two bounded reconciliations; no duplicated provider work |
| Interruption/resume | Faults before/after claim, reservation and completion commit; completed chunks remain completed, stale recovery explicit, allowance never decreases |
| Delete/rechunk races | Both transaction orders; no resurrection, stale-generation assets, dangling live provenance or premature artifact removal |
| Compacted core size | Record `compacted_core_snapshot_utf8_bytes` immediately after migration and alongside representative workload measurements |
| Saved output revision | Record total state bytes written by one representative saved output revision, revision payload size, write count and resulting core size, including reconciliation if any |

The compacted-core and output-revision observations determine whether output
persistence is a later evidenced hotspot. They do not justify immediate output
partitioning. Distinguish logical UTF-8 payload bytes from billed transfer and
protocol overhead.

### Downstream knowledge-read parity and performance

For every path below, compare the legacy and partitioned implementations against
the same fixture state, source selection and query. Require equivalent user-visible
results, provenance, ordering and historical/current evidence semantics. Record
hosted request/query count, bytes transferred where measurable, and median/p95
latency over repeated runs where meaningful (separate cold/warm cache results).
There must be no per-asset remote-call pattern or full-corpus reload. Use scoped
bulk reads and safely versioned caches; do not hide unbounded reads inside the
composed compatibility view.

| Representative path | Functional parity evidence |
| --- | --- |
| Knowledge-unit consolidation | Same groups, canonical choices, active filtering and provenance |
| Explore / grounded-answer retrieval | Same eligible units, ranking/context and grounded references; same no-evidence behavior |
| Workshop evidence selection and generation | Same selected evidence and request contract; valid references/acceptance behavior using deterministic provider fixtures |
| Source/asset browsing | Same source summaries, status, asset counts, visible records and pagination/order where supported |
| Multi-source retrieval | Same source scope, cross-source grouping/coverage and references; queries do not scale per asset |
| Saved-output evidence resolution | Historical evidence remains reproducible after replacement; current assets do not silently replace saved evidence; deletion consent behavior preserved |

For generation, deterministic synthetic-provider fixtures establish parity; real
provider text need not be identical. Any later authorized production Workshop
canary checks valid evidence references and successful generation, not byte-equal
model output. Report the persistence/read metrics separately from provider time.

Bandwidth arithmetic uses decimal MB/KB. The operator-reported baseline is
5.6 MB × 2 writes × 50 chunks = 560 MB. Assumed narrow checkpoint averages of
25 KB or 100 KB give 2 × 25 KB × 50 = 2.5 MB or 2 × 100 KB × 50 = 10 MB.
Savings are 1 − 2.5/560 = 99.55% (~99.6%) and 1 − 10/560 = 98.21% (~98.2%).
Checkpoint sizes are illustrative assumptions, not measured production results;
allowance traffic, core writes, reads, artifacts, provider traffic and protocol
costs are excluded. Report actual observed savings after implementation.

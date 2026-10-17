# Phase 2: jobs and source lifecycle authority

## Settled semantics (recorded before implementation)

Operation receipts and source lifecycle tombstones are retained indefinitely for
beta. There is no automatic cleanup in MVP. Future receipt cleanup requires
material volume/cost evidence and must preserve idempotency; deleted source IDs
and generations must never be reused to make stale work valid again.

Each checkpoint belongs to one workspace, partition version, migration attempt
and pinned core snapshot revision. Preparing may resume only at that exact
revision. Drift invalidates continuation; no silent repinning. Verified means
exact equivalence checks succeeded, not activation. Only an explicit guarded
cutover changes authority. Shadow/backfill data is never authoritative before
cutover. Afterwards jobs/lifecycle are narrow-owned with no writable core copies.

## Inventory before edits

- `db/persistence.py`: all snapshots, reconciliation and live restoration;
  `db/mock_data.py`: startup jobs/source state and process-wide projections.
- `services/knowledge_extraction.py`: create/find/claim/fail/complete/recover,
  checkpoint rollback/capture, audit; every mutator currently calls persist_state.
- `services/gemini_knowledge_extraction.py`: running checkpoint/source status;
  `source_interpretation.py`: job selection, completion-derived progress,
  pending/running decisions, final status/stopped reason.
- `services/source_summary.py`: history/replacement eligibility, latest jobs,
  progress, stale recovery and stopped state.
- `routers/knowledge.py`: job/status/results/recovery and interpretation APIs.
- `routers/sources.py`: separate source lookup, detail/status, processing, upload,
  extraction failures/success, chunk publication; all processing_status writes.
- `routers/control.py`: integrity, backup/export, logical deletion before artifact
  cleanup; `structure.py`, `libraries.py`, `services/outputs.py`, and output routes
  also call the shared snapshot writer and must not reintroduce narrow-owned data.
- `ai_gateway.py`: hosted allowance stays in its existing ledger. Local legacy
  usage snapshot paths and explicit allowance copy-back stay separate.

## Transaction boundary and authority

Core snapshots and narrow records use the same PostgreSQL database. Cross-domain
changes use one connection/transaction, fixed order: core row when needed, source
fence(s) in source-ID order, job row(s). No transaction or workspace request lock
is held during provider execution. Assets/outputs/libraries/manifests remain core
owned. Phase 2 is not the major asset-bandwidth optimization.

The version-2 active marker owns exactly `jobs` and `source_lifecycle`. Version 1
primitives remain supported but do not authorize a Phase 2 cutover. Full processing
status and stopped reason are composed from lifecycle records; descriptive source
metadata remains in core. Progress is derived from current-generation jobs.

An incompatible legacy writer is excluded by a database guard once active: a
stale client cannot remove the marker or reintroduce jobs/owned source fields.
Preparing/verification require pinned revision and no in-flight current-generation
running legacy jobs at cutover. Maintenance/drained writers remain mandatory operationally.
No runtime or production flag automatically invokes migration or cutover.

## Implemented boundaries

`Phase2Coordinator` extends the existing Postgres partition adapter and uses the
same workspace/database as the core StateStore. Administrative methods are
`prepare`, `backfill`, `verify`, `cutover` and `rollback`. None is invoked by
startup, the factory getter, a public route, or a configuration/environment flag.
The additive `create_knowledge_engine_phase2.sql` must be applied explicitly after
the state and Phase 1 schema; it is applied only in disposable tests in this pass.

The SQL adds API-projection JSON and stable ordering columns, indexes and guards.
Job/source API JSON is regenerated from authoritative columns by triggers; it is
not independently writable status/generation state. Original optional fields and
historical timestamp spelling are preserved for exact API/backfill comparison.
Claim tokens remain in the internal envelope, not the public job DTO.

The core marker is exactly:

```json
{"partition":{"version":2,"state":"active","domains":["jobs","source_lifecycle"]}}
```

There is no second active flag in the migration table. Its preparing/verified
state records staging progress only; verified plus the core active marker means
cutover has occurred. The single authority switch is the core marker transaction. Authenticated ingress
polls only that small marker (health is excluded). A compatible existing worker
reloads once when authority changes, so no manual worker reload is needed to
start narrow reads. Unchanged markers do not cause full-workspace reloads.

Preparation pins the existing core revision without editing that snapshot.
Backfill checkpoints complete source batches, with source-scoped job records and
original global ordinals. A batch and its checkpoint commit together; retry at
that same revision resumes missing sources. Verification compares exact API data
and relational IDs, source/chunk linkage, generation, extraction version, status,
provider/result metadata, timestamps and ordering. A source snapshot revision
change refuses continuation, including at verified cutover. A different attempt
cannot silently replace an existing attempt. Reset/restart of invalidated staging
requires a separately reviewed explicit administrative procedure; none is automatic.

Cutover requires a verified supported migration, matching expected core revision,
an explicit drained-writers assertion and no current-generation running legacy jobs. It rechecks
exact equivalence while holding core/source locks, writes the marker and removes
only jobs/owned source fields from the core. It does not move, shrink or delete
assets, output history, libraries or source descriptions/manifests. A database
guard rejects old writers removing the marker or reintroducing owned fields.
Requests also pin their starting authority: reconciliation cannot silently cross
cutover/rollback, and legacy preparation cannot dispatch a provider without an
active claim if authority changes underneath it.

Before cutover, routes/services remain legacy. Afterwards:

- Jobs use scoped narrow reads and guarded create/claim/finish/recover operations.
  Current-generation jobs alone drive progress; history remains available for
  audits, evidence provenance and backup. A same-chunk live slot is unique.
- Source metadata comes from core; processing_status, stopped/interruption fields
  and lifecycle generation/fence come from narrow rows. Core writes strip those
  fields and all authoritative extraction_jobs. There is no writable progress
  count, authoritative process-wide job list, or separate active-assets copy.
- The compatibility collections use request-local ContextVar projections in active
  mode. Read scopes do not reload/copy the asset corpus; assets/outputs are lazy
  copies of an immutable cache if the route actually needs them. Scoped source
  summaries query asset counts, not asset payloads. Health stays pure liveness.
- The legacy HTTP workspace lock remains for legacy mode. Active mode uses isolated
  projections and no workspace lock around a provider call; independent HTTP chunk
  requests can enter the synthetic provider concurrently.

## Completion, reconciliation and lifecycle

A claim/status/failure/finalization changes narrow records only. Completion is
still the Phase 2 exception: core assets remain authoritative. After validation,
completion locks core, then source, then job; checks captured source/chunk/version,
generation, revision and token; supersedes/inserts legacy asset records in core;
finishes the narrow job; and commits together. No asset rows are inserted into the
narrow asset table. Empty valid replacements are still successful replacements.
The adapter/cache revision advances only after commit and never regresses if an
independent later commit has already been published.

Operation receipts bind the whole command. Replayed claims cannot dispatch. An
uncertain completion acknowledgement is confirmed by its receipt without repeating
provider work. Definite stale-core persistence gets at most two reconciliation
attempts; uncertain missing receipts fail closed. Core-only facade reconciliation
also remains bounded and merges core fields separately from owned source fields.
Concurrent incompatible edits fail rather than choosing a winner. Superseded
historical extraction versions and stale generations cannot recover into live work.

Deletion commits core source/asset/output-history removal, generation/deleted fence
and narrow job deletion in one transaction, preserving output-history consent.
Tombstones and operation receipts remain indefinitely. Artifacts are removed only
after commit; failed/uncertain logical commits retain artifacts. Rechunk publication
advances the generation with its core manifest/locator change. Old-generation
completion fails; completed-first work is seen by the later lifecycle operation.
Existing public chunk requests still preserve existing chunks; no force-rechunk
endpoint is added. Disposable tests exercise internal publication in both orders.
Historical reads cannot substitute current-generation text into an old job prompt.

## Rollback compatibility

Rollback is explicit, drained and CAS-guarded. It rehydrates all live-source job
history (including old generations) and owned source fields from narrow records,
then removes the active marker in one transaction. Current-generation running jobs
block rollback. Narrow tombstones and receipts remain retained; the dedicated
allowance ledger stays authoritative and is never reset or rolled back.

Generation/extraction-version fences are included in rehydrated legacy data when
needed. This implementation's legacy mode respects them in selection, recovery
and mutation. After generation changes, rollback requires this generation-aware
code; arbitrary older binaries ignoring these fields are not claimed safe.
There is no automatic code downgrade or flag-only rollback. Re-cutover after a
rollback uses the explicit `restart_after_rollback` operation below; it does not
reuse the old pinned checkpoint. These are rollout compatibility constraints,
not a different transactional datastore or a change to asset ownership.

## Acceptance coverage and remaining Phase 3 work

### Historical-generation backfill correction

Job generation is immutable provenance. Source generation is the live-transition
fence. Backfill preserves each job's explicit generation; a legacy job without a
generation uses the original generation 1, consistently with legacy eligibility
checks. It never substitutes the source's current generation. A future-generation
job is rejected and the entire backfill batch/checkpoint transaction rolls back.
Exact verification compares against that same original job generation.

The PostgreSQL `guard_partition_record` exception now applies only to job INSERTs
within a workspace-scoped, version-2 preparing migration pinned to the current
core revision with legacy authority. Such an INSERT may preserve a generation
less than or equal to the live source generation. Missing/deleted sources and
future generations remain rejected. Every UPDATE, ordinary runtime INSERT and
asset mutation retains the current-generation fence. The preparing exception no
longer bypasses job UPDATE transition guards. Generation immutability, revisions,
claim tokens and unique live-claim slots remain enforced; no historical flag or
second authority is introduced. Backfill and ordinary creation remain separate
store paths.

Cutover's running-job check now considers current-generation jobs only. An old
generation's historical `running` status cannot execute and does not represent
an in-flight current writer. The explicit drained-writer requirement still
applies. Current-generation running work continues to block cutover.

`restart_after_rollback` creates a logically new administrative attempt at the
new legacy snapshot revision. It requires the expected newer revision and drained
writers, then checks exact source/job equivalence before reusing the retained
narrow rows. The previous verified attempt is copied to an immutable
`partition_migration_attempt_history` row, including its pinned revision,
checkpoint, verification time and cutover revision. The current migration row
then names the new attempt, with a fresh pin and empty checkpoint. Its old pin is
never changed within that attempt. Attempt IDs cannot be reused. Backfill accepts
existing rows only when provenance and API payload exactly match the new pinned
snapshot; mismatches fail closed. Tombstones, jobs and receipts remain intact.
Revision drift during the new preparing attempt blocks continuation. The separate
explicit `restart_after_revision_drift` operation archives the invalidated attempt
and starts a fresh attempt; it does not erase its provenance or change authority.
The core authority marker remains absent until the new explicit cutover.

The original PostgreSQL regression failed before code changes at `verify` with
`Job relational equivalence failed.` It uses actual rollback output: source
generation 2 and a completed generation-1 job. It now passes same-workspace
restart under a new attempt ID, backfill, checkpoint replay, exact verification,
explicit cutover, historical reads, current progress exclusion and a second
rollback preserving generation 1. Assertions confirm that the old attempt keeps
its original pin and cutover revision in immutable history, while the new
attempt receives a new pin and empty checkpoint. Original operation receipts are
unchanged.

The correction's final validation passed: the 15 new PostgreSQL regression cases,
all 88 combined Phase 1/Phase 2 disposable PostgreSQL tests, 226 focused offline
tests (including Phase 1 primitives and affected extraction/source/grounding
regressions), and all 1,074 offline backend tests. The offline suite emitted two
existing Starlette test-client deprecation warnings. No provider requests were
made.

The schema correction changes the explicit Phase 2 schema definition only. It is
tested on disposable PostgreSQL. No automatic migration or activation is added.
An already initialized database would need an explicitly reviewed replacement of
the trigger function; rerunning the entire non-idempotent CREATE/ALTER script is
not an upgrade procedure.

### Generation-assumption audit

| Path | Classification | Required behavior / review result |
| --- | --- | --- |
| `Phase2Coordinator.backfill`, `_equivalent` | HISTORICAL/PROVENANCE PATH | Preserve original job generation, default absent legacy values to 1, reject future generations; corrected here. |
| `compose(history=True)`, `history_jobs`, `rollback` | HISTORICAL/PROVENANCE PATH | Read all retained generations for live sources; rollback copies relational job generations into legacy records. Source current generation is copied independently. |
| `PartitionTransaction.read_job`, `query_jobs` | HISTORICAL/PROVENANCE PATH | Identity reads preserve the row; generation-filtered queries use the caller's requested generation, allowing history inspection without mutation. |
| `partition_authority.find_job`, history reads, control integrity/backup | HISTORICAL/PROVENANCE PATH | Preserve existing job data; do not infer provenance from the current source generation. |
| `Phase2Coordinator.create_job`; `PartitionTransaction.create_job` | LIVE ELIGIBILITY CHECK | Only create jobs at the current live source generation; runtime behavior unchanged. |
| `_fence`, `_job_fence`, `_running`, claim/finish/recover | LIVE ELIGIBILITY CHECK | Exact source/job generation equality plus existing revision/token/status checks; unchanged. |
| `compose(history=False)`, `scoped`, `partition_authority.jobs/jobs_many` | LIVE ELIGIBILITY CHECK | Current-generation jobs drive selection and progress. Explicit history reads bypass only the read filter. |
| `source_fields`, completion progress count, recovery job selection | LIVE ELIGIBILITY CHECK | Count/select jobs in the current fenced generation, never historical completions. |
| Cutover/rollback running-job guards | LIVE ELIGIBILITY CHECK | Only current-generation running jobs block authority change; cutover corrected to match rollback. |
| `save_core`, source-field updates, request generation captures | LIVE ELIGIBILITY CHECK | Preserve current source fence; advance it on delete/rechunk and reject stale requests. These are source fields, not historical job reconstruction. |
| Legacy `jobs`, `legacy_generation_guard`, `legacy_mutation_guard`, `guard_chunk_read` | LIVE ELIGIBILITY CHECK | Equality correctly prevents old jobs from dispatching or reading new-generation chunk text; explicit history remains readable. The audit also found and fixed a missing `legacy_mutation_guard` call in `mark_extraction_job_failed`, so direct failure transitions now enforce the same fence. |
| SQL record guard | Both, separate branches | Historical INSERT exception only during pinned preparation; runtime creation and all transitions retain equality and immutable job generation. |
| Phase 1 asset insert/supersede and active asset queries | LIVE ELIGIBILITY CHECK | Existing current-generation fencing is unchanged; Phase 2 assets remain core-authoritative. |

The generation audit found that the legacy branch of
`knowledge_extraction.mark_extraction_job_failed` omitted the generation guard
used by claim, completion and recovery. A direct helper call could therefore
change a historical generation-1 job while its source was at generation 2. The
helper now calls `legacy_mutation_guard` before changing status; a focused
regression verifies this live-transition fence. Narrow-store failure
transitions remain fenced as before.

The tests cover legacy and shadow authority, pinned migration/resume/drift,
exact verification/tampering, verified versus active, activation guards, API
parity, narrow-only status writes, atomic completion rollback, explicit recovery,
duplicate/stale claims and generations, independent HTTP requests, delete/rechunk
orders, artifact cleanup ordering, bounded persistence-only reconciliation,
receipt replay/uncertain acknowledgement, retained tombstones, rollback history,
source/job projection synchronization and assets remaining in core.

No broad architecture/datastore deviation is introduced. The request-local
compatibility layer is necessary to remove active-mode provider serialization
without promoting process-wide lists to persistence authority. The staged version
owns only Phase 2 domains, deliberately leaving the major asset cutover for Phase 3.

Before Phase 3/any hosted rollout, review the explicit invalidated-attempt restart
procedure, operational drained-writer controls and compatible rollback deployment.
Then move assets atomically with job completion, verify downstream evidence parity,
and remeasure the remaining query/transaction overhead. Batching requests can
reduce small-call overhead; the counts below must not be described as two wire
requests per chunk. Production artifact traffic, network overhead and real provider
latency have not been measured in this pass.

## Recorded validation and fixture measurements

Validation used Python 3.12 and disposable PostgreSQL 16; synthetic providers only.

- Focused Phase 2/affected offline regressions plus Phase 1 primitives: 227 passed.
- Combined disposable PostgreSQL integration suite: 90 passed.
- Full offline backend suite: 1,075 passed (including the drift-restart and legacy failure-transition generation-fence regressions).
- The final extended measurement test also passed independently. Two existing
  FastAPI/Starlette test-client deprecation warnings remain; no SDK/dependency
  upgrade is included.

The following is one reproducible smoke fixture, not a production benchmark: one
source, one pending job, a 500,000-character synthetic legacy asset payload, and
local artifact files. Temporary locator lengths can change a few bytes between
runs. Asset bytes remain in core. JSONB request/result counters exclude SQL text,
scalar bindings, PostgreSQL wire framing, TLS and billed-transfer accounting.
Query counts are client SQL statements, not trigger-internal SQL or wire packets.

| Measurement | Legacy mode | Phase 2 active |
| --- | ---: | ---: |
| Core UTF-8 bytes | 500,877 | 500,628 |
| Claim: core snapshot JSON bytes sent | 500,820 | 0 |
| Claim: all JSONB values sent | At least the core value above | 1,022 |
| Completion: core snapshot JSON bytes sent | 500,902 | 500,656 |
| Completion: all JSONB values sent | At least the core value above | 502,552 |
| Isolated claim/completion transactions | 1 + 1 | 1 + 1 |
| Source-summary client SQL statements | 1 | 7 |
| Source-summary median / p95 ms | 8.6 / 11.4 | 34.5 / 49.0 |

The legacy comparison exercised actual legacy API claim/completion writes on a
separate workspace clone. It uses this updated binary in pre-cutover mode, so its
summary includes the new marker poll; the original older binary used cached state
without that poll. Static API parity is checked separately against identical
fixture state before preparation, while verified, and after cutover.

In active mode, isolated claim used 12 client statements and
isolated completion used 17. A complete one-chunk
interpret request used **9 persistence
transactions / 57 statements**, sending
504,832 JSONB bytes, including one
500,656-byte core update. Its synthetic
end-to-end duration was 159.4 ms. This does
not include real model latency. The fake provider bypasses allowance admission;
a real attempt retains the existing two ledger transactions per provider attempt,
including an additional pair for the existing confirmed-503 retry.

Scoped source summary used 4 transactions and about
1,060 serialized query-result bytes; source status used
2 transactions / 5 statements and
about 1,444 result bytes. Status median/p95 was
19.6/21.3 ms. Both latency samples
contain 12 local requests and are smoke observations, not production SLO evidence.
Neither path retrieves asset payloads.

An injected stale CAS followed by successful persistence reconciliation sent
1,004,210 total JSONB bytes, including
1,001,312 attempted core payload bytes over
2 UPDATE attempts / 2
transactions. Only the successful core update is durable. Provider work was not
repeated; the number of persistence reconciliations is bounded at two.

Core size fell by only 249 bytes
in this one-job fixture. One full core write per successful interpreted chunk
remains because assets are still legacy-authoritative. Phase 2 removes job/status
snapshot writes; it does not establish the Phase 3 98.2–99.6% bandwidth projection.
Output revisions and other core mutations can still write large snapshots.

## Migration-attempt lifecycle and revision-drift restart

Each migration attempt ID is permanently bound to one pinned core snapshot
revision. An existing attempt's pin never changes. Preparing/backfill can resume
only while the authoritative legacy snapshot remains at that pin. Revision drift
invalidates a preparing attempt for continuation; it can never later resume,
verify or cut over.

The explicit `restart_after_revision_drift` transition is separate from
`restart_after_rollback`. It requires the expected current legacy revision,
attempt ID and old pin, confirms the existing attempt is preparing, unverified
and not cut over, and records the invalidation in the same transaction that
creates a replacement attempt. The immutable history row retains the original
attempt ID, partition version, pin, checkpoint, start time and migration
revision. It has `terminal_reason=revision_drift`; verification and cutover
fields remain null because neither occurred. The replacement gets a new attempt
ID, pins the current authoritative legacy revision and starts with a fresh empty
checkpoint. This administrative operation does no provider work and does not
change authority.

Restart after rollback remains the separate path for a previously verified and
cut-over attempt whose authority was explicitly rolled back to legacy. It records
the prior attempt with `terminal_reason=rollback_restart`, preserves its pin and
verification/cutover provenance, then creates a new attempt at the current
legacy revision with a fresh checkpoint. It also does no provider work and does
not change authority.

For both restart paths, archived history is append-only. Repeating a restart
against an already archived attempt is rejected; it does not create another
history row or replacement attempt. `verified` means equivalence checks passed;
it does not activate partition authority. Only the existing explicit guarded
cutover changes authority.

| Transition | Starting state -> result | Authority before -> after | History row | New attempt ID | Existing pin changes? |
| --- | --- | --- | --- | --- | --- |
| Prepare | No attempt -> preparing | Legacy -> legacy | No | Yes | Initial pin only |
| Resume/backfill | Preparing -> preparing | Legacy -> legacy | No | Same ID | Pin unchanged |
| Verify | Preparing -> verified | Legacy -> legacy | No | Same ID | Pin unchanged |
| Cutover | Verified -> verified with cutover revision | Legacy -> partition | No | Same ID | Pin unchanged |
| Rollback | Active verified -> legacy snapshot | Partition -> legacy | No | No | Pin unchanged |
| Restart after rollback | Rolled-back verified -> new preparing | Legacy -> legacy | Archived `rollback_restart` history | Yes | Old pin unchanged |
| Restart after pinned-revision drift | Drifted preparing -> new preparing | Legacy -> legacy | Archived `revision_drift` history | Yes | Old pin unchanged |

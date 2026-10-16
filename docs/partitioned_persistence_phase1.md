# Partitioned hosted persistence: Phase 1 review

Architecture contract: [approved plan](partitioned_persistence_plan.md).
This slice adds dormant primitives only. It does not change routes, interpretation,
provider dispatch, snapshot loading/saving, ownership, allowance admission, or local
SQLite persistence. No production schema/data migration is performed.

## Schema delivery

`apps/api/schema/create_knowledge_engine_partitions.sql` follows the existing
repository's additive administrative SQL convention. It is not an application
startup migration. Apply only to a disposable database for Phase 1 testing; hosted
application of this schema needs a later explicit rollout decision. The SQL runs
in one transaction; failure rolls back the DDL. It is intentionally a one-time
migration, not `IF NOT EXISTS` masking a mismatched existing definition.

The five new tables in the existing private `knowledge_engine` schema are:

- `partition_sources`: one lifecycle/interpretation row per workspace/source;
  monotonically increasing generation/revision, deleted fence, status/reason.
- `partition_jobs`: one job row with chunk/generation/extraction version,
  guarded status, claim token, metadata and timestamps. Pending/running jobs share
  one unique live slot per workspace/source/generation/chunk. No progress counter.
- `partition_assets`: one stable asset row with exact job/source/chunk/generation/
  extraction-version provenance, active/supersession state and model-valid JSON
  payload. No independent authoritative active-assets collection.
- `partition_operations`: command-bound operation receipts committed with the
  mutation; supports explicit resolution after uncertain acknowledgement.
- `partition_migrations`: staging checkpoints only, with version, fixed source
  snapshot revision, preparing/verified stage and checkpoint CAS. It never becomes
  the active-authority marker. The future marker belongs in the core snapshot.

Relational keys/constraints and triggers enforce generation fences, immutable
identity, monotonic revisions, contiguous per-chunk extraction versions, legal job
transitions, ten-minute stale-running recovery, exact asset provenance, one active
extraction version per chunk, and irreversible supersession. Empty replacements
retain their version in completed jobs rather than a second progress/batch counter.
Indexes cover source/chunk jobs, active chunk assets, source assets and batch ID
reads. RLS is enabled with no public table/function grants or API policies. A later
schema rollout must use the existing backend owner/appropriate private-role setup;
no new browser access is introduced.

## Store interface and transaction boundary

`get_partition_store()` lazily constructs `PostgresPartitionStore` only in hosted
mode. Construction performs no IO. No current route/service/loader calls it.
`PartitionStore` extends the existing persistence contracts rather than replacing
StateStore or creating another application state facade.

Reads: `read_source`, `read_job`, `query_jobs`, `query_assets`, `assets_by_ids`,
`read_operation`, `read_migration`. All are workspace-scoped; jobs/assets require
source/generation or explicit asset IDs. Active queries also require a live current
generation. Explicit historical/by-ID reads preserve provenance, including old
versions; these are primitives, not authorization or deletion API endpoints.

Mutations are grouped through `apply(operation_id, complete_command, callback)`.
The callback receives `PartitionTransaction` methods:

- `create_source`, `advance_generation`, `update_source`;
- `create_job`, `claim_job`, `finish_job`, `recover_job`;
- `insert_assets`, `supersede_assets`;
- `prepare_migration`, `checkpoint_migration`.

`finish_job` is a guarded database status primitive, not an application completion
or provider-dispatch workflow. Future completion must compose supersession, batch
insertion, terminal transition and source outcome in one transaction. Phase 1 does
not wire that composition into interpretation. `insert_assets` validates the full
batch then performs one set-based insertion, not per-asset calls. Batch ID reads
use one scoped query; empty batches do no IO.

An operation ID is bound to the entire JSON command, including expected revisions,
generation, token and payload. Reuse with different inputs fails. Replay returns the
original result and `replayed=True`; it is never permission to dispatch a provider.
No automatic retry occurs on a driver/commit error. `read_operation` can establish
whether that mutation committed. If absent, any later user action must revalidate
current state; never infer that a model call should be repeated. Receipts remain
private and must not be logged along with commands or driver connection details.

Normal operations own one short connection transaction. A caller may pass an
already-transactional connection to `apply` or `transaction`; the store uses a
savepoint and leaves the outer commit to the caller. This supports future atomic
core+narrow lifecycle mutations in the same Postgres database. No external side
effects belong inside these callbacks. Constraint errors and driver details are
sanitized. No unbounded reconciliation is added.

## Version scaffolding and rollback safety

`PARTITION_VERSION = 1`. `snapshot_authority` is a pure compatibility helper for
future readers: no marker or a supported preparing marker means legacy authority;
a supported active marker means partitioned; malformed/unknown versions fail
closed. Current live loaders do not invoke it and still read the full snapshot.

Staging begins at preparing and supports revision-checked checkpoints against a
fixed migration ID/source revision, then verified. Verification here records a
caller's staging milestone; the actual backfill/composed-state comparison is not
implemented. No primitive activates a version, compacts state, backfills existing
data, or changes authority. The staging table is not another live marker. Any
future preparation must compare the real snapshot revision under the shared
transaction; the primitive's input alone is not proof of that comparison.

Before cutover the unchanged snapshot remains authoritative for jobs/assets/source
state; narrow fixture/staging rows do not merge into it. Narrow data can be ignored
by the old application. Do not run narrow writes as a parallel production workflow.
The standalone test database has no core snapshot table, proving these primitive
operations need no workspace load. The live allowance ledger remains unchanged.

## Verification

Offline tests live in `apps/api/tests/test_partition_primitives.py` and preserve
the existing PostgreSQL/Storage deny guards. They cover compatibility, no eager IO,
unchanged loader/factory behavior, scope/batching and sanitized driver failures.

Explicit integration tests live outside the offline suite at
`apps/api/integration_tests/test_partition_store.py`. Run:

```sh
.venv/bin/python -m pytest apps/api/integration_tests/test_partition_store.py -q
```

The fixture creates a uniquely named disposable `postgres:16-alpine` container on
the local Docker socket, binds only an ephemeral loopback port, applies the new
SQL and removes its own container in `finally`. It accepts no configured DSN,
uses synthetic data only, and never reads hosted credentials. It tests real SQL
constraints, concurrent claims/idempotency, source fencing, atomic rollback,
provenance, recovery, migration checkpoints and commit-acknowledgement loss.
Normal `apps/api/tests` remain entirely offline; Docker tests are explicitly run
separately and are not silently skipped when unavailable.

Recorded Phase 1 verification on Python 3.12 / disposable PostgreSQL 16:

- Focused offline persistence/grounding/extraction/reliability regressions: 171 passed.
- Disposable PostgreSQL integration suite: 29 passed.
- Full offline backend suite: 1,060 passed, including 26 new offline tests.
- Existing FastAPI/Starlette test-client deprecations: two warnings; no dependency
  upgrades included. No real provider calls or hosted database operations.

## Phase 2 decisions and work still required

- Build a core CAS coordinator that shares the narrow connection and only advances
  the in-memory core revision after the outer transaction commits. Existing
  `PostgresStateStore.save()` still owns its transaction and must not be composed
  with a separate commit and called atomic. No datastore change is needed.
- Implement verified backfill/resume, checkpoint meaning/cursors, exact legacy DTO
  reconstruction/order, and atomic core marker activation/compaction. An active
  flag or a verified staging row alone is insufficient to switch authority.
- Specify source-scoped receipt retention/redaction/cleanup and tombstone lifetime
  for deletion guarantees before a live workflow uses operation receipts. There
  is no automatic receipt/tombstone pruning in this slice.
- Wire current-generation scoped reads/caches and downstream parity/performance
  checks from the approved plan. Historical ID reads cannot be used as current
  active-evidence selection without checking source generation/deletion.
- Implement the full lifecycle cleanup and interruption-safe artifact publication
  order, public conflict mapping and bounded reconciliation. The source fence
  primitive blocks stale writes but does not delete artifacts or core records.

These are deferred cutover work, not authority or architecture changes in Phase 1.

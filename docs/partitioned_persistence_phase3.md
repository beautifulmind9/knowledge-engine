# Phase 3: narrow Knowledge Asset authority

Phase 3 introduces partition version 3. Version 2 remains the completed job
and source-lifecycle authority transition; assets stay in the core snapshot at
v2. Version 3 adds active and superseded Knowledge Assets to narrow PostgreSQL
authority. A v2 worker must reject a v3 marker. The v3 migration attempt and
history are stored separately from the v2 migration record.

After explicit v3 cutover, the core snapshot keeps libraries, outputs and
revisions, descriptive source metadata, chunk manifests and artifact metadata.
It does not keep authoritative asset arrays, extraction jobs, interpretation
progress, or source lifecycle/interpretation fields. Request-local composed
objects are projections. Narrow asset rows preserve the full validated payload,
stable ID, source/chunk/job relationship, generation, extraction version,
active/superseded state, superseding job, creation time, and workspace-global
ordinal. Reads of current assets require an active row, a live source, and an
asset generation equal to the source's current generation. Explicit history
reads can include superseded and older-generation rows while their source is
live.

V3 migration pins both the core revision and a SHA-256 fingerprint of the
canonical, sorted source-generation/deletion and immutable job-provenance
inputs. The pin is checked for every backfill batch, verification, and
cutover. A changed pin invalidates the attempt; it is archived and a new
attempt ID with fresh pins and checkpoint is required. Backfill inserts
set-based batches and refuses mismatching existing rows. Verification checks
payload, order, lifecycle, provenance, timestamps, missing/extra/duplicate
rows, and active extraction-version consistency. `verified` does not activate
authority. Cutover compacts v3-owned data from the core snapshot and switches
the marker in one PostgreSQL transaction.

Successful interpretation performs provider work and strict validation before
opening a transaction. Settlement then verifies the v3 marker, source fence,
job claim/revision/version, and receipt; checks the complete prior active set;
supersedes it in one set-based update; inserts the new batch in one
`jsonb_to_recordset` statement using an atomically reserved ordinal range;
completes the job; updates derived source interpretation status; and settles
the receipt. Empty results supersede prior assets and insert no rows. Any
failure rolls the transaction back. Receipt reconciliation handles uncertain
acknowledgements without provider replay. Settlement statement count is
constant in the returned asset count.

The legacy asset array is migrated in exact array order. Missing provenance is
resolved only from a unique matching immutable v2 job; missing or ambiguous
matches fail with the asset ID and are never assigned the source's current
generation as a guess. Runtime replacement appends the new batch after prior
workspace-global ordinals; superseded rows retain their original positions.
Independent chunks reserve disjoint contiguous ordinal ranges under the
workspace allocator row.

Only current-generation active assets may receive structure enrichment.
Superseded and older-generation payloads are historical and immutable through
runtime enrichment. Rechunk advances the source generation without rewriting
old asset rows. Delete fences source generation/deletion before set-based asset
and job cleanup; artifact cleanup follows the logical commit. Rollback
rehydrates the legacy snapshot from core plus narrow jobs, lifecycle and asset
history under a guarded full-snapshot CAS, then changes authority to legacy in
the same transaction. Narrow rows, receipts, and migration history remain for
verification and re-cutover; a re-cutover gets a new attempt identity and fresh
pins.

Reads use scoped or multi-source set-based queries. Workshop asset retrieval
and evidence-base summaries are batched. Consolidation receives one selected
scope. Explore preserves the existing Python ranker; its exact token predicate
is an unbounded lexical superset and does not enable candidate limiting or a
speculative search index. Saved output evidence continues to use its immutable
`knowledge_snapshot` and does not need current asset lookup.

The Phase 2 operator-surface blocker remains in force. The coordinator's
`writers_drained=True` argument is a caller assertion, not evidence that new
writers are blocked or active writers have drained. Do not run a hosted v3
migration, cutover, rollback, or restart until a protected operator surface can
block new writes and prove the authoritative in-flight writer count is zero.
This blocker does not prevent disposable PostgreSQL implementation testing.
The Phase 3 schema file is additive and must not be applied to a hosted
database in this phase.

## Disposable acceptance

Acceptance uses only synthetic providers and disposable PostgreSQL. Record
transactions, client-issued SQL statements, JSON payload bytes, returned rows,
approximate payload bytes, and local median/p95 latency for settlement with 1,
5, and 20 assets and for summary, Workshop multi-source preparation, evidence
base, Explore, consolidation, and browsing. Confirm statement count does not
grow linearly with asset count or selected-source count. Record the core
snapshot revision/UTF-8 size and confirm routine v3 settlement performs zero
core snapshot writes. These fixture measurements are not production wire,
network, or billing measurements.

Parity fixtures cover extraction, replacement, global/source ordering, source
detail and summary, counts, consolidation, Explore ranking and matched terms,
grounded answers, Workshop evidence and generation inputs, multi-source reads,
saved-output evidence, deletion, rechunking, and rollback/rehydration. Include
historical-generation and superseded assets, empty replacement, interruption,
and lost-acknowledgement receipt resolution. Race coverage includes concurrent
same-chunk completions, independent chunks, delete/rechunk before and during
settlement, stale generation/claim/revision/version, rollback/cutover fencing,
and supersession collisions.

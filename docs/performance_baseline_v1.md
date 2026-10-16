# Performance Baseline v1 — hosted benchmark procedure

Date: 2026-10-15

This is a manual measurement guide for the observability-only slice. Events are
best-effort structured log records prefixed `PERF` in backend logs and
`KE_PERF` in browser developer-console logs. Do not enable verbose request/body
logging. Never copy source contents, prompts, provider response bodies, cookies,
or credentials into benchmark notes.

The current Render AI Studio Free-tier limit for Gemini 3.1 Flash Lite is 500
requests per day. The deployed KE cap is `GEMINI_DAILY_CALL_LIMIT=450` provider
attempts per Pacific day, leaving a 50-attempt safety margin. Every actual
provider attempt counts, including the bounded identical second attempt after
a confirmed 503.

Render Metrics evidence reported for the knowledge-engine service this month:
11.94 GB total outbound, 38 MB HTTP Responses, 0 MB WebSocket Responses,
11.9 GB Service-Initiated, and 0 MB Service-Initiated Private Link. This made
application-originated external calls a leading bandwidth investigation and led
to the persistence and read-path acceptance work recorded below.

## Hosted acceptance results — 2026-10-15

### Persistence amplification

A real failed one-chunk/two-attempt request measured a whole-workspace snapshot
of about **4.65 MB** and **7 full snapshot writes**, approximately **32.56 MB**
of snapshot payload. The two Gemini request-payload estimates totaled only about
**71 KB**, confirming that whole-state persistence was the dominant measured
outbound application payload in that request.

After the dedicated hosted allowance ledger and two-checkpoint interpretation
lifecycle were deployed, production acceptance confirmed the same class of
provider-failure path used:

- **2** full workspace snapshots;
- approximately **9.31 MB** of snapshot payload;
- **2** small allowance reservations for the two actual provider attempts;
- no duplicate provider work from persistence reconciliation.

This is approximately a **71% reduction in snapshot payload** for the measured
two-attempt failure path. The observed request duration also improved, but it is
not treated as a controlled latency comparison because provider response times
differed.

### Read-path/storage amplification

Before optimization, the representative 33-source Library summary measured
approximately **41.6 seconds**, about **40 Storage metadata/list operations**,
and about **20 chunk artifact GETs / 9.7 MB** of chunk data. Opening Settings
also automatically triggered an integrity sweep of about **105 Storage metadata
operations**.

The deployed read-path changes introduced request-scoped
`ArtifactStore.status_many`, versioned source chunk manifests, and an explicit
Settings integrity action. Existing-source hosted backfill completed with:

- **35 sources updated**;
- **0 skipped** for missing, malformed, invalid or non-artifact chunk data;
- final verification dry-run: **0 remaining updates**.

Post-backfill Library acceptance for the same 33-source corpus recorded:

- `requested_path_count=66`;
- `unique_path_count=66`;
- `parent_group_count=2`;
- `list_request_count=2`;
- `individual_status_count=0`;
- `exact_fallback_count=0`;
- `library_source_summaries.duration_ms=1441.42`;
- **0 chunk-content GETs** in the summary path for the backfilled sources.

This is about **29× faster** than the earlier approximately 41.6-second result,
or roughly a **96.5% reduction in observed Library summary latency**.

A fresh browser session then proved that opening Settings requested `/usage`
without requesting `/data/integrity`. When the user explicitly selected **Check
data integrity**, the audit recorded:

- `requested_path_count=105`;
- `unique_path_count=105`;
- `parent_group_count=3`;
- `list_request_count=3`;
- `individual_status_count=0`;
- `exact_fallback_count=0`;
- `storage_status_many.duration_ms=2151.94`;
- `/data/integrity` returned **200 OK**.

Therefore the ordinary Settings view no longer pays the integrity-audit cost,
and the explicit audit reduces the observed metadata-request shape from about
105 serial checks to 3 grouped inventories while preserving live verification.

### Acceptance conclusion

The two largest measured non-provider amplifiers are production-accepted as
corrected:

1. whole-workspace snapshot write amplification;
2. Library/Settings Storage read and metadata amplification.

Benchmark C's server-side Library aggregation target is complete for the
current corpus. Remaining performance work should start with a fresh post-fix
interpretation benchmark before deciding whether request-scoped chunk-content
reuse inside `/interpret` is worth implementing. Do not infer that a known
repetitive path is an MVP blocker without current measurement.

## Benchmark setup and common fields

Use the same hosted deployment, browser, network, and provider configuration for
comparisons where practical. Note deployment/version, UTC start/end, browser,
file byte size, source count, and active Knowledge Asset count. Match backend
and browser events by source ID and time window. Record medians and ranges for
repeated ordinary requests; do not infer provider performance from one call.

Capture these events as available: `source_create`, `source_create_request`,
`source_upload_request`, `source_upload`, `artifact_write`,
`artifact_publication`, `text_extraction`, `chunk_construction`,
`source_extraction_request_total`, `source_chunk_request_total`,
`gemini_attempt`, `provider_response_adaptation_validation`, `state_persistence`,
`state_persistence_attempt`, `allowance_reservation`, `hosted_state_load`,
`hosted_state_reconciliation`, `storage_request`, `storage_status_many`,
`source_summary`, `library_source_summaries`, `material_preparation_request`,
`data_fetch`, `material_safely_saved`, `material_read_complete`,
`reading_to_preparation_start`, `material_batch_start`,
`material_batch_item`, `material_batch_item_complete` (item elapsed time),
`preparation_queue_dispatch`, `material_first_usable`, `material_ready`,
`preparation_interruption`, `preparation_continuation`,
`preparation_batch_complete`, `library_data_fetch`,
`library_render`, `material_detail_fetch`, and `material_detail_render`.

`state_persistence_attempt` records one attempted whole-snapshot write, including
stale compare-and-swap attempts. It includes `snapshot_utf8_bytes`,
`save_kind` (`normal` or `reconciliation`), duration, destination category,
source count, extraction-job count, interpreted-part count, active Knowledge
Asset count, and safe operation context. During the UI's one-part interpretation
request, `request_id`, source ID, and chunk ID correlate provider and state-save events.
Count each persistence-attempt event once; do not count the encompassing
`state_persistence` event as another write. `hosted_state_load` records duration;
its original serialized payload size is unavailable without reserializing the
parsed state. `storage_request` records request and response body byte counts by
artifact operation, without path or content. `storage_status_many` records safe
bulk-presence counts such as requested/unique paths, parent groups, list request
count and exact-fallback count without paths or object names. `gemini_attempt`
records an estimated provider request payload size from the already-built input
and response contract; SDK envelope, headers, and transport framing are excluded.
Hosted provider admission also emits one `allowance_reservation` event per
actual attempt. It reports reservation duration, a byte estimate for the
small safe reservation fields, outcome category, attempt number, and reservation
ID. It is a separate Postgres ledger write and never a workspace snapshot.
Safe request IDs join Storage reads/writes to source-summary and interpretation
requests, including repeated full chunks-artifact reads during preparation.

Example safe records (illustrative values):

```json
{"event":"state_persistence_attempt","destination_category":"state","save_kind":"normal","snapshot_utf8_bytes":185432,"duration_ms":74.2,"request_id":"b7d4…","source_id":"source_…","chunk_id":"chunk_…"}
{"event":"storage_request","destination_category":"artifact","operation_category":"artifact_read","request_payload_bytes":0,"response_payload_bytes":856321,"duration_ms":119.4,"result":"success"}
{"event":"allowance_reservation","destination_category":"state","operation_category":"provider_attempt_admission","approximate_payload_bytes":108,"duration_ms":21.6,"attempt_number":1,"reservation_id":"a91c…","result":"admitted"}
```

For a representative book, calculate and record:

1. **State-save count:** number of `state_persistence_attempt` events in the
   benchmark window, with normal, reconciliation, stale, and failed counts
   broken out. For each interpretation `request_id`, count matching save
   attempts to obtain per-part saves.
2. **Snapshot size:** median and maximum `snapshot_utf8_bytes` across those
   events. Compare size against each event's `source_count`,
   `interpreted_part_count` / `extraction_job_count`, and
   `active_knowledge_asset_count` to test growth as the corpus and prepared
   knowledge increase.
3. **Estimated cumulative Postgres payload sent:** sum `snapshot_utf8_bytes`
   across every attempted write, including stale/reconciliation attempts.
4. **Storage traffic:** sum `request_payload_bytes` and
   `response_payload_bytes` by `storage_request.operation_category` and record
   `storage_status_many` request shape for bulk-presence paths.
5. **Provider traffic estimate:** sum `estimated_request_payload_bytes` for
   attempts and separately total `provider_response_utf8_bytes` from response
   adaptation/validation events.
6. **Render bandwidth delta:** record Service-Initiated and HTTP Responses
   totals immediately before and after the same benchmark window, with UTC
   start/end. Also record the monthly cumulative metric at both points. Run the
   benchmark in a quiet window where practical; Render metric granularity and
   unrelated service activity limit precision.

For each Gemini attempt compare source/chunk IDs, attempt number/kind, elapsed
time, safe result category, and HTTP status. Exclude allowance admission and
the fixed retry sleep from provider-attempt elapsed time; include them in the
overall material preparation request. Compare per-part median, p90/max, and
the sum against total preparation duration. Count attempt 2 separately.

## A — one small supported document

1. Choose one ordinary small supported file not already in the workspace.
2. Record its byte size and selected-to-`material_safely_saved` time.
3. Record `source_upload`, artifact publication/write, extraction duration and
   extracted character count, chunk construction duration/count, and
   `material_read_complete`.
4. Record `reading_to_preparation_start`, preparation request duration, each
   `gemini_attempt`, validation, persistence, summary refresh, first usable,
   and Ready times.

Compare browser saved/read/preparation-start milestones with server upload,
extract, chunk, provider, persistence and summary timings. This establishes
fixed request/round-trip overhead and per-stage baseline for a one-chunk or
few-chunk source.

## B — one large real book

1. Use a large real supported book with enough chunks to expose repeated
   provider waits. Record only byte size; do not copy text into notes.
2. Capture extraction characters, chunk count, every per-chunk attempt and
   validation event, per-request Postgres snapshot writes, Supabase Storage
   request/response bytes (especially repeated artifact reads), summary
   refreshes, and total request and time-to-Ready.
3. Compare provider attempt median/p90/max and retry count with extraction,
   validation, persistence, and summary totals. Note chunk index is not logged;
   correlate by chunk ID and event order.

This identifies whether provider waits dominate and how much repeated hosted
state and interpretation artifact work contributes to a representative book.

## C — existing multi-book library

**Current status: server-side aggregation acceptance passed for the 33-source
hosted corpus on 2026-10-15.** Repeat only when the corpus or read-path design
changes materially, or when browser/cold-start behavior needs separate evidence.

1. With the current real corpus, load Library from a fresh navigation and
   capture `data_fetch` for `/libraries`, `/sources`, and `/sources/summaries`,
   `library_source_summaries`, `library_render`, source count, active Knowledge
   Asset count, and browser-observed completion.
2. Open several material details; capture source/summary/library fetch calls,
   `material_detail_fetch`, summary endpoint latency and visible completion.

Compare server aggregation time with browser fetch latency and render time.
Repeat once in the same warm session. Do not treat response-header timing as
full JSON parse/render cost.

## D — multi-book ingestion

1. Select several supported books together and note selected count and sizes.
2. Capture each `material_safely_saved`, `material_read_complete`, batch queue
   position, `preparation_queue_dispatch`, provider and persistence events,
   first usable and Ready events, and batch completion/interruption.
3. Include a material with already committed partial progress and explicitly
   continue it. Capture `preparation_continuation` and its remaining provider
   attempts/time to Ready.

Compare queue wait to own preparation duration for each material, selection
order to dispatch order, total batch time, time-to-first-usable and time-to-Ready
distributions, and explicit continuation count/cost. Check counts: selected,
saved, read, source count, chunks, assets, and per-material completed parts.

A confirmed `provider_unavailable` result is now a batch-wide stop condition
after the backend's bounded 503 policy, so later siblings should receive zero
interpretation dispatches in that foreground batch. Do not manufacture provider
failures to prove this path.

## E — interruption and continuation

1. Prefer navigation away from the foreground preparation view after at least
   one part has committed. A controlled deployment/restart is optional and
   should only be used when operationally practical.
2. Do not manufacture provider failures. Capture `preparation_interruption`
   reason where known, already committed progress, and saved/read state.
3. Return to the material, record the explicit continuation action/time, then
   capture continuation count, initial completed/remaining parts, subsequent
   provider attempts, first usable/Ready, and total continuation cost.

Compare lost dispatch time (work not started) with committed work, remaining
cost, and user actions. Verify completed progress survived and that future work
only resumed after explicit continuation.

## Known measurement gaps

- ASGI route timing begins after request-body receipt; upload browser fetch time
  includes transfer/connection but does not isolate browser-to-server receipt.
- Current artifact write timing covers extraction/chunk artifact saves. Upload
  event covers route entry through publication/commit, but does not split raw
  storage write from publication cleanup and state save.
- Provider timing excludes the fixed retry sleep and hosted allowance-admission
  persistence; total interpretation request includes both. This separates model
  wait from the larger user-visible cost.
- `data_fetch` ends when response headers arrive. JSON parsing, browser task
  scheduling, and paint/compositor presentation are not measured. Library render
  currently measures asynchronous view work through DOM assembly, not a paint.
- The short interpretation-to-progress callback interval excludes later source
  summary retrieval and paint; those have separate fetch and view measurements.
- Snapshot byte measurement serializes the in-memory snapshot once for size
  accounting before the Postgres save. The `state_persistence_attempt` duration
  excludes that measurement step; total request time includes its instrumentation
  overhead.
- Background/autonomous recovery does not exist in this architecture, so this
  baseline cannot measure a background queue or process-owned continuation.
- User time between stopping/navigation and choosing Continue must be noted
  manually; no analytics or cross-session user tracking is added.

## Synthetic snapshot growth check

Run the synthetic unit test
`test_synthetic_snapshot_size_grows_with_sources_chunks_and_assets`. It builds
an in-memory snapshot and confirms serialized UTF-8 size increases when source
records, interpreted-job/chunk records, and Knowledge Asset records are added.
Do not seed or serialize hosted customer state for the test. This verifies that
the measured snapshot byte field responds to those record classes; it does not
substitute for a hosted benchmark at current corpus size.

## Outbound path accounting

| External path | Outbound payload measurement | Limits |
| --- | --- | --- |
| Supabase Postgres snapshot save | `state_persistence_attempt.snapshot_utf8_bytes`, a UTF-8 JSON estimate for every attempted save, including stale CAS writes | Excludes SQL/connection/TLS/protocol framing. |
| Hosted allowance ledger | `allowance_reservation.approximate_payload_bytes` records the small durable provider-admission record for each actual attempt | Not a whole-workspace snapshot; wire/protocol framing excluded. |
| Supabase Postgres state load | Duration is measured; serialized received payload size is unavailable from the parsed row without reserializing | No extra serialization is performed for load measurement. |
| Supabase Storage | `storage_request` measures request and response body byte counts for artifact and metadata operations; `storage_status_many` records request grouping/counts | Excludes HTTP headers, TLS, and transport framing; categories omit object paths. |
| Gemini / Google API | `gemini_attempt.estimated_request_payload_bytes` measures the already-built provider input plus response contract; validated response text bytes are measured separately | SDK envelope, headers, and full wire response framing are not exposed by the current client. |
| Other app-originated external APIs | No other direct external HTTP client path was found in `apps/api/app` | Render platform telemetry/network accounting is outside application code. Browser requests to KE are response traffic, not service-initiated API calls. |

The original baseline showed both Postgres snapshot writes and Supabase Storage
reads were material. Whole-state snapshot amplification has since been reduced
through the allowance-ledger/two-checkpoint design, and ordinary Library summary
chunk reads have been removed for valid/backfilled manifests. Storage traffic
inside actual interpretation remains a separate measurement target.

## Decisions informed by the results

The data can establish whether provider latency, foreground serial queueing,
upload/storage, deterministic extraction, whole-state saves/reconciliation,
interpretation artifact reads, summary aggregation, or browser work dominates.
D/E quantify whether time-to-first-usable and explicit continuation burden make
durable background preparation a pre-MVP usability requirement. C's current
server-side Library aggregation concern is closed for the 33-source corpus.
B now needs a fresh post-fix sample to determine whether provider waits or
remaining interpretation artifact reads dominate preparation latency.

The baseline alone does not justify concurrency, weaker validation, fewer
persistence guarantees, or infrastructure spend; those choices require the
measured bottleneck plus product usability evidence.

The accepted persistence change targets two full snapshot writes for a
one-chunk interpretation: one pre-provider checkpoint and one settlement.
Expected hosted counts are therefore two `state_persistence_attempt` events
plus one `allowance_reservation` event for a normal single attempt, or two
snapshot events plus two reservation events for a confirmed 503 retry. At the
observed approximately 4.65 MB snapshot size before manifest backfill, that was
approximately 9.3 MB of snapshot payload per request, plus small ledger payloads.
The additive chunk manifests increased snapshot size only modestly in synthetic
measurement; continue to use actual `snapshot_utf8_bytes` from new benchmarks
rather than relying on the old fixed estimate.

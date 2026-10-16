# Knowledge Engine performance plan

Date: 2026-10-15

## Why this exists

The current private hosted beta is functionally reliable enough to continue product acceptance, but book addition, preparation and some Library views were perceptibly slow. The performance work is evidence-driven: measure first, correct the measured bottleneck, then re-measure before choosing the next optimization or spending on infrastructure.

The goal is to preserve the settled correctness rules—independent chunk interpretation, provenance, strict validation, progressive saving, bounded recovery and zero-cost operation—while identifying where user-visible latency is actually spent.

## Current performance shape

A large material can currently pass through several serial stages:

```text
browser upload
→ artifact persistence
→ deterministic extraction
→ chunking
→ one isolated Gemini request per chunk
→ strict local validation
→ hosted-state persistence
→ progress / summary refresh
→ browser rendering
```

Preparation is foreground and processes one material at a time. Each interpreted part uses its own provider request. A confirmed Gemini HTTP 503 may receive one additional identical provider attempt after the fixed retry delay; no other provider failure is automatically retried. A confirmed provider-unavailable result now stops the current foreground multi-material batch so later sibling materials do not spend additional provider attempts during the same outage.

A real hosted multi-book run also exposed an orchestration cost that raw per-chunk timing alone would miss: several books can be safely saved/read, but the preparation dispatcher is still foreground and serial. During a Render deployment/restart, committed progress survived while the active dispatcher did not. Some healthy books reached Ready and others remained partially prepared until explicitly continued. This is not data loss, but it is user-visible latency and operational friction.

The hosted service also runs on Render's free instance, so cold starts and limited compute can contribute to latency. Supabase Postgres and private Storage provide hosted persistence. These infrastructure limits must be measured separately from application design costs.

### Hosted-state write amplification: fixed and production-accepted

Performance Baseline v1 exposed whole-workspace snapshot persistence as a major bandwidth and latency amplifier. In the measured failed one-chunk/two-attempt path, the workspace snapshot was about **4.65 MB** and the request produced **7 full snapshot writes**, approximately **32.56 MB** of snapshot payload, while the two Gemini request payload estimates totaled only about **71 KB**.

The accepted MVP persistence change separated provider-attempt admission into a dedicated hosted allowance ledger and coalesced interpretation state into one pre-provider checkpoint plus one settlement checkpoint. Production acceptance then confirmed the expected two-attempt failure shape:

- **2 full workspace snapshots** rather than 7;
- approximately **9.31 MB** of snapshot payload rather than 32.56 MB;
- **2 small allowance reservations**, one for each actual provider attempt;
- no provider replay from persistence reconciliation.

This is approximately a **71% reduction in snapshot payload** for the measured two-attempt failure path. Request duration also fell in the observed sample, but that timing is not treated as a clean A/B because provider latency differed between runs.

The allowance ledger migration is live and authoritative for hosted provider admission. The original snapshot usage state remains rollback-compatible rather than being used as the hosted admission counter.

### Read-path/storage amplification: fixed and production-accepted

Production measurements before the fix showed that a 33-source Library summary took approximately **41.6 seconds**, performed about **40 Storage metadata operations**, and downloaded about **20 chunk artifacts / 9.7 MB** merely to reconstruct summary progress. Opening Settings also automatically ran a whole-workspace integrity sweep that produced about **105 Storage metadata operations**.

The accepted read-path change introduced:

- request-scoped bulk artifact presence through `ArtifactStore.status_many`;
- versioned source chunk manifests for summary/progress calculation;
- an explicit Settings integrity action rather than an automatic audit on Settings entry.

Existing-source backfill was completed against the hosted workspace on 2026-10-15:

- **35 sources updated**;
- **0 skipped** for missing, malformed, invalid or non-artifact chunk data;
- the verification dry-run reported **0 remaining updates**.

Hosted acceptance after backfill produced the following real results:

#### Library summary

For the same 33-source Library:

- `requested_path_count`: **66**;
- `unique_path_count`: **66**;
- `parent_group_count`: **2**;
- `list_request_count`: **2**;
- `individual_status_count`: **0**;
- `exact_fallback_count`: **0**;
- `library_source_summaries.duration_ms`: **1441.42 ms**;
- chunk-content GETs during the summary path: **0** for the backfilled sources.

Compared with the prior approximately 41.6-second result, this is about **29× faster** and approximately a **96.5% reduction in observed summary latency**, while retaining live artifact-presence checks.

#### Settings and integrity

A fresh frontend session proved that simply opening Settings makes the ordinary `/usage` request and **does not call `/data/integrity`**.

When the user explicitly selected **Check data integrity**, the full audit checked **105 referenced paths** through:

- `parent_group_count`: **3**;
- `list_request_count`: **3**;
- `individual_status_count`: **0**;
- `exact_fallback_count`: **0**;
- `storage_status_many.duration_ms`: **2151.94 ms**;
- `/data/integrity`: **200 OK**.

The audit therefore retains live verification semantics but no longer imposes roughly 105 serial remote metadata checks on every Settings visit.

### Current performance conclusion

The two largest measured non-provider amplifiers are now production-accepted as corrected:

1. whole-workspace snapshot write amplification;
2. Library/Settings Storage read and metadata amplification.

The next performance question is narrower: repeated chunk-content reads inside a single `/interpret` request remain deferred until a fresh post-fix one-chunk benchmark shows whether they materially affect the remaining preparation latency. Do not optimize that path merely because it is known to be repetitive.

## Measurement before optimization

Instrument or otherwise capture elapsed time for these boundaries without logging private source text or provider bodies:

1. browser-to-API upload;
2. artifact-store write/publication;
3. text extraction;
4. chunk construction;
5. each provider attempt, including attempt number and outcome category;
6. local schema validation;
7. hosted-state persistence and reconciliation;
8. source-summary / library aggregation endpoints;
9. browser data fetch and render time for Library and material detail views;
10. foreground dispatch delay between the completion of one part/source and the start of the next eligible part/source;
11. time and user actions required to resume a partially prepared multi-material run after navigation, process restart or deployment interruption.

Record counts alongside timings where useful: file size, page count where available, extracted character count, chunk count, active Knowledge Asset count, source count and library size.

## Benchmark set

Use four representative cases:

- **Small source:** fast, ordinary material that establishes baseline overhead.
- **Large book:** enough chunks to expose provider and persistence costs.
- **Current multi-book library:** representative of real Library and summary rendering load.
- **Multi-material ingestion run:** add several books together and record save/read completion, serial preparation order, time-to-first-usable knowledge, time-to-ready per book, and behavior after one controlled foreground/process interruption.

Do not use performance measurements to justify weakening grounding, provenance or validation.

## Decisions to make from evidence

Only after profiling, decide whether the dominant improvement should come from one or more of:

- limited concurrency across independent one-chunk provider requests while retaining one chunk per model context;
- durable/background preparation rather than a tab-owned foreground dispatcher;
- more granular hosted-state persistence beyond the accepted allowance-ledger/two-checkpoint change;
- request-scoped chunk-content reuse during interpretation if a fresh benchmark justifies it;
- lazy loading / virtualization for large knowledge views;
- improved extraction or upload pipeline behavior;
- paid Render compute to remove cold starts and increase consistent CPU/RAM;
- paid provider or database capacity only if measured quotas/throughput are the actual constraint.

The multi-book production observation makes durable/background preparation a concrete candidate rather than a purely theoretical future improvement, but it is not automatically an MVP requirement. The decision should depend on whether foreground serial preparation and explicit continuation make realistic use materially frustrating or unreliable for a beta user.

A paid platform is not a substitute for correcting unnecessary serial or repetitive application work.

## Performance acceptance target

Before declaring performance work complete, track at minimum:

- time until an added material appears as safely saved;
- time until deterministic reading is complete;
- median and high-percentile time per prepared part;
- total time to prepare a representative book;
- time-to-ready distribution across a multi-book add;
- user-visible recovery cost after a foreground/session/process interruption;
- Library load time with the current real corpus;
- recovery behavior when a provider 503 or hosted-state reconciliation occurs.

The current Library summary and Settings-integrity acceptance targets have been met in the hosted beta. Large-book preparation and foreground continuation costs remain open benchmark questions.

## Relationship to product acceptance

Performance is a first-class beta usability concern, but it is separate from knowledge usefulness. Product-value testing should continue against the real library while the remaining preparation profile is gathered.

The MVP question is not whether every large book becomes ready instantly. It is whether the wait is understandable, completed work remains safe, useful knowledge becomes available progressively, and realistic multi-book use does not require so much manual babysitting that it undermines the product's value.

The next overall sequence is:

**fresh post-fix interpretation benchmark → product-value acceptance → background/autonomy decision → external tester → final v1 beta decision**.

## Deferred performance and platform backlog

Every item below is **deferred, not rejected**. Revisit items against hosted measurements, MVP acceptance, provider/platform capability, and product-value evidence. This is the owning backlog for performance and platform follow-up; do not create a parallel performance roadmap.

### Deferred performance and infrastructure work

- Request-scoped chunk-content reuse inside `/interpret` (not implemented; a separately measured follow-up).
- Persisted artifact availability (deferred; live request-scoped presence checks remain authoritative).
- Larger persistence partitioning or normalization.
- Further Supabase artifact-read and source-summary efficiency work only if new hosted evidence exposes another material read-path bottleneck.
- Gemini model identifier and token instrumentation gap.
- Controlled Gemini 3.1 Flash Lite versus 3.5 Flash-Lite benchmark.
- Broader Google AI Studio and Gemini platform capability audit.
- Embeddings and semantic retrieval evaluation.
- Frontend and large-knowledge-view rendering performance.
- Wider network and upload efficiency.
- Supabase architecture and cost remeasurement after the accepted persistence/read-path changes.
- Render paid-infrastructure decision after measured optimization.
- Remaining hosted Performance Benchmarks A, B, D and E in [Performance Baseline v1](performance_baseline_v1.md). Benchmark C's Library/server aggregation target is now production-accepted; browser rendering/cold-start observations may still be repeated as needed.

### Deferred preparation and workflow decisions

- Durable/background material preparation.
- Webhook/completion signalling.
- Limited AI concurrency while preserving one chunk per Gemini request.
- Multi-book queue/autonomy.
- Preparation-state UX refinement.
- Explicit MVP background-autonomy decision based on interruption and continuation evidence.

### Deferred persistence options

These are later alternatives beyond the accepted dedicated allowance ledger and coalesced interpretation checkpoints:

- **C.** Independent source/job persistence.
- **D.** Partitioned Knowledge Asset/state persistence.
- **E.** Normalized/granular persistence.

### Deferred product acceptance and learning loop

- Real product-value acceptance on useful decisions and outputs.
- External-user acceptance.
- Longer-term learning loop:
  **Read → understand → interrogate → compare → apply → specify → build/test → reflect.**

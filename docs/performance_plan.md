# Knowledge Engine performance plan

Date: 2026-10-15

## Why this exists

The current private hosted beta is functionally reliable enough to continue product acceptance, but book addition, preparation and some Library views are perceptibly slow. The next performance step is measurement, not speculative optimization or immediate infrastructure spend.

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

Preparation is foreground and processes one material at a time. Each interpreted part uses its own provider request. A confirmed Gemini HTTP 503 may receive one additional identical provider attempt after the fixed retry delay; no other provider failure is automatically retried. This reliability rule can increase elapsed time when Gemini is unavailable or slow.

A real hosted multi-book run also exposed an orchestration cost that raw per-chunk timing alone would miss: several books can be safely saved/read, but the preparation dispatcher is still foreground and serial. During a Render deployment/restart, committed progress survived while the active dispatcher did not. Some healthy books reached Ready and others remained partially prepared until explicitly continued. This is not data loss, but it is user-visible latency and operational friction.

The hosted service also runs on Render's free instance, so cold starts and limited compute can contribute to latency. Supabase Postgres and private Storage provide hosted persistence. These infrastructure limits must be measured separately from application design costs.

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
- less frequent or more granular hosted-state writes;
- cached or incremental source/library summaries;
- lazy loading / virtualization for large knowledge views;
- improved extraction or upload pipeline behavior;
- paid Render compute to remove cold starts and increase consistent CPU/RAM;
- paid provider or database capacity only if measured quotas/throughput are the actual constraint.

The multi-book production observation makes durable/background preparation a concrete candidate rather than a purely theoretical future improvement, but it is not automatically an MVP requirement. The decision should depend on whether foreground serial preparation and explicit continuation make realistic use materially frustrating or unreliable for a beta user.

A paid platform is not a substitute for correcting an unnecessarily serial or repetitive application path.

## Performance acceptance target

Before declaring performance work complete, define targets from the measured baseline rather than inventing arbitrary numbers now. At minimum, track:

- time until an added material appears as safely saved;
- time until deterministic reading is complete;
- median and high-percentile time per prepared part;
- total time to prepare a representative book;
- time-to-ready distribution across a multi-book add;
- user-visible recovery cost after a foreground/session/process interruption;
- Library load time with the current real corpus;
- recovery behavior when a provider 503 or hosted-state reconciliation occurs.

## Relationship to product acceptance

Performance is now a first-class beta usability concern, but it is separate from knowledge usefulness. Product-value testing should continue against the real library while the latency profile is gathered.

The MVP question is not whether every large book becomes ready instantly. It is whether the wait is understandable, completed work remains safe, useful knowledge becomes available progressively, and realistic multi-book use does not require so much manual babysitting that it undermines the product's value.

The next overall sequence is:

**measure performance → test knowledge usefulness on a real decision → optimize the measured bottlenecks → external tester → final v1 beta decision**.

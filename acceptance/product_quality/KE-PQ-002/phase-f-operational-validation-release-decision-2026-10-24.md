# KE-PQ-002 Phase F — operational validation and release decision

Date: 2026-10-24. Baselines: [Phase D retrieval quality](phase-d-retrieval-quality-2026-10-24.md),
[Phase E capacity validation](phase-e-capacity-release-gate-2026-10-24.md), and the
[Measuring Narrative Engagement investigation](measuring-narrative-engagement-investigation-2026-10-24.md).

**Decision: local offline development is ready; limited supervised beta and broader
research-workflow release are no-go.** Application-level fail-closed behavior and
process RSS are now measured, but this environment has no PostgreSQL server or cached
PostgreSQL container. Actual plans, buffers, TOAST reads, database concurrency and
production-like HTTP worker behavior remain unverified. No provider call, hosted
infrastructure access, migration, commit, push or deployment occurred.

The original Measuring Narrative Engagement incident remains unresolved. Present-day
scope, identity and capacity safeguards are independently demonstrated; they do not
recover the missing historical source, request, retrieval, preparation, answer or
citation records and do not establish the historical root cause.

## Preservation and environment

Phase F started on `feature/knowledge-assets` at
`95c8f652045a342c315c4c20b884e5c599d76403`. Staging was empty and all existing
modified and untracked KE-PQ-002 work was preserved. The separate
`/workspace/knowledge-engine` worktree remained clean on `work` at
`9b4183bcef375364d46de2876d5e547c82d3a0c1`.

The executor has no `postgres`, `initdb`, `pg_ctl`, `psql` or `pgbench` binary. Its
local Docker daemon is reachable only through the managed socket and contains no
cached images. Phase F did not pull an image or enable network access. Therefore this
report does not present simulated SQL plans or relabel Python measurements as database
or production measurements.

## Indexed PostgreSQL query review

Phase E introduced two statements for each indexed asset read:

1. an aggregate with `count(*)` and `sum(pg_column_size(a.payload))` over the exact
   workspace, active generation, nondeleted source and caller scope clauses;
2. a payload query with the same clauses, deterministic ordinal/asset order and a
   defensive `LIMIT 1001` when the 1,000-item budget applies.

For lexical search, both statements additionally evaluate
`regexp_replace(lower(a.payload::text),'[^a-z0-9]+',' ','g')` for the full normalized
query and bounded term variants.

Static conclusions, pending real `EXPLAIN (ANALYZE, BUFFERS)` evidence:

| Concern | What the schema/query establishes | What remains unverified |
| --- | --- | --- |
| Source filtering | `partition_assets_active_order`, `partition_assets_active_chunk`, `partition_assets_source`, source primary/foreign keys and the active partial indexes can support workspace/source/generation filtering. Exact use is planner- and distribution-dependent. | Scan type, join order, row estimates and sort behavior for one source, `ANY(many sources)` and all-source scopes. |
| Row count | The aggregate counts the complete matching SQL scope before Python payload transfer. | Wall time, buffers, concurrent statement snapshots and planner behavior at realistic cardinalities. |
| JSONB size | `pg_column_size` measures PostgreSQL's stored datum representation. It avoids constructing application JSON and supplies an early storage-size guard. | It is not UTF-8 wire JSON size. Compression/external TOAST representation and actual TOAST page reads require a server plan and buffer measurements. The application UTF-8 check remains authoritative. |
| Lexical acquisition | Exact selected-source predicates are included in both statements; no outside-scope row is intentionally introduced. | The transformed `payload::text` predicate has no matching expression index. It is expected to scan scoped rows and serialize/detoast JSONB for matching; actual CPU, I/O and TOAST costs are unknown. The expression is evaluated again by the second statement. |
| Ordering | Ordinal/asset ID yields deterministic returned order. | Whether an index supplies the order or PostgreSQL sorts, particularly across many source IDs. |

The current indexes protect identity and common scope lookups. They do not make the
lexical JSONB expression indexed. Adding a speculative expression/search index without
representative plans and corpus distributions is not justified in this phase.

## Concurrent statement consistency

The aggregate and fetch are separate statements in the same default transaction. At
PostgreSQL `READ COMMITTED`, each statement can observe a different committed snapshot.
Concurrent deletion only reduces work. A concurrent insert or payload growth can make
the fetch larger than the aggregate admitted.

Phase E already bounded the count race to 1,001 fetched rows and search repeated the
authoritative application budget. Phase F found that indexed `list_knowledge_assets`
did not repeat that check. It now calls `check_candidate_budget(items)` immediately
after indexed acquisition. A deterministic adapter test simulates an aggregate that
admitted 1,000 rows followed by a fetch returning 1,001 and verifies an explicit 413,
`evidence_capacity_exceeded`, and the no-truncation message.

This closes the public acceptance gap: Find, Ask/Create preparation and indexed list
paths all reject changed oversized results before scoring, consolidation or generation.
The SQL race is still an efficiency risk. A same-count payload expansion can be
transferred and materialized before the application byte check rejects it. Replacing
the two statements with a one-snapshot query or changing transaction isolation requires
real PostgreSQL plans and contention tests; doing so unmeasured would trade one unknown
for another. This remains a beta blocker, not a reason to weaken or silently truncate
evidence.

Both statements retain the exact workspace/source/library-derived source IDs, active
generation and deletion clauses. The application then repeats source membership,
Knowledge Asset identity and JSON-byte validation. The Phase F correction does not
change source selection, provenance, citation identity, ranking, strict models or
evidence content.

## Local process measurements

`scripts/measure_retrieval_capacity.py` now supports one-workload processes and records
Linux worker current/peak RSS with `resource.getrusage`, alongside the existing
`tracemalloc` figures. Every run uses strict `KnowledgeAsset` validation, temporary
local storage and the real offline Find and Workshop preparation functions. Provider
and hosted-storage configuration is removed. Raw JSON results are outside Git under
`/workspace/ke-pq-002-validation/phase-f/`.

These measurements include Python import/runtime, synthetic fixture construction,
model validation, retrieval, consolidation and preparation. They exclude an HTTP
server, PostgreSQL, network transfer, provider work and production observability.

| Isolated workload | Outcome | Find / Workshop | Worker peak RSS |
| --- | --- | ---: | ---: |
| Small: 50 assets, 5 sources, 2 libraries | both succeed | 0.034 / 0.074 s | 64.6 MB |
| Source-heavy: 50 assets, 1,000 sources, 10 libraries | both succeed | 0.040 / 0.271 s | 68.1 MB |
| Adversarial duplicates: 1,000 assets | Find succeeds; Workshop rejects 413 at complete-preview budget | 0.558 / 0.826 s | 71.1 MB |
| Oversized count: 1,001 assets | both reject 413 before ranking/consolidation | 0.0013 / 0.0016 s | 66.3 MB |
| Oversized bytes: 128 assets / 4.53 MB candidate JSON | both reject 413 before ranking/consolidation | 0.023 / 0.023 s | 78.3 MB |

A single process running the entire seven-workload sweep completed in 8.87 seconds and
peaked at 88.1 MB RSS. That peak is cumulative for a reused process and must not be
treated as a per-request allocation.

Four independent processes were started together for representative contention:

| Concurrent workload | Wall time | Sum of per-worker peak RSS | Per-worker Find | Per-worker Workshop |
| --- | ---: | ---: | ---: | ---: |
| 4 × typical (250 assets / 25 sources / 3 libraries) | 3.93 s | 269.5 MB | 0.291–0.588 s | 0.503–0.973 s |
| 4 × large distinct (1,000 assets / 100 sources / 5 libraries) | 17.29 s | 312.2 MB | 1.558–3.613 s | 4.776–9.714 s |

The summed peak is a conservative sum of each process's lifetime high-water mark; the
individual peaks need not have occurred simultaneously. It is still the most useful
available free local bound. The 1,000-distinct workload shows significant CPU latency
under contention even though RSS remains bounded. Phase F therefore does not validate
the 1,000-item ceiling as a broad-service SLO.

## Numerical limits and user behavior

| Limit | Phase F assessment |
| --- | --- |
| 64 KiB request | Deterministic pre-acquisition boundary. Suitable as a conservative local guard; no real request-distribution evidence. |
| 1,000 candidates | Bounds memory and pairwise work, but four concurrent distinct workloads take 17.29 seconds wall time. Keep unchanged; require an explicit concurrency/latency budget before beta approval. |
| 4 MiB candidate JSON | Application UTF-8 rejection is measured. PostgreSQL `pg_column_size` is only an early storage proxy; real TOAST and transfer behavior is unverified. |
| 20 prepared units / 512 KiB preview | Complete evidence is retained or explicitly rejected. The 1,000-member duplicate group confirms rejection instead of evidence loss. |
| 256 KiB provider context | Existing exact pre-attempt guard remains; no provider/window claim is made. |
| 128 entries / 8 MiB preview cache | Existing deterministic eviction remains; aggregate worker RSS under a warmed real service is unmeasured. |

No limit was raised, reduced or converted to truncation. These values remain conservative
MVP operating policy, not production capacity or semantic sufficiency thresholds.

The existing 413 text is actionable in both the shared API transport and Ask card:
it says the scope is too large, asks the user to choose fewer materials or a smaller
scope, states that no evidence was truncated, and states that no provider request was
sent. Create and Find surface the same API detail. No new form or configuration panel
is justified. A future beta may benefit from preserving the selected scope while
linking directly to the existing library selector, but this is usability validation,
not an enforcement blocker.

## Verification

| Check | Result |
| --- | --- |
| Phase F count-drift plus Phase E capacity boundary tests | 17 passed, 0 failed |
| Phase D evaluation and capacity subset | 45 passed, 0 failed, 1 TestClient case deselected; creator acceptance remains 8/8 supported findings, 2/2 bounded vocabulary cases and 9/9 exact-scope cases |
| Coverage, scope, diagnostics and consolidation files completed separately | 25 passed, 0 failed |
| Complete frontend with shared module state | 207 passed, 0 failed |
| Complete backend | **Unverified in this executor.** Starlette `TestClient` blocks in `__enter__` while AnyIO's portal thread is idle, before application lifespan execution. Faulthandler captured this in fixture setup. Non-TestClient tests complete normally. This run is neither counted as a pass nor classified as a product regression. |
| `git diff --check` | passed before report creation; rerun required after final report edit |

No test or measurement made a Gemini/provider call. The PostgreSQL test guard and local
persistence isolation remain in place. The existing dependency warnings about Starlette
`TestClient`/httpx and AnyIO's `BlockingPortal` remain relevant to the blocked complete
backend run and need an environment/dependency-compatible rerun.

## Release decisions

### Local development readiness — GO

Scope: single-machine offline development and review, with synthetic or explicitly
authorized local data and no claim of hosted equivalence.

- Demonstrated: bounded offline behavior, explicit 413s, no evidence truncation,
  exact-scope regressions, process RSS measurements and all 207 frontend tests.
- Accepted limitations: the largest admitted workload can take several seconds;
  semantic retrieval and research sufficiency remain outside these guards.
- Required action: rerun the complete backend suite in a compatible clean test
  environment before merging any release candidate.

### Limited supervised beta readiness — NO-GO

Blockers:

1. no real PostgreSQL query plans, index evidence, buffers, TOAST/I/O or lexical scan
   timing on representative small/typical/large/adversarial datasets;
2. no database replay of READ COMMITTED aggregate/fetch drift or contention;
3. no production-like HTTP worker RSS/latency and no approved worker/concurrency budget;
4. the current executor could not complete the full backend suite;
5. the numerical ceilings have no representative user-distribution or SLO approval.

The new application recheck makes changed oversized indexed results fail closed, so
the remaining race is primarily resource efficiency rather than misleading partial
success. That safeguard does not substitute for beta operating evidence.

### Broader research-workflow readiness — NO-GO

All supervised-beta blockers apply. In addition, semantic-vocabulary coverage,
question-dimension coverage, evidence applicability/fidelity and discovery-to-
application continuity remain Phase G research-intelligence evaluations. Lexical
retrieval scores and capacity checks do not establish semantic completeness or
autonomous research sufficiency. The historical Measuring Narrative Engagement
incident remains unverifiable from the missing original records.

## Smallest next actions

1. Run the current schema and exact Phase E SQL against an isolated PostgreSQL instance
   with synthetic small/typical/large/adversarial data. Capture `EXPLAIN (ANALYZE,
   BUFFERS, SETTINGS)` for aggregate and fetch, table/index/TOAST sizes, cold/warm runs,
   and one-source/many-source/all-source scopes.
2. Replay insert, delete and payload-growth commits between aggregate and fetch at
   `READ COMMITTED`; measure bytes transferred and verify the public 413, source IDs
   and asset identities. Evaluate a one-snapshot alternative only against those plans.
3. Run the complete backend suite in a dependency-compatible clean environment and
   retain the exact pass/fail count.
4. Define an explicit free-tier memory, worker count and latency budget. Compare it with
   the measured four-worker 312.2 MB / 17.29-second large-distinct case before changing
   any numerical ceiling.

Until those steps pass, the integrity/resource release gates remain open and no commit,
push or deployment is recommended.

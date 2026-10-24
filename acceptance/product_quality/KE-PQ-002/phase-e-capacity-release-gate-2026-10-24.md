# KE-PQ-002 Phase E — capacity, resource limits and release-gate validation

Date: 2026-10-24. Baselines:
[Phase D retrieval quality](phase-d-retrieval-quality-2026-10-24.md),
[incident investigation](measuring-narrative-engagement-investigation-2026-10-24.md),
and the retained KE-PQ-001/002 integrity records.

**Decision: the offline application safeguard is demonstrated, but the overall
resource and integrity release gates cannot yet close.** Hosted PostgreSQL load,
query plans and concurrency remain unmeasured, the numerical budgets remain
product operating policy rather than production SLOs, and the original incident
chain remains unavailable. No provider call, commit, push or deployment occurred.

## Preservation and scope

Phase E began on `feature/knowledge-assets` at
`95c8f652045a342c315c4c20b884e5c599d76403` with all existing KE-PQ-002 changes
preserved and staging empty. A 148-file SHA-256 baseline is outside Git at
`/workspace/ke-pq-002-validation/phase-e-start.sha256`. The separate
`/workspace/knowledge-engine` worktree remained clean and untouched.

This phase changes retrieval capacity handling only. It does not alter semantic
ranking, sufficiency, strict KnowledgeAsset models, source selection, member
identity, citations, grounding, extraction validation or history.

## Path inspection

| Path | Acquisition and earliest current guard | Remaining work before/after guard |
| --- | --- | --- |
| Local Find | Active local assets are already resident in application state. A filtered list is built, then the 1,000-item/4 MiB check runs before scoring or consolidation. | The filtered Python list is allocated before the guard. The underlying state already owns the asset objects. Query-free library/material calls are independent. |
| Indexed Find | Phase 3 SQL applies exact source/library/type clauses. New count and `pg_column_size(payload)` aggregation rejects over-budget matches before payload rows transfer to Python. A defensive `LIMIT 1001` bounds a changed second read. The application repeats its exact UTF-8 JSON check before scoring. | PostgreSQL still scans matching rows to calculate count/size. Real query plans, TOAST behavior and concurrent inserts are unmeasured. Database size is not identical to serialized JSON size; the application recheck is authoritative. |
| Local Workshop/Ask/Create preparation | Selected source IDs filter active assets. Candidate count/bytes reject before relevance scoring and pairwise consolidation. Request JSON rejects at 64 KiB before acquisition. | Local state and the filtered-reference list already exist. At the admitted ceiling, full-pool consolidation remains potentially quadratic. |
| Indexed Workshop/Ask/Create preparation | `active_assets` now uses the same database-side count/size preflight and defensive fetch ceiling before returning selected-source payloads. The application repeats scope, identity and capacity checks. | Same unmeasured hosted SQL/concurrency assumptions as indexed Find. |
| Consolidation and selection | At most 1,000 / 4 MiB admitted candidates. Complete admitted groups are formed before the declared result limit, preserving member identity. | Distinct worst-case comparison work remains quadratic. A large duplicate trail can be expensive before preparation size is known. |
| Prepared preview/cache | Maximum 20 units and 512 KiB serialized preview; explicit 413 with no truncation. Preview cache also has 128-entry and 8 MiB serialized limits. | Exact preview size is known only after consolidation/context construction. Cache bytes do not equal process resident memory. |
| Generation context | Existing exact serialized payload plus adapted schema guard is 256 KiB and runs before the single provider attempt. | This phase made no provider call and does not validate a Gemini token window. The limit remains an application ceiling. |
| Multi-library web discovery | Each selected library/material request is separately bounded; existing UI merging displays at most 50 and pages ten cards. | Total client/network work grows with selected scopes. Concurrent many-library behavior was not load tested in Phase E. |

The demonstrated defect was the hosted boundary: Phase 3 `active_assets` and
`search_candidates` previously materialized every matching JSON payload in the
application before `check_candidate_budget()` rejected it. The existing indexed
`limit` argument was intentionally unused to avoid silently losing relevant
evidence.

## Implemented safeguard

Phase 3 now accepts caller-owned `max_items` and `max_bytes` budgets. Within the
same read transaction it:

1. applies the exact workspace, active-generation, nondeleted, source and lexical
   clauses;
2. obtains match count and `sum(pg_column_size(payload))` without selecting
   payload objects;
3. raises a content-free `PartitionCapacityExceeded` when either bound is over;
4. only then selects payloads, with `LIMIT max_items + 1` as a race/defense bound.

The retrieval service maps that exception to the existing explicit HTTP 413 and
`evidence_capacity_exceeded` category. It does not return the first 1,000, choose
a cheaper subset, retry, repair or claim that the scope has been fully searched.
The ordinary application count/UTF-8 JSON check remains after retrieval and will
catch a changed result or database/JSON size mismatch.

New tests prove the aggregate precedes `_all()` payload retrieval, inclusive
count/byte boundaries succeed, the fetch ceiling is 1,001, and local/indexed
service paths produce the existing public 413. Oversized search and Workshop
requests reject before candidate acquisition.

## Representative synthetic measurements

Run with `scripts/measure_retrieval_capacity.py`. The script validates every
asset through the strict KnowledgeAsset adapter, removes provider/hosted
configuration, warms one-time imports, uses local temporary storage and makes no
network/provider call. Timing is wall time; peak memory is Python allocation
visible to `tracemalloc`, not RSS, database memory or a production concurrency
measurement. Results are a single run on this executor.

| Workload | Candidates / sources / libraries | Candidate JSON | Full consolidated JSON | Find time / peak | Workshop time / peak | Outcome |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| Small | 50 / 5 / 2 | 24,350 B | 61,780 B | 0.033 s / 151,062 B | 0.073 s / 237,617 B | 40 cross-library Find groups; 20-unit, 93,158 B preview |
| Typical | 250 / 25 / 3 | 122,850 B | 311,630 B | 0.205 s / 474,140 B | 0.361 s / 1,197,499 B | 60 cross-library Find groups; 20-unit, 105,442 B preview |
| Source-heavy | 50 / 1,000 / 10 | 24,390 B | 61,900 B | 0.036 s / 152,995 B | 0.254 s / 2,024,011 B | 50 Find groups; 20-unit, 396,469 B preview |
| Large distinct | 1,000 / 100 / 5 | 493,350 B | 1,251,380 B | 1.089 s / 1,140,583 B | 4.059 s / 4,822,969 B | 100 cross-library Find groups; 20-unit, 127,571 B preview |
| Adversarial duplicates | 1,000 / 100 / 5 | 502,680 B | 526,371 B (one all-member group) | 0.555 s / 1,065,005 B | 0.822 s / 1,832,803 B | Find succeeds per library; Workshop explicitly rejects 413 at 512 KiB preview boundary |
| Oversized count | 1,001 / 100 / 1 | 493,848 B | not processed | 0.0013 s / 102,258 B | 0.0017 s / 118,371 B | Both reject 413 before scoring/consolidation |
| Oversized bytes | 128 / 16 / 1 | 4,532,362 B | not processed | 0.023 s / 87,364 B | 0.022 s / 87,613 B | Both reject 413 before scoring/consolidation |

The source-heavy preview uses about 76% of the 512 KiB application budget. The
large-distinct workload demonstrates the main remaining performance concern:
admitted full-pool consolidation takes about four seconds in this synthetic
single request. The adversarial duplicate case demonstrates evidence-preserving
failure: all 1,000 member identities create a preview over budget, so preparation
rejects rather than dropping members.

These figures validate deterministic behavior at the tested boundaries. They do
not validate production throughput, p95/p99 latency, process RSS, multiple
workers, concurrent requests, network transfer, PostgreSQL execution cost or
real corpus text distributions.

## Current ceilings and status

| Ceiling | Enforcement | Validation status |
| --- | --- | --- |
| Workshop/search request: 64 KiB UTF-8 JSON/query | Before acquisition | Boundary regression; application policy, not a user-text quality limit |
| Candidate count: 1,000 | Indexed aggregate before payload transfer; local/app check before scoring | Inclusive and 1,001 rejection tested; large synthetic workload measured |
| Candidate serialized JSON: 4 MiB | Indexed `pg_column_size` preflight plus authoritative application UTF-8 JSON check | Application 4.53 MiB rejection measured; database byte equivalence deliberately not claimed |
| Prepared units: 20 | Existing request/model and preflight | Regression tested |
| Prepared preview: 512 KiB | After consolidation/context construction | Duplicate 526,371 B group leads to explicit 413; no truncation |
| Provider context plus schema: 256 KiB | Before provider admission/attempt | Exact inclusive application test retained; no real-provider capacity claim |
| Preview cache: 128 entries / 8 MiB serialized | On insertion/eviction | Existing explicit-eviction tests retained; not RSS measurement |

## Verification

| Check | Result |
| --- | --- |
| New capacity/hosted-boundary tests | 16 passed, 0 failed |
| Focused capacity, Phase 3, partitions, integrity, relevance, diagnostics, consolidation and coverage | 106 passed, 0 failed |
| Phase D nine-case replay | No evaluated result change: supported creator findings remain 8/8, bounded vocabulary case 2/2, scope 9/9 |
| Complete backend | 1,235 passed, 0 failed; two existing dependency deprecation warnings |
| Complete frontend | 207 passed, 0 failed |
| `git diff --check` | passed |

No real Gemini, PostgreSQL or hosted storage call was made. Tests used local
state, fake hosted transactions and existing fake provider transports. There was
no paid service, provider retry, repair call, migration, commit, push or deployment.

Phase E touched only the hosted read-boundary exception/query implementation,
candidate-capacity mapping, focused tests, the synthetic measurement script and
this report. Existing historical evidence and unrelated product work remain
unchanged.

## Release blockers and recommendation

Demonstrated offline safety:

- oversized requests stop before acquisition;
- oversized local pools stop before scoring/consolidation;
- oversized indexed pools stop before JSON payload transfer in the tested SQL
  control flow;
- application checks repeat after transfer and preserve exact source/provenance;
- over-budget evidence is rejected explicitly without silent truncation;
- Phase D relevance and all full-suite regressions remain stable.

Untested operating assumptions:

- representative hosted PostgreSQL `EXPLAIN (ANALYZE, BUFFERS)` results for the
  scoped aggregate and lexical expression;
- TOAST/I/O and database memory behavior for large JSONB rows;
- concurrency, transaction visibility and app-worker RSS under simultaneous
  large requests;
- user-scope distributions and acceptable latency/SLOs, especially the measured
  four-second 1,000-distinct local consolidation;
- whether 64 KiB / 1,000 / 4 MiB / 512 KiB / 256 KiB are approved product
  operating budgets rather than conservative provisional values;
- many-library browser/network load beyond existing functional tests.

Recommendation: **do not close the overall resource release gate yet.** The
materialization defect is corrected and sufficiently guarded for offline review,
but hosted/load validation and budget approval remain P0 release work. Also do
not close the integrity gate: the original Measuring Narrative Engagement chain
is still unavailable, so historical causation and complete incident prevention
remain undecidable.

The next smallest step is an offline or isolated representative PostgreSQL
dataset using synthetic assets, with query-plan/buffer and concurrent worker/RSS
measurements. It requires no provider call. Do not proceed to semantic retrieval,
sufficiency or deployment on these measurements alone.

# Knowledge Engine V1 release-candidate operational validation

Date: 2026-10-24. Baselines: the KE-PQ-002 traceability review, incident
investigation, Phase D retrieval report, Phase E capacity report, Phase F operational
report, and the V1 blocker register.

## Decision

The preserved V1 overlay is internally consistent and ready for local development.
The Candidate 1 production-prompt defect, indexed preflight/fetch consistency defect,
and complete backend-test execution blocker are closed.

Limited supervised beta remains **NOT VERIFIED** until the deployment is checked against
its actual PostgreSQL version, memory allocation, connection limits and current export
size, and the owner approves the resulting operating envelope. Broader research-workflow release remains
**NOT VERIFIED** because semantic and synthesis evaluations are intentionally deferred.
No provider call, hosted-infrastructure access, push, merge, rebase, or deployment
occurred.

The historical Measuring Narrative Engagement incident remains unresolved. Missing
historical records prevent a causal conclusion; present-day safeguards are independent
evidence and are not a reconstruction of that incident.

## Preserved integration baseline

- Worktree: `/workspace/knowledge-engine-ke-pq-002`
- Branch and HEAD: `feature/knowledge-assets` at
  `95c8f652045a342c315c4c20b884e5c599d76403`
- Locally known `origin/feature/knowledge-assets`: the same commit
- Staging: empty before and after validation
- The modified and untracked Phase D-F/V1 files remain an overlay on that commit.
- `/workspace/knowledge-engine` remains a separate clean worktree on `work` at
  `9b4183bcef375364d46de2876d5e547c82d3a0c1`.
- Source-first work in the separate Mac environment was not accessed.

The logical integration order remains:

1. Candidate 1 accepted-control restoration plus extraction containment and tests.
2. Evidence integrity, exact-source closure, provenance and citation safeguards.
3. Phase D diagnostics, relevance evaluation, and narrowly supported retrieval changes.
4. Phase E/F/G indexed capacity safeguards, including repeatable-read consistency.
5. Evidence presentation, exploration, navigation, and Create continuity.
6. Acceptance reports and this release decision.

Files that span groups must be reviewed and staged as complete hunks. They must not be
rebuilt from an older checkout. The full file inventory remains visible in `git status`;
no unrelated file was staged or rewritten during this validation.

## PostgreSQL validation

### Environment and limits of the evidence

The actual migrations and indexed queries were run against an isolated local
`postgres:17-bookworm` container, PostgreSQL 17.11, bound only to loopback. The data was
synthetic. This is real PostgreSQL execution, but it is not production infrastructure:
the deployed PostgreSQL version and free-tier resource configuration are not recorded
in the repository, and cold-cache behavior was not established. All reported plans
were warm-cache plans with zero shared reads.

The container used `shared_buffers=128 MiB`, `work_mem=4 MiB`,
`effective_cache_size=4 GiB`, and `max_connections=100`. Those are measurements of the
local validation server, not recommended or inferred production settings.

Representative scopes contained 50/5, 250/25, 50/1,000 and 1,000/100
asset/source combinations, 1,000 duplicate-heavy assets, 1,001 over-count assets, and
128 oversized JSONB assets. The final synthetic database occupied approximately
1.97 MB heap, 1.97 MB indexes and 4.83 MB TOAST for `partition_assets`.

### Plans and timing

PostgreSQL used the active-order/source indexes for selective scopes and was free to
choose a sequential asset scan at the 1,000-row scale. That choice was rational for
the small synthetic relation and is not evidence of a missing index. Exact source and
active-generation predicates remained in both aggregate and fetch queries.

Thirty-sample client timings in milliseconds:

| Workload | Count p50/p95 | Fetch p50/p95 | Search count p50/p95 | Search fetch p50/p95 |
| --- | ---: | ---: | ---: | ---: |
| Small, 50 assets | 0.64 / 1.48 | 0.96 / 1.86 | 2.03 / 3.62 | 2.17 / 3.08 |
| Typical, 250 assets | 0.70 / 0.75 | 2.20 / 4.29 | 6.65 / 9.74 | 8.58 / 9.64 |
| Large, 1,000 assets | 1.28 / 2.91 | 9.12 / 13.95 | 24.89 / 37.64 | 33.35 / 43.49 |
| Over-count, 1,001 | 1.14 / 2.15 | 8.45 / 10.49 | 22.23 / 24.82 | 32.28 / 99.30 |
| Oversized JSONB | 1.68 / 2.86 | 53.29 / 78.33 | 64.77 / 92.61 | 91.02 / 107.59 |

The lexical `payload::text` transformation has no expression index and drives the
largest CPU/TOAST cost. It remains bounded by selected scope and the explicit candidate
budgets. The evidence does not justify adding an index without production corpus and
write-cost measurements.

### Consistency correction

Real concurrent mutation reproduced the Phase F concern at `READ COMMITTED`:

- an insert after aggregate preflight caused the fetch to materialize 1,001 rows before
  the application rejected it;
- same-count payload growth caused approximately 5.64 MB to materialize before
  rejection; and
- deletion reduced the returned set.

Both `active_assets` and `search_candidates` now establish `REPEATABLE READ` before the
marker check, aggregate preflight, and payload fetch. Post-correction replay returned
the original admitted snapshot for concurrent insert, growth, and deletion. Oversized
requests already present at transaction start reject before payload fetch. The existing
post-fetch application check remains defense in depth. Unit regressions assert the
isolation command on both paths; 17 focused capacity tests pass.

This closes the demonstrated query/fetch race. It does not prove production contention
or cold-I/O behavior.

## End-to-end HTTP and process measurements

Measurements used the actual hosted-mode FastAPI/Uvicorn application with one worker,
the isolated PostgreSQL database, beta authentication, and synthetic data. No artifact
or provider endpoint was invoked. RSS came from the operating system rather than
Python traced allocations.

| Workload | Result | Single-request latency | Four-request concurrency | Worker RSS |
| --- | --- | --- | --- | --- |
| Typical 250 | Search/prepare 200 | search p95 124 ms; prepare p95 153 ms | search p95 357 ms | 100.0 to 104.9 MiB |
| Large 1,000 | Search/prepare 200 | search p95 917 ms; prepare p95 708 ms | search p95 2.79 s | 100.4 to 120.8 MiB |
| Duplicate-heavy 1,000 | Search 200; prepare 413 | search p95 302 ms; prepare p95 207 ms | search p95 929 ms | 100.4 to 133.6 MiB |
| Over-count 1,001 | Explicit 413 | search p95 54 ms; prepare p95 32 ms | search p95 157 ms | peak 102.9 MiB |
| Oversized JSONB | Explicit 413 | search p95 98 ms; prepare p95 31 ms | search p95 291 ms | peak 101.7 MiB |

The duplicate-heavy and oversized runs preceded the isolation correction, but no
concurrent mutation occurred in them and the over-budget paths reject during aggregate
preflight. The typical and large HTTP runs were repeated after the correction.

The local database's post-workload snapshot was 55.4 MiB RSS with six processes. This
is not a recorded peak and does not represent a managed production database.

Hosted Phase 3 requests are not serialized by the legacy application lock. The actual
deployment command fixes Uvicorn at one worker. The release-candidate middleware now
admits at most four authenticated API requests in that process. A fifth fails immediately
with HTTP 503, code `request_capacity_exceeded` and `Retry-After: 1`; it is not queued.
Health, login/logout and static delivery bypass the capacity gate. Four overlapping
large requests stayed bounded in the measured case, with the latency shown above.

## Proposed supervised-beta operating envelope

These values are a proposal for owner approval, not current guarantees or production
SLOs:

| Dimension | Proposed envelope | Basis and enforcement |
| --- | --- | --- |
| Uvicorn workers | 1 | Already enforced by `scripts/render_start.sh`; matches measurements and hosted mutation design. |
| Active user requests | At most 4; one owner | Four-request measurements exist and the process-local fail-fast gate enforces four because deployment is fixed at one instance and one worker. |
| Worker RSS | 256 MiB operational ceiling | Highest observed worker RSS was 133.6 MiB. This supplies about 1.9x headroom, but actual hosting memory must be confirmed. |
| Candidate pool | 1,000 assets and 4 MiB serialized candidate JSON | Already fails closed; no silent truncation. |
| Prepared evidence | 20 units and 512 KiB | Already fails closed before generation. |
| Provider context | 256 KiB | Already fails closed; no extra provider call or retry. |
| Request body/cache | 64 KiB request; 128 entries/8 MiB serialized evidence cache | Already enforced by the current overlay. |
| Local latency guardrail | typical p95 under 0.5 s; large single p95 under 1.5 s; four concurrent large p95 under 4 s; oversized rejection under 0.5 s | All passed locally. These are regression guardrails, not production SLOs. |

The 256 MiB worker ceiling cannot be approved until the actual service memory allowance
is known. Silent limit increases and silent evidence truncation remain prohibited.

## Deployment, cold start and recovery evidence

`render.yaml` declares one free Render web-service instance, hosted persistence, the
private artifact bucket name and secret Supabase/PostgreSQL environment bindings.
`scripts/render_start.sh` fixes Uvicorn at one worker. These files match the proposed
topology. They do not reveal the connected Supabase project identity, PostgreSQL version,
connection allowance or Render memory allocation, so configuration alone cannot verify
those hosted facts.

Historical hosted acceptance on 2026-10-08 demonstrated restart persistence on an older
build. Current tests show invalid hosted configuration and failed state loads stop startup
rather than opening an empty workspace, hosted startup needs no persistent Render disk,
portable artifact locators survive reload, and allowance reservations survive restart.
Free Render services may sleep or restart. No current-RC hosted cold-start latency or
post-sleep smoke test was performed because hosted access was not authorized.

The private ZIP export and local restore procedure remain covered by regression tests,
including history and provenance. Two operational limitations remain: the ZIP is built in
worker memory, and its included restore instructions target a new local storage directory,
not an automated Supabase import. Before supervised beta, confirm the current hosted
export size fits the approved memory envelope and retain a private copy. A quiesced restore
into a new empty hosted workspace must be documented and tested before claiming hosted
disaster recovery.

## Regression evidence

| Check | Result |
| --- | --- |
| Complete backend suite, locked repository environment | **1,242 passed, 0 failed**, 2 deprecation warnings, 47.67 s |
| Complete frontend suite | **207 passed, 0 failed**, 0 skipped |
| Focused startup/recovery/admission/extraction/capacity/relevance set | **436 passed, 0 failed**, 2 warnings |
| Focused indexed capacity suite | **17 passed, 0 failed** |
| Phase D deterministic replay | creator variants **8/8**, vocabulary-changing cases **2/2**, exact-scope cases **9/9** |
| Candidate 1 prompt contract | production hash `6395ac95…`; containment removal gives accepted control `a9a7e8a7…` |
| Diff whitespace validation | passed |

The backend suite initially hung because the managed command sandbox blocks AnyIO's
blocking portal even for an empty FastAPI application. Isolated httpx and AnyIO upgrades
did not change that. The same locked repository environment completed outside that
command restriction, so no dependency change was made. The two warnings concern
Starlette's deprecated `httpx` label and AnyIO's `BlockingPortal` alias.

## Gate decision

| Gate | Status | Evidence or remaining action |
| --- | --- | --- |
| Integrated V1 implementation preserved | **PASS** | File-level overlay reconciled; no unrelated or separate-track work changed. |
| Candidate 1 production prompt | **PASS** | Accepted Rules 1, 9 and 15 restored exactly; containment retained; frozen experiment unchanged. |
| Retrieval/source/provenance integrity | **PASS** | 8/8, 2/2 and 9/9 replays plus full suites pass; strict models and citation identity preserved. |
| Indexed capacity and transaction consistency | **PASS** for demonstrated local cases | Actual PostgreSQL plans and concurrent mutations measured; repeatable-read correction passes replay. Production version/cold I/O remain unverified. |
| Complete offline regressions | **PASS** | 1,242 backend and 207 frontend tests pass. |
| Free-tier resource envelope | **NOT VERIFIED** | Proposed values need owner approval and actual service/database quotas. |
| Four-request overload protection | **PASS** | Process-local four-slot admission fails the fifth API request immediately; health/auth/static remain available. One instance/worker is required and configured. |
| Cold start and hosted recovery | **NOT VERIFIED** | Historical restart plus offline fail-closed tests exist; current-RC hosted cold start, export size and hosted restore are not verified. |
| Limited supervised beta | **NOT VERIFIED / no-go pending hosted checks** | Confirm actual quotas/version/export size, approve the envelope, then run a supervised no-provider cold-start smoke check. |
| Broader research workflow | **NOT VERIFIED / no-go** | Dimension coverage, applicability/fidelity, continuity and semantic limits require the already-defined next-phase evaluation. |

## Minimum remaining work

1. Record the actual hosted PostgreSQL version, service memory, connection allowance,
   worker memory allocation and current private-export size without changing hosted data.
2. Owner approves or adjusts the resulting one-worker, four-active-request, 256 MiB and
   latency envelope.
3. Run a no-provider current-RC cold-start/persistence smoke check after deployment
   authorization.
4. Document and later rehearse a quiesced restore into a new empty hosted workspace.
5. Keep the Measuring Narrative Engagement historical incident explicitly unresolved.

The implementation and acceptance records may be committed as the reviewed release
candidate. Hosted verification, push and deployment remain separate authorization gates.

## Release-candidate implementation commits

- `a3f0a8e` — restore the accepted extraction prompt controls while retaining source
  containment.
- `493eb46` — retrieval diagnostics, relevance evaluation, exact evidence integrity,
  capacity safeguards and repeatable-read indexed acquisition.
- `c677590` — evidence discovery, presentation, navigation and frontend regressions.
- `a8032f0` — fail-fast four-request hosted admission and operational documentation.

These commits are local only. Acceptance records follow as a separate documentation
commit so reviewers can assess implementation independently from the reports.

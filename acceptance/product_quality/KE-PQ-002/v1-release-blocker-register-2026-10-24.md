# Knowledge Engine V1 release-blocker register

Updated: 2026-10-24. This register supersedes the earlier same-day operational
blocker list. Full measurements and qualifications are in
[`v1-release-candidate-operational-validation-2026-10-24.md`](v1-release-candidate-operational-validation-2026-10-24.md).

## Baseline

- `feature/knowledge-assets` remains at
  `95c8f652045a342c315c4c20b884e5c599d76403`, equal to the locally known origin ref.
- The complete Phase D-F/V1 implementation remains an unstaged/untracked overlay.
- The separate `/workspace/knowledge-engine` worktree is unchanged.
- Source-first research in the separate Mac environment was not accessed.
- No provider call, hosted-infrastructure access, commit, push, merge, rebase, or
  deployment occurred.

## Closed blockers

| Former blocker | Resolution and evidence |
| --- | --- |
| Candidate 1 rules in production | Rules 1, 9 and 15 exactly match accepted commit `74cb1d7`; containment remains. Production hash is `6395ac95…`; removing containment reproduces accepted `a9a7e8a7…`. Frozen Candidate 1 evidence is unchanged. |
| Indexed preflight/fetch race | Real PostgreSQL replay demonstrated the `READ COMMITTED` drift. Both indexed reads now use one repeatable-read snapshot; insert, payload-growth and delete replay preserve the admitted snapshot. Post-fetch checks remain. |
| PostgreSQL plans and TOAST cost unknown | Actual schema and queries ran on local PostgreSQL 17.11 with small, typical, large, duplicate-heavy and oversized synthetic scopes. Plans, buffers, sizes and latency are recorded. Production equivalence is not claimed. |
| Complete backend suite blocked | Root cause was the managed command sandbox's AnyIO portal restriction. The locked repository environment completed outside that restriction: **1,242 passed, 0 failed**, 2 warnings. No dependency changed. |
| Frontend regression status | Complete suite: **207 passed, 0 failed**. |
| Phase D acceptance preservation | Creator variants **8/8**, vocabulary-changing cases **2/2**, selected-scope cases **9/9**. |
| Four-request overload policy | A process-local gate admits four authenticated API requests and immediately rejects the fifth with 503 and `Retry-After`; it creates no work queue. Health/auth/static remain available. One instance/worker is configured. |

## Open release gates

### P0 — before limited supervised beta

1. **Hosted facts and owner approval of the numerical operating envelope.** Proposed: one Uvicorn
   worker; at most four active user requests for the single-owner beta; 256 MiB worker
   RSS ceiling; existing 1,000-candidate/4 MiB, 20-unit/512 KiB and 256 KiB provider
   limits; local p95 guardrails of 0.5 s typical, 1.5 s single-large, 4 s four-large,
   and 0.5 s oversized rejection. These values are measured proposals, not approved
   SLOs.
2. **Actual deployment resource facts.** Record hosted PostgreSQL version, service
   memory allocation, connection allowance, worker memory and current private-export
   size. The local PostgreSQL
   evidence cannot establish production/free-tier capacity.
3. **Current-RC cold start.** Historical restart persistence and offline fail-closed
   startup tests exist, but the current release candidate has not been timed after a
   free-service sleep or checked against hosted persistence without provider calls.
4. **Hosted recovery.** Export/local restore is tested, but the in-memory ZIP must fit
   the hosted memory envelope and a quiesced restore into a new empty hosted workspace
   is not yet documented or rehearsed.

### P1 — accepted beta limitations and later evidence

1. The original Measuring Narrative Engagement source, request, retrieval,
   preparation, answer and citation records remain unavailable. Historical root cause
   and incident resolution remain unverifiable.
2. Prompt containment is a deterministic instruction/data boundary, not proof of model
   obedience. Any provider evaluation requires separate authorization.
3. Production cold-cache, real corpus distribution and contention remain unmeasured.
4. Semantic-only retrieval, question-dimension coverage, evidence applicability and
   discovery-to-application continuity remain the next research-intelligence phase.

## Release status

| Level | Status | Minimum action |
| --- | --- | --- |
| Local development | **PASS** | Preserve the overlay and review logical staging groups. |
| Limited supervised beta | **NOT VERIFIED / no-go pending hosted checks** | Close the P0 hosted facts, obtain owner approval, then perform an authorized no-provider cold-start smoke check. |
| Broader research workflow | **NOT VERIFIED / no-go** | Complete the defined semantic, dimension, fidelity and continuity evaluations. |

The historical incident is tracked separately and does not automatically block a
supervised beta once present-day integrity and operational gates are approved.

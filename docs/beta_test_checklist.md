# v1 beta release decision and acceptance checklist

Date: 2026-10-15. Decision: **private hosted beta live and internally accepted; external tester evidence and final v1 beta decision remain pending**.

The current private hosted beta runs on Render with Supabase Postgres + private Supabase Storage. The $0 development target, Gemini free-tier-only rule, no paid fallback, and hosted cap of 450 provider attempts per Pacific day remain in force. This leaves a 50-attempt margin below Gemini 3.1 Flash Lite's active 500 RPD AI Studio Free-tier limit; every attempt counts, including the bounded second attempt after a confirmed 503.

The latest reliability work closed the material-add/delete and hosted-state concurrency incidents that were blocking realistic multi-book use. Real hosted acceptance then confirmed the originally failing workflow: one book continued preparing while another book was added, both records survived, and the first book retained its progress. A real Gemini first-attempt HTTP 503 also recovered through the bounded identical second attempt while Render health stayed 200 and preparation continued.

A subsequent real multi-book ingestion run exposed a different, non-data-loss limitation: preparation is still foreground and serial. During a Render deployment/restart, committed source state and completed knowledge survived, but the active preparation dispatcher did not. Some healthy books reached Ready while other healthy books remained partially prepared until explicitly continued. This is now tracked as an MVP usability/performance question rather than a reliability incident.

The latest implementation checkpoint before those hosted acceptance runs reported **950 backend tests passed** and **172 frontend tests passed**.

In scope: source upload/reading/chunking, validated knowledge extraction and reprocessing, deterministic retrieval, grounded multi-source reasoning, Create/Workshop outputs, saved revisions, browser UI, quota controls, local and hosted persistence, beta access gate, deletion and export.

Deferred: public access, multi-user accounts/team authorization, OCR, native mobile, semantic contradiction guarantees, generalized agents, and any paid-provider fallback.

## Settled reliability rules

- One source chunk per Gemini extraction request.
- No shared multi-chunk model context.
- No automatic semantic repair calls, prompt mutation or model fallback.
- A confirmed Gemini HTTP 503 may receive one additional identical attempt; all actual attempts are separately allowance-gated and counted.
- HTTP 400, 429, validation failures, timeouts and uncertain transport outcomes are not automatically retried.
- Completed knowledge and completed sibling materials survive later failures.
- Hosted persistence keeps optimistic revision protection and only reconciles independent JSON changes. Overlapping edits fail closed.
- Persistence reconciliation never re-enters routes/services and therefore cannot repeat Gemini, extraction, upload or other external side effects.
- Source deletion persists the logical deletion before artifact cleanup. Failed state persistence leaves artifacts untouched; post-commit cleanup failure may leave a private orphan artifact rather than restoring a broken source record.

## Real-source extraction acceptance — completed

- [x] Restore the owner's actual *Workshop Survival Guide* source and existing jobs without losing history.
- [x] Use a billing-disabled/free-tier Gemini project with `GEMINI_FREE_TIER_CONFIRMED=true`; no paid fallback exists.
- [x] Finish the real source: **46/46 chunks interpreted**.
- [x] Audit the resulting knowledge: **121 active assets**, **0 missing evidence**, **0 missing keywords**, confidence **83 at 5 / 38 at 3**.
- [x] Review the evidence queue: **13 items** retained for manual review, inspected as source-supported compressed or near-exact evidence rather than known defects.
- [x] Repair historical cross-chunk provenance and the known compound crowd-recovery asset.
- [x] Validate the production extraction contract with a real strict single-chunk control.

### Extraction architecture decision

Production extraction is **one chunk per Gemini request**. Shared-context multi-chunk probes produced under-extraction and cross-chunk evidence leakage, so that path is not used. Gemini asynchronous Batch API is also not part of the current production path because it is unavailable on the Developer API free tier used by this project.

## Real-model output acceptance — completed

- [x] Exercise at least four materially different output modes with the real provider: Workshop Plan, Decision Brief, Study Guide, and Research / Synthesis.
- [x] Review source claims, applied knowledge, design-choice separation and usefulness.
- [x] Revise at least two real outputs while preserving lineage, provenance and original versions.
- [x] Run one meaningful same-task two-source comparison.
- [x] Record that lexical agreement/tension signals are advisory and can miss complementary relationships or overstate consensus.

Human review remains part of acceptance. Deterministic grounding checks are conservative review signals, not semantic certification.

## Hosted reliability acceptance — completed

- [x] Private Render beta and access gate work.
- [x] Supabase-hosted state and source artifacts survive restart.
- [x] Material add failures remain visible and recoverable rather than being treated as success.
- [x] Browser deletion tries ordinary source deletion first and only requests dependent-output deletion after an explicit backend conflict and user confirmation.
- [x] Logical source deletion commits before artifact cleanup; a state-save failure cannot leave a live record pointing to a deleted artifact.
- [x] Hosted optimistic-concurrency reconciliation preserves independent changes and fails closed on overlapping changes.
- [x] **Production concurrency acceptance:** while Book A was actively preparing, Book B was added successfully; both survived and Book A retained progress without the prior stale-revision error.
- [x] **Production transient-provider acceptance:** a real Gemini attempt 1 returned HTTP 503, the bounded identical second attempt succeeded, the interpretation endpoint completed 200, the source summary refreshed 200, and preparation continued.
- [x] **Production multi-material durability observation:** during a real multi-book run, successful books and already committed preparation progress survived a Render deployment/restart even though the foreground dispatcher stopped and some otherwise healthy books remained partial.

The concurrency and provider-retry incident paths are closed unless new production evidence contradicts the current behavior. Foreground preparation autonomy remains an open usability/performance issue, not a data-loss defect.

## Browser and external tester acceptance

### Internal browser evidence completed

- [x] Fresh setup / desktop happy path exercised internally.
- [x] Material preparation, pause/recovery, quota-stop, failed-job and stale-running states exercised.
- [x] Narrow mobile-width pass completed without blocking page overflow.
- [x] Core keyboard flow exercised in Safari, subject to Safari's keyboard-navigation settings.
- [x] Missing-key / unavailable AI states show understandable messages without consuming a provider attempt.
- [x] Saved-output revision, comparison, provenance and Markdown export exercised.
- [x] Multi-book hosted concurrency and provider-503 recovery exercised in the deployed app.
- [x] Real multi-material run confirmed that completed work survives a deployment interruption, while incomplete healthy materials may still require explicit continuation.

### Required before external invitation

Use the settled one-tester AI access policy: one trusted tester at a time, KE-owned server credential, shared 450 provider attempts per Pacific day, no personal-account or personal-allowance claim. Every actual provider attempt counts, including the bounded second attempt after a confirmed 503. Different browser sessions do not isolate data. No tester AI Studio account/key is required.

- [ ] Owner verifies current live hosted cap/configuration and billing-disabled $0-only operation before the session.
- [ ] Owner verifies current provider/tester eligibility and applicable provider terms for the material being used.
- [ ] Shared workspace contents are approved for tester access; no private owner material is unintentionally exposed.
- [ ] Tester understands shared data/control access and owner visibility into their material/work.

Tester: ______  Date: ______  OS/browser: ______  Result: ______

- [ ] Add material and understand save/read/preparation progress without terminal access.
- [ ] Correctly distinguish **Ready**, **Partially prepared / Continue preparing**, and a material that genuinely **Needs attention**.
- [ ] Ask/interrogate knowledge and understand the scope/evidence being used.
- [ ] Compare or synthesize across more than one relevant source.
- [ ] Use Create to turn a natural request into a grounded useful output.
- [ ] Distinguish source-grounded material from KE interpretation/design choices.
- [ ] Save, revise, compare and export work.
- [ ] Recover from at least one realistic interruption or unavailable state without losing completed work.
- [ ] Complete the core flow on desktop without confusing internal/schema terminology.
- [ ] Record qualitative feedback on usefulness, trust, speed and places where the system asks too much of the user.

## Known beta lifecycle limitation — foreground preparation

KE does not currently operate a durable background ingestion queue. Multi-material preparation is serial and owned by the foreground preparation context. A deployment, process restart, navigation away from that context or another foreground-run termination can stop future dispatch while leaving already saved material and completed knowledge intact.

For MVP acceptance, this limitation is tolerable only if users can understand the resulting state and continue without losing work. A partially prepared material must not be presented as though the source itself is corrupt or failed. Product language should separate ordinary incomplete preparation from genuine attention-required failures.

The performance baseline must therefore measure not only provider/extraction speed but also the manual recovery cost of serial foreground preparation. If realistic multi-book use requires excessive babysitting, durable/background preparation becomes a stronger pre-MVP requirement; if progressive knowledge and explicit continuation are understandable and tolerable, it can remain a post-MVP architecture improvement.

## Open beta usability risk — performance

Reliability is no longer the only concern. Large-book addition/preparation and some Library/material rendering are currently slow enough to affect the beta experience.

Do not guess that paid infrastructure is the complete fix. The next technical step is to profile the pipeline by stage: upload, artifact persistence, extraction, chunking, provider latency/retries, validation, hosted-state persistence/reconciliation, source-summary aggregation, foreground dispatch gaps and browser rendering.

Use a small source, a large book, the current multi-book library and a real multi-material ingestion run as the benchmark set. See [Performance plan](performance_plan.md).

Performance profiling should run alongside product-value acceptance; optimization should follow measured bottlenecks and must not weaken provenance, validation or safe recovery.

## Final release gate

The current product is **internally accepted as a private hosted beta**, not yet an externally validated v1 beta.

Remaining material gates:

1. Complete a real product-value test showing that KE materially helps a user **understand → interrogate → compare → apply** knowledge to a consequential decision, not merely summarize sources.
2. Establish a measured performance baseline, including multi-material foreground/recovery cost, and identify the dominant latency costs before changing infrastructure or processing architecture.
3. Decide from that evidence whether durable/background preparation is required before MVP or can be explicitly deferred.
4. Have at least one external tester complete the core workflow and record feedback.
5. Resolve or explicitly defer any critical defects or usability blockers discovered in those tests.
6. Record the final v1 beta release decision.

Release principle: a passing automated suite proves software behavior; it does not prove that the knowledge experience is useful, understandable or fast enough.

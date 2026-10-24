# KE-PQ-002 continuation — 2026-10-20

## Baseline reconciliation

The supplied `/workspace/knowledge-engine` checkout was clean on `work` at
`9b4183b`, tracking only `origin/main`. Its staged diff, unstaged diff and
untracked inventory were empty; it had one registered worktree and no local
`feature/knowledge-assets` or source-first branch. It did not contain KE-PQ-002.
After fetching origin and explicitly fetching the feature ref, the verified
remote feature tip was `95c8f652045a342c315c4c20b884e5c599d76403` (bulk library
moves), following `2501e19` (long-question discovery). These are different
histories: the supplied checkout and feature tip had 10/333 unique commits.

Implementation uses a new isolated worktree at
`/workspace/knowledge-engine-ke-pq-002`, local branch `feature/knowledge-assets`,
starting at that exact remote tip. No reset, checkout replacement, stash, stage,
commit, push or deployment was performed. No separate source-first worktree was
present or changed. Untracked work from another machine cannot be recovered from
this environment; the remote tip is the available verified baseline, not a claim
that unavailable local changes were inspected. All new research fixtures are
synthetic. The private export/database discussed in the historical README was
not available or read.

## Stage A — pipeline map

| Path | Candidate retrieval and ranking | Consolidation, limits and presentation | Generation and accounting |
| --- | --- | --- | --- |
| Find matching ideas | `app.js` loads `/knowledge-assets/search?consolidated=true` separately for selected libraries/materials. `knowledge_extraction.search_knowledge_assets` scores exact normalized query phrases and additive token hits in title, keywords, interpretation and evidence. | Raw candidates were capped at `max(limit*3,20)` before `consolidate_knowledge_assets`. Frontend merges/sorts batches, caps to 50, then `filterSearchResults` independently filters/reranks canonical text. Member-only matches can disappear. | No provider call. Selected canonical IDs and selected scope pass to Create; preparation expands selected units to their in-scope members. |
| Browse useful ideas | Query-free consolidated inventory by material; frontend runs four loaders concurrently and caches successful responses, retaining partial failure status. | Existing similarity consolidation, type/chapter filtering, ten-card pagination and selection. No relevance score or semantic interpretation of a question. | No provider call. Same Create handoff. |
| Ask & Explore | Workshop request builds normalized query, validates library/material scope, retrieves raw assets and scores separately from Find. Per-section relevance adds goal, situation, audience and every constraint. Single-source Ask permits zero-overlap context. | Raw cap `max(limit*5,30)`, hard multi-source quotas, consolidation, then a source reservation rule admitting scores at least half the best. Provider context is compacted but retains member provenance. | Dedicated grounded-answer provider schema adapts to strict internal output; member allowlists, source agreement guard, broad-scope guard and exact citation accounting. Prepared selected-source readiness was computed after generation. |
| Create / research synthesis | Same Workshop retrieval, with no single-source no-overlap fallback. Explicit selected asset IDs expand only within the selected scope. | Same consolidation and output limit; server-owned preparation token pins brief and evidence with TTL, deep-copy and source-existence checks. | General artifact contract and gap instructions, one validation pass, immutable snapshots/history. Applied references are traceability; synthesis has no section-level claim attribution. No semantic sufficiency gate. |

Both retrieval algorithms are lexical. Existing Workshop term expansions are a
small fixed vocabulary, not semantic interpretation. Long questions contribute
every surviving term: neither path knows which domain terms are incidental to
the user's information need. Asset type, confidence and reference count do not
establish empirical quality, causal support or independent studies.

## Confirmed mechanisms and unresolved hypotheses

Confirmed by code inspection and reproducible synthetic cases:

1. Local `list_knowledge_assets` accepted but ignored `source_ids`, allowing
   Workshop candidates outside the requested materials. The partitioned store's
   filter does not make the local implementation safe.
2. Workshop deduplicated terms within a field but added the same terms again
   across request fields and repeated constraints; every matched constraint
   also received an extra bonus despite an unchanged normalized query.
3. Find counted a repeated word across several asset fields; exact whole-query
   bonuses were unstable when a short question gained surrounding wording.
   Its frontend used another score and omitted noncanonical evidence.
4. Pre-consolidation limits could allow many duplicates to crowd out distinct
   findings and truncate independent supporting members. Source quotas and
   half-best reservation could replace higher-scoring evidence.
5. Preparation coverage listed only retained sources, conflating an absent
   selected source with a source that had no retained lexical match. Ask and
   Create did not expose comparable verified scope limitations.
6. The gateway already allowed one automatic confirmed-503 retry. Workshop
   generation needs a single-attempt scope to honor this task's explicit
   no-retry constraint without rewriting unrelated extraction behavior.

Already implemented and preserved: canonical/member citation identity,
member-to-material mapping, used versus retrieved counts, exact-member agreement
checks, immutable generation snapshots, source-grounding validation, strict
KnowledgeAsset validation, free-project admission and allowance accounting.

Unresolved: why the user's actual “Character…” and “Micro-Influencer…” records
ranked as reported, whether the two methodology pairs are duplicates, whether
their materials are independent studies, and which source limitations apply.
Only titles and the reported outcome are available; no actual candidate scores,
complete member evidence or bibliographic records were supplied here. Synthetic
fixtures test the mechanisms without pretending to reconstruct those records.

## Ranked minimal proposal and boundaries

1. Enforce exact selected-material scope locally and test with the real listing
   function, including empty lists and asset selections.
2. Add opt-in offline score/exclusion diagnostics using production scoring and
   consolidation. Keep source prose out of default diagnostic output.
3. Evaluate unique-term scoring, consolidate before output limits, and restrict
   diversity to relevance ties. Retain provenance for every consolidated member.
4. Stop frontend reranking authoritative scored results. Reuse pagination and
   display matched words, reference counts, distinct material records and member
   evidence within source/evidence disclosure. Do not infer research strength or
   thematic/semantic equivalence.
5. Give Ask and research synthesis verified preparation/retained-source coverage
   and an explicit retrieval-versus-sufficiency limitation; keep provider output
   schemas and exact citation accounting intact. Use one Workshop dispatch,
   with no retries, repair requests or additional sufficiency requests.

This proposal authorizes no semantic classifier, learned relevance cutoff,
automatic research sufficiency decision, domain taxonomy, extra infrastructure
or migration. Actual contextual applicability and claim support still require
human evaluation of the evidence.

## Stage B — implementation and verification

Implementation results, reproducible evaluation and validation follow. Baseline
tests were run from a clean `git
archive 95c8f65` with the repository's exact Python requirements lock. Provider
credentials are removed by the existing test configuration; storage and database
network guards remain active. TestClient/loopback checks require sandbox network
access in this environment; restricted runs stalled and were terminated rather
than counted as passing.

Untouched baseline results: focused KE-PQ-002, coverage-aware retrieval,
evidence-aware answers and library-move tests **36 passed**; complete backend
**1,151 passed, 0 failed**, with two dependency deprecation warnings. Complete
frontend baseline **194 passed, 5 failed** out of 199. Failures were in the
navigation harness and are recorded separately from implementation acceptance.
No unrelated candidate-execution tools/tests or frozen-commit failures were
present at this fetched baseline; absent untracked files are not considered
verified.

### Implemented changes

| Area | Files and behavior |
| --- | --- |
| Scope and Find ranking | `apps/api/app/services/knowledge_extraction.py`: honor local `source_ids`, including an explicitly empty list. Score distinct matched query terms once, using the strongest matching field per term. Field and exact-phrase contributions are bounded below one extra term, so repeated fields cannot overpower broader word overlap. This is a lexical ordering, not a semantic relevance estimate. |
| Ask/Create ranking and selection | `apps/api/app/services/workshop.py`: each unique term uses its strongest request-section priority once; repeated constraints add no extra score. Keep all admitted candidates through consolidation; limit complete groups. Source diversity only breaks equal-relevance ties. Explicit selected ideas still expand to their in-scope members. Preparation coverage now includes selected materials with zero retained ideas, separate from candidate and retained counts. |
| Consolidation performance and provenance | Existing similarity/tension rules and thresholds are unchanged. Precompute immutable comparison features within one consolidation, sharing equivalent comparisons without dropping member IDs, source IDs, quotations or canonical-selection behavior. Eight equivalence tests compare against the original rules, including negation, numerical differences, asset types and different thresholds. No global cache holds source text. |
| Development diagnostics | New `apps/api/app/services/retrieval_diagnostics.py` is an opt-in in-memory collector. Record query fingerprint/terms, scope, candidate IDs, field contributions, scores, pre/post consolidation positions, retained flags, exclusions and available preparation facts. The production score path produces these facts; there is no parallel explanatory scoring algorithm. Capture does not change the answer schema or perform provider requests. |
| Grounding and limitations | `apps/api/app/services/workshop_generation.py`: research modes receive preparation-snapshot coverage and retained-context facts before dispatch. Live results separate applied references from section citations, preserve unknown legacy match status, and state that counts establish neither independence nor sufficiency. Ask broad-coverage claims must satisfy both preparation and validation readiness and exact selected identities. |
| Attempt control | `apps/api/app/services/ai_gateway.py`: a request-local, token-reset context disables retry for Workshop generation, including confirmed 503 responses. SDK retry remains disabled; a failure consumes one admitted attempt and causes no repair or sufficiency call. The unrelated extraction gateway's existing default retry behavior is preserved. |
| Result usability | `apps/web/knowledge-browser.js`, `app.js`, `enhancements.js`, `style.css`: preserve scored backend eligibility/order, including noncanonical matches. Legacy unscored results retain their local fallback. Find pages ten ideas at a time; selections and Create handoff remain intact. Show word matches and singular/plural references alongside distinct saved-material counts, with an explicit research-quality limitation. Consolidated evidence stays inspectable without asserting equivalence or independent support. Create and Ask explain unavailable preparation and omitted context; saved research work has a general provenance limitation. |
| Navigation | `apps/web/navigation.js`: store the actual hash with each in-memory navigation entry. Rendering can fill default scope state; recomputing a different hash previously discarded saved queries on Back/Forward. Request text stays out of URLs and browser storage. |

Frontend baseline failures are not all stale tests. Two exposed the actual
navigation-state bug above. Three used outdated expectations for the existing
scope/handoff contract or omitted the input event that updates the unified
request. Those fixtures now assert the exact source-ID scope and retained
request; their behavioral assertions were not removed. The SDK serialization
test now requires one Workshop dispatch on 503, matching the explicit attempt
policy; standalone gateway retry tests retain their existing contract.

### Offline evaluation and reproduction

The tracked fixture is `apps/api/tests/fixtures/relevance/research_cases.json`.
Its labels are analyst judgments on synthetic records, never runtime labels or
claims about actual studies. Nine cases cover the supplied creator question,
short wording, added request wording, a lexical paraphrase, a second domain,
empty scope, a vocabulary-changing paraphrase, partly prepared scope and a
prepared material without matches. Synthetic lifecycle artifacts establish
preparation facts rather than merely naming sources “prepared.”

Compact reports are retained alongside the fixture as `baseline_95c8f65.json`
and `evaluated_current.json`. These measure backend Find results merged across
the chosen scopes and Workshop preparation; they do not pretend to measure the
old frontend's additional filtering or real provider output quality.

| Evaluation | Before | After |
| --- | --- | --- |
| Four supported creator-question variants, Find at limit 5 | 1 of 2 labeled direct findings retained in each | Both retained in positions 1–2 in each; same top-two order |
| Same variants, Workshop at limit 5 | 1 of 2 direct findings retained; outside-scope material present | Both retained; all evidence stays inside the selected materials |
| Second-domain direct evidence versus repeated generic field matches | Generic blood-pressure advice ahead of the labeled cohort finding | Labeled direct finding first |
| Selected-scope preservation across nine cases | 3 of 9 preserved; six leaked material outside the selected scope | 9 of 9 preserved |
| Vocabulary-changing creator paraphrase | 0 of 2 direct findings retrieved | 0 of 2: explicitly unresolved, excluded from lexical acceptance claims |

The four creator variants retain **8/8** expected direct-finding appearances,
versus **4/8** before. This is a small deterministic evaluation, not a general
semantic quality benchmark. Separate regression fixtures exercise a flood of
45 duplicate records, a supporting member from another material, a distinct
finding competing for the second slot, source diversity, repeated constraints,
near-duplicate grouping with distinct evidence, out-of-scope explicit selections,
and actual partial preparation. All 46 admitted members remain traceable in the
duplicate group, while the distinct finding retains its own result slot.

One proposed near-duplicate assertion failed: the synthetic titles ending in
“method” and “methodology” did not meet the existing clustering rule. No
threshold or validator was loosened. That original pair is recorded as a
remaining limitation with both records visible and their provenance intact;
it is not counted as a fixed duplicate case. A separate conservative case with
reordered title words verifies that an accepted group retains both different
member quotations and leaves a distinct finding separate.

Run from this worktree, without credentials or provider access:

```sh
.venv/bin/python scripts/diagnose_relevance.py --output /tmp/ke-relevance-after.json
.venv/bin/python scripts/diagnose_relevance.py --diagnostics --output /tmp/ke-relevance-trace.json
mkdir -p /tmp/ke-pq-002-baseline
git archive 95c8f65 | tar -x -C /tmp/ke-pq-002-baseline
.venv/bin/python scripts/diagnose_relevance.py --code-root /tmp/ke-pq-002-baseline --output /tmp/ke-relevance-before.json
```

The command reads only the tracked synthetic fixture, initializes temporary local
storage and removes provider/hosted configuration before importing application
code. Default reports omit full diagnostic traces. For development use,
`RetrievalDiagnostics()` can be passed to the existing search or prepare function
privately; no HTTP diagnostic endpoint was added. Its default capture omits
titles, excerpts and full request text. IDs and matched terms can still be
sensitive: real captures belong in private local storage, not Git. A query
fingerprint alone cannot replay unavailable source records.

### Performance and provider-context limits

Full-pool consolidation removes the old truncation but increases work for large
scopes. One local, synthetic search measurement at a result limit of 20 gave:

| Pool | Before | After | Members retained before → after |
| --- | --- | --- | --- |
| 100 distinct assets | 0.096 s | 0.023 s | 20 → 20 |
| 300 distinct assets | 0.088 s | 0.148 s | 20 → 20 |
| 1,000 distinct assets | 0.080 s | 1.591 s | 20 → 20 |
| 1,000 duplicate assets | 0.031 s | 0.041 s | 60 → 1,000 |

These single-run measurements are diagnostic, not performance guarantees. The
existing all-pairs worst case remains quadratic; large scopes need further
profiling. Local feature caching avoids repeated normalization and preserves the
original pairwise decisions, but does not make processing a full pool free.
In the duplicate probe, compact knowledge JSON grew from 9,764 to 160,946 bytes
because all member evidence remained intact. A group-count limit does not bound
provider-context size. Real provider capacity and output quality were not tested;
silently truncating member references or adding automatic retries would not be
an acceptable substitute.

### Remaining limitations and product review

- Lexical matches do not establish direct contextual applicability, empirical
  quality, causality, entailment or claim-specific research sufficiency. Added
  genuine domain terms can still displace other evidence; the older incidental
  marketing-context characterization remains a weakness, not an acceptance pass.
- Different vocabulary can miss semantically equivalent material. There is no
  semantic classifier, new topic-specific synonym list, automated sufficiency
  gate or additional model call. Next validation needs privately supplied actual
  candidate records/provenance and human claim/evidence labels, with held-out
  paraphrases and domains. Any real-provider validation needs separate explicit
  authorization.
- Existing heuristic consolidation is not proof that findings are equivalent.
  Some near-duplicates remain separate. All admitted members are retained before
  result limits, but this does not recover a zero-overlap asset that was never
  admitted; explicit idea selections still expand their in-scope groups.
- Find still merges capped per-library/material responses and displays at most
  50 results. Cross-library duplicate groups can remain separate. Browse retains
  its per-material grouping. No speculative thematic taxonomy was introduced.
- Single-source Ask can retain representative context with no word overlap;
  explicit selections can do the same. These cases are disclosed as context,
  never a deterministic proof of relevance or sufficiency.
- New preparation/retrieval coverage is available in previews and live research
  results. Existing saved-output records preserve their snapshots and citation
  metadata, but do not persist these new coverage fields. Historical coverage is
  not reconstructed, and a generic saved-work caveat does not supply missing facts.
- The original creator result ordering, the actual duplicate pairs' provenance,
  bibliographic independence, semantic output depth and empirical support remain
  unverified. Inspect those privately before claiming this workflow is validated
  comprehensive research.

No KnowledgeAsset schema, migration, source-grounding validator, extraction
integrity rule, generation-history behavior or member citation mapping was
weakened. Bulk-library-move files/tests and unrelated KE-PQ-001 material are
unchanged. No source-first branch/worktree was modified, and no private source
material was added. Changes remain unstaged and uncommitted for review.

### Verification — 2026-10-21

| Check | Actual result |
| --- | --- |
| Focused backend retrieval, diagnostics, consolidation, coverage, grounding, Create and library-move tests | 150 passed, 0 failed |
| Focused default-call compatibility and final diagnostic-limit checks | 39 passed, 0 failed |
| Complete backend suite | 1,199 passed, 0 failed; two existing dependency deprecation warnings |
| Complete frontend suite | 205 passed, 0 failed |
| Mocked relevance browser acceptance | 2 viewport groups passed: desktop 1,280 px and mobile 390 px |
| Existing bulk-move browser acceptance | Desktop and mobile passed, including partial failure, retained selection, retry and fresh destination listings |
| Final diff/protected paths | `git diff --check` passed; staging area empty; original checkout clean |

The first complete implementation run had 1,198 passes and one failure: the
normal prepare call passed a new `diagnostics=None` keyword to an existing
retrieval test adapter. The implementation now preserves the original invocation
when capture is disabled. The test was not weakened; affected checks and the
complete suite were rerun. The earlier near-duplicate assumption and obsolete
two-attempt SDK assertion were also handled explicitly as described above.

Relevant new backend modules are `test_relevance_evaluation.py`,
`test_retrieval_diagnostics.py`, `test_consolidation_equivalence.py` and
`test_research_scope_coverage.py`. Existing KE-PQ-002, coverage, beta, provider
contract, source-attribution, history, integrity and bulk-move regressions remain
in the complete suite. No unrelated candidate-execution test was removed or
edited, and no frozen-commit failure was encountered in this supplied baseline.

Reproduce complete suites from this worktree:

```sh
.venv/bin/python -m pytest apps/api/tests -q -o faulthandler_timeout=30
node --test --test-isolation=none apps/web/tests/*.test.mjs
```

New browser acceptance is `scripts/test_relevance_browser.cjs`; it intercepts
every request and rejects external traffic. It checks the exact three-library
scope, backend/member-only ranking, source evidence, pagination, second-page
selection, partial Browse failure/retry caching, exact Create material/asset
handoff, Back restoration, overflow and runtime errors, with zero generation
requests. Playwright was installed outside the application under
`/workspace/ke-pq-002-validation/browser`, using `/usr/bin/chromium`:

```sh
KNOWLEDGE_ENGINE_PLAYWRIGHT=/workspace/ke-pq-002-validation/browser/node_modules/playwright KNOWLEDGE_ENGINE_CHROME=/usr/bin/chromium node scripts/test_relevance_browser.cjs
```

The pre-existing bulk browser script was run through a temporary copy that only
adjusted its repository root and `/private/tmp` screenshot path for this Linux
environment; its tracked bytes are unchanged. Logs, synthetic diagnostic traces
and screenshots are outside Git at `/workspace/ke-pq-002-validation/`.

Tests removed real provider credentials and used fake SDK clients or
`httpx.MockTransport` where needed. Database/storage guards remained active.
There were **zero real Gemini requests, $0 provider cost, no paid fallback, no
hosted operations, no migration, no commit, no push and no deployment**.

# KE-PQ-002 requirement-to-implementation review — 2026-10-21

Finalized 2026-10-24, retaining the 2026-10-21 implementation and validation
checkpoint below. The resumed preservation audit confirmed the same HEAD, empty
staging area, clean original checkout and the recorded 20 unchanged / 6 extended
review-start files. No further production changes were made during finalization.

**Decision: no commit, push or deployment approval.** The retrieval improvements
do not complete KE-PQ-002's research-intelligence requirements. Source isolation,
evidence transport, question coverage and operating capacity are separate gates.

The governing doctrine remains **Capture naturally. Structure invisibly. Confirm
visually.** The objective is to help users move from available knowledge to
informed understanding and practical decisions. Nothing in this review introduces
a mandatory facet form, taxonomy, semantic classifier or research-agent system.

## Requirements reconciled and evidence boundary

This review treats these as cumulative requirements:

1. The original [KE-PQ-002 baseline](README.md): relevance, sufficiency, precise
   canonical/member attribution, comparable Ask/Create limitations, and rigorous
   execution. Its historical observations and characterization tests are not
   rewritten as completed acceptance criteria.
2. The creator-research evaluation in this conversation: exact selected libraries;
   inconsistent ranking; duplicate/overlapping findings; contextual transfer;
   references versus independent research; useful organization and Create handoff.
3. The two-stage implementation request and [implementation report](relevance-implementation.md):
   reproducible offline diagnostics and small labeled evaluation, only supported
   corrections, $0, no real provider calls, and preserved models/history.
4. The latest instruction: single-source evidence integrity, the reported
   **Measuring Narrative Engagement** contamination concern, large-scope safety,
   question-dimension coverage and available-but-unused knowledge. These are
   additional requirements; they do not replace items 1–3.

The detailed intervening pre-commit instruction text and a source/output capture
of the contamination incident are not present in the available conversation or
checkout. The current instruction establishes their requirements; it does not
supply their missing incident evidence or numerical capacity limits. A private
path or existing source/output IDs were requested asynchronously. No incident
content, source IDs, output text or supposed root cause has been invented.

The current branch is `feature/knowledge-assets`, HEAD `95c8f65`, with the earlier
uncommitted implementation preserved. Before this review, a private hash manifest
recorded all **26** existing changed/untracked files at
`/workspace/ke-pq-002-validation/traceability-start.json`. The original checkout
and source-first work remain untouched. No staged changes existed. Prior
verification was 1,199 backend / 205 frontend tests passing; those numbers are a
historical checkpoint, not this review's final results.

Status vocabulary: **completed** = the narrowly stated behavior is implemented
and supported by the cited evidence; **partially completed** = a protection exists
but the whole product criterion is not established; **unresolved** = a known gap
without a validated solution; **deferred** = deliberately outside this bounded
implementation; **blocked** = required evidence or a release decision is missing.
P0 precedes commit/deployment approval; P1 is current KE-PQ-002 acceptance; P2 is
the next research-intelligence evaluation. A completed row never implies semantic
completeness or empirical evidence quality.

## A. Pre-commit integrity blockers

| ID / original concern or criterion | Existing protection and justified correction in this review | Evidence of completion | Remaining gap / classification | Next action and priority |
| --- | --- | --- | --- | --- |
| A1. A single selected material must isolate every evidence representation throughout retrieval, consolidation, preparation and generation. | Earlier local `source_ids` filtering is retained. New `evidence_safety.py` checks scoped adapter results, canonical/member/trail sources, conflicting member/chunk identity, group source declarations and synthesis-context references. Known valid chunk manifests corroborate source/chunk ownership. Generation and snapshot resolution revalidate; a library membership change invalidates the preview. | `test_ke_pq_002_integrity_review.py`: outside-scope adapters in local and indexed paths; canonical, trail, group, context, missing/foreign member and conflicting-chunk mutations; source borrowing another source's known chunk; moved-library snapshot. Rejections happen before the fake provider, without output creation. | **Completed for tested identity-closure paths.** This does not prove that a quotation or interpretation actually came from the declared source when all historical metadata is consistently wrong. Missing original content is not reconstructed. | Keep these checks mandatory. Inspect the actual incident chain under A2; P0. |
| A2. Investigate Measuring Narrative Engagement contamination rather than assume retrieval fixes resolved it. | No matching incident capture is in this checkout. The original checkout's storage inventory has no local database; this worktree has no private case directory/database. A synthetic test uses the reported material name with an explicit synthetic label; it is not the incident. | Code inspection and synthetic cross-source failures demonstrate previously unguarded paths. They do **not** demonstrate which path caused the reported output. | **Blocked.** Actual selected IDs, member provenance, source text/chunks, prepared/provider context, response and displayed/exported references are unavailable here. This is unavailable incident evidence, not proof that the Engine lacked the research finding. | Obtain an existing private capture/backup or IDs. Read and compare the stages below, without generation; do not approve closure of the incident from synthetic passes. P0. |
| A3. Explicitly selected ideas must not silently disappear at a result limit. | Existing selection expands in-scope consolidated members. New post-selection and generation checks require every explicitly selected asset ID to remain represented. An oversized selection returns 409 instead of quietly cutting it. | New selection-versus-limit regression: two distinct selected ideas with limit 1 reject explicitly; original assets and provider calls remain untouched. Existing Create snapshot/handoff tests remain. | **Completed for explicit-selection retention.** Ordinary unselected retrieval still uses its declared result limit. Ask's Create-checkbox behavior is a separate continuity issue under C4. | Preserve fail-closed behavior; evaluate how best to explain/recover from a large explicit selection using existing controls. P0 protection / P1 usability. |
| A4. Exact member citations must not credit the whole group or an ambiguous source. | Existing `reference_maps`, canonical idea counts, provider allowlists, agreement/broad-coverage guards and export/history citation metadata are preserved. New preflight rejects conflicting or unresolvable multi-source member identity before those maps can be used for generation. | Existing KE-PQ-002, evidence-aware answer, grounded-provider and save/export/revision tests. The seven old multi-source fixture cases now explicitly select both intended sources; their original one-cited-member/count/history assertions remain. | **Completed for traceable member attribution.** Counts still do not establish entailment, independent studies or evidence strength. Historical ambiguous records remain historical, not silently repaired. | Keep member provenance separate from consolidated context and research independence; P0. |
| A5. Consolidation/compaction must not silently lose a member's available interpreted knowledge. | Before review, trails kept member quotes/IDs but discarded noncanonical `what_it_says`, application conditions and other interpreted fields. New trails retain the existing interpretation fields separately from each original quote; compaction already carries the complete trail. Similarity rules, thresholds and canonical selection are unchanged. | The new noncanonical-interpretation transport test failed before the change and now verifies the member's statement and `when_not_to_use` reach provider context with its own asset ID and unchanged evidence. | **Completed for new-context transport, partially completed overall.** Older saved snapshots lack those fields and are not backfilled. A model may still omit supplied knowledge; see C1/C4. | Preserve new member fields and original quotes under byte budgets. Validate usefulness and actual uptake separately; P0 transport / P2 uptake. |
| A6. Full-pool consolidation must not permit unbounded pairwise work. | Existing local comparison-feature caching is retained. New pre-comparison limits reject more than 1,000 acquired candidate assets or 4 MiB of serialized candidate data. Search/Workshop also check before ranking/consolidation; no candidate subset is silently substituted. | Capacity tests prove rejection before `_similarity_features` runs and check UTF-8 bytes. Prior 1,000-record measurements establish the largest measured pool, not a universal performance guarantee. | **Partially completed.** Acquisition itself can still materialize an oversized indexed result before the application rejects it. Limits can reject a broad scope with few eventual matches. Concurrency, hostile text/query distributions and representative production scopes need validation. | Bound indexed acquisition with an explicit overflow outcome, profile worst cases, and review operating budgets on actual scope sizes. This is an outstanding P0 release item, not a semantic threshold proposal. |
| A7. Provider context must be bounded, including all members, schema, brief and revision. | New preflight measures the actual UTF-8 payload plus the gateway-adapted response contract before `generate`. Application budget: 256 KiB. Request budget: 64 KiB. Preparation budget: 512 KiB / existing 20-unit maximum. No quote/member truncation, retries or repair calls. | Capacity tests cover an exact inclusive byte boundary, one-byte overflow, oversized preparation and a large prior revision. Provider-call count remains unchanged on rejection. | **Partially completed.** The guard is implemented, but these are conservative application budgets, not Gemini token-window claims or an approved capacity/SLO. Real user scopes may hit them, especially after member interpretations are preserved. | Review these provisional limits and recovery behavior with representative offline scopes before release. Do not run Gemini to discover a limit without explicit authorization. P0. |
| A8. Safety failures must preserve snapshots, saved parents and history. | Server-owned preview identity, TTL and deep copies remain. Cache is additionally bounded to 8 MiB of serialized evidence as well as 128 entries. Generation copies incoming prepared data before authorship updates. AI revision validates provenance and requires its selected/represented materials to remain available before pairwise synthesis. Evicted previews fail explicitly; saved histories are not pruned or rewritten. | Capacity tests verify byte-driven eviction, explicit expired-token failure, no provider call or parent mutation on rejected revision, missing-material rejection, and no snapshot mutation on failed preflight. Existing history/manual revision/export tests remain. | **Completed for tested rejection/history behavior.** Serialized-size budgets are not exact resident-memory guarantees; historical unsafe context can now be blocked from AI revision while remaining readable/exportable. | Keep read-only history available; review unsafe historical evidence privately rather than rewrite it automatically. P0. |
| A9. $0, strict models, one Workshop attempt and no repair/sufficiency calls. | Strict KnowledgeAsset and grounded-answer models, free-project/allowance admission and single-attempt Workshop context are unchanged. New checks run before provider admission. No source classification or extra AI call is introduced. | Existing strict-model/provider/503/allowance tests; new rejected-context tests use only fake clients/responses. No real credentials or provider calls are used in this review. | **Completed for this scoped execution contract.** Unrelated extraction's existing default 503 policy is not redefined by this review. | Preserve the Workshop one-attempt contract and credential-free test isolation; P0. |
| A10. Display must not make an unknown/out-of-scope citation look like selected-source support. | Earlier renderer accepted both directions of prefix matching. An unknown longer ID could borrow the sole selected source's name/quotes. It now accepts full identity or an exact unambiguous legacy digest, and rejects conflicting/out-of-scope member evidence when a material scope is provided. Unresolved references are labeled unverified. | Two new frontend tests: longer unknown ID cannot borrow a selected prefix, and a foreign member quote is not displayed as support. Prior exact-member and legacy ambiguity tests pass. | **Completed for the identified binding defects.** The renderer cannot verify free-text claims or recover missing historical provenance. | Include the actual incident's rendered display/export in A2; P0. |

### Scope of the corrections and capacity policy

The 8 failing pre-correction integrity probes establish concrete defects, not a
hypothesis about the historical incident. Corrections are restricted to identity,
transport and resource rejection. There is no new semantic relevance score or
automatic question-completeness verdict. A 409/413 response is an explicit stop;
it does not silently pick a cheaper subset, regenerate, repair, or spend quota.

The capacity values above are **provisional application policy requiring review**.
They are grounded in the largest pool previously measured, existing API unit
limits and a bounded request envelope. They have not been approved as production
capacity. Full candidate acquisition, concurrent requests and actual user scope
sizes remain release work. The new guards make the rejection boundary visible;
they do not make large-scope support complete.

## B. Current KE-PQ-002 acceptance requirements

| ID / original concern or criterion | Existing implementation/protection | Evidence supporting completion | Remaining gap / classification | Recommended next action / priority |
| --- | --- | --- | --- | --- |
| B1. Interpret natural questions usefully; retain direct evidence through concise, long and equivalent wording. | Distinct-term breadth with bounded field/phrase tie-breakers; source evidence is searchable. Workshop deduplicates request terms at their strongest stated priority. | Prior fixture: the four supported creator variants retain 8/8 expected direct-finding appearances versus 4/8 before, at limit 5. | **Partially completed.** This is a small lexical fixture. Vocabulary-changing paraphrase still retrieves 0/2. Domain context words and interaction instructions can still alter ranking. No semantic interpretation is implemented. | Preserve the fixture and evaluate actual UI-shaped requests and held-out paraphrases/domains. P1, with semantic work evaluated under C2. |
| B2. Repeated words/constraints must not manufacture relevance. | Repeated literal terms contribute once; repeated identical constraints add no score. A stated constraint can still have greater priority than a goal. | Relevance and KE-PQ-002 repeated-constraint regressions. | **Completed for literal repetition; partial for broader instruction dilution.** Different incidental terms can still accumulate matches. | Keep the literal regression. Label instruction/background terms in held-out requests before changing their weighting. P1. |
| B3. Exact chosen library/material scope, with no useful-looking evidence imported from elsewhere. | Earlier local list filtering plus A1 validation and existing library/source request checks. An empty selected library stays empty; the UI prevents dispatch from an empty material selection. | Nine prior cases preserve scope; source-specific/empty/partial preparation and explicit out-of-scope selection tests, now supplemented by adapter/prepared-state rejection tests. | **Partially completed overall; completed for tested explicit boundaries.** The legacy API still interprets `source_ids: []` with no library as unrestricted default scope, rather than an explicit empty selection. Actual creator/contamination runtime records are unavailable for case-level acceptance. | Replay privately with the reported selected IDs. Preserve the current API contract unless a separate explicit all/none distinction is agreed and evaluated; P0 incident / P1 scope semantics. |
| B4. Source diversity must not displace materially stronger evidence. | Remove hard raw quotas and half-best reservation; diversify only equal-relevance candidates after complete admitted-pool consolidation. | Existing stronger-evidence versus 100/70/60-source regression and labeled generic-flood tests. | **Completed for the deterministic policy.** Lexical equality does not prove equally useful research, and the score is not an empirical-quality estimate. | Add human pairwise relevance judgments before changing diversity or evidence-quality policy. P1. |
| B5. Duplicate findings must not dominate or erase distinct/independent member evidence. | Limit complete groups after consolidation; preserve member IDs, quotations and now interpreted fields. Existing conservative similarity/tension rules remain. | Duplicate-flood fixture preserves 46 members and a distinct second result; near-duplicate and exact legacy-equivalence tests; uncertain method/methodology pair stays visible. | **Partially completed.** Some near-duplicates remain separate; similar titles can group non-equivalent findings. Cross-library Find groups remain separate. No bibliographic independence is inferred. | Inspect the actual reported pairs' member provenance before suppressing them. Evaluate false merges and missed overlaps separately; P1. |
| B6. Explain why “Character…” ranked above “Micro-Influencer…” for the real information need. | ID/field/term/score/position/exclusion diagnostics are available without a provider call. | Production scoring is used by the collector and synthetic reports. | **Blocked for the observed pair.** Titles alone do not establish their matched fields, provenance or score contributions, and do not prove which should rank first. | Run private diagnostics on the actual records/request and have a human label applicability. Do not hardcode either topic or winner. P1. |
| B7. Evidence transparency: references, material records, independent studies, preparation and claim support are different. | UI uses reference/material counts and word-match language. Exact applied/section citations are separate. Ask and research synthesis expose verified preparation and retained coverage plus generic limits. | Existing coverage, rendering, citation and save/export tests. | **Partially completed.** Counts and readiness are addressed; claim-specific applicability/empirical strength and question-dimension gaps are not. New live coverage is not persisted in old saved records. | Keep provenance wording. Define claim/dimension acceptance under C1/C3/C5; do not equate a generic caveat with adequate synthesis. P1/P2. |
| B8. Related Ideas must be useful, inspectable and conservatively organized without a speculative taxonomy. | Authoritative backend ordering, matched-word cues, ten-card Find pagination, related consolidated-evidence disclosure and source trails. No added thematic model call. | Frontend/backend member-match, pagination and evidence tests; prior desktop/mobile mocked acceptance. | **Partially completed.** “Related” currently means lexical matches or existing consolidation, not validated conceptual support or question themes. The 50-result cap remains. | Label supporting concepts versus incidental matches in evaluation. Test organization against relevance and provenance errors before adding themes. P1/P2. |
| B9. Preserve query-free Browse, multi-library selection, responsive loading, selection and Create handoff. | Existing browse concurrency/cache/partial failures, selectors, paging and natural Create adapter remain. Back/Forward state bug was fixed in the earlier pass. | Existing frontend/browser handoff and bulk-move regressions; selected materials/assets remain explicit in Create requests. | **Completed for tested interface mechanics; partially completed for knowledge continuity.** Ask uses a different context selection, and transport does not prove use in output. | Retain these regressions; investigate C4 without adding a mandatory workflow. P1. |
| B10. Diagnostics and evaluation must be reproducible, private and honest about weaknesses. | Synthetic fixture and before/after reports, in-memory ID/term explanations and opt-in request text. Current replay construction now binds synthetic assets to its generated synthetic chunk IDs, respecting A1; historical fixture/reports are unchanged. | Nine cases replayable offline; collector privacy tests; explicit unresolved-vocabulary and weak-evidence characterization. | **Completed for deterministic diagnostics; partial for research evaluation breadth.** Original runtime records, sufficient semantic labels and end-to-end answer quality are missing. | Keep characterization separate from acceptance. Extend labeled evidence in C; P1/P2. |

## Current retrieval paths and where a finding can be lost

The earlier report's Stage A map describes the original mechanisms. This table
records the current implementation after the evaluated retrieval changes and this
integrity review; it is not a second retrieval redesign.

| Path | Acquisition, interpretation and ranking | Selection, context and output |
| --- | --- | --- |
| Find matching ideas | Frontend requests the selected library/material batches. Backend local or indexed acquisition stays in each batch's scope; distinct literal terms and bounded field/phrase tie-breakers score assets. | Consolidate all admitted positive matches before the per-request limit; frontend preserves scored order, merges batches, caps at 50 and pages ten cards. Member terms remain visible. No provider call. Checked ideas carry IDs and scope to Create. |
| Browse useful ideas | Query-free per-material inventory, four concurrent frontend loaders, successful-response caching and visible partial failures. | Existing conservative consolidation and type/chapter filters, ten-card paging and Create selection. No query interpretation, relevance claim or provider call. |
| Ask & Explore | A fresh Workshop request scores goal/situation/audience/constraints, counting each term at its strongest request priority once. All active in-scope assets are candidates; single-source Ask can retain representative zero-overlap context. | Consolidate before the default eight-group limit; diversity breaks equal-relevance ties only. Complete member trails enter compact context. Dedicated grounded-answer schema, exact member citation checks and accounting; no semantic dimension-completeness check. |
| Create / research synthesis | Same Workshop retrieval, with explicit selected-idea expansion and no single-source zero-overlap fallback for synthesis. | Selected IDs must survive or preparation rejects. Reviewed server snapshots pin context; provider-context budgets precede one attempt. General artifact schema, applied-member attribution and saved immutable history; no section-level factual-entailment or sufficiency validator. |

The existing core grounding/attribution checks remain distinct from lexical
ranking, source readiness, resource preflight and answer-quality evaluation.

### Available versus unavailable or unused

| Stage | What the code/evidence establishes | Consequence and current status |
| --- | --- | --- |
| Source preparation | Partial/unavailable preparation is represented separately from ready material and zero retained matches. | Unprepared content is unknown. A ready material without a lexical match is not evidence that the research finding does not exist. |
| Candidate retrieval | Token overlap, limited expansions and question/constraint terms determine admission. The vocabulary-changing fixture has available labeled assets but retrieves none. | **Available but not retrieved** is a confirmed lexical failure mode; not “research unavailable.” |
| Selection | Find can show 50 results; Ask performs its own fresh retrieval with limit 8. Ordinary result limits can exclude an admitted candidate. | **Retrieved but not retained** is visible in diagnostics. Explicit selections now reject rather than silently drop; the general relevance limit remains. |
| Consolidation/preparation | Previously, a member's quote/ID could survive while its distinct interpreted statement/application guidance disappeared behind the canonical asset. | **Available but not transported** was reproduced and corrected for new snapshots. Existing saved snapshots cannot be retroactively reconstructed. |
| Capacity preflight | Candidate, preparation and complete provider-context limits return a visible 413 before generation; an over-limit explicit selection returns 409. | **Available but blocked from this execution** is distinct from missing or irrelevant research. No cheaper subset or automatic retry is substituted. Large-scope acceptance remains partial under A6/A7. |
| Ask continuity | `enhancements.js:generateKnowledgeAnswer` sends `asset_ids: []`; Create checkbox selections do not seed its context. “Ask about this idea” configures title/context, not a pinned idea ID. | A Find result is not proof that the same idea reached Ask. This is a continuity gap, not automatically a violation of the current checkbox label “Use in Create.” No new selection semantics were imposed here. |
| Generation | A new fake-provider test receives both curiosity and trust evidence, returns only the curiosity section, and passes grounding validation. Both assets are present in the captured provider input; only one is cited/applied. | **Available, supplied, but not represented** is an explicitly reproducible limitation. Grounded individual claims do not establish question-dimension coverage. The fake response characterizes acceptance behavior; it does not validate real model performance. |
| Presentation | Existing structured rendering shows returned sections; it does not add missing question dimensions. Earlier canonical-only Find filtering was fixed. New citation binding is stricter. | No supplied historical capture establishes presentation as the cause of the reported omitted dimensions. Source display defects were demonstrated separately; C1 still needs answer-content labels. |

For a real incident, record these states separately: active asset exists; asset
admitted; group retained; member fields supplied; asset applied; member cited;
dimension represented; dimension explicitly limited. Citation absence alone does
not prove a concept was ignored in prose, and a citation does not prove the
dimension was answered. Human analysis must assess the answer's actual claims.

### Measuring Narrative Engagement: incident-resolution protocol

Keep the original record unchanged and private. Identify the application's
running build/worktree and code revision; uncommitted fixes here do not establish
what code produced an older or hosted result. Collect the actual request and
selected library/source/asset IDs, active asset/source/chunk/job associations,
source evidence text, prepared token/snapshot if still available, compact provider
context or existing logs, raw response or saved output, exact citation IDs, and
the displayed/exported result. Collect existing records only; no new generation.

Check, in order:

1. Was foreign material already present in the active asset or source/chunk/job
   associations, or did retrieval widen an otherwise correct scope?
2. Did consolidation misstate canonical/member sources, or did synthesis context
   carry material not represented by its retained members?
3. Did preparation/canonicalization remove the useful interpretation while keeping
   only a generic quote? Did a result limit or explicit selection remove the asset?
4. Did the provider receive the finding, and did the answer use, omit, transfer or
   overgeneralize it? Distinguish source claims from KE reasoning in the actual text.
5. Were the response's exact references correct but the UI/export bound them to
   another source? Was the scope label accurate for the evidence actually supplied?

Until those records are available, **historical root cause and repair are blocked**.
Do not merge/suppress the actual ideas, rewrite old snapshots, or call the reported
finding unavailable merely because its capture is absent from this workspace.

## C. Next research-intelligence phase — evaluation first

No automatic semantic coverage, applicability classifier or sufficiency call is
implemented by this review. The following are cumulative product requirements,
with measurable next steps rather than promises based on lexical benchmarks.

| ID / original product concern | Current implementation/protection | Evidence and remaining gap | Classification | Minimal next action and measurable acceptance / priority |
| --- | --- | --- | --- | --- |
| C1. Answers should address the question's central dimensions, not just produce individually grounded claims. | Natural question reaches the provider; gap/applicability/open-question sections are permitted. There is no dimension inventory or completeness validator. | The available-but-unused fake-provider case passes today. Actual creator-answer dimension coverage is not captured here. | **Unresolved.** | Build an analyst-labeled set of central/optional dimensions and claim-to-evidence mappings for existing outputs, including creator questions and held-out domains. Require every central dimension to be addressed with valid support or an explicit, accurate limitation; separately count available-but-overlooked dimensions. No critical omission may be disguised as unavailable research. P2, without new provider calls. |
| C2. Semantic relevance should survive meaningful vocabulary changes and distinguish direct context from transfer. | Lexical breadth, evidence search and transparent matches; no semantic claim. | A paraphrase using narratives/information gaps/online personalities/followers still misses both labeled findings. Speeches, business writing and creator evidence may share words. | **Unresolved.** | Add held-out paraphrases, direct/transferable/incidental human labels and pairwise rankings. Report recall@8, precision@5 and large generic-pool competition separately by label. Investigate an approach only after the failure set and cost policy are reviewed. P2. |
| C3. Evidence fidelity should distinguish research findings, practitioner advice, case examples, transferred principles, KE interpretation and unsupported generalization. | Source/member provenance, separated extracted interpretation/quote fields, dedicated Ask reasoning kinds, generator design choices and conservative grounding checks. | Asset type/confidence/citation count cannot establish empirical category or causal support. The provider labels are not semantically verified. | **Partially completed.** | Human-label claims using source passages, setting, method and limitation. Require zero unsupported causal/generalized research claims in the reviewed set, and trace every factual claim to an appropriate member. Do not infer study independence or category from the KnowledgeAsset discriminator. P2. |
| C4. Discovery → interrogation → application should preserve useful knowledge without manual reconstruction. | Create selections, exact reviewed snapshots and member transport; A3/A5 correct loss and omission during preparation. | Ask re-retrieves eight groups and ignores Create checkboxes; preserved input can still go unused. No validated shared-context continuity model exists. | **Partially completed.** | Trace the same labeled asset through Find/Browse, Ask-about-idea, selection, Create, output and revision. Require 100% explicit-selection preservation or visible rejection, plus human-judged dimension use. Review whether the existing idea action should pin, seed or merely contextualize evidence before changing behavior; no mandatory new form. P2. |
| C5. Research sufficiency must distinguish missing evidence from unused available evidence at the affected question/claim. | Empty evidence blocks dispatch; preparation/source/retained/applied/cited counts and generic uncertainty are explicit. Weak-only evidence still permits generation. | No entailment, semantic sufficiency or dimension-specific absence check; comprehensive research is not validated. | **Partially completed.** | Evaluate with four distinct conditions: unprepared/unknown, prepared but finding absent, available but unretrieved, supplied but omitted. Require accurate affected-dimension limitations; count false “not available” and false completeness statements separately. Lexical scores/counts are never acceptance evidence for sufficiency. P2. |
| C6. Related/supporting concepts and conservative organization should help understanding and practical decisions. | Paged ranked results, canonical summaries, member trails and existing conservative grouping. | No reliable topic-theme synthesis, concept-role explanation or validated applicability organization; cross-library overlaps remain. | **Deferred for implementation; unresolved as acceptance.** | Label why a supporting concept contributes to a question or decision. Evaluate false equivalence, missed distinct findings and navigation effort. Prototype a small presentation only if it preserves provenance and works without additional model calls or hardcoded topics. P2. |

## Proposed resolution order and release gates

1. **P0 — actual incident and source closure:** retain the new rejection tests;
   inspect the private Measuring Narrative Engagement chain. Do not equate its
   absence here with absent research or conclude the reported incident is fixed.
2. **P0 — capacity:** review the provisional budgets on representative existing
   scopes; bound indexed acquisition with explicit overflow instead of silently
   limiting candidates; profile concurrent/adversarial workloads. Verify that
   existing scope controls provide an understandable recovery path. No provider
   call is needed for this work.
3. **P0 — preservation and final regressions:** exact member attribution,
   no-provider-on-rejection, unchanged saved parents, and no dropped selected or
   transported member evidence. Review the complete uncommitted diff before any
   commit; deployment remains unauthorized.
4. **P1 — current acceptance:** replay actual creator questions with ID-only
   diagnostics and human relevance labels, including actual UI constraints, near
   duplicates and large generic competition. Keep current lexical improvements.
5. **P2 — research intelligence:** conduct C1–C6's human-labeled evaluations on
   existing data. Choose the smallest supported next change. Do not add a semantic
   classifier, new AI call, broad redesign or compulsory workflow to make a
   coverage checklist appear complete.

### Targeted verification and change provenance

New backend regressions are `test_ke_pq_002_integrity_review.py` and
`test_ke_pq_002_capacity.py`. They cover local/indexed adapter isolation, all
prepared source representations, known source/chunk association, member identity,
explicit selection, noncanonical interpretation transport, a deliberately
omitting fake response, request/context/cache byte limits, and immutable revision
failure. New renderer tests cover unknown-prefix attribution and foreign member
evidence. None consumes Gemini quota.

Existing fixtures were corrected rather than validators weakened: multi-source
accounting fixtures explicitly select both intended materials; the output-format
test registers its fake material; an inconsistent prepared-scope test now expects
an earlier pre-provider 409, with zero fake calls, instead of waiting for a broad
claim rejection after dispatch. The existing exact-member/broad-claim assertions
remain in other valid-scope tests. The synthetic replay builder binds assets to
its generated chunk IDs without changing the retained fixture or historical
reports. Saved artifacts and the earlier implementation report remain untouched.

### Final verification — 2026-10-21

| Check | Actual result and practical limit |
| --- | --- |
| Focused retrieval, integrity, capacity, coverage, grounding and snapshot regressions | **110 passed, 0 failed** before the final missing-material revision guard. |
| Final focused integrity/capacity, saved-artifact, revision, accounting and Create regressions | **71 passed, 0 failed** after that guard. These focused runs overlap; their counts are not added together. |
| Complete backend suite after all production changes | **1,224 passed, 0 failed**, two existing dependency deprecation warnings, 53.20 seconds. Includes the existing bulk-library-move and candidate-execution tests; no frozen-commit exception or excluded failure was needed. |
| Complete frontend suite | **207 passed, 0 failed**, no skipped tests. Includes the two new citation-binding regressions. |
| Relevance browser acceptance | **2 viewport groups passed**, desktop and mobile: exact three-library scope, scored ordering, member evidence, paging, partial Browse, selection/Create handoff and navigation. Zero runtime errors or generation requests. |
| Existing bulk-move browser acceptance | Desktop and mobile passed: preview, partial failure, retained selection, retry, refreshed old/destination listings, no overflow/runtime errors. The tracked script and its tests are unchanged. |
| Synthetic nine-case replay | All nine retain the prior report's result IDs, member IDs, Workshop selections and scope results. The four supported creator variants still retain **8/8** direct-finding appearances (original baseline **4/8**); the vocabulary-changing case still retains **0/2**. This review makes no new relevance-improvement claim. |
| Preservation | All 26 review-start files remain present. Twenty are byte-identical; six received the targeted service/fixture/replay extensions described above. The original baseline README, earlier implementation report and all three retained fixture/report files are byte-identical to review start. Staging is empty; original checkout is clean. |

Reproduce the automated checks from repository root:

```sh
.venv/bin/python -m pytest apps/api/tests/test_ke_pq_002_integrity_review.py apps/api/tests/test_ke_pq_002_capacity.py -q
.venv/bin/python -m pytest apps/api/tests -q -o faulthandler_timeout=30
node --test apps/web/tests/*.test.mjs
.venv/bin/python scripts/diagnose_relevance.py --output /tmp/ke-pq-002-relevance.json
```

The browser command and dependency setup remain in the earlier implementation
report. Current private validation logs/screenshots are outside the repository at
`/workspace/ke-pq-002-validation/traceability-*`; no private research was added to
Git. All provider behavior in tests uses fake clients or `httpx.MockTransport`;
loopback/socket permission was used for local application tests only. **Zero real
Gemini calls, $0 provider spend, no hosted writes, migrations, commit, push or
deployment.** Passing regressions establish the listed safeguards, not completion
of A2, A6/A7 or C1–C6.

### Files affected by this review

This list describes changes since the review-start manifest, not every earlier
uncommitted file visible in `git status`:

- `apps/api/app/services/evidence_safety.py` (new): source/member/context closure,
  known-manifest checks, availability check and explicit resource preflight.
- `knowledge_extraction.py`, `workshop.py`, `workshop_generation.py` in that
  directory: adapter checks, selection retention, member interpretation transport,
  provider-context validation and defensive copying.
- `prepared_evidence.py`, `outputs.py` in that directory: snapshot byte budget and
  validated, non-mutating AI revision.
- `apps/web/answer-renderer.js` and its test: exact source binding and unverified
  foreign/unknown references.
- New `test_ke_pq_002_integrity_review.py`, `test_ke_pq_002_capacity.py`; targeted
  existing fixture corrections in `test_product_quality_ke_pq_002.py`,
  `test_research_scope_coverage.py`, `test_knowledge_questions_and_output_modes.py`;
  synthetic lifecycle binding in `scripts/diagnose_relevance.py`.
- This traceability review. Earlier retrieval/UI implementation files, strict
  KnowledgeAsset models, core evidence-accounting/grounding services, bulk-move
  code/tests and historical evidence artifacts are preserved.

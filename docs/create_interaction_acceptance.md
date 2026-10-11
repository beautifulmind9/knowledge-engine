# Create interaction slice — reconciliation and acceptance

Status: core Create interaction accepted after external visual review. Final scoped polish is ready for the pre-commit report; no commit or push performed. Real-provider output usefulness remains untested in this review. Home and Library were not refined in these passes.

## Accepted interaction and final polish — 2026-10-11

The accepted flow remains natural request → Continue → concise editable understanding + current knowledge → Create. The unchanged original request is authoritative; visual confirmation surfaces consequential structure and decisions without restating every nuance. Coverage and relevance remain factual signals, with no synthetic adequacy/sufficiency score.

Final polish only:

- The CTA uses the confirmed output format when available, otherwise the existing supported mode label; saving behavior is unchanged. No separate label mapping was added.
- Search scope replaces the Knowledge disclosure label, including inherited scope.
- Source coverage replaces Source preparation; normal Create wording is sections ready and Partial coverage.
- At widths up to 600px, the initial preview shows two ideas with View all X ideas / Show fewer ideas. Every idea remains inspectable and in the unchanged prepared snapshot. Desktop still shows all ideas. The Create action follows coverage without a sticky CTA.
- Uses the knowledge shown above replaces the operational drafting-attempt helper. Provider-attempt details remain in Advanced; error, quota and pause feedback remain intact.

Validation: **80 frontend tests passed; 838 backend tests passed** (three existing dependency warnings); **10 synthetic browser scenarios passed**, zero runtime errors, zero real Gemini calls. The multi-idea mobile scenario checks bounded presentation, expansion without requests or draft revisions, and generation against the complete prepared snapshot; desktop checks all ideas remain visible. The professional, creative mobile and coverage screenshots were regenerated and visually inspected. Review artifacts remain ignored under outputs/create-review/ and are excluded from the proposed commit.

## Create refinement — 2026-10-11

Doctrine: **Capture naturally. Structure invisibly. Confirm visually.**

- Continue replaces Review & find ideas. The original request collapses unchanged after this intentional transition. Default confirmation is a concise intent summary, populated consequential instructions, knowledge scope, and actual relevant knowledge. Result surfaces when unresolved or deliberately changed; existing controls remain available through Adjust details. Empty optional editors are hidden until explicitly added. Developer/manual JSON import is nested inside Advanced.
- The local interpreter picks a substantive action clause rather than a leading material instruction. No arbitrary default output family is assigned: vague or conflicting specific result families require a local choice. Negative result instructions cannot select the forbidden family or format. Unrecognized prose remains intact; this is conservative phrase recognition, not semantic understanding.
- Across your library means eligible prepared knowledge, with narrower inherited scope retained. Material selection uses native labeled checkboxes inside a fieldset, with no modifier keys. The list stays open across selections.
- Preparation returns contributing source titles, relevant-unit counts, and completed/total source sections from the real interpretation summary when available. Unknown coverage is explicitly unavailable. Relevance and source preparation are distinct; no semantic adequacy assertion is made from counts. Preview includes idea statements and optional source evidence.
- Create uses the exact server-owned prepared evidence snapshot. Transport metadata binds a snapshot reference to the complete preparation payload and InteractionDraft revision. The browser checks its prepared revision and evidence identity; the server rejects changed briefs/revisions, forged/missing/expired references and removed materials before provider access. Generation does not re-retrieve for InteractionDraft requests, and saved knowledge equals reviewed knowledge. Existing non-InteractionDraft API clients retain their prior retrieval semantics.
- Server snapshots use the existing application's single-process execution model: bounded to 128 entries, 30-minute expiry, deep copies, and no durable storage. Restart/expiry/eviction requires Update knowledge, never silent retrieval. This is a fail-closed availability limitation, not a durable/multi-worker preview service.
- Typing invalidates evidence without a request. Committed detail/scope edits refresh deterministic preparation; pending stale successes/errors are ignored. Update knowledge appears only when needed. Create follows current relevance/coverage and is unavailable while stale or empty. Explicit provider attempts, CSRF/auth/quota, strict generation validation and no automatic retry/repair/fallback remain intact.

Validation: **78 frontend tests passed; 838 backend tests passed** (three existing dependency warnings). **Nine rendered browser scenarios passed**, with zero runtime errors and zero real Gemini calls. Browser and backend TestClient execution required running outside the restricted sandbox after sandbox startup failures. Screenshots are synthetic fixtures, not real generated-output acceptance. `/tmp/ke-create-review/` is reproduced by `scripts/test_create_browser.cjs`; ignored copies are at `outputs/create-review/`. `10-coverage-current-knowledge.png` includes contributing source names, partial coverage, relevant idea content and the final Create action.

Actions counted from an open Create screen (focus/scroll excluded; text operations and Tab-to-commit counted separately):

| Journey | Sequence | Actions |
| --- | --- | --- |
| Ordinary detailed request | Enter → Continue → Create | 3: two clicks, one text operation |
| One populated-detail correction | Enter → Continue → Adjust details → edit → Tab to commit/auto-prepare → Create | 6: three clicks, two text operations, one key action |
| Ambiguous scope, deliberate global choice | Enter → Continue → Search across your library/auto-prepare → Create | 4: three clicks, one text operation |
| Changed original request | Enter → Continue → open original request → edit → Continue → Create | 6: four clicks, two text operations |

UX assessment accepted by the user: the default no longer presents a form to audit; Adjust details remains an explicit form for exceptions. A concise confirmation need not repeat every nuance because the unchanged original request remains authoritative. Coverage remains factual progress, never proof of adequacy. The final scoped polish above bounds multi-idea mobile previews without changing evidence or correction behavior. Real provider output quality remains untested by design.

## Historical first-slice record

The following records the earlier implementation and its review; refinement decisions above supersede its preview/retrieval and presentation behavior.

## Authoritative baseline (2026-10-09)

The actual Codespaces tree on `feature/knowledge-assets` was accessible. After fetching, HEAD and `origin/feature/knowledge-assets` both pointed to `b1e67be50b5f57d858f2677a5d3f4b3aeef3d9db`. Newer UI work was uncommitted: ten tracked modified files (113 insertions, 78 deletions) and four untracked frontend files. There were no staged changes. `test_source.txt` was absent from the reported tree; it was not read, modified, deleted, staged or committed.

A backup of those fourteen existing local paths was saved as `/tmp/ke-before-interaction.tar.gz`, explicitly excluding any file named `test_source.txt`. No reset, checkout, stash or replacement from the remote implementation was performed.

Existing behavior retained:

| Area | Verified local behavior |
| --- | --- |
| Home | Three task actions; Add opens the existing Library Add form |
| Navigation | Home/Library/Create/My work/Settings, hash routes, material/output detail routes, Back/Forward, refresh routing and malformed-route fallback |
| Create state | Brief fields, format and creator direction restored across supported tab navigation; no request text in URLs/storage; no durable unsaved refresh promise |
| Result | Output families, separate output-format preference, generation/save and advanced manual import |
| Creator authority | Creative intent, creator context, preserve and avoid |
| Scope and ideas | Library/material subset bounds search and browse; chosen idea IDs pass through; scope changes clear incompatible selections |
| Async safety | View revisions block delayed view append/navigation; preparation preview revisions protect scope changes; detached format decoration ignored |
| Saved work | Artifact first, evidence, review, versions, compare, export and manual/AI revisions |

Baseline tests: `node --test --test-isolation=none apps/web/tests/*.test.mjs` — **51 passed, 0 failed**. `.venv/bin/python -m pytest apps/api/tests -q` — **834 passed, 3 existing dependency deprecation warnings, 50.97s**.

Home, Library and Create were rendered from the current local modules in Chromium with synthetic API data before editing. Screenshots: `/tmp/ke-before-home.png`, `/tmp/ke-before-library.png`, `/tmp/ke-before-create.png`. No browser runtime errors occurred. Create visibly opened with the old Situation/Goal/Audience/Constraints/Tone form; that presentation was the main change needed.

The external Interaction Review was not in the repository. The user's implementation prompt and subsequent review decisions, together with this local tree, are the authority.

## Implementation and architectural decisions

- Create opens with one natural request, kept exactly in `InteractionDraft.originalRequest`. The local interpreter retains the whole request in the execution context, including details it cannot extract. A task summary never replaces the request.
- `InteractionDraft` is separate presentation state: revision, interpreted request identity, intended task/context/goal/result/format, audience, constraints/style, creator direction, scope, provenance and resolution, clarification, confirmation snapshot and prepared evidence identity.
- `workshopRequest` is the single Create adapter for prepare, generate and manual import. Reviewed corrections win over subsequent inference. The saved situation retains the original wording and an explicitly authoritative correction block. Domain/backend models are unchanged.
- Complete, unique material/library names can resolve against application data. Partial, duplicate, excluded or otherwise unresolved material scope asks for a local choice. Unknown IDs cannot enter execution through the adapter. Idea IDs come from application selections, never prose/model output; backend validation remains authoritative.
- Interpretation is conservative and deterministic, not rich semantic AI interpretation. No provider call occurs on review, typing (including Enter in an editor), navigation, correction, format/scope changes or retrieval. Only deliberate Create button activation invokes generation; implicit form submission is blocked. Clear clauses, preserve/avoid directions, labeled context and supported result/format phrases are exposed; unrecognized instructions remain in the original execution context. All materials is a visible starting scope when no direction is given.
- “Review & find ideas” combines local understanding and deterministic preparation. “Create & save” confirms the displayed draft and calls existing generation once. There is no extra mandatory approve screen or conversation wizard. Rich Gemini interpretation was not added; its failure/retry path is therefore not claimed as tested.
- Material edits invalidate confirmation and prepared knowledge. Delayed success **and error** responses cannot restore stale evidence, redirect an edited draft, or reopen a departed view. Manual save uses the same stale-result guard. A request already accepted by the server may still save its output; My work remains its recovery location.
- Generation retrieves against the current reviewed brief again. Preview identity protects browser state; it is not a backend lock on library contents. Corrections do not trigger hidden re-preparation. Unsaved text/corrections remain in memory within the tab, not across full refresh.
- Existing source/chunk evidence, confidence, consolidation, strict validation, applied-knowledge references, creator sovereignty, output formats, idea selection, authentication, CSRF, usage/quota and recovery controls are retained. The backend provider pipeline, one-chunk isolation, one-attempt rules, no repair/retry/paid fallback and atomic valid-knowledge replacement rules were not changed.

## Files changed for this slice

Existing local changes in navigation, shell, knowledge browser and output revision were retained. These are the files edited/added for this implementation, rather than a list of every pre-existing dirty path:

| Files | Purpose |
| --- | --- |
| `apps/web/interaction-draft.js` | Presentation model, conservative interpretation, scope resolution, single adapter, confirmation/evidence identities |
| `apps/web/app.js` | Natural Create, editable understanding, selective clarification, preparation/generation/manual-save integration and stale-state protection |
| `apps/web/enhancements.js` | Remove format payload reconstruction; preserve knowledge-question handoff into natural Create |
| `apps/web/creator-direction.js` | Remove runtime fetch wrapper/decoration from Create; retain pure direction helpers and legacy decorator code |
| `apps/web/api.js`, `apps/web/style.css`, `apps/web/README.md` | Transport documentation, bounded Create styling and usage documentation |
| `apps/web/tests/interaction-draft.test.mjs`, `apps/web/tests/task-navigation.test.mjs`, `apps/web/tests/api.test.mjs` | Model/adapter, navigation/state/races, no hidden calls and consolidated transport coverage |
| `apps/api/tests/test_knowledge_questions_and_output_modes.py` | Move obsolete static format-wrapper assertion to frontend behavioral adapter coverage; retain existing shortcut tests |
| `apps/api/tests/test_create_interaction.py` | Actual adapter → strict API preparation → mocked one-attempt generation → saved provenance integration |
| `scripts/test_create_browser.cjs` | Reproducible deterministic rendered browser scenarios, desktop/mobile screenshots |
| `docs/product_vision.md`, `docs/interface_strategy.md`, `docs/architecture.md` | Doctrine, bounded interaction architecture and future learning/application vision |
| `docs/real_product_migration_plan.md` | Mark Streamlit migration text as historical context |
| `docs/create_interaction_acceptance.md` | This reconciliation, acceptance evidence and remaining questions |

## Verification

Final behavior checks:

- Frontend: `node --test --test-isolation=none apps/web/tests/*.test.mjs` — **70 passed, 0 failed**.
- Backend: `.venv/bin/python -m pytest apps/api/tests -q -o faulthandler_timeout=30` — **834 passed, 3 existing warnings, 57.00s**. The old format-wrapper test moved into behavioral frontend coverage, and the new saved-output integration test replaces its backend count.
- New integration test independently: `.venv/bin/python -m pytest apps/api/tests/test_create_interaction.py -q` — **1 passed, 3 warnings, 1.11s**, with isolated storage and a mocked gateway. Some targeted TestClient starts stalled inside the restricted sandbox and were interrupted; the independent test passed outside the sandbox. The complete backend suite passed inside it.
- Rendered browser: **8 scenarios passed**, including partial coverage and mobile fit, with **zero runtime errors** and mocked API/provider results.
- `git diff --check`: clean after whitespace fixes.
- **Real Gemini calls: 0.** No real source interpretation, generation, repair, retry or fallback was used for testing.

Tests cover exact detailed capture, negation, preserve/avoid, deliberately cleared/user-corrected values, optional missing context, unique/ambiguous/partial/duplicate/excluded material names, unknown IDs, task/constraint/scope evidence invalidation, stale success/error responses, navigation restoration, existing output format and idea behavior, zero provider requests on local actions, one generation request per explicit action and no automatic retries. Existing backend security/provider/provenance regressions pass.

Browser reproduction (Playwright/Chromium are temporary tooling installed outside project dependencies):

```bash
PLAYWRIGHT_BROWSERS_PATH=/tmp/ke-browser/browsers \
KNOWLEDGE_ENGINE_PLAYWRIGHT=/tmp/ke-browser/node_modules/playwright \
node scripts/test_create_browser.cjs
```

Screenshots are under `/tmp/ke-create-review/`; the script regenerates them. They contain synthetic examples only.

## Human-review scenarios and walkthrough

These scenarios were exercised and their rendered desktop/mobile screenshots inspected during implementation. They are **not independent end-user acceptance** and do not establish the quality of a real generated artifact.

| Scenario | Observed behavior / human-review focus |
| --- | --- |
| Vague one-sentence request | Suggested result and visible all-material scope; no optional interrogation. Check whether the default result is useful enough. |
| Detailed professional brief | Original multiline wording retained, task/result/constraints visible, audience exposed when supplied. Inspect inference on more varied professional prose. |
| Creative request | Preserve/avoid and direction remain visible; edited preserve survives navigation and reaches generation. Check that the actual output honors creator judgement. |
| Ambiguous material selection | Local question opens material controls; no retrieval/provider call until a deliberate choice. Check wording and discoverability of selecting several materials. |
| Partial coverage | Limitations appear with retrieved ideas; saved work retains evidence and separate design choices. Check whether gaps are clear enough before spending a generation attempt. |
| Interpretation failure | Empty/whitespace request produces a local error, retains text and makes no request. There is no rich-provider interpretation in this slice. |
| Request edited while pending | Earlier preparation result is ignored and the newer text remains; stale generation success/errors are also covered in DOM integration tests. |
| Preparation/generation failure | Request and corrections remain; no retry, repair or fallback occurs automatically. |

Walkthrough: open Create → write naturally → Review & find ideas → inspect “Here’s what I understood” and relevant ideas → correct only consequential items, with a local material question if needed → Create & save. Create records confirmation state and invokes the rigorous pipeline; saved work opens with the artifact, expandable evidence and separate design choices. Editing an understood item does not require a repeated approval ceremony.

## Remaining UX questions and next slice

1. Conservative phrase extraction does not semantically understand arbitrary prose. Are intact-request grounding plus visible suggestions sufficient, or does observed use justify an explicit one-attempt richer interpretation action? Do not add it merely to satisfy optional fields.
2. How much constraint/direction detail helps users confirm faithfully without feeling repetitive? The original request is intentionally still visible.
3. Is “All materials” the right visible starting scope? How clearly do partial coverage and the material selector explain what will ground a result?
4. Does the combined review/retrieval action feel natural on repeated requests? Confirmation should remain draft state, not another wizard.
5. Generation refreshes retrieval; if users need an exact reviewed evidence set later, a server-owned evidence identity would require a separate design decision.

Next: independently review these Create scenarios with representative real briefs and prepared knowledge, then validate useful saved outputs under explicit provider-call controls if needed. Refine the Create interaction based on that evidence before beginning another UI slice. Home/Library natural capture and the longer-term **read → understand → interrogate → compare → apply → specify → build/test → reflect** environment are not started here. This vision grows from validated knowledge architecture and does not replace it with generic chat.

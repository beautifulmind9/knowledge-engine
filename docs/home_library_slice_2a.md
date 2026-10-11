# Home and Library entry — Slice 2A

Doctrine: **Capture naturally. Structure invisibly. Confirm visually.**

Home captures one exact request and offers explicit Ask & Explore / Create choices. It does not classify, interpret execution fields, retrieve or invoke AI. Empty requests open exploration or resume Create. Add and saved-work shortcuts remain secondary. Recent-work previews and attention summaries are not added in this slice.

Library exposes Ask & Explore with its current library scope. Source exploration retains its narrower scope. The canonical exploration route is `#/library/explore`; the previous `#/create/ideas` route remains a picker-compatible alias. Library is highlighted while exploring, including during Create's idea-picker visit.

New requests enter Create's unchanged natural capture and Continue flow. A meaningful existing Create draft is protected by a local Use new request / Keep current draft choice. Source-only handoffs are also protected. Keeping resumes the original request, scope, corrections and current prepared snapshot. Replacing creates a fresh InteractionDraft only after the explicit decision. The Create picker returns selections and compatible scope without replacing the request. Main navigation resumes Create's own scope, rather than silently adopting a different Library browsing scope.

Home uses the existing InteractionDraft capture model. Exploration has ordinary view state for its single request, context, filters, pagination, selections, deterministic results and completed answer. Editing the request updates the request passed by Use selected ideas; Open in Create from an answer carries that answer's original question/context. No second interpretation or execution model is introduced.

Browser history stores an opaque entry number and the existing scope URL. Route objects and request/result state remain in memory. Back/Forward restores each exploration visit independently, including distinct queries at the same scope. Full refresh retains routes/scope but loses unsaved requests and answers. Late responses cannot update a departed view; restoring a completed answer makes no provider call.

All existing question shortcuts, chapter/idea checks, deterministic search, browsing, filters, pagination, evidence and deliberate selections remain. Explicit questions continue through the existing guarded AI endpoint, without automatic retry/repair/fallback. Chapter context remains prose context, not a hard chapter-only retrieval boundary. One natural request serves both Find ideas (deterministic) and Ask with AI (explicit generation). Try a question contains compact suggestions that only populate/configure the request. Add context is closed by default; section/example prompts reveal only applicable controls. Source & evidence uses material names without raw-ID fallbacks. Home destinations have equal visual emphasis.

## Boundary

No source-add redesign, default-library creation, new source states, recovery redesign, coverage endpoint, background processing, new ingestion mode or longer-term learning features. No backend or prepared-evidence implementation changes. Create compatibility edits are limited to protected handoffs, resume scope and the picker return flag.

## Verification and visual review

- Frontend: `node --test --test-isolation=none apps/web/tests/*.test.mjs`.
- Backend: `.venv/bin/python -m pytest apps/api/tests -q -o faulthandler_timeout=30`.
- Create browser regression: `scripts/test_create_browser.cjs`.
- Slice 2A browser acceptance/screenshots: `scripts/test_home_library_browser.cjs`.

Final validation: **90 frontend tests passed; 838 backend tests passed** with three existing dependency warnings; **10 Create browser scenarios and five Slice 2A acceptance groups passed**. `git diff --check` is clean.

Browser scripts use synthetic API data and no real Gemini calls. Screenshot outputs default to `/tmp/ke-home-library-2a-refined`; ignored review copies are under `outputs/home-library-review-2a-refined/`. Human visual acceptance remains pending; no commit is authorized yet.

Actions below count entering text as one operation and each click/activation as one, excluding focus and scroll:

| Journey | Actions |
| --- | --- |
| Empty Home → Ask & Explore | 1 |
| Home request → Ask & Explore | 2 |
| Home request → deterministic results | 3 |
| Home request → explicit AI answer | 3 |
| Home request → Create capture | 2 |
| Home request → Continue → final Create | 4 |
| Same journey with existing-draft choice | 5 |
| Library → Ask & Explore | 1 |
| Existing results → select one idea → Use in Create | 2; 3 with a draft choice |
| Confirmed Create → open Search scope → Choose ideas → select one → return | 4 |

Remaining concerns: browsing and searched results still have separate result areas; the handoff reads “Use this scope in Create” with zero selections and “Use selected ideas in Create” otherwise, retaining both handoff behaviors. Chapter/section context guides grounding but is not exclusive. Full refresh loses unsaved view state. Source statuses and first-add organization remain intentionally reserved for 2B.

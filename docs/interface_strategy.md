# Interface Strategy

## Governing interaction doctrine

> Capture naturally. Structure invisibly. Confirm visually. Knowledge Engine accepts a person's request or source material in a natural form, organizes what it can responsibly infer, and exposes consequential interpretations for correction before execution. The system carries the structure; the user carries the intent.

The interaction contract is **natural capture → interpreted draft → visual confirmation → targeted clarification where necessary → existing rigorous execution**. Confirmation is state on a draft, not necessarily a separate approval screen. Natural capture must not become compulsory chat or a long question sequence.

- Ask only for missing or uncertain information that materially affects retrieval, reasoning or the result.
- Preserve explicit user direction. User corrections override later inference.
- Use visible defaults where they matter.
- Reveal complexity progressively; use configuration by exception.
- Make uncertainty visible.
- Keep backend/schema terminology out of the normal interface unless it genuinely benefits the user.
- Backend rigor and frontend simplicity reinforce each other.
- Source knowledge expands choices; it does not override creator judgement.
- Never confuse precedent with prescription.

Interpret quietly when confidence is high and consequence low; show material interpretations even when confidence is high. Ask locally when uncertainty has material consequences. Leave nonessential missing information unset, or show a useful default. Preserve explicit input unless deliberately corrected.

## Active interface and reconciled baseline

The active interface is the browser application in `apps/web`, served by FastAPI. It already supports Home, Library, Create, My work and Settings, browser history, material preparation/recovery, scoped idea selection, saved outputs and revisions. Streamlit validated the early extraction/retrieval/workshop workflow; its archived implementation in `legacy/streamlit_prototype` is historical reference, not the current UI or a migration still to be performed.

The October 9, 2026 reconciliation used the actual uncommitted Codespaces tree, not just GitHub. Existing Home/navigation/draft behavior is retained. See [Create slice acceptance](create_interaction_acceptance.md) for the baseline, implementation boundaries, verification and remaining review.

## First implementation slice: Create

Start with a natural request. Keep the request exactly, including details the interpreter does not recognize. Present a compact, editable understanding with a proposed result, consequential constraints, creator direction and knowledge scope. Other context is available by exception; optional backend fields are not questions to complete.

An `InteractionDraft` is presentation state separate from strict domain models. It tracks revisions, original wording, value provenance/resolution, clarification, confirmation snapshots and prepared-evidence identity. One adapter maps the reviewed state into existing Workshop requests. Source/library matches resolve against current application data, never model-generated IDs.

The first slice uses conservative local interpretation, with **zero provider calls**. “Continue” combines local interpretation and deterministic retrieval. Confirmation shows one concise intent summary, populated consequential instructions and knowledge scope; optional fields live under Adjust details. “Create & save” confirms the displayed draft and makes one explicit generation attempt through the existing pipeline. Corrections invalidate prior preparation; committed local edits refresh it without a provider call. Generation uses the exact reviewed server-owned evidence snapshot, bound to the current InteractionDraft revision. Global scope is “Across your library”: relevant prepared knowledge, never a claim of complete source interpretation. Contributing source preparation counts are shown separately from relevance counts. There is no mandatory extra approve step. Rich language interpretation remains future work and would need a clearly explicit action, at most one provider attempt, and no repair/retry/fallback.

Unsaved requests and corrections survive supported navigation within a tab; they are not durable across full refresh. Hash routes carry scope, never request text. Delayed preparation/generation results cannot restore older drafts or redirect a user who has moved on. A generation already accepted by the server may still save its result; My work remains the place to find it.

This slice does not implement the interaction redesign across Home, Library or the whole application. Automated checks and synthetic browser scenarios do not establish real-output usefulness; human acceptance remains required.

## Longer-term learning and application vision

**Read → understand → interrogate → compare → apply → specify → build/test → reflect**

This grows from validated knowledge assets, evidence, consolidation, retrieval and saved outputs. It does not replace Knowledge Engine with generic chat. Future views may help users read, ask grounded questions, examine differences, apply learning, specify an artifact and reflect on its use. They must continue to distinguish evidence from generated choices and preserve creator authority.

This is product direction, not this MVP's implementation scope. It does not authorize agents, autonomous research, a semantic knowledge graph, requirements-management software, experiment tracking, paid infrastructure or a framework migration.

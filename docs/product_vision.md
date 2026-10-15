# Product Vision

## Product definition

**Knowledge Engine transforms source material into structured, reusable knowledge assets that can be connected, retrieved, and assembled into useful outputs.**

Short form: **Knowledge in. Useful outputs out.**

## Interaction doctrine

> Capture naturally. Structure invisibly. Confirm visually. Knowledge Engine accepts a person's request or source material in a natural form, organizes what it can responsibly infer, and exposes consequential interpretations for correction before execution. The system carries the structure; the user carries the intent.

The contract is **natural capture → interpreted draft → visual confirmation → targeted clarification where necessary → existing rigorous execution**. Confirmation is draft state, not a mandatory wizard. Ask only about unresolved material uncertainty; preserve explicit direction and corrections; show consequential defaults; reveal complexity progressively and configure by exception. Backend rigor and frontend simplicity reinforce each other. The normal interface should express intent and useful results rather than internal schema terminology. Source knowledge expands choices; it does not override creator judgement. Never confuse precedent with prescription.

See [Interface Strategy](interface_strategy.md) for the governing interaction rules and Create direction.

## What the product is for

People often read books, reports, articles, notes, and research but struggle to retrieve the right idea later and apply it to a real task. Knowledge Engine is designed to reduce that gap between consuming information and using it.

The product is not primarily a summarizer or a chat-with-PDF tool. It creates a reusable knowledge layer that can support writing, decisions, study, planning, messaging, playbooks, workshops, content creation, research synthesis, presentations, and other practical outputs.

The product should make a user better able to answer:

- What does this material actually teach?
- What matters for the problem I am working on?
- Where do sources agree, differ, or operate at different levels?
- What assumptions does an idea depend on?
- What should I apply, test, reject, or adapt?
- What evidence would change my decision?

A useful answer is not merely fluent. It should improve the user's understanding of the decision landscape while preserving source traceability and uncertainty.

## Core product model

```text
Private Library
↓
Sources
↓
Chunks
↓
Validated Knowledge Assets
↓
Consolidated Knowledge Units
↓
Retrieval / Selection
↓
Knowledge Exploration + Create / Knowledge Workshop
↓
Saved Outputs + Revisions
```

Knowledge Assets retain source and chunk provenance, evidence, retrieval keywords, confidence, and type-specific structure. Current asset types include concepts, problems, principles, insights, decision rules, patterns, examples, warnings, frameworks, mental models, and processes.

## Knowledge exploration

Knowledge Engine must support grounded questions about one source, a chapter or section, selected Knowledge Units, or a broader library. These are first-class product behaviors, not incidental prompt examples.

Core questions include:

- What does this source teach?
- What concepts appear in this source?
- What problems does this source help solve?
- What did this chapter teach?
- What examples support this idea?
- What decision rules can I apply?
- Ask my knowledge — a free-form grounded question across the selected scope.

Knowledge-answer retrieval should use asset type and chapter/section provenance when available. Broad source questions must still return a representative grounded set rather than failing only because the question has few lexical matches. Multi-source reasoning should distinguish materials selected, evidence actually represented, and sources actually cited; it must not imply corpus-wide coverage when the evidence set is narrower.

## Workshop output families

Create/Workshop turns retrieved knowledge into ready-to-use artifacts. Current output families are:

- Writing / editing
- Knowledge answer / synthesis
- Research / synthesis brief
- Decision brief
- Study guide
- Content / social media
- Product messaging
- Playbook / process
- Action plan
- Presentation / talking points
- Workshop / facilitation plan

Output families may expose a more specific format where useful. Content / social media currently supports LinkedIn posts, Instagram captions, carousels, short-form video scripts, threads, long-form articles, and content ideas. Presentation output supports slide outlines, speaker talking points, or both.

The format is a shape/channel preference. It should not alter which knowledge is considered relevant to the user's actual subject or problem.

## Workshop creative sovereignty

When Workshop supports creative work, knowledge should expand the creator's options rather than optimize them toward generic best practice.

The creator remains the authority over the work. Their visual language, personality, memories, cultural context, taste, preferences, instincts, and meaningful imperfections should carry more weight than generalized conventions.

Workshop should explain what a creative choice may communicate, why it may work, what alternatives exist, and what trade-offs those alternatives create. It should not decide what the creator's creativity should look like.

The core rule is: **never confuse precedent with prescription.**

Creative recommendations should emerge from the intersection of source knowledge, creator knowledge, and project intent. Source knowledge alone is not sufficient authority for a creative recommendation.

A corresponding design question is: **What here should not be improved away?**

See `docs/workshop_creative_sovereignty.md` for the full product principle and guidance requirements.

## Main workflow

1. Add material to a private library.
2. Save it safely, extract its text and chunk it while preserving useful section hints where possible.
3. Interpret each chunk independently into structured Knowledge Assets.
4. Validate the result locally before storing or superseding existing assets.
5. Search, browse, or ask grounded questions across one source or a library.
6. Consolidate overlapping raw assets into Knowledge Units while preserving evidence trails.
7. Use a natural Create request or selected knowledge to produce a useful grounded output.
8. Save, revise, compare, and export outputs with provenance.
9. Reflect on what worked, what remained uncertain, and what should be tested next.

## AI role

AI is used as an interpretation and generation layer, not as the system of record.

For source interpretation, each chunk is sent to Gemini independently. Chunks do not share model context. Returned provider structure is adapted where necessary and then validated against strict internal Pydantic models before it can become active knowledge.

For Knowledge answers and Create/Workshop generation, the model receives the task brief plus retrieved knowledge and must distinguish source-grounded claims from generated choices. Saved records retain the applied Knowledge Asset references.

AI latency and availability are product constraints. The system should expose useful progress and recover safely rather than pretending provider work is instantaneous.

## Reliability rules

The current architecture deliberately favors isolation, auditability and recovery over provider-call efficiency:

- one source chunk per Gemini extraction request;
- no shared multi-chunk model context;
- no automatic semantic retries, repair calls, model fallbacks or prompt mutation;
- a user-authorized operation may make one additional **identical** provider attempt for an explicitly transient HTTP 503, for at most two provider attempts total;
- each provider attempt is separately allowance-gated and counted;
- HTTP 400, 429, validation failures, timeouts and uncertain transport outcomes are not automatically retried;
- strict local schema validation before replacement;
- failed replacements do not supersede good active assets;
- completed material progress survives later failures;
- hosted optimistic state conflicts are reconciled only when independent JSON changes can be merged safely; overlapping changes fail closed;
- persistence reconciliation never repeats Gemini, extraction, uploads or other external side effects;
- source deletion commits logical state before artifact cleanup so a failed state save cannot leave a live record pointing to a missing file;
- local/hosted daily call caps preserve the zero-cost operating rule.

Shared-context multi-chunk extraction was tested and produced under-extraction and cross-chunk provenance leakage. Gemini's asynchronous Batch API is not used because it is not available on the current Gemini Developer API free tier used by the project.

## Current interface

The active product is a FastAPI application with a browser interface in `apps/web`, supporting both local single-owner use and a private hosted beta. The earlier Streamlit implementation is archived under `legacy/streamlit_prototype` and is no longer active.

The browser supports Library/material management, uploads, deterministic reading/chunking, foreground Gemini preparation, knowledge browsing and search, grounded Ask & Explore flows, natural-language Create, evidence-aware generation, saved outputs, revisions, comparison, export, quota controls, audit views and data backup.

Material preparation remains foreground/tab-owned rather than a durable background job system. That is an accepted current limitation, not the long-term interaction goal.

## Current validation state

The original real-source extraction/audit acceptance remains complete for *The Workshop Survival Guide*: 46/46 chunks, 121 active Knowledge Assets, zero missing evidence, zero missing keywords, and 13 evidence-review items retained as a manual review queue rather than known defects.

Real-output acceptance has also covered Workshop Plan, Decision Brief, Study Guide and Research / Synthesis, including manual revision and a meaningful two-source comparison. Grounding checks remain conservative review signals rather than semantic certification.

The latest hosted reliability checkpoint additionally closed two production failures:

- **Hosted concurrency:** while one book was actively preparing, another book was added successfully; both materials survived and the first book retained its saved progress without the stale-revision failure.
- **Transient Gemini 503:** a real first-attempt HTTP 503 recovered through the bounded identical second attempt while Render health remained 200; interpretation completed and preparation continued.

The reliability implementation checkpoint reported **950 backend tests passed** and **172 frontend tests passed** before production acceptance.

The remaining product question is no longer whether these incident paths work. It is whether Knowledge Engine is useful enough, fast enough and understandable enough for a real user to prefer it for serious knowledge work.

## Performance as a product requirement

Large-book addition/preparation and some Library rendering are currently too slow for the intended experience. This is now a first-class beta usability concern.

Do not assume the solution is simply paid infrastructure. Current latency may come from multiple boundaries: upload, PDF extraction, chunk count, serial provider calls, provider 503/latency, validation, progressive persistence, summary aggregation, browser rendering, and Render free-instance cold starts/compute.

The next technical step is measurement before optimization. See [Performance plan](performance_plan.md). Performance work must preserve provenance, chunk isolation, validation and safe recovery.

## Long-term learning and application vision

**Read → understand → interrogate → compare → apply → specify → build/test → reflect**

This learning and application environment grows from the existing validated knowledge architecture: traceable knowledge assets, consolidated units, source evidence, retrieval, grounded application and saved work. It does not replace Knowledge Engine with generic chat or treat every task as a fresh unstructured conversation.

The sequence preserves future space for deeper reading, interrogation, comparison, application, specification, practical verification and reflection. It is not an expansion of the current MVP by default. Near-term work should prove the value of the existing loop, characterize performance, and close external beta acceptance before broadening the product.

Richer organization, retrieval and future account infrastructure remain possible when justified by product needs. Source-backed claims must remain distinct from generated choices, and creator judgement remains authoritative.

# Personal research release — September 11, 2026

## Finish line used for this implementation

A local, single-owner workflow from uploaded sources to reviewed knowledge and a saved, editable, exportable workshop output. The prior prototype's manual ChatGPT handoff is preserved explicitly.

## Implemented

- Durable SQLite records for libraries, sources, knowledge units, and workshops.
- Responsive Library / Knowledge / Workshop browser interface served by the existing FastAPI application.
- Upload and text extraction for PDF, EPUB, Word, TXT, Markdown, CSV, JSON, and HTML.
- Real process endpoint, with chunking, processing feedback, empty-file errors, and limits.
- Passage-specific extraction prompts with a structured output contract.
- Atomic result import, chunk ownership validation, quote matching, exact-import deduplication, and human approval/rejection.
- Search across knowledge and explicit selection of approved units from multiple sources.
- Workshop evidence briefs, separate AI drafting prompts, editable output, save, Markdown export, and deletion.
- Stable data paths, timestamps, and source deletion controls that preserve workshop traceability.
- Working root launch instructions; original Streamlit prototype preserved separately.

## Acceptance check

Upload original research notes → process → export prompt → supply a structured response → import → approve → select → create workshop → edit → save → export → restart and recover saved work.

The automated test uses a synthetic, explicitly authored extraction response. It does not claim that an AI model produced that response. API and file extraction tests pass; browser visual QA and hosted deployment have not been performed.

## Remaining before an automated, hosted product is finished

1. Decide the AI provider/model and add server-side extraction and synthesis with credentials, usage limits, retries, and evaluations. Current handoffs are manual.
2. Add accounts, authorization, tenant isolation, and private object storage before remote/multiuser access.
3. Add background processing, bounded document parsing, cancellation, and recovery for large sources.
4. Add semantic retrieval and evaluated synthesis if keyword search plus explicit selection is insufficient.
5. Design a verified migration for existing legacy graph data; nothing from the legacy graph has been silently imported.
6. Choose and configure hosting for the Python backend and durable storage. No hosted deployment was made in this change.
7. Run browser QA and the complete user acceptance flow with the owner's own source and real AI response.

This is a reviewable first personal workflow implementation, not a claim that the entire long-term roadmap or an automated SaaS product is complete.

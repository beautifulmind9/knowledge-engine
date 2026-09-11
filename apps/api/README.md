# Knowledge Engine API

Single-owner, local FastAPI application with a same-origin browser workspace.
Run it from the repository root (Python 3.11+):

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn app.main:app --app-dir apps/api --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000. `/docs` documents the API (the strict application CSP may prevent the CDN-based Swagger interface; `/openapi.json` is available).

State and uploaded files persist in `apps/api/storage/`, independent of the launch directory.
Override that directory with `KNOWLEDGE_ENGINE_STORAGE`. Back up the complete directory with the server stopped. No source material is seeded into the new workspace.

This release is **local and single owner**, without accounts or tenant isolation. Do not bind it to a public interface or deploy it as a multiuser app. Source extraction runs synchronously, with a 25 MB upload limit. PDF extraction needs an embedded text layer; OCR and encrypted documents are not supported.

## Workflow

1. Create a library and upload a source.
2. Process the source to extract text and prepare passages.
3. Copy a passage's extraction prompt into your AI assistant.
4. Paste the JSON response into the source workspace. Every unit must cite an existing chunk and contain a matching evidence quote.
5. Review each unit in Knowledge. Evidence matching verifies the quote, **not** whether an inference is correct.
6. Select approved units, including units from different sources, and create a workshop.
7. The workshop assembles an evidence brief. Edit directly, or copy the workshop prompt to an AI assistant and paste its draft into the editor.
8. Save and export the output as Markdown.

AI is a **manual handoff** in this release. No API key is requested, no AI call is made by the application, and evidence briefs are deterministic assemblies rather than generated answers. The user chooses what source text to share with their AI provider.

Exact repeated imports are idempotent and preserve review state. All units in a batch are validated before any are saved. Workshops snapshot approved evidence so later review changes do not silently rewrite saved work. A source used by a workshop cannot be deleted until that workshop is deleted. Uploaded files cannot be replaced in place; add a new source for a revision.

## Validation

```bash
pip install -r apps/api/requirements-dev.txt
PYTHONPATH=apps/api python -m pytest apps/api/tests -q
node --check apps/web/app.js
```

Tests cover the complete API workflow, restart persistence, evidence validation and batch atomicity, duplicate imports, review gating, editing/export/deletion, file extraction, chunk coverage, static assets, and cross-origin mutation rejection. They do not constitute browser interaction or live AI testing.

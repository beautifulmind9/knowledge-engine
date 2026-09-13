# Knowledge Engine

Knowledge Engine turns source material into reusable, traceable knowledge and applies it to real work: writing, decisions, study guides, product messaging, playbooks, and workshop plans.

The active application is a **local, single-owner FastAPI application with a browser interface**. Source text becomes chunks, validated Knowledge Assets, consolidated Knowledge Units, and saved outputs with revision history. The original Streamlit experiment is archived in `legacy/streamlit_prototype`; it is not the active app.

## Run locally

Requires Python 3.11+ on macOS or Linux. Windows users can use WSL. From the repository root:

```bash
bash scripts/setup.sh
bash scripts/run.sh
```

Open http://127.0.0.1:8000. The same process serves both the API and web interface; Node and a frontend build are unnecessary. Interactive API documentation is at `/docs`.

To verify the build:

```bash
.venv/bin/python -m pytest apps/api/tests -q
```

Setup installs the tested versions in `apps/api/requirements-lock.txt`. The tests use isolated temporary data and fake provider responses. They never consume an AI quota. The SDK contract test uses the installed Google SDK against an in-memory HTTP transport.

## Try it without an AI key

With the app running, in another terminal:

```bash
.venv/bin/python scripts/seed_demo.py
```

Refresh the Library screen and choose **Knowledge Engine — synthetic demo**. It contains two original sample sources, manually imported knowledge, and a saved playbook with two versions. Open Knowledge to inspect evidence; open Workshop to preview retrieval across both sources; open Saved outputs to revise or export the playbook. Re-running the seed command leaves an existing demo unchanged.

The demo is explicitly synthetic and manually authored. It does not pretend to be a model response. See [the beta test checklist](docs/beta_test_checklist.md) for the full acceptance exercise.

## Use Gemini within the zero-cost rule

Copy `.env.example` to `.env` and add your own `GEMINI_API_KEY`. Set `GEMINI_FREE_TIER_CONFIRMED=true` only after checking that the key belongs to a project with billing disabled. The application cannot inspect your billing configuration.

- No automatic paid upgrade or paid-model fallback.
- Each extraction or generation request makes at most one provider attempt; the default local budget is 20 attempts per UTC day.
- A quota error pauses further AI calls until you explicitly resume under **Data & usage**. Resuming cannot bypass the local daily cap.
- Interpretation processes one chunk per browser action; the API supports batches of at most five.
- A revision is either a manual edit with no provider call or one explicit AI request.
- `GEMINI_MODEL` can override the configured model. Availability and free quota must be checked in your own project; no live-provider validation was performed for this implementation pass.

When you choose an AI action, the relevant source chunk or retrieved evidence and brief are sent to Google. Requests set `store=false` for interaction retrieval; this is not a guarantee about all provider logging or retention policies. Manual imports and the seeded demo do not send source content to an AI provider.

## Main workflow

1. Create or select a library and add a supported file.
2. Open its source page and choose **Extract & chunk**.
3. Interpret small batches with Gemini, or download a structured prompt and import your result.
4. Inspect the source audit, search consolidated knowledge, and select useful units.
5. Enter a Workshop brief, preview the evidence and possible source tensions, then generate and save.
6. Reopen saved work, make a new revision, compare versions, or export Markdown.
7. Use Data & usage for quota state, integrity checks, and a private backup.

Supported uploads: PDF with selectable text, EPUB, DOCX, TXT, Markdown, HTML, CSV, and JSON, up to 25 MB. Scanned PDFs need OCR, which is not implemented. Markdown, HTML, EPUB and DOCX headings are retained as section hints. EPUB follows spine reading order; DOCX preserves paragraph/table order. PDF chapter inference remains limited.

## Architecture and storage

| Location | Responsibility |
|---|---|
| `apps/api/app` | API, extraction, retrieval, generation, persistence and controls |
| `apps/web` | Dependency-free browser UI and API client |
| `apps/api/tests` | API, error-path, SDK contract, backup and restart regression tests |
| `examples` | Original, synthetic, public-safe source material |
| `scripts` | Setup, local launcher and no-API demo seed |
| `docs` | Roadmap, item-level sprint status, storage decision and beta checklist |

Records persist as a transactionally replaced SQLite snapshot. Uploads, extracted text, and chunks live alongside it in `apps/api/storage`, or at the absolute `KNOWLEDGE_ENGINE_STORAGE` path you configure. A first launch migrates legacy `state.json` without modifying that original file. Corrupt state stops loading rather than silently replacing data.

Run exactly one server worker. A process lock prevents simultaneous servers using the same storage, and requests are serialized. This simple arrangement is suitable for a small local beta; long AI requests can temporarily delay other actions. The app has local host/origin restrictions but no user accounts, multi-user authorization, encryption at rest, or public hosting support. Keep it bound to localhost.

Back up under Data & usage. The ZIP includes private source files and saved work; keep it private. Restore into a **new empty directory**, set `KNOWLEDGE_ENGINE_STORAGE` to the extracted storage folder, and start the server. Do not overwrite a live SQLite database. See [storage and privacy](docs/storage_and_privacy.md).

## Readiness

The implementation covers all eight remaining sprint areas. **The full v1 beta acceptance gates are not yet closed.** Live Gemini output review, the complete real-book run and quality audit, browser/mobile acceptance, and an external tester remain outstanding. Lexical agreement/tension flags and structural output checks assist review; they do not establish semantic correctness.

- [Item-level sprint status](docs/sprint_status.md)
- [Original remaining sprint backlog](docs/remaining_sprint_backlog.md)
- [Release decision and test checklist](docs/beta_test_checklist.md)

MIT License. Process only sources you have the right to use. Keep copyrighted uploads, extracted source text, private backups, and API keys out of commits.

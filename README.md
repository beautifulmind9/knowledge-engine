# Knowledge Engine

**Created by Taneen Lewis · © 2026 Taneen Lewis. All rights reserved.**

**Knowledge Engine transforms source material into structured, reusable knowledge assets that can be connected, retrieved, and assembled into useful outputs.**

Short form: **Knowledge in. Useful outputs out.**

Knowledge Engine is proprietary software. Access to this repository does not grant permission to copy, modify, distribute, host, commercialize, or create derivative works from the proprietary code or materials. See [LICENSE](LICENSE).

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
- Each extraction or generation request makes at most one provider attempt. For the verified local free-tier project using Gemini 3.1 Flash Lite, AI Studio showed a 500 requests/day provider limit; Knowledge Engine keeps a conservative default local guardrail of **450 attempts per provider day**, aligned with Gemini's midnight Pacific RPD reset. Override `GEMINI_DAILY_CALL_LIMIT` only after checking the limits on your own project.
- A quota error pauses further AI calls until you explicitly resume under **Data & usage**. Resuming cannot bypass the local daily cap.
- Browser interpretation processes one chunk per action. The API can orchestrate up to ten chunks in one explicit run, but each chunk uses its own normal Gemini request and never shares source text with another chunk.
- Shared-context multi-chunk extraction is intentionally not used in production because live probes showed under-extraction and cross-chunk evidence leakage.
- Gemini's asynchronous Batch API is not used because the current Gemini Developer API free tier does not include Batch processing.
- A revision is either a manual edit with no provider call or one explicit AI request.
- `GEMINI_MODEL` can override the configured model. Availability and free quota must be checked in your own project; no paid provider feature is required by the application.

When you choose an AI action, the relevant source chunk or retrieved evidence and brief are sent to Google. Requests set `store=false` for interaction retrieval; this is not a guarantee about all provider logging or retention policies. Manual imports and the seeded demo do not send source content to an AI provider.

## Main workflow

1. Create or select a library and add a supported file.
2. Open its source page and choose **Extract & chunk**.
3. Interpret chunks with Gemini using independent one-chunk requests, or download a structured prompt and import your result.
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
| `docs` | Architecture, product vision, sprint status, storage decisions and beta acceptance |

Records persist as a transactionally replaced SQLite snapshot. Uploads, extracted text, and chunks live alongside it in `apps/api/storage`, or at the absolute `KNOWLEDGE_ENGINE_STORAGE` path you configure. A first launch migrates legacy `state.json` without modifying that original file. Corrupt state stops loading rather than silently replacing data.

Run exactly one server worker. A process lock prevents simultaneous servers using the same storage, and requests are serialized. This simple arrangement is suitable for a small local beta; long AI requests can temporarily delay other actions. The app has local host/origin restrictions but no user accounts, multi-user authorization, encryption at rest, or public hosting support. Keep it bound to localhost.

Back up under Data & usage. The ZIP includes private source files and saved work; keep it private. Restore into a **new empty directory**, set `KNOWLEDGE_ENGINE_STORAGE` to the extracted storage folder, and start the server. Do not overwrite a live SQLite database. See [storage and privacy](docs/storage_and_privacy.md).

## Current validation snapshot

The real *Workshop Survival Guide* source is complete at **46/46 chunks**. The latest active set contains **121 Knowledge Assets**, with **0 missing evidence**, **0 missing keywords**, and **13 evidence-review items** retained as a manual review queue rather than known defects. The confidence distribution is 83 assets at 5 and 38 at 3.

A live strict single-chunk control returned the expected five valid assets for chunk 007. A known compound crowd-recovery asset was repaired deterministically so `Talking in circles` and `Borrowing goodwill` are now separate atomic assets with correct chunk provenance.

Shared grounding review is currently at **report version 8**. The latest local backend suite is **205 passed** with two unchanged upstream deprecation warnings. Real-provider A2 acceptance covered Workshop Plan, Decision Brief, Study Guide, and Research / Synthesis, including a same-task two-source comparison.

For that two-source acceptance exercise, *Made to Stick* was intentionally interpreted only far enough to provide a legitimate second current-pipeline source: **10 of 91 chunks**, yielding **38 active assets / 35 consolidated Knowledge Units**. This is acceptance-scope evidence, not a claim that the full source has been interpreted or audited.

## Readiness

The implementation covers all eight remaining sprint areas. Real-source extraction/audit acceptance and **Acceptance Sprint A2 (real-model output and multi-source quality) are complete**. **The full v1 beta acceptance gates are still not closed.** Remaining material gates are A3 release-readiness work:

- fresh-machine/local setup acceptance;
- completion of the remaining desktop happy-path checks from a clean state;
- remaining error-state checks, including quota pause and any still-unverified stale/failed-job behavior;
- one external tester completing the core workflow;
- resolution or explicit deferral of critical defects followed by the final v1 beta decision.

A narrow mobile-width pass and the core keyboard workflow have already been exercised internally; they are not substitutes for the external-user acceptance gate.

Lexical agreement/tension flags and structural output checks assist review; they do not establish semantic correctness.

Workshop quality reports check top-level agenda timings and exclude nested notes and later sections. Component durations are reconciled, and differing practice/role-play timings across sections are flagged for review. Malformed timestamps require review; saved outputs can be rechecked without a Gemini call. See [timing validation](docs/workshop_timing_validation.md).

- [Product vision](docs/product_vision.md)
- [Architecture](docs/architecture.md)
- [Item-level sprint status](docs/sprint_status.md)
- [Release acceptance backlog](docs/release_acceptance_backlog.md)
- [Release decision and test checklist](docs/beta_test_checklist.md)
- [Original remaining sprint backlog](docs/remaining_sprint_backlog.md)

## Ownership and licensing

Knowledge Engine was created by **Taneen Lewis**. © 2026 Taneen Lewis. All rights reserved.

The proprietary project is not offered under an open-source license. No permission to use, copy, modify, distribute, host, sublicense, sell, commercially exploit, or create derivative works from the proprietary code or materials is granted except by prior written permission. Third-party dependencies remain subject to their own licenses and terms. See [LICENSE](LICENSE).

Process only sources you have the right to use. Keep copyrighted uploads, extracted source text, private backups, and API keys out of commits.

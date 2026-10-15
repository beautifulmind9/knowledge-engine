# Knowledge Engine

**Created by Taneen Lewis · © 2026 Taneen Lewis. All rights reserved.**

**Knowledge Engine transforms source material into structured, reusable knowledge assets that can be connected, retrieved, and assembled into useful outputs.**

Short form: **Knowledge in. Useful outputs out.**

Knowledge Engine is proprietary software. Access to this repository does not grant permission to copy, modify, distribute, host, commercialize, or create derivative works from the proprietary code or materials. See [LICENSE](LICENSE).

The active application is a **single-owner FastAPI application with a browser interface**. It supports local storage and a private hosted beta using Supabase persistence. Source text becomes chunks, validated Knowledge Assets, consolidated Knowledge Units, and saved outputs with revision history. The original Streamlit experiment is archived in `legacy/streamlit_prototype`; it is not the active app.

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

Setup installs the tested versions in `apps/api/requirements-lock.txt`. Automated tests use isolated temporary data and fake provider responses unless a test explicitly says otherwise; the normal suite does not consume Gemini quota.

## Try it without an AI key

With the app running, in another terminal:

```bash
.venv/bin/python scripts/seed_demo.py
```

Refresh the Library screen and choose **Knowledge Engine — synthetic demo**. It contains two original sample sources, manually imported knowledge, and saved work. The demo is explicitly synthetic and manually authored; it does not pretend to be a model response.

See [the beta test checklist](docs/beta_test_checklist.md) for current acceptance status.

## Use Gemini within the zero-cost rule

Copy `.env.example` to `.env` and add your own `GEMINI_API_KEY`. Set `GEMINI_FREE_TIER_CONFIRMED=true` only after checking that the key belongs to a project with billing disabled. The application cannot independently inspect billing configuration.

Current provider rules:

- No automatic paid upgrade or paid-model fallback.
- One source chunk is sent per extraction request; chunks never share model context.
- No automatic semantic repair call, prompt mutation, or model fallback.
- A confirmed Gemini HTTP 503 may receive **one additional identical attempt**, for at most two provider attempts total.
- Every actual provider attempt is separately allowance-gated and counted.
- HTTP 400, 429, validation failures, timeouts and uncertain transport outcomes are not automatically retried.
- A quota error pauses further AI work until the user explicitly resumes within the permitted cap.
- Gemini's asynchronous Batch API is not used because it is not available on the Developer API free tier used by this project.
- A revision is either a manual edit with no provider call or one explicit AI request.

Shared-context multi-chunk extraction is intentionally not used because live probes showed under-extraction and cross-chunk provenance leakage.

When an AI action is chosen, the relevant source chunk or retrieved evidence and brief are sent to Google. Manual imports and the seeded demo do not send source content to an AI provider.

## Main workflow

1. Create or select a library and add supported material.
2. KE safely saves and deterministically reads/chunks the material.
3. Eligible material is prepared through independent one-chunk Gemini interpretation requests.
4. Inspect, search, browse, or ask grounded questions across the resulting knowledge.
5. Use Create / Workshop to turn a natural request plus relevant knowledge into a grounded output.
6. Save, revise, compare, and export the result with provenance.
7. Use Data & usage for quota state, integrity checks, and private backup.

Supported uploads: PDF with selectable text, EPUB, DOCX, TXT, Markdown, HTML, CSV, and JSON, up to **50,000,000 bytes per file**. Scanned PDFs need OCR, which is not implemented. Markdown, HTML, EPUB and DOCX headings are retained as section hints. PDF chapter inference remains limited.

## Architecture and storage

| Location | Responsibility |
|---|---|
| `apps/api/app` | API, extraction, retrieval, generation, persistence and controls |
| `apps/web` | Browser UI and API client |
| `apps/api/tests` | API, persistence, error-path, quota and regression tests |
| `examples` | Original synthetic public-safe source material |
| `scripts` | Setup, local launcher, browser acceptance and demo tooling |
| `docs` | Product vision, architecture, acceptance, performance and operating decisions |

In local mode, records persist as a transactionally replaced SQLite snapshot. Uploads, extracted text and chunks live under the configured private storage root.

Hosted mode uses **Supabase Postgres + private Supabase Storage**. Whole-workspace state snapshots use optimistic revision protection. When independent hosted writes race, KE can conservatively rebase and retry the **state save only**; persistence reconciliation does not rerun Gemini, extraction, upload, artifact publication or allowance admission. Overlapping changes fail closed rather than silently choosing a winner.

Source deletion persists the logical deletion before artifact cleanup. If state persistence fails, artifacts are left untouched. If cleanup fails after a durable logical deletion, the source remains deleted and an orphaned private artifact may remain for later housekeeping rather than restoring a broken source record.

See [Architecture](docs/architecture.md) for the full persistence and reconciliation rules.

## Hosted beta status

The private Render beta is live using Supabase persistence and the shared-password beta gate. The latest reliability implementation checkpoint on `feature/knowledge-assets` closed the material lifecycle and concurrent hosted-state failures at:

- `656406e878a73d910aa2fd1f03abec20374bdf55` — material add/delete lifecycle safety
- `87b38de4c041bf9707339dabc8c34d882f47d9b5` — concurrent hosted-state reconciliation

Hosted production acceptance subsequently confirmed:

- one book can continue preparing while another book is added without the prior stale-revision failure;
- both books and previously saved preparation progress survive;
- a real first-attempt Gemini HTTP 503 can recover through the one permitted identical retry while Render remains healthy;
- preparation continues after that successful retry.

A later real multi-book ingestion run confirmed an important remaining lifecycle limitation: **material durability is stronger than preparation autonomy**. Multiple books can be safely saved/read and completed parts remain committed, but AI preparation is still foreground and serial. A Render deployment/restart during the run stopped the active dispatcher while preserving already saved records and completed knowledge. Some healthy books reached **Ready** while other healthy books remained partially prepared until explicitly continued. That state is not, by itself, evidence that the material failed.

The current product should therefore distinguish **Ready**, **Partially prepared / Continue preparing**, and genuine **Needs attention** states. KE does not yet provide a durable background ingestion queue; whether that becomes a pre-MVP requirement depends on measured multi-book usability rather than on data-loss risk.

The implementation checkpoint reported **950 backend tests passed** and **172 frontend tests passed** before production acceptance.

## Current product status

Real-source extraction acceptance is complete for *The Workshop Survival Guide* at **46/46 chunks** with **121 active Knowledge Assets**, zero missing evidence, zero missing keywords, and 13 manual evidence-review items retained rather than classified as known defects.

Real-output acceptance has covered Workshop Plan, Decision Brief, Study Guide and Research / Synthesis, including manual revision and a meaningful two-source comparison. Deterministic grounding checks remain conservative review signals rather than semantic proof.

The private hosted beta is now internally reliable enough to return focus to product value. The remaining v1 beta work is not another extraction rewrite. It is to prove that the knowledge experience is useful, understandable and fast enough for real use.

The current next sequence is:

**measure performance → test knowledge usefulness on a real decision → optimize measured bottlenecks → external tester → final v1 beta decision**

Large-book preparation and some Library/material rendering are currently too slow for the intended experience. Multi-material use also requires explicit continuation after some foreground/process interruptions. Do not assume paid infrastructure alone is the answer; profile upload, extraction, chunking, provider latency/retries, validation, persistence, aggregation, foreground dispatch/recovery and browser rendering first. See [Performance plan](docs/performance_plan.md).

## Current docs

- [Product vision](docs/product_vision.md)
- [Architecture](docs/architecture.md)
- [Automatic material preparation](docs/automatic_material_preparation.md)
- [Performance plan](docs/performance_plan.md)
- [Beta release checklist](docs/beta_test_checklist.md)
- [Release acceptance backlog](docs/release_acceptance_backlog.md)
- [Sprint status](docs/sprint_status.md)

## Ownership and licensing

Knowledge Engine was created by **Taneen Lewis**. © 2026 Taneen Lewis. All rights reserved.

The proprietary project is not offered under an open-source license. No permission to use, copy, modify, distribute, host, sublicense, sell, commercially exploit, or create derivative works from the proprietary code or materials is granted except by prior written permission. Third-party dependencies remain subject to their own licenses and terms. See [LICENSE](LICENSE).

Process only sources you have the right to use. Keep copyrighted uploads, extracted source text, private backups, and API keys out of commits.

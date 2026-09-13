# Knowledge Engine API

Active FastAPI backend; run from the repository root with `bash scripts/run.sh` after `bash scripts/setup.sh`. The same process serves `apps/web` at `/`. Open `/docs` for complete schemas.

| Endpoint family | Capability |
|---|---|
| `/libraries`, `/sources` | Create/list libraries and sources; upload and process files |
| `/sources/{id}/chunks`, `/interpret`, `/audit` | Chunk progress, bounded interpretation and quality audit |
| `/knowledge-extractions` | Validated extraction imports, Gemini execution and stale-job recovery |
| `/knowledge-assets/search` | Raw/consolidated retrieval; optional source and library scope |
| `/workshops/prepare`, `/workshops/generate` | Evidence selection, synthesis context and saved grounded generation |
| `/outputs` | List/filter, manual import, get, revise, history, compare and Markdown export |
| `/usage`, `/usage/resume` | Local daily budget and explicit quota recovery |
| `/data/integrity`, `/data/export` | Integrity checks and private backup |
| `DELETE /sources/{id}`, `/outputs/{id}`, `/libraries/{id}` | Intentional deletion with dependent-history safeguards |

Development tests: `.venv/bin/python -m pytest apps/api/tests -q` from the root. Tests select temporary storage before importing the app. Real-source data is never needed for automated tests.

See the root README and `docs/storage_and_privacy.md` before changing persistence. One worker, loopback only. Do not enable public access without implementing authentication and a suitable storage/concurrency architecture.

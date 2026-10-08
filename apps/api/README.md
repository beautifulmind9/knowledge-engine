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


Hosted persistence selects `PostgresStateStore` and `SupabaseArtifactStore` with
`KNOWLEDGE_ENGINE_PERSISTENCE_MODE=hosted`. Set the required private configuration
in `.env.example` through server environment variables. Storage requires an HTTPS
project URL, an `sb_secret_...` server key, a private bucket, and a workspace key
containing only letters, digits, underscores, and hyphens (starting with a letter
or digit). Missing or invalid configuration fails startup, without a local fallback.

Artifact locators are mapped relative to `STORAGE_ROOT` beneath the workspace key.
Hosted snapshots store root-relative source locators so restarting on another
machine does not depend on the previous storage directory. Existing absolute
locators must be beneath the configured root; outside paths and traversal are
rejected. No directory or server lock is created in hosted mode. Temporary working
files exist only during IO/parser contexts and are removed afterward. Export uses
portable ZIP metadata in hosted mode and preserves filesystem metadata locally.
The bucket reference SQL in `schema/create_knowledge_engine_artifacts_bucket.sql`
is idempotent and private; it defines no public/anon/authenticated access policies.

Hosted source uploads write to a fresh versioned locator. Only a confirmed upload
is published in state, with extracted text/chunks and processing status invalidated.
Superseded objects are cleaned up afterward, best effort. If an upload response is
lost, previously published bytes and derived data remain unchanged; cleanup may
leave a private unreferenced orphan. If state saving fails, the live record is
restored and both object versions are retained: the state commit may have succeeded
before its response was lost. Reload state before continuing after an indeterminate
state save. Cleanup failures after confirmed publication do not undo publication.

Generic hosted `replace()` still overwrites then deletes the source in separate
operations. A failed or lost response may occur after remote mutation; it does not
guarantee the old destination is preserved. Source publication does not use it.
Continue to run exactly one worker/owner: cached application state and
artifact mutations are not designed for concurrent workers. Postgres CAS rejects
stale state writes, but does not serialize artifact operations. The private hosted
beta gate is described below. Render host/proxy compatibility remains a separate
deployment checkpoint.

Storage tests replace the HTTP opener with an in-memory API and deny remote DNS/socket
connections and the real Storage opener before importing the app, including
configuration subprocesses. Target URL checks prevent loopback proxies from
relaying remote requests; inherited proxy configuration is cleared. Loopback is
allowed for the local server smoke test. No live project verification is part of automated tests. The adapter uses the Python
standard library; no new dependency or SDK is required.


Hosted private-beta access requires `KNOWLEDGE_ENGINE_BETA_PASSWORD` and
`KNOWLEDGE_ENGINE_SESSION_SECRET` at startup, before hosted state is loaded. Supply
them through private server environment variables. The signing secret must contain
at least 43 URL-safe characters, with obvious placeholders/repetition rejected;
generate it independently with `secrets.token_urlsafe(32)` (32 random bytes). Use
a long private shared password (maximum 1024 UTF-8 bytes). Local mode is ungated
by default, even if these environment variables are inherited.

Sessions use HMAC-SHA256, signed issuance/expiry times, and a random CSRF value;
they expire after 12 hours. The password is never stored in a token. Session and
CSRF cookies use the `__Host-` prefix, Secure, SameSite=Strict, and Path=/ without
Domain. Only the CSRF cookie is browser-readable. Unsafe authenticated requests
must supply `X-CSRF-Token` matching the signed session. The same-origin check also
compares scheme and authority. Login POST requires a same-origin Origin header.
Anonymous access is limited to GET/HEAD health, GET/HEAD login, POST login, and
GET/HEAD the login stylesheet. Other routes, assets, downloads, backups, and API
documentation are gated. Browser navigation redirects to login; fetch/API requests
receive JSON 401. Login uses an ordinary form under the existing CSP; no inline
scripts are needed. Logout is POST and requires CSRF verification.

Five failed logins impose a global five-minute cooldown using bounded worker
memory. This is a small shared-password gate, not accounts or multi-user auth.
Keep one worker/owner. Global throttling can temporarily block the owner too and
resets on process restart. Logout clears browser cookies; a copied valid token
remains usable until expiry. Rotating either the password or session secret revokes
all existing tokens. A stateful revocation service is deliberately absent.
Render hostname/trusted proxy/HTTPS compatibility is Checkpoint 7; no deployment
settings were changed here. Auth tests inject a gate into the local app without
Postgres/Storage connections. Existing offline network guards remain active.

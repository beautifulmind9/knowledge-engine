# Render private beta configuration

As of 2026-10-08, the private beta is live at
https://knowledge-engine-sb50.onrender.com/ on commit **693511e**. One free
Python web service serves FastAPI and the existing static frontend. It uses
Supabase Postgres for state and the private Supabase Storage bucket for artifacts.
There is no persistent Render disk, paid database, or additional service.

Build from the repository root:

```sh
pip install -r apps/api/requirements-lock.txt
```

Start command: `bash scripts/render_start.sh`. It changes to the repository root
and executes:

```sh
python -m uvicorn app.main:app --app-dir apps/api \
  --host 0.0.0.0 --port "$PORT" --workers 1 --no-proxy-headers
```

`PORT` must be supplied by Render; there is no production default. One worker is
mandatory for cached state ownership, serialized operations, and in-memory login
throttling. The blueprint pins the tested Python 3.14.2 and installs the existing locked
dependencies. No Node/frontend build is needed. Local launch scripts are unchanged.

## Environment checklist

Enter the `sync: false` values privately in Render. The blueprint generates the
session secret and references this service's own external hostname automatically;
neither requires manual entry. No credentials are committed. Both service instances
and application workers are explicitly limited to one.

| Name | Requirement |
|---|---|
| `KNOWLEDGE_ENGINE_PERSISTENCE_MODE` | `hosted` (blueprint default) |
| `KNOWLEDGE_ENGINE_DATABASE_URL` | Private Postgres connection configuration |
| `KNOWLEDGE_ENGINE_WORKSPACE_KEY` | Existing workspace namespace |
| `SUPABASE_URL` | HTTPS Supabase project URL |
| `SUPABASE_SECRET_KEY` | Server-only secret key |
| `KNOWLEDGE_ENGINE_STORAGE_BUCKET` | `knowledge-engine-artifacts` (private) |
| `KNOWLEDGE_ENGINE_BETA_PASSWORD` | Long private shared password |
| `KNOWLEDGE_ENGINE_SESSION_SECRET` | Render-generated base64-encoded 256-bit random value (`generateValue: true`) |
| `KNOWLEDGE_ENGINE_PUBLIC_HOST` | Self-reference to `RENDER_EXTERNAL_HOSTNAME` |
| `PORT` | Automatically supplied by Render |

At the historical 2026-10-08 deployment checkpoint, the live hosted beta had
`GEMINI_DAILY_CALL_LIMIT=20`. The current Render configuration, confirmed
2026-10-15, is `GEMINI_DAILY_CALL_LIMIT=450` provider attempts per Pacific day.
This leaves a deliberate 50-attempt margin below the active 500 RPD Gemini 3.1
Flash Lite AI Studio Free-tier limit, and every actual attempt counts, including
the bounded second attempt after a confirmed 503. The deployment remains
free-tier-only with no paid fallback and a $0 cost target. The blueprint default
remains unconfirmed; AI configuration is not needed at startup. Without a
confirmed free-tier key, AI-required actions return a configuration error
without calling a provider.

## HTTPS, hosts, and health

Hosted ingress must come exclusively through Render's HTTPS edge. The blueprint
supplies the assigned public hostname automatically. Hosted mode permits only
that exact Host authority; ports, duplicate Host headers, alternate hosts, and
wildcards are rejected. Local mode retains its localhost/testserver allowlist.

Uvicorn ignores forwarding headers. After validating Host, the hosted application
uses its fixed HTTPS scheme to reflect TLS termination at Render. It never derives
host, scheme, or client identity from `Forwarded` or `X-Forwarded-*`. Origin checks
therefore require the configured HTTPS origin even if a client supplies spoofed
forwarding headers. This assumes an HTTPS-only public edge; the command is not a
general-purpose launcher for exposing an unprotected HTTP port. Cookies remain
Secure, HttpOnly for sessions, and SameSite=Strict. Redirects use fixed local paths.

`/health` is public and returns only `{"status":"ok"}`. It makes no database,
Storage, or Gemini calls. Startup still validates all required configuration and
loads hosted state; a failed state load prevents startup rather than producing an
empty local fallback. Health reports process health after successful startup,
not a dependency connectivity check.

## Restarts and remaining acceptance

Restarts reload state from Supabase Postgres and artifacts from Supabase Storage.
No local disk recovery is required. Parser/download materialization uses temporary
files cleaned at context exit; ZIP export is buffered in memory. Python caches and
runtime temporary files can be discarded. Sessions survive restart while their
password/secret and expiry remain valid; login throttle memory resets.

The beta access gate and hosted persistence across restart are verified; restart
preserves usage accounting. See the
[release acceptance backlog](release_acceptance_backlog.md#current-release-decision)
for the detailed workflow, call snapshot, and regression evidence. R8-08 is
complete; R8-09 external testing and R8-10 final release decision remain pending.
Free services may sleep or restart; no paid fallback is configured.

## Hosted allowance ledger migration and rollback

The hosted provider-attempt allowance is stored separately from the workspace
snapshot so each admitted attempt does not rewrite the whole workspace. The
legacy `usage` object remains in snapshots as a rollback copy, but after the
versioned migration the ledger is authoritative for hosted admission and
`/usage/status` reads.

Before deploying a build that uses the ledger, quiesce AI use for this
single-user private beta. The app has no durable background worker and this
migration does not add a pause endpoint:

1. The user stops initiating Gemini-backed actions. Wait for any current
   `/interpret`, grounded-answer/Create, or other provider request to finish.
   Do not use the app during the SQL migration and deployment. Health checks and
   ordinary non-AI Render traffic may continue.
2. Keep Gemini-backed actions quiesced through deployment so snapshot-based
   admission and ledger-based admission never run concurrently. Do not use a
   rolling deployment with both code versions serving provider requests.
3. Apply
   [`apps/api/schema/create_knowledge_engine_allowance_ledger.sql`](../apps/api/schema/create_knowledge_engine_allowance_ledger.sql)
   to the existing Supabase Postgres project. It creates additive tables only.
4. Deploy the new build while Gemini-backed actions remain quiesced. Its first
   allowance read, or the migration check before an attempt reservation, seeds
   the ledger from the loaded snapshot `usage` state and records migration
   version 1 in that ledger transaction. Reservation is a separate atomic
   transaction. Initialization verifies Pacific day, admitted count, pause
   state/reason, and last-attempt time; it does not reset the current day's
   count. Later reads never reseed
   an initialized ledger. If a same-day snapshot is ahead of the ledger, the
   app fails closed for allowance admission so a stale cutover cannot undercount.
5. Before allowing AI actions again, inspect the single workspace row in
   `knowledge_engine.allowance_state`. Confirm version 1 and compare
   `accounting_day`, `admitted_attempts`, `paused`, `pause_reason`, and
   `last_attempt_at` with the pre-cutover snapshot backup. Resolve any mismatch
   while AI actions remain quiesced. Then check `/usage/status` and resume use.

For rollback, use the same quiescence procedure: stop new Gemini-backed actions
and wait for any current provider request to finish. Run
`app.services.ai_gateway.copy_allowance_to_legacy_snapshot()` from the deployed
hosted application context (with the normal hosted environment and loaded
workspace state) and confirm its returned day/count/pause/last-attempt values
match the ledger. This performs one ordinary snapshot save. Only after that
save succeeds should the old snapshot-authoritative build be deployed. Do not
use the app during that deployment. Keep the ledger tables intact for
audit/retry; do not clear or reseed them during rollback. If copy-back cannot
be confirmed, keep Gemini-backed actions quiesced rather than reverting to a
potentially stale snapshot. Ordinary health checks and non-AI Render traffic
may continue.
Treat this rollback as a move back to snapshot authority. If the ledger-enabled
build is to be restored later, keep admissions quiesced and add a versioned
reconciliation step that seeds/verifies the ledger from the then-current
snapshot before reopening; simply reusing migration version 1 would retain the
old ledger count.

## Chunk-manifest backfill

The read-path release adds versioned chunk manifests as additive fields in
source state. No SQL or database schema migration is required. Deploy the
compatible code before running the existing-source backfill. Legacy sources
without a recognized valid manifest continue through the existing chunk
artifact read and validation path until backfilled.

Run the backfill from the repository root with application writes idle. The
command defaults to a dry run and does not call Gemini:

```sh
python apps/api/scripts/backfill_chunk_manifests.py
```

Review the reported update and skip counts. Missing, malformed, or inconsistent
artifacts are skipped and reported; the command never invents a manifest for
them. If the dry run is acceptable, apply the valid additions:

```sh
python apps/api/scripts/backfill_chunk_manifests.py --apply
```

The backfill stages validated manifests and persists them using the existing
optimistic-concurrency safeguard. If a concurrency conflict occurs, stop; once
application writes have ceased, rerun the dry run, review the new counts, and
retry the apply. Finish with another dry run and verify it reports zero
remaining updates. No Gemini calls are involved.

For rollback, older code ignores the additive manifest fields. Sources with no
valid recognized manifest continue to use the legacy artifact path, so the
backfill can be left in place when reverting application code.

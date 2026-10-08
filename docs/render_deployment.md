# Render private beta configuration

Configuration is prepared; no service has been created or deployed. One free
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
| `KNOWLEDGE_ENGINE_SESSION_SECRET` | Render-generated random value (`generateValue: true`) |
| `KNOWLEDGE_ENGINE_PUBLIC_HOST` | Self-reference to `RENDER_EXTERNAL_HOSTNAME` |
| `PORT` | Automatically supplied by Render |

For the first deployment, leave `GEMINI_API_KEY` unset and keep
`GEMINI_FREE_TIER_CONFIRMED=false` (blueprint default). AI configuration is not
needed at startup. Manual/non-AI operations remain available; AI-required actions
return a clean configuration error without calling a provider. Existing free-tier
safeguards remain in place. Do not add a Gemini key for this checkpoint.

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

Before the first deployment, review the blueprint in Render, enter the private
`sync: false` environment values, and confirm free-plan/runtime support.
After separately authorizing deployment, verify HTTPS login/cookies, health-check
Host behavior, and persistence across a restart. These live checks have not been
performed here. Free services may sleep or restart; no paid fallback is configured.

#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ "${KNOWLEDGE_ENGINE_PERSISTENCE_MODE:-}" != "hosted" ]]; then
  printf '%s\n' 'Render startup requires hosted persistence mode.' >&2
  exit 1
fi
exec python -m uvicorn app.main:app --app-dir apps/api \
  --host 0.0.0.0 --port "${PORT:?Render PORT must be set}" --workers 1 \
  --no-proxy-headers

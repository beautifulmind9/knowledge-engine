#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 -c 'import sys; assert sys.version_info >= (3, 11), "Python 3.11 or newer is required"'
python3 -m venv .venv
.venv/bin/python -m pip install -r apps/api/requirements-lock.txt
printf '%s\n' 'Setup complete. Run bash scripts/run.sh, then open http://127.0.0.1:8000.'

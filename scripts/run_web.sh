#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [ ! -d web/dist ]; then
  echo "Building frontend..."
  (cd web && npm install && npm run build)
fi

exec .venv/bin/uvicorn api.main:app --host 0.0.0.0 --port 8000

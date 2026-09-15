#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
PORT="${PORT:-8000}"
exec python -m uvicorn backend.app.main:app --host 0.0.0.0 --port "$PORT"

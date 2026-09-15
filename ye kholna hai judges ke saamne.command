#!/usr/bin/env bash
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"
PORT="${PORT:-8000}"
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port "$PORT" > /tmp/prahari-api.log 2>&1 &
PID=$!
sleep 3
if ! kill -0 "$PID" 2>/dev/null; then
  cat /tmp/prahari-api.log
  exit 1
fi
open "http://127.0.0.1:${PORT}"
echo "PRAHARI is running (PID $PID). Keep this terminal open during the demo."
wait "$PID"

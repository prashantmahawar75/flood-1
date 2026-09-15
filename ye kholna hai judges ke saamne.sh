#!/usr/bin/env bash
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"
PORT="${PORT:-8000}"
echo "Starting PRAHARI FastAPI backend on http://127.0.0.1:${PORT} ..."
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port "$PORT" > /tmp/prahari-api.log 2>&1 &
PID=$!
sleep 3
if ! kill -0 "$PID" 2>/dev/null; then
  echo "Backend failed to start. Log: /tmp/prahari-api.log"
  cat /tmp/prahari-api.log
  exit 1
fi
URL="http://127.0.0.1:${PORT}"
if command -v xdg-open >/dev/null 2>&1; then xdg-open "$URL" >/dev/null 2>&1 || true;
elif command -v open >/dev/null 2>&1; then open "$URL";
fi
echo "PRAHARI is running at $URL (PID $PID)."
echo "Stop with: kill $PID"

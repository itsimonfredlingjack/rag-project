#!/usr/bin/env bash
set -euo pipefail

BACKEND_PORT="${BACKEND_PORT:-8900}"
FRONTEND_PORT="${FRONTEND_PORT:-3003}"

echo "Stopping Constitutional AI local demo"

if fuser -k "$BACKEND_PORT/tcp" >/dev/null 2>&1; then
  echo "Stopped backend on port $BACKEND_PORT"
else
  echo "No backend process found on port $BACKEND_PORT"
fi

if fuser -k "$FRONTEND_PORT/tcp" >/dev/null 2>&1; then
  echo "Stopped frontend on port $FRONTEND_PORT"
else
  echo "No frontend process found on port $FRONTEND_PORT"
fi

pkill -f "uvicorn app.main:app" >/dev/null 2>&1 || true
pkill -f "vite.*$FRONTEND_PORT" >/dev/null 2>&1 || true
rm -f logs/backend.pid logs/frontend.pid

echo "Ollama was left running on port 11434. Stop it separately if needed."

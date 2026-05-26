#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

MODEL="${OLLAMA_MODEL:-gemma4:26b}"
BACKEND_PORT="${BACKEND_PORT:-8900}"
FRONTEND_PORT="${FRONTEND_PORT:-3003}"
LOG_DIR="${LOG_DIR:-logs}"
FRONTEND_DIR="apps/konstitutionell-frontend"
BACKEND_PY="backend/.venv/bin/python"

mkdir -p "$LOG_DIR"

echo "Starting Constitutional AI local demo"
echo "Model:    $MODEL via Ollama http://127.0.0.1:11434"
echo "Backend:  http://localhost:$BACKEND_PORT"
echo "Frontend: http://localhost:$FRONTEND_PORT"
echo

if ! command -v ollama >/dev/null 2>&1; then
  echo "ERROR: ollama is not installed or not on PATH"
  exit 1
fi

if [ ! -x "$BACKEND_PY" ]; then
  echo "ERROR: backend virtualenv not found at $BACKEND_PY"
  echo "Run: cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
  exit 1
fi

if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
  echo "ERROR: frontend node_modules missing"
  echo "Run: cd $FRONTEND_DIR && npm ci"
  exit 1
fi

if ! curl -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
  echo "Ollama is not responding; starting ollama serve..."
  setsid env OLLAMA_HOST=127.0.0.1:11434 ollama serve </dev/null > "$LOG_DIR/ollama.log" 2>&1 &
  OLLAMA_PID=$!
  echo "$OLLAMA_PID" > "$LOG_DIR/ollama.pid"
  for _ in {1..30}; do
    if curl -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
      break
    fi
    sleep 1
  done
  if ! curl -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
    echo "ERROR: Ollama did not become ready. See $LOG_DIR/ollama.log"
    kill "$OLLAMA_PID" >/dev/null 2>&1 || true
    exit 1
  fi
else
  echo "Ollama is already running"
fi

if ! curl -fsS http://127.0.0.1:11434/api/tags | grep -q "\"name\":\"$MODEL\""; then
  echo "ERROR: Ollama model '$MODEL' is not installed"
  echo "Available models:"
  ollama list || true
  exit 1
fi

echo "Warming model with a short chat request..."
curl -fsS http://127.0.0.1:11434/api/chat \
  -H "Content-Type: application/json" \
  -d "{\"model\":\"$MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"Svara exakt: OK\"}],\"stream\":false,\"think\":false,\"options\":{\"num_predict\":8,\"temperature\":0}}" \
  >/dev/null

echo "Stopping old backend/frontend processes on ports $BACKEND_PORT and $FRONTEND_PORT..."
fuser -k "$BACKEND_PORT/tcp" >/dev/null 2>&1 || true
fuser -k "$FRONTEND_PORT/tcp" >/dev/null 2>&1 || true
sleep 1

echo "Starting backend..."
setsid bash -c "cd '$SCRIPT_DIR/backend' && exec .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port '$BACKEND_PORT'" </dev/null > "$LOG_DIR/backend.log" 2>&1 &
BACKEND_PID=$!
echo "$BACKEND_PID" > "$LOG_DIR/backend.pid"

for _ in {1..60}; do
  if curl -fsS "http://localhost:$BACKEND_PORT/api/constitutional/health" >/dev/null 2>&1; then
    break
  fi
  if ! kill -0 "$BACKEND_PID" >/dev/null 2>&1; then
    echo "ERROR: backend exited. See $LOG_DIR/backend.log"
    tail -40 "$LOG_DIR/backend.log" || true
    exit 1
  fi
  sleep 1
done

if ! curl -fsS "http://localhost:$BACKEND_PORT/api/constitutional/health" >/dev/null 2>&1; then
  echo "ERROR: backend did not become ready. See $LOG_DIR/backend.log"
  exit 1
fi

echo "Running deep readiness once to warm runtime data checks..."
curl -fsS "http://localhost:$BACKEND_PORT/api/constitutional/ready" >/dev/null 2>&1 || true

echo "Starting frontend..."
setsid bash -c "cd '$SCRIPT_DIR/$FRONTEND_DIR' && exec npm run dev -- --host 127.0.0.1 --port '$FRONTEND_PORT'" </dev/null > "$LOG_DIR/frontend.log" 2>&1 &
FRONTEND_PID=$!
echo "$FRONTEND_PID" > "$LOG_DIR/frontend.pid"

for _ in {1..60}; do
  if curl -fsS "http://localhost:$FRONTEND_PORT" >/dev/null 2>&1; then
    break
  fi
  if ! kill -0 "$FRONTEND_PID" >/dev/null 2>&1; then
    echo "ERROR: frontend exited. See $LOG_DIR/frontend.log"
    tail -40 "$LOG_DIR/frontend.log" || true
    exit 1
  fi
  sleep 1
done

if ! curl -fsS "http://localhost:$FRONTEND_PORT" >/dev/null 2>&1; then
  echo "ERROR: frontend did not become ready. See $LOG_DIR/frontend.log"
  exit 1
fi

echo
echo "Local demo started"
echo "Backend health:  http://localhost:$BACKEND_PORT/api/constitutional/health"
echo "Backend ready:   http://localhost:$BACKEND_PORT/api/constitutional/ready"
echo "Frontend:        http://localhost:$FRONTEND_PORT"
echo "Logs:            $LOG_DIR/backend.log, $LOG_DIR/frontend.log"
echo
echo "Note: /ready will stay not_ready until backend/.env points to restored ChromaDB and BM25 data."

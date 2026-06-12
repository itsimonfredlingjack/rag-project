#!/usr/bin/env bash
# Verify Ollama warmup aligns with public profile config and measure cold vs warm latency.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
OUTPUT="${OUTPUT:-/tmp/rag-warmup-check.json}"
BACKEND_PORT="${BACKEND_PORT:-8900}"
PYTHON="${REPO}/backend/.venv/bin/python"

MODEL="$("$PYTHON" -c "
import os, sys
sys.path.insert(0, '$REPO/backend')
os.environ['CONST_PROFILE'] = 'public-riksdag-demo'
from app.services.config_service import ConfigSettings, PUBLIC_RIKSDAG_MODEL
s = ConfigSettings(_env_file=None)
print(PUBLIC_RIKSDAG_MODEL)
print(s.ollama_num_ctx)
" 2>/dev/null)"
MODEL_NAME="$(echo "$MODEL" | sed -n '1p')"
CONFIG_CTX="$(echo "$MODEL" | sed -n '2p')"

WARMUP_CTX="$(grep -oE 'num_ctx\\?":?[0-9]+' "$REPO/start_system.sh" | head -1 | grep -oE '[0-9]+' || echo 'missing')"

echo "=== RAG Coldstart Warmup Sentinel ==="
echo "Config model: $MODEL_NAME"
echo "Config ollama_num_ctx: $CONFIG_CTX"
echo "Warmup num_ctx in start_system.sh: $WARMUP_CTX"
echo

echo "[ollama ps]"
OLLAMA_PS="$(curl -fsS http://localhost:11434/api/ps 2>/dev/null || echo '{}')"
echo "$OLLAMA_PS" | python3 -m json.tool 2>/dev/null || echo "Ollama unreachable"
echo

echo "[ready]"
READY="$(curl -fsS "http://localhost:$BACKEND_PORT/api/svensk-ragg/ready" 2>/dev/null || echo '{}')"
echo "$READY" | python3 -c "
import json,sys
try:
    p=json.load(sys.stdin)
    llm=p.get('checks',{}).get('llm_service',{}).get('details',{})
    print('can_answer:', p.get('can_answer'))
    print('llm model:', llm.get('model'))
except Exception:
    print('ready unreachable')
" 2>/dev/null || echo "ready unreachable"
echo

CHAT_PAYLOAD() {
  local label="$1"
  python3 -c "import json; print(json.dumps({
    'model': '$MODEL_NAME',
    'messages': [{'role': 'user', 'content': 'Svara exakt: OK'}],
    'stream': False,
    'think': False,
    'options': {'num_predict': 8, 'num_ctx': int('$CONFIG_CTX'), 'temperature': 0}
  }))"
}

echo "[cold query] unloading model first..."
curl -fsS -X POST http://localhost:11434/api/generate \
  -H "Content-Type: application/json" \
  -d "{\"model\":\"$MODEL_NAME\",\"keep_alive\":0}" >/dev/null 2>&1 || true
sleep 1

COLD_START=$(date +%s%3N)
curl -fsS http://localhost:11434/api/chat \
  -H "Content-Type: application/json" \
  -d "$(CHAT_PAYLOAD cold)" >/dev/null
COLD_END=$(date +%s%3N)
COLD_MS=$((COLD_END - COLD_START))

WARM_START=$(date +%s%3N)
curl -fsS http://localhost:11434/api/chat \
  -H "Content-Type: application/json" \
  -d "$(CHAT_PAYLOAD warm)" >/dev/null
WARM_END=$(date +%s%3N)
WARM_MS=$((WARM_END - WARM_START))

echo "cold_ms: $COLD_MS"
echo "warm_ms: $WARM_MS"
echo

STATUS="OK"
if [[ "$WARMUP_CTX" != "$CONFIG_CTX" ]]; then
  STATUS="DRIFT"
fi

python3 - <<PY >"$OUTPUT"
import json

issues = []
if "$WARMUP_CTX" != "$CONFIG_CTX":
    issues.append("warmup num_ctx ($WARMUP_CTX) != config ($CONFIG_CTX)")

report = {
    "status": "$STATUS",
    "model": "$MODEL_NAME",
    "config_ctx": int("$CONFIG_CTX") if "$CONFIG_CTX".isdigit() else "$CONFIG_CTX",
    "warmup_ctx": "$WARMUP_CTX",
    "cold_ms": $COLD_MS,
    "warm_ms": $WARM_MS,
    "issues": issues,
}
print(json.dumps(report, indent=2))
PY

cat "$OUTPUT"
if [[ "$STATUS" == "DRIFT" ]]; then
  exit 1
fi
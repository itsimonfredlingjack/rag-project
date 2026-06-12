#!/usr/bin/env bash
set -euo pipefail

BACKEND_PORT="${BACKEND_PORT:-8900}"
FRONTEND_PORT="${FRONTEND_PORT:-3003}"
RUNTIME_PROFILE="${CONST_PROFILE:-public-riksdag-demo}"
MODEL="${OLLAMA_MODEL:-gemma4:e2b}"

check_url() {
  local label="$1"
  local url="$2"
  if curl -fsS "$url" >/dev/null 2>&1; then
    echo "OK       $label $url"
  else
    echo "MISSING  $label $url"
  fi
}

echo "Svensk Ragg local demo status"
echo "Profile: $RUNTIME_PROFILE"
echo "Model:   $MODEL"
echo

echo "[GPU]"
if command -v nvidia-smi >/dev/null 2>&1; then
  if GPU_OUTPUT="$(nvidia-smi --query-gpu=name,memory.used,memory.total,temperature.gpu --format=csv,noheader,nounits 2>&1)"; then
    printf "%s\n" "$GPU_OUTPUT" |
      awk -F', ' '{printf "OK       %s, VRAM %s/%s MB, temp %s C\n", $1, $2, $3, $4}'
  else
    echo "WARN     nvidia-smi present but unavailable: $(printf "%s" "$GPU_OUTPUT" | head -1)"
  fi
else
  echo "MISSING  nvidia-smi"
fi
echo

echo "[Ollama]"
if curl -fsS http://localhost:11434/api/tags >/dev/null 2>&1; then
  echo "OK       Ollama http://localhost:11434"
  if curl -fsS http://localhost:11434/api/tags | grep -q "\"name\":\"$MODEL\""; then
    echo "OK       model installed: $MODEL"
  else
    echo "MISSING  model not installed: $MODEL"
  fi
  RUNNING="$(curl -fsS http://localhost:11434/api/ps 2>/dev/null | grep -o '"name":"[^"]*"' | cut -d'"' -f4 | paste -sd ', ' - || true)"
  if [ -n "$RUNNING" ]; then
    echo "OK       loaded model(s): $RUNNING"
  else
    echo "INFO     no model currently loaded"
  fi
else
  echo "MISSING  Ollama http://localhost:11434"
fi
echo

echo "[Backend]"
check_url "health" "http://localhost:$BACKEND_PORT/api/svensk-ragg/health"
if curl -fsS "http://localhost:$BACKEND_PORT/api/svensk-ragg/ready" >/tmp/svensk-ragg-ready.json 2>/dev/null; then
  python3 - <<'PY'
import json
from pathlib import Path

try:
    payload = json.loads(Path("/tmp/svensk-ragg-ready.json").read_text())
    print(f"INFO     readiness: {payload.get('status', 'unknown')}")
    print(f"INFO     profile: {payload.get('profile', 'unknown')}")
    print(f"INFO     corpus_scope: {payload.get('corpus_scope', 'unknown')}")
    checks = payload.get("checks", {})
    chroma = checks.get("chromadb", {}).get("details", {})
    if chroma:
        counts = chroma.get("collection_counts", {}) or {}
        missing = chroma.get("missing_expected_collections", []) or []
        empty = chroma.get("empty_expected_collections", []) or []
        print(f"INFO     chroma collections: {chroma.get('collections', 0)}")
        for name in chroma.get("expected_collections", []) or []:
            print(f"INFO       {name}: {counts.get(name, 0)} docs")
        if missing:
            print("INFO     chroma missing: " + ", ".join(missing))
        if empty:
            print("INFO     chroma empty: " + ", ".join(empty))
    bm25 = checks.get("bm25", {}).get("details", {}) or payload.get("bm25", {})
    if bm25:
        if "documents_count" in bm25:
            print(
                "INFO     bm25: "
                f"status={bm25.get('status')} docs={bm25.get('documents_count')} "
                f"fts={bm25.get('fts_count')} provenance={bm25.get('provenance_status')} "
                f"path={bm25.get('path')}"
            )
        else:
            print(
                "INFO     bm25: "
                f"usable={bm25.get('usable')} loaded={bm25.get('loaded')} "
                f"docs={bm25.get('doc_count')} path={bm25.get('index_path')}"
            )
    llm = checks.get("llm_service", {}).get("details", {}) or payload.get("llm", {})
    if llm:
        print(
            "INFO     llm: "
            f"status={llm.get('status')} model={llm.get('model')} "
            f"available={llm.get('primary_available')}"
        )
except Exception:
    print("INFO     readiness: unknown")
PY
else
  echo "MISSING  readiness http://localhost:$BACKEND_PORT/api/svensk-ragg/ready"
fi
echo

echo "[Frontend]"
check_url "ui" "http://localhost:$FRONTEND_PORT"
echo

echo "Start: ./start_system.sh"
echo "Stop:  ./stop_system.sh"
echo "Logs:  logs/backend.log and logs/frontend.log"

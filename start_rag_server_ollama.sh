#!/usr/bin/env bash
set -euo pipefail

MODEL="${OLLAMA_MODEL:-gemma4:e2b}"
OLLAMA_URL="${OLLAMA_URL:-http://localhost:11434}"

echo "Checking Ollama RAG model"
echo "Endpoint: $OLLAMA_URL"
echo "Model:    $MODEL"

if ! command -v ollama >/dev/null 2>&1; then
  echo "ERROR: ollama is not installed or not on PATH"
  exit 1
fi

if ! curl -fsS "$OLLAMA_URL/api/tags" >/dev/null 2>&1; then
  echo "Ollama is not responding. Start it with:"
  echo "  ollama serve"
  exit 1
fi

if ! curl -fsS "$OLLAMA_URL/api/tags" | grep -q "\"name\":\"$MODEL\""; then
  echo "ERROR: model '$MODEL' is not installed"
  echo "Install it with:"
  echo "  ollama pull $MODEL"
  exit 1
fi

echo "Warming $MODEL..."
curl -fsS "$OLLAMA_URL/api/chat" \
  -H "Content-Type: application/json" \
  -d "{\"model\":\"$MODEL\",\"messages\":[{\"role\":\"user\",\"content\":\"Svara exakt: OK\"}],\"stream\":false,\"think\":false,\"options\":{\"num_predict\":8,\"temperature\":0}}" \
  >/dev/null

echo "OK: Ollama and $MODEL are ready for backend CONST_LLM_BASE_URL=$OLLAMA_URL"

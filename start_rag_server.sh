#!/bin/bash
# RAG Server Startup Script - 12GB VRAM Optimized
# Models verified: Mistral-Nemo-Instruct-2407-Q5_K_M.gguf (8.2GB) + Qwen2.5-0.5B-Instruct-Q8_0.gguf (645MB)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Binary
LLAMA_BIN="./llama.cpp/build/bin/llama-server"

# MODELS (Korrekta filnamn)
MODEL_PATH="models/Mistral-Nemo-Instruct-2407-Q5_K_M.gguf"
DRAFT_PATH="models/Qwen2.5-0.5B-Instruct-Q8_0.gguf"

echo "=============================================="
echo "🚀 STARTING RAG ENGINE (12GB VRAM OPTIMIZED)"
echo "=============================================="
echo ""
echo "Binary: $LLAMA_BIN"
echo "Main Model: $MODEL_PATH"
echo "Draft Model: $DRAFT_PATH"
echo ""
echo "⚙️  Critical Flags:"
echo "  -ctk q8_0 -ctv q8_0  (8-bit KV Cache)"
echo "  -ngl 60               (GPU Offload all layers)"
echo "  -c 16384              (Context window 16K)"
echo "  --model-draft          (Speculative decoding)"
echo "  -fa on                (Flash Attention)"
echo ""

# Verify binary
if [ ! -f "$LLAMA_BIN" ]; then
    echo "❌ ERROR: Binary not found at $LLAMA_BIN"
    exit 1
fi
echo "✅ Binary verified"

# Verify models
if [ ! -f "$MODEL_PATH" ]; then
    echo "❌ ERROR: Main model not found at $MODEL_PATH"
    exit 1
fi
MAIN_SIZE=$(du -h "$MODEL_PATH" | cut -f1)
echo "✅ Main model verified: $MAIN_SIZE"

if [ ! -f "$DRAFT_PATH" ]; then
    echo "⚠️  WARNING: Draft model not found, running without speculative decoding"
    DRAFT_PATH=""
else
    DRAFT_SIZE=$(du -h "$DRAFT_PATH" | cut -f1)
    echo "✅ Draft model verified: $DRAFT_SIZE"
fi

# Clean up port 8080
echo ""
echo "🧹 Cleaning up port 8080..."
fuser -k 8080/tcp 2>/dev/null || true
sleep 2

echo ""
echo "🔥 STARTING SERVER..."
echo "=============================================="

# Build command
CMD="$LLAMA_BIN -m '$MODEL_PATH'"
if [ -n "$DRAFT_PATH" ]; then
    CMD="$CMD --model-draft '$DRAFT_PATH'"
fi
CMD="$CMD -c 16384 -ngl 60 -ctk q8_0 -ctv q8_0 --port 8080 --host 0.0.0.0 --ctx-size 16384 --parallel 2 -fa on"

# Execute
eval $CMD

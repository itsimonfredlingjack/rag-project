#!/usr/bin/env bash
#
# Port Consistency Check
# Ensures all config files agree on canonical ports.
# Source of truth: this block ↓
#
# CANONICAL PORTS:
#   BACKEND=8900
#   FRONTEND=3003
#   LLM=8080
#
# Run: bash scripts/check_port_consistency.sh
# Exit 0 = consistent, Exit 1 = drift detected

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

ERRORS=0

err() {
    echo "DRIFT: $1" >&2
    ERRORS=$((ERRORS + 1))
}

# --- Canonical values ---
CANONICAL_FRONTEND=3003
CANONICAL_BACKEND=8900
CANONICAL_LLM=8080

# --- Check start_system.sh ---
FILE="$REPO_ROOT/start_system.sh"
if [ -f "$FILE" ]; then
    VAL=$(grep -oP '^FRONTEND_PORT=\K[0-9]+' "$FILE" 2>/dev/null || true)
    if [ -n "$VAL" ] && [ "$VAL" != "$CANONICAL_FRONTEND" ]; then
        err "$FILE: FRONTEND_PORT=$VAL (expected $CANONICAL_FRONTEND)"
    fi

    VAL=$(grep -oP '^BACKEND_PORT=\K[0-9]+' "$FILE" 2>/dev/null || true)
    if [ -n "$VAL" ] && [ "$VAL" != "$CANONICAL_BACKEND" ]; then
        err "$FILE: BACKEND_PORT=$VAL (expected $CANONICAL_BACKEND)"
    fi

    VAL=$(grep -oP '^LLM_PORT=\K[0-9]+' "$FILE" 2>/dev/null || true)
    if [ -n "$VAL" ] && [ "$VAL" != "$CANONICAL_LLM" ]; then
        err "$FILE: LLM_PORT=$VAL (expected $CANONICAL_LLM)"
    fi
fi

# --- Check status.sh ---
FILE="$REPO_ROOT/status.sh"
if [ -f "$FILE" ]; then
    # Look for curl calls to localhost with wrong frontend port
    BAD=$(grep -nP 'localhost:(3000|3001|3002)[^0-9]' "$FILE" 2>/dev/null || true)
    if [ -n "$BAD" ]; then
        err "$FILE: references wrong frontend port:\n$BAD"
    fi
fi

# --- Check config_service.py CORS ---
FILE="$REPO_ROOT/backend/app/services/config_service.py"
if [ -f "$FILE" ]; then
    # Ghost ports that nothing should use
    for PORT in 3000 3001 3002 5175; do
        if grep -qP "localhost:$PORT" "$FILE" 2>/dev/null; then
            err "$FILE: CORS contains ghost port $PORT (nothing runs there)"
        fi
    done
fi

# --- Check vite.config.ts ---
FILE="$REPO_ROOT/apps/constitutional-retardedantigravity/vite.config.ts"
if [ -f "$FILE" ]; then
    VAL=$(grep -oP 'port:\s*\K[0-9]+' "$FILE" 2>/dev/null || true)
    if [ -n "$VAL" ] && [ "$VAL" != "$CANONICAL_FRONTEND" ]; then
        err "$FILE: vite port=$VAL (expected $CANONICAL_FRONTEND)"
    fi
fi

# --- Result ---
if [ "$ERRORS" -gt 0 ]; then
    echo "" >&2
    echo "FAILED: $ERRORS port drift(s) detected. Fix them before committing." >&2
    exit 1
else
    echo "OK: All ports consistent (frontend=$CANONICAL_FRONTEND, backend=$CANONICAL_BACKEND, llm=$CANONICAL_LLM)"
    exit 0
fi

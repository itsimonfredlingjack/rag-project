#!/usr/bin/env bash
#
# RAG Server Stop Script
# Stops the Ollama RAG server cleanly
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${CYAN}Stopping RAG Server...${NC}"

# Read PID from file if it exists
if [ -f /tmp/rag-server.pid ]; then
    PID=$(cat /tmp/rag-server.pid)
    if ps -p $PID > /dev/null 2>&1; then
        echo -e "${YELLOW}Killing RAG server process (PID: $PID)...${NC}"
        kill $PID
        rm -f /tmp/rag-server.pid
    else
        echo -e "${YELLOW}RAG server process not found, cleaning up PID file${NC}"
        rm -f /tmp/rag-server.pid
    fi
fi

# Also try to kill any process on port 8080
if lsof -Pi :8080 -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo -e "${YELLOW}Stopping any process on port 8080...${NC}"
    pkill -f "ollama.*:8080" || true
    sleep 2
fi

echo -e "${GREEN}RAG Server stopped${NC}"

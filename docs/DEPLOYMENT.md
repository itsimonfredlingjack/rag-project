# Deployment Guide

Local/self-hosted deployment notes for the Swedish public-document RAG system. This is not a public service runbook.

## Document status

This is a deployment runbook for local and production-like experiments.

- **Status:** Active
- **Last reviewed:** February 13, 2026
- **Canonical source of truth:** `docs/DEPLOYMENT.md`
- **Documentation map:** `docs/README_DOCS_AND_RAG_INSTRUCTIONS.md`

## System Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| CPU | 4 cores | 8+ cores |
| RAM | 16 GB | 32 GB |
| GPU | 8 GB VRAM (RTX 3060) | 12+ GB VRAM (RTX 4070+) |
| Storage | 50 GB | 100 GB (for 521K+ docs) |
| Python | 3.12+ | 3.12 |
| OS | Ubuntu 22.04 / Debian 12 | Ubuntu 24.04 |

## Quick Start (Docker)

```bash
cd rag-project

# 1. Configure
cp backend/.env.example backend/.env
# Edit backend/.env — set CONST_CHROMADB_PATH, CONST_API_KEY, etc.

# 2. Prepare local model/runtime
# Current local-demo profile uses Ollama with gemma4:e2b.
ollama pull gemma4:e2b

# 3. Start backend services
docker compose up -d

# 4. Verify
curl http://localhost:11434/api/tags       # Ollama reachable
curl http://localhost:8900/api/svensk-ragg/health
curl http://localhost:8900/api/svensk-ragg/ready
```

## Manual Installation (without Docker)

### 1. ChromaDB

ChromaDB runs as an embedded database (no separate server needed). Data is stored at the path configured by `CONST_CHROMADB_PATH`.

```bash
# ChromaDB is included in Python dependencies
# Just ensure the data directory exists:
mkdir -p /path/to/chromadb_data
```

### 2. LLM Server

Option A: **Ollama** — current local-demo profile

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull gemma4:e2b
OLLAMA_MODEL=gemma4:e2b ./start_rag_server_ollama.sh
```

Set:

```dotenv
CONST_LLM_BASE_URL=http://localhost:11434
CONST_SVENSK_RAGG_MODEL=gemma4:e2b
CONST_SVENSK_RAGG_FALLBACK=gemma4:e2b
```

Option B: **llama.cpp (llama-server)** — advanced/manual profile
```bash
# Build llama.cpp with CUDA support
git clone https://github.com/ggerganov/llama.cpp
cd llama.cpp && make -j$(nproc) LLAMA_CUDA=1

# Download a policy-approved GGUF model and set backend environment variables
# to match the server endpoint and model identifier.

# Start server (OpenAI-compatible API on port 8080)
./llama-server \
    -m /path/to/models/approved-model.gguf \
    --host 0.0.0.0 --port 8080 \
    -c 8192 -ngl 99
```

### 3. Backend

```bash
cd backend

# Create virtual environment
python3.12 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env — see "Environment Variables" section below

# Start server
uvicorn app.main:app --host 0.0.0.0 --port 8900
```

### 4. Verify Installation

```bash
# Health check (basic)
curl http://localhost:8900/api/svensk-ragg/health

# Readiness check (deep — verifies ChromaDB, LLM, embeddings)
curl http://localhost:8900/api/svensk-ragg/ready

# Test query
curl -X POST http://localhost:8900/api/svensk-ragg/agent/query \
    -H "Content-Type: application/json" \
    -d '{"question": "Vad är personuppgiftslagen?"}'
```

## Environment Variables

All backend variables use the `CONST_` prefix. See `backend/.env.example` for the full list.

### Required

| Variable | Description | Default |
|----------|-------------|---------|
| `CONST_CHROMADB_PATH` | Path to ChromaDB data | `/data/chromadb` |
| `CONST_LLM_BASE_URL` | LLM API endpoint (OpenAI-compatible) | `http://localhost:8080/v1` |

### Recommended

| Variable | Default | Description |
|----------|---------|-------------|
| `CONST_API_KEY` | _(none)_ | API key for write operations. **Set in production\!** |
| `CONST_PORT` | `8900` | Backend listen port |
| `CONST_LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `CONST_LOG_JSON` | `false` | JSON-formatted log output |
| `CONST_CRAG_ENABLED` | `false` | Enable Corrective RAG pipeline |
| `CONST_RERANKING_ENABLED` | `true` | Jina reranker for search quality |
| `CONST_STRUCTURED_OUTPUT_ENABLED` | `true` | JSON-structured LLM responses |
| `CONST_EMBEDDING_MODEL` | `jinaai/jina-embeddings-v3` | Embedding model (1024 dim) |

### CORS

Origins are configured as a JSON list:
```bash
CONST_CORS_ORIGINS=["http://localhost:5173","http://your-frontend:3000"]
```

## API Documentation

- **Swagger UI**: `http://localhost:8900/docs`
- **ReDoc**: `http://localhost:8900/redoc`

### Key Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/svensk-ragg/health` | GET | Basic health check |
| `/api/svensk-ragg/ready` | GET | Deep readiness check |
| `/api/svensk-ragg/agent/query` | POST | RAG query (30 req/min limit) |
| `/api/svensk-ragg/agent/query/stream` | POST | SSE streaming RAG (20 req/min) |
| `/api/svensk-ragg/stats/overview` | GET | Document statistics |
| `/api/svensk-ragg/collections` | GET | ChromaDB collections |
| `/api/svensk-ragg/metrics` | GET | RAG pipeline metrics |

### Rate Limits

- **Query endpoints**: 30 requests/minute per IP
- **Streaming endpoints**: 20 requests/minute per IP
- Returns HTTP 429 when exceeded with `retry_after` header

### Authentication

Write operations (document CRUD) require `X-API-Key` header when `CONST_API_KEY` is set:
```bash
curl -X POST http://localhost:8900/api/documents/ \
    -H "X-API-Key: your-secret-key" \
    -H "Content-Type: application/json" \
    -d '{"content": "...", "collection": "legal_documents"}'
```

## Monitoring

### Health Checks

```bash
# Quick: is the server running?
GET /api/svensk-ragg/health

# Deep: are all dependencies (ChromaDB, LLM, embeddings) available?
GET /api/svensk-ragg/ready
```

### Logs

With `CONST_LOG_JSON=true`, logs are structured JSON for easy parsing:
```json
{"timestamp": "2026-02-07 10:30:00", "level": "INFO", "module": "orchestrator", "message": "Query processed", "request_id": "abc-123"}
```

### Prometheus Metrics

```bash
GET /api/svensk-ragg/metrics/prometheus
```

## Troubleshooting

### ChromaDB connection fails
- Verify `CONST_CHROMADB_PATH` points to a valid directory
- Ensure the directory has correct permissions
- Check if another process is holding a lock on the SQLite DB

### LLM timeouts
- Verify Ollama is running: `curl http://localhost:11434/api/tags`
- Check model availability: `ollama list | grep gemma4:e2b`
- Increase timeout: `CONST_LLM_TIMEOUT=120`
- Check GPU memory — the model may not be fully loaded

### Embedding model fails to load
- First load downloads ~2.3 GB for Jina v3
- Ensure sufficient disk space and internet access
- Model cache: `~/.cache/huggingface/`

### Rate limit exceeded
- Default: 30 req/min for queries, 20 for streaming
- Wait for the `retry_after` period indicated in the 429 response

### Out of GPU memory
- Reduce `CONST_CONTEXT_WINDOW`
- Use the smaller current demo profile (`gemma4:e2b`) before testing larger candidates
- Disable reranking: `CONST_RERANKING_ENABLED=false`

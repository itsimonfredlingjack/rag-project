# SYSTEM SNAPSHOT — Svensk RAG

_Generated: 2026-05-27 05:33:25 UTC_

## 1) Runtime configuration (effective from env/.env/.env.example)

- `CONST_APP_NAME`: `Svensk RAG`
- `CONST_PORT`: `8900`
- `CONST_LLM_BASE_URL`: `http://localhost:11434`
- `CONST_CONSTITUTIONAL_MODEL` (legacy key): `gemma3:12b`
- Frontend backend URL (`VITE_BACKEND_URL`): `http://localhost:8900`

## 2) Feature flags

- BM25 (`CONST_BM25_ENABLED`): **enabled**
- Reranking (`CONST_RERANKING_ENABLED`): **enabled**
- CRAG (`CONST_CRAG_ENABLED`): **enabled**
- Critic-Revise (`CONST_CRITIC_REVISE_ENABLED`): **enabled**
- Structured output (`CONST_STRUCTURED_OUTPUT_ENABLED`): **enabled**
- Intent fallback (`CONST_INTENT_LLM_FALLBACK_ENABLED`): **disabled**

## 3) API endpoint summary

### Agent/health/readiness/statistics
- **/api/svensk-rag**
  - `POST /agent/query`
  - `POST /agent/query/stream`
  - `POST /agent/query/stream/resume`
  - `GET /collections`
  - `GET /health`
  - `GET /metrics`
  - `GET /metrics/prometheus`
  - `GET /ready`
  - `GET /stats/overview`
- **/api/constitutional (legacy)**
  - `POST /agent/query`
  - `POST /agent/query/stream`
  - `POST /agent/query/stream/resume`
  - `GET /collections`
  - `GET /health`
  - `GET /metrics`
  - `GET /metrics/prometheus`
  - `GET /ready`
  - `GET /stats/overview`

### Documents
- `DELETE /api/documents/{document_id}`
- `GET /api/documents/{document_id}`
- `PATCH /api/documents/{document_id}`
- `PUT /api/documents/{document_id}`

## 4) Data stores

- ChromaDB path: `/path/to/chromadb_data`
- BM25 index path: `/tmp/workspace/itsimonfredlingjack/rag-project/data/bm25_fts5/bm25.db`

### ChromaDB collections
- Ingen lokal ChromaDB-data hittades eller kunde läsas.

### BM25 (FTS5)
- Ingen lokal BM25-data hittades eller kunde läsas.

## 5) Legacy compatibility

- Publikt namn är **Svensk RAG**.
- Legacy API-prefix `/api/constitutional/*` finns kvar för bakåtkompatibilitet.
- Legacy env-prefix `CONST_` och vissa interna `constitutional_*` identifierare är kvar tills vidare för säker migrering.

## 6) Warnings

- ⚠️ ChromaDB path saknas: /path/to/chromadb_data
- ⚠️ BM25-index saknas: /tmp/workspace/itsimonfredlingjack/rag-project/data/bm25_fts5/bm25.db

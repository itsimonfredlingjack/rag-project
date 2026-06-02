# RAG System Architecture

**Project**: Swedish Government Document Retrieval Augmented Generation (RAG) System  
**Framework**: FastAPI 0.109+ (Python 3.12) backend + React 19 + TypeScript frontend  
**Repository root**: `rag-project/`
**Last Updated**: 2026-05-16
**Version**: 1.3

---

## Document status

This is the canonical architecture reference for the RAG portfolio project.

- **Status**: Canonical
- **Last reviewed**: May 16, 2026
- **Canonical source of truth**: `docs/ARCHITECTURE.md`
- **Documentation map**: `docs/README_DOCS_AND_RAG_INSTRUCTIONS.md`

---

## Table of Contents

1. [System Overview](#system-overview)
2. [Architecture Principles](#architecture-principles)
3. [High-Level Data Flow](#high-level-data-flow)
4. [Backend Service Architecture](#backend-service-architecture)
5. [RAG Pipeline Flow](#rag-pipeline-flow)
6. [CRAG Pipeline Details](#crag-pipeline-details)
7. [API Endpoint Catalog](#api-endpoint-catalog)
8. [ChromaDB Collections](#chromadb-collections)
9. [LLM Integration](#llm-integration)
10. [Sprint 2 Decomposition](#sprint-2-decomposition)
11. [Frontend Architecture](#frontend-architecture)

---

## System Overview

### Purpose

The system is a local RAG implementation for Swedish public documents such as laws, regulations, parliamentary material and agency texts. It uses retrieval-augmented generation to make source material visible in the answer flow. It is a portfolio project, not an authoritative legal service.

### Core Capabilities

- **Multi-modal retrieval**: Dense semantic search + BM25 lexical search + adaptive routing
- **Corrective RAG**: Automatic document relevance grading and query rewriting
- **Intent-aware responses**: Different response formats based on query type (legal text, policy analysis, etc.)
- **Guardrail validation**: Security checks, confidence scoring and experimental hallucination-risk checks
- **Streaming responses**: Real-time generation with Server-Sent Events (SSE)
- **Agentic workflows**: LangGraph state machine for complex multi-step reasoning

### Technology Stack

| Layer | Technology | Version | Purpose |
|-------|-----------|---------|---------|
| **Frontend** | React + TypeScript | 19 + Latest | Web UI with real-time updates |
| **State Mgmt** | Zustand | — | Client-side state |
| **Visualization** | Three.js | — | 3D source viewer |
| **Backend Framework** | FastAPI | 0.109+ | REST/WebSocket API |
| **Python** | Python | 3.12 | Runtime |
| **Vector DB** | ChromaDB | — | Semantic search storage |
| **LLM Backend** | Configured via `CONST_LLM_BASE_URL` | — | Local LLM runtime such as Ollama or llama-server |
| **RAG Framework** | LangChain + LangGraph | — | Chain orchestration & agentic flows |
| **Embeddings** | Jina v3 | 570M | Asymmetric multilingual embeddings |
| **Sparse Search** | BM25 | rank-bm25 | Lexical full-text search |
| **Async Runtime** | asyncio | — | Concurrent I/O |

---

## Architecture Principles

### 1. Service-Oriented Architecture (SOA)

The backend follows a **Service-Oriented Architecture** with clear separation of concerns:
- **API Layer**: REST routes for HTTP requests
- **Business Logic**: 29 specialized service classes
- **Data Access**: ChromaDB and LLM API abstraction
- **Configuration**: Centralized ConfigService with Pydantic settings

### 2. Orchestrator Pattern

The **OrchestratorService** (956 lines) acts as the central brain:
- Query classification and decontextualization
- Retrieval orchestration
- Guard rail enforcement
- LLM invocation and response generation

### 3. Dependency Injection & Singletons

Services use **Singleton Factory Pattern** with `@lru_cache()` decorators for lazy initialization.

### 4. Async-First Design

- All I/O operations use `asyncio`
- Non-blocking HTTP client (`httpx.AsyncClient`)
- ChromaDB async API where available

### 5. Type Safety

- Pydantic models for all request/response validation
- Type hints on all service methods
- Discriminated unions for pipeline events

---

## High-Level Data Flow

### Request → Response Pipeline

```
Frontend Query (AgentQueryRequest)
    ↓
POST /api/svensk-ragg/agent/query
    ↓
OrchestratorService.process_query()
    ↓
[1] Intent Classification (detect: legal_text, policy_args, research, etc.)
    ↓
[2] Query Decontextualization (remove pronouns, build standalone search query)
    ↓
[3] Multi-Strategy Retrieval (RAG Fusion, adaptive routing, BM25 + semantic search)
    ↓
[4] CRAG Grading & Reflection (grade docs, rewrite if low confidence)
    ↓
[5] Guardrail Validation (security checks, confidence scoring)
    ↓
[6] LLM Generation (stream tokens or batch response)
    ↓
[7] Structured Output Parsing (JSON validation, 3-attempt retry)
    ↓
[8] Critic → Revise Loop (detect hallucinations, request revision if needed)
    ↓
[9] Response Formatting & Citations (link claims to sources)
    ↓
Return AgentQueryResponse (answer, sources, citations, evidence_level)
    ↓
Frontend displays results
```

---

## Backend Service Architecture

### Overview: 30 Services

#### Core Orchestration Services

| Service | Lines | Purpose |
|---------|-------|---------|
| **orchestrator_service.py** | 956 | PRIMARY COORDINATOR — Orchestrates entire RAG pipeline |
| **retrieval_orchestrator.py** | 1,357 | MULTI-STRATEGY RETRIEVAL — Manages Phase 1-4 with RAG Fusion |

#### Retrieval & Search Services

| Service | Lines | Purpose |
|---------|-------|---------|
| **retrieval_service.py** | 883 | ChromaDB wrapper for semantic search |
| **rag_fusion.py** | 629 | Query expansion and result fusion |
| **query_rewriter.py** | 539 | Query enhancement and rewriting |
| **bm25_service.py** | 271 | Lexical BM25 search |
| **embedding_service.py** | 209 | Jina v3 embedding generation (asymmetric) |
| **reranking_service.py** | 340 | Jina cross-encoder document reranking |

#### LLM Integration & Generation

| Service | Lines | Purpose |
|---------|-------|---------|
| **llm_service.py** | 705 | llama-server integration (Ollama fallback) |
| **prompt_service.py** | 412 | System prompts and legal context |
| **generation_service.py** | 403 | Structured JSON parsing, anti-truncation |
| **agentic_service.py** | 150 | LangGraph agentic flow |
| **streaming_service.py** | 201 | SSE streaming RAG pipeline |

#### Quality & Validation Services

| Service | Lines | Purpose |
|---------|-------|---------|
| **crag_service.py** | 219 | Corrective RAG pipeline (grading, self-reflection) |
| **grader_service.py** | 529 | Document relevance assessment |
| **critic_service.py** | 522 | Hallucination detection and evaluation |
| **guardrail_service.py** | 607 | Safety gates and confidence scoring |
| **confidence_signals.py** | 595 | Evidence scoring and source reliability |
| **structured_output_service.py** | 258 | JSON schema validation |

#### Query Understanding & Intent

| Service | Lines | Purpose |
|---------|-------|---------|
| **query_processor_service.py** | 529 | Query classification and decontextualization |
| **intent_classifier.py** | 403 | Intent classification (16 research patterns, 9 intent types) |
| **intent_routing.py** | 170 | EPR two-pass routing with DiVA secondary budget |

#### Configuration & Utilities

| Service | Lines | Purpose |
|---------|-------|---------|
| **config_service.py** | 424 | Configuration management |
| **graph_service.py** | 740 | LangGraph builder |
| **rag_models.py** | 254 | Pydantic data models |
| **swedish_compound_splitter.py** | 477 | Swedish linguistic preprocessing |
| **legal_abbreviations.py** | 273 | Swedish legal term expansion |
| **source_hierarchy.py** | 39 | Source priority enumeration |
| **base_service.py** | 127 | Abstract base class |
| **sse_stream_service.py** | 37 | SSE stream handling |

---

## RAG Pipeline Flow

### Step-by-Step Execution

#### Phase 1: Query Classification

QueryProcessorService.classify_query() detects intent:
- LEGAL_TEXT: Quoting law text (routes to SFS primary)
- PARLIAMENT_TRACE: Parliamentary decisions (routes to riksdag + DiVA secondary)
- POLICY_ARGUMENTS: Political argument analysis (routes to riksdag + DiVA secondary)
- RESEARCH_SYNTHESIS: Research synthesis (routes to DiVA primary)
- PRACTICAL_PROCESS: Step-by-step procedures (routes to procedural guides + SFS)
- EDGE_ABBREVIATION: Law abbreviations (RF 2:1 → RF 2 kap. 1 §)
- EDGE_CLARIFICATION: Disambiguation queries
- SMALLTALK: Greetings, off-topic (no retrieval)
- UNKNOWN: Fallback (all collections + DiVA secondary)

#### Phase 2: Decontextualization

Removes pronouns and implicit context to create standalone search query.

#### Phase 3: Multi-Strategy Retrieval

RetrievalOrchestrator executes selected strategy:
- **Parallel V1**: Parallel dense + BM25 search, deduplicate and rank
- **RAG Fusion**: Query expansion (3-5 variants), parallel search, RRF fusion. BM25 runs in parallel with dense embedding via `asyncio.gather()`.
- **Rewrite V1**: Detect complexity, rewrite if needed, fuse results
- **Adaptive**: Confidence-based escalation (A→B→C→D) with RAG Fusion
- **EPR Two-Pass**: Intent-based routing with primary/secondary collections and DiVA budget

Latency optimizations:
- Example retrieval prefetched during retrieval via `asyncio.ensure_future()`
- BM25 parallelized with dense embedding (saves ~100-150ms per query)

#### Phase 4: CRAG Grading & Reflection

- GraderService grades documents: RELEVANT | IRRELEVANT | PARTIALLY_RELEVANT
- If <3 relevant: self-reflection asks "Do we have enough evidence?"
- If low confidence: QueryRewriter.rewrite_query() and retry
- Evidence refusal if insufficient documents

#### Phase 5: Guardrail Validation

GuardrailService checks:
- Confidence scoring (source reliability, recency)
- Evidence coverage analysis
- Hallucination risk detection
- Returns: APPROVED | REQUIRES_REVISION | EVIDENCE_REFUSAL

#### Phase 6: LLM Generation

- Build system prompt with Svensk Ragg directives
- Insert retrieved sources as context
- Stream tokens or batch generation via LLMService

#### Phase 7: Structured Output Parsing

- Attempt 1-3 to parse JSON from LLM response
- If parse fails: Ask LLM to fix with error feedback
- Anti-truncation retry if answer appears cut off

#### Phase 8: Critic → Revise Loop

CriticService evaluates answer quality:
- Check for hallucinations
- Verify citations match sources
- Request revision if needed (max 3 attempts)

#### Phase 9: Response Formatting & Citations

Build AgentQueryResponse:
- Extract claims and link to sources
- Build Citation objects
- Assign evidence_level (HIGH/MEDIUM/LOW/NONE)
- Include metrics and guardrail status

---

## CRAG Pipeline Details

### What is CRAG?

**Corrective RAG** grades retrieved documents, rewrites queries if insufficient evidence, and enforces evidence-based answers with automatic refusal capability.

### Document Grading

Uses the configured local LLM to classify each document when CRAG grading is enabled:
- RELEVANT: Keep for context
- PARTIALLY_RELEVANT: Conditional inclusion
- IRRELEVANT: Filter out

### Self-Reflection

If <3 relevant documents:
1. Ask LLM: "Can we answer this question with available evidence?"
2. If NO: Propose rewritten query
3. If YES: Continue to generation

### Query Rewriting

Proposes improved search query focusing on:
- Legal terminology
- Specific law paragraphs
- Relevant keywords

### Evidence Refusal

If after grading + rewriting, evidence is still insufficient:
Return Swedish refusal: "Tyvärr kan jag inte besvara denna fråga utifrån de dokument som har hämtats..."

---

## API Endpoint Catalog

### Base URLs
- **Local development**: `http://localhost:8900`
- **Self-hosted experiments**: configured per environment

### Health & Monitoring

| Method | Endpoint | Purpose | Response |
|--------|----------|---------|----------|
| GET | `/api/svensk-ragg/health` | Health check | {status, services, timestamp} |
| GET | `/api/svensk-ragg/metrics` | Local/operator RAG metrics; 404 in public profile | {total_queries, avg_latency, by_mode} |
| GET | `/api/svensk-ragg/metrics/prometheus` | Local/operator Prometheus export; 404 in public profile | text/plain format |
| GET | `/api/svensk-ragg/ready` | Readiness check | {status, checks, timestamp} |

### Query & Retrieval

| Method | Endpoint | Purpose | Validation |
|--------|----------|---------|------------|
| POST | `/api/svensk-ragg/agent/query` | Main RAG pipeline (batch) | question: 1-2000 chars ✓ |
| POST | `/api/svensk-ragg/agent/query/stream` | Streaming variant (SSE) | Same as above ✓ |
| POST | `/api/svensk-ragg/agent/query/stream/resume` | SSE replay when enabled | session_id + last_event_id ✓ |

Operator-only routes such as `/mcp`, legacy `/sse`, `/sse/message`, `/ws/harvest`,
and generated docs are local/private by default. In `public-riksdag-demo`, they
are not registered unless an explicit local review flag enables docs.

### Document Management

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/svensk-ragg/collections` | Local/operator ChromaDB collection listing; 404 in public profile |
| GET | `/api/svensk-ragg/stats/overview` | Local/operator document statistics; 404 in public profile |

---

## ChromaDB Collections

### Overview

ChromaDB stores locally indexed documents embedded with Jina v3 multilingual embeddings. The database itself is not included in the repository.

### Collections (all suffixed `_jina_v3_1024`)

| Collection | Purpose | Documents |
|-----------|---------|-----------|
| **swedish_gov_docs** | Government documents (myndigheter, propositioner) | Historical local subset |
| **riksdag_documents_p1** | Parliamentary documents (motioner, betänkanden) | Historical local subset |
| **sfs_lagtext** | Swedish law text (Författningssamling) | Historical local subset |
| **procedural_guides** | Process guides for citizens | Historical local subset |
| **diva_research** | DiVA academic research metadata/text where available | Historical local subset |

**Historical local environment**: older project notes describe a larger local index across legal/government material and DiVA metadata. Treat this as local runtime history, not as a dataset included in the repo.

### Embedding Details

- **Model**: jinaai/jina-embeddings-v3
- **Dimension**: 1024
- **Languages**: 100+ including Swedish
- **Metric**: Cosine similarity
- **Reranker**: jinaai/jina-reranker-v2-base-multilingual (cross-encoder, XLM-RoBERTa, 278M params)
- **Storage**: local disk-backed ChromaDB data, size depends on the corpus and is not distributed in Git

### Public Corpus Artifacts

Det aktiva publika demot distribuerar Riksdag-korpusen som release-artifact i stället för att
kräva lokala Chroma-reindexeringsjobb. Återställ BM25/FTS5-bundlen enligt
[PUBLIC_RIKSDAG_DEMO.md](PUBLIC_RIKSDAG_DEMO.md). Historiska Chroma/Jina-recovery-jobb och
engångsskrapningar hörde till privat labbdrift och ligger inte längre som körbara root-skript.

### Retrieval Pipeline 2026

Aktuell projektpipeline för fråga-svar i RAG-systemet:

```text
User Query
→ Query Expansion / rewriting
→ Parallel: Dense Retrieval (Jina v3, task=retrieval.query) + BM25 (expanded terms)
→ Reciprocal Rank Fusion (k=60)
→ Cross-Encoder Reranking (Jina Reranker v2, CPU, top-30 → top-5)
→ CRAG-inspired grading / confidence signals
→ LLM Generation via configured local runtime
```

Resursbudget (riktvärden):

- **GPU (12 GB)**:
  - Gemma 4 E2B via Ollama: ~7.2 GB model download, current local-demo default
  - Gemma 4 26B: ~18 GB model download, validate GPU/RAM headroom before use
  - KV cache (q8_0, 8K context): ~1.0-1.8 GB beroende på kontextlängd och parallellism
  - CUDA/runtime-overhead: ~0.5-1.0 GB
- **CPU/RAM**:
  - Jina embeddings v3: ~2.3 GB
  - Jina Reranker v2: ~560 MB
  - BM25 index: ~2-4 GB
  - FastAPI + ChromaDB + process-overhead: varierar med workload

---

## LLM Integration

### Backend Runtime

The backend calls a local LLM runtime through the configured `CONST_LLM_BASE_URL`. In development this may be Ollama on port 11434 or an OpenAI-compatible llama-server setup.

```bash
# Current local-demo profile
ollama pull gemma4:e2b
OLLAMA_MODEL=gemma4:e2b ./start_rag_server_ollama.sh
```

Model choice is environment-specific. The repo does not include model weights,
and runtime model identifiers are checked against the repository model policy.

### LLMService

**File**: backend/app/services/llm_service.py (705 lines)

Methods:
- `chat()`: Batch completion (wait for response)
- `chat_stream()`: Streaming completion (yield tokens)
- `count_tokens()`: Token estimation

### System Prompts

Prompt directives:
1. ONLY cite sources in retrieved documents
2. Prioritize law text over interpretation
3. Use official Swedish legal terminology
4. Refuse if insufficient evidence
5. Always cite original source

### Token Counting

Uses tiktoken to estimate token usage before LLM invocation.

### Streaming Integration

Server-Sent Events (SSE) for real-time token delivery:
```
data: {"type":"token","content":"Processen"}
data: {"type":"token","content":" för"}
...
data: {"type":"done"}
```

---

## Sprint 2 Decomposition

### Background

Sprint 2 refactored the monolithic orchestrator_service.py (originally 2,517 lines) into 6 focused modules.

### Extracted Modules

| Module | Lines | Responsibility |
|--------|-------|-----------------|
| **rag_models.py** | 254 | Data models (RAGResult, Citation, SearchResult) |
| **prompt_service.py** | 412 | System prompts and legal context building |
| **crag_service.py** | 219 | CRAG grading and self-reflection |
| **generation_service.py** | 403 | Structured output parsing and critic loop |
| **agentic_service.py** | 150 | LangGraph agentic flows |
| **streaming_service.py** | 201 | SSE streaming RAG pipeline |

### Remaining Orchestrator

**orchestrator_service.py** (956 lines) coordinates:
1. Intent routing
2. Query decontextualization
3. Retrieval orchestration
4. CRAG grading (via crag_service)
5. Guardrail validation
6. LLM generation (via generation_service)
7. Response formatting

### Benefits

- **Modularity**: Single responsibility per service
- **Testability**: Isolated unit testing possible
- **Reusability**: Services imported in multiple flows
- **Readability**: Reduced cognitive load (956 vs 2517 lines)
- **Parallelization**: Independent optimization per service

---

## Frontend Architecture

### Structure

```
apps/svensk-ragg-frontend/src/
├── App.tsx                    # Root component
├── components/
│   ├── QueryBar.tsx          # User input
│   ├── ResultsPanel.tsx      # Answer display
│   ├── SourcesPanel.tsx      # Document sidebar
│   ├── CitationsList.tsx     # Claim-to-source linking
│   ├── 3d/                   # Three.js visualization
│   │   ├── SourceViewer3D.tsx
│   │   ├── DocumentCloud.tsx
│   │   └── InteractiveFlow.tsx
│   ├── ErrorBoundary.tsx     # Error handling
│   └── ui/                   # Shared UI components
├── stores/                    # Zustand state (query, results, settings)
├── hooks/                     # Custom hooks (useQuery, useSSE)
├── types/                     # API and UI types
├── constants.ts              # App-wide constants
├── theme/                    # Tailwind colors and dark mode
└── utils/                    # Formatting, API, validation
```

### Technology Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **UI Framework** | React 19 | Component-based UI |
| **Language** | TypeScript | Type safety |
| **Styling** | Tailwind CSS | Utility-first CSS |
| **State Mgmt** | Zustand | Lightweight state |
| **3D Viz** | Three.js | WebGL visualization |
| **Build Tool** | Vite | Fast dev server and bundler |
| **Package Mgr** | npm | Dependency management |

### Key Features

- **Responsive Design**: Desktop 2-column, mobile full-screen
- **Real-time Streaming**: SSE integration for live updates
- **3D Visualization**: Interactive document cloud with Three.js
- **Citation Linking**: Hover to highlight source text
- **Dark Mode**: Theme switching support
- **Accessibility**: ARIA labels and semantic HTML

### State Management (Zustand)

Stores:
- `queryStore`: Current question and search history
- `resultsStore`: RAG results and display state
- `settingsStore`: User preferences

### API Integration

Fetch wrapper with error handling for:
- `/api/svensk-ragg/agent/query` (POST)
- `/api/svensk-ragg/agent/query/stream` (POST SSE)

---

## Configuration & Environment

### Backend (.env)

```bash
# FastAPI
FASTAPI_ENV=development
API_BASE_URL=http://localhost:8900

# LLM
CONST_LLM_BASE_URL=http://localhost:11434
CONST_SVENSK_RAGG_MODEL=gemma4:e2b
CONST_SVENSK_RAGG_FALLBACK=gemma4:e2b
CONST_LLM_TIMEOUT=120.0

# ChromaDB
CONST_CHROMADB_PATH=/path/to/local/chromadb
CONST_BM25_INDEX_PATH=/path/to/local/bm25_fts5/bm25.db

# Features
CONST_CRAG_ENABLED=false
CONST_STRUCTURED_OUTPUT_ENABLED=true
CRITIC_ENABLED=true

# Logging
LOG_LEVEL=INFO
LOG_JSON=false
```

### Frontend

Configuration via environment variables (Vite):
- `VITE_API_BASE_URL`: Backend URL
- `VITE_WS_URL`: WebSocket URL

---

## Monitoring & Observability

### Logging

Structured logging via `get_logger()` in all services.

### Metrics

Available in local/private profiles via `/metrics` and `/metrics/prometheus`
and disabled in the public profile:
- Total queries
- Latency (avg/p95/p99)
- Evidence refusal rate
- Parse error rate
- Metrics by mode (chat/assist/evidence)

### Health Checks

- `/health`: Service health
- `/ready`: Full readiness check with dependency status

---

## Deployment

### Local Development

```bash
# Backend
cd backend && pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8900

# Frontend
cd apps/svensk-ragg-frontend
npm install && npm run dev
```

### Deployment Templates

Docker Compose and systemd templates are included for local/self-hosted experiments. They are not evidence of a public production service.

---

**Document Version**: 1.3
**Last Updated**: 2026-05-16

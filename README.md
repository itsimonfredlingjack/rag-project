# Constitutional AI

> RAG-system för svenska myndighetsdokument med **1,075,956 indexerade dokument**

[![Status](https://img.shields.io/badge/status-production-green)]()
[![Backend](https://img.shields.io/badge/backend-FastAPI-blue)]()
[![Frontend](https://img.shields.io/badge/frontend-React%20%2B%20TypeScript-blue)]()
[![LLM](https://img.shields.io/badge/LLM-llama.cpp-orange)]()

## Översikt

Swedish RAG-system för att söka och analysera dokument från Riksdagen, SFS (Svensk författningssamling) och svenska myndigheter. Systemet använder en agentic LLM-pipeline med LangGraph, FastAPI-backend och React + Three.js frontend.

## Quick Start

### Backend (port 8900)
```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8900

# Eller via systemd
systemctl --user start constitutional-ai-backend
```

### Frontend (port 3001)
```bash
cd apps/constitutional-retardedantigravity
npm install
npm run dev -- --port 3001 --host 0.0.0.0
```

### LLM Server (port 8080)
```bash
./start_system.sh  # Startar llama-server med optimerade inställningar
```

## Teknisk Stack

### Inference (llama.cpp)

Systemet använder **llama-server** från llama.cpp (inte Ollama):

| Komponent | Värde |
|-----------|-------|
| LLM Backend | llama-server (OpenAI-kompatibelt API) |
| Primär modell | Mistral-Nemo-Instruct-2407-Q5_K_M.gguf |
| Draft modell | Qwen2.5-0.5B-Instruct-Q8_0.gguf |
| Grading modell | Qwen2.5-0.5B-Instruct-Q5_K_M.gguf |
| Kontext | 16,384 tokens |

**GPU-optimeringar** (RTX 4070 12GB):
- Speculative Decoding - Qwen 0.5B draftar tokens, Mistral-Nemo validerar
- KV-Cache Quantization (`-ctk q8_0 -ctv q8_0`) - 4x minnesreduktion
- Flash Attention (`-fa on`)
- GPU Offloading (`-ngl 60`) - 60 lager på GPU

### Embeddings

| Komponent | Värde |
|-----------|-------|
| Modell | BAAI/bge-m3 |
| Dimensioner | 1024 |
| Typ | Hybrid search (dense + sparse) |

### Frontend

- **Framework**: React 18 + Vite + TypeScript
- **Styling**: TailwindCSS
- **3D**: Three.js (källvisualisering)
- **State**: Zustand
- **Streaming**: Server-Sent Events (SSE)

## Projektstruktur

```
rag-project/
├── backend/                    # FastAPI backend (port 8900)
│   ├── app/
│   │   ├── api/                # API routes
│   │   ├── services/           # 17 services (~10K rader)
│   │   ├── core/               # Exceptions, error handlers
│   │   └── main.py             # FastAPI entry point
│   └── requirements.txt
├── apps/
│   └── constitutional-retardedantigravity/  # React frontend
├── indexers/                   # ChromaDB indexering
├── scrapers/                   # Web scrapers
├── chromadb_data/              # Vector database (~16GB)
├── start_system.sh             # llama-server launcher
└── CLAUDE.md                   # AI-instruktioner
```

## Data

**Totalt: 1,075,956 dokument** i ChromaDB

| Collection | Dokument |
|------------|----------|
| swedish_gov_docs_bge_m3_1024 | 304,871 |
| riksdag_documents_p1_bge_m3_1024 | 230,143 |
| sfs_lagtext_bge_m3_1024 | 2,887 |

## API Endpoints

| Endpoint | Metod | Beskrivning |
|----------|-------|-------------|
| `/api/constitutional/health` | GET | Hälsokontroll |
| `/api/constitutional/stats/overview` | GET | Statistik |
| `/api/constitutional/collections` | GET | Lista collections |
| `/api/constitutional/agent/query` | POST | RAG-fråga (synkron) |
| `/api/constitutional/agent/query/stream` | POST | RAG-fråga (streaming) |

Full API-dokumentation: `http://localhost:8900/docs`

## RAG Pipeline

Systemet implementerar en avancerad RAG-pipeline med:

- **Corrective RAG (CRAG)** - Dokumentrelevansgradering och kritik
- **RAG-Fusion** - 3-query expansion (semantisk, lexikal, parafras)
- **BGE Reranker** - Cross-encoder reranking (bge-reranker-v2-m3)
- **4-stegs adaptiv eskalering** - Gradvis utökning vid låg träffsäkerhet
- **10 confidence signals** - Viktad kvalitetsbedömning
- **SFS-prioritering** - Svenska lagtexter prioriteras

### Dataflöde

```
User Query → FastAPI (8900) → OrchestratorService
    → RetrievalOrchestrator → ChromaDB (1M+ docs)
    → GraderService (Qwen 0.5B) → CriticService (CRAG)
    → LLMService → llama-server (8080) → Mistral-Nemo
    → GuardrailService → Response med källor
```

## Portar

| Tjänst | Port |
|--------|------|
| llama-server | 8080 |
| Backend API | 8900 |
| Frontend | 3001 |

## Utveckling

### Tester
```bash
cd backend
pytest tests/ -v                    # Alla tester
pytest tests/test_file.py -v        # En fil
pytest -k "test_search" -v          # Pattern match
```

### Linting
```bash
ruff check .        # Kontrollera
ruff check --fix .  # Auto-fix
ruff format .       # Formatera
```

### Health Check
```bash
curl http://localhost:8900/api/constitutional/health | jq .
```

## Konfiguration

Huvudkonfiguration finns i:
- `backend/app/services/config_service.py` - Alla service-inställningar
- `start_system.sh` - llama-server parametrar

### Miljövariabler
- `CONST_PORT` - Backend port (default 8900)
- `RAG_SIMILARITY_THRESHOLD` - Score threshold (default 0.5)
- `CONST_CRAG_ENABLED` - Aktivera Corrective RAG
- `CONST_LOG_LEVEL` - Loggnivå

## Viktigt

- **Data exkluderas från git**: `chromadb_data/`, `pdf_cache/`, `backups/` (~16GB+)
- **Backend service**: Körs som `constitutional-ai-backend` via systemd
- **GPU**: Optimerat för RTX 4070 (12GB VRAM)

## License

[Lägg till license]

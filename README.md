# Constitutional AI — RAG-system för svenska myndighetsdokument

> **Personligt lärande- och portföljprojekt** — inte en produkt eller tjänst.

Jag byggde det här för att lära mig end-to-end hur ett modernt RAG-system fungerar i praktiken: från datainsamling och vektorindexering till LLM-inferens och streaming-svar. Allt körs lokalt på en RTX 4070 — inga molntjänster, inga abonnemangskostnader.

**Vad det gör:** tar en fråga på svenska → hämtar relevanta stycken ur 1,37 miljoner svenska myndighetsdokument → genererar ett källhänvisat svar med en lokal LLM (Gemma 3 12B via Ollama).

![Query results](docs/assets/query-results.png)
![Pipeline details](docs/assets/pipeline-details-expanded.png)

## Varför jag byggde det

Jag ville ha ett konkret projekt som demonstrerar att jag kan navigera ett komplext tekniklandskap med verkliga trade-offs: vektordatabaser, LLM-inferens, streaming-API:er och 30+ datakällor. Inte en tutorial — ett fungerande system som jag itererat på under flera månader.

## Vad som funkar — och vad som är experiment

✅ **Fungerar:** Pipeline end-to-end (fråga → hämtning → svar med källhänvisningar), SSE-streaming till React-frontend, CRAG-dokumentgradering (relevant/ambiguous/irrelevant), hybrid-sökning BM25 + vektor, eval-ramverk med 16 testfiler.

⚠️ **Halvfärdigt / under iteration:** Guardrail-systemet (Jail Warden v2) är grovkalibrerat — EVIDENCE-läget blockerar ~40 % av legitima svar. Critic-Revise-loopen är implementerad men sällan aktiverad i praktiken.

❌ **Inte inkluderat i repot:** ChromaDB-datan (57 GB) körs lokalt och finns inte i git.

## Vad jag lärde mig

- **RAG-pipeline i djupet:** vektorsökning (ChromaDB + Jina Embeddings v3, 1024-dim, asymmetrisk encoding), BM25 sparse search, Reciprocal Rank Fusion
- **CRAG-mönstret:** dokumentgradering + self-reflection för att minska hallucinationer
- **Lokal LLM-inferens:** quantiserade modeller (Q4_K_M), context-hantering, GPU-minnesbegränsningar med RTX 4070 12 GB
- **Systemdesign i skala:** ~1,37M vektorer, 33 tjänstemodulor, LangGraph state machine, SSE-streaming
- **Datainsamling i praktiken:** web-scrapers för 30+ myndigheter, OAI-PMH-harvesting för DiVA-forskning (829K akademiska publikationer)

## Vad ingår

```
backend/          FastAPI RAG-backend med 33 service-moduler (port 8900)
apps/             React-frontend med 3D-visualisering (port 3003)
scrapers/         Web scrapers för 30+ svenska myndigheter
indexers/         ChromaDB-indexeringsskript
eval/             Utvärderingsramverk (RAGAS, retrieval quality, chunk analysis)
docs/             Dokumentation och arkitektur
```

## Tech Stack

### Backend (Python 3.12)

| Komponent | Teknik |
|-----------|--------|
| API | FastAPI 0.109+, Uvicorn, Pydantic v2 |
| Vector DB | ChromaDB (~57 GB, 1,37M+ dokument) |
| Embeddings | jinaai/jina-embeddings-v3 (1024 dim, asymmetrisk encoding) |
| Reranker | jinaai/jina-reranker-v2-base-multilingual (cross-encoder, XLM-RoBERTa, 278M params) |
| LLM | Gemma 3 12B Q4_K_M (~8 GB) via Ollama |
| Pipeline | LangGraph (CRAG med relevance grading + self-reflection) |
| Sparse search | BM25 (SQLite FTS5) |
| Fusion | RAG-Fusion med Reciprocal Rank Fusion |
| Hallucinationsskydd | Jail Warden v2 (guardrail service) |
| Linting | Ruff (line-length 100, target py310) |
| Tester | pytest, pytest-asyncio |

### Frontend (TypeScript)

| Komponent | Teknik |
|-----------|--------|
| UI | React 19, TypeScript 5.9 |
| Build | Vite 7 |
| 3D | Three.js 0.182 via React Three Fiber 9 + Drei 10 |
| Styling | Tailwind CSS 4 |
| State | Zustand 5 |
| Animation | Framer Motion 12 |

### Infrastruktur

| Komponent | Teknik |
|-----------|--------|
| Hosting | Self-hosted, RTX 4070 12 GB VRAM |
| LLM-runtime | Ollama port 11434 |
| Process | 3 systemd user services (backend, llm, frontend) |
| Containers | Docker Compose (valfritt) |
| CI/CD | GitHub Actions — ruff, mypy, pytest, eslint, tsc build |

## RAG-pipeline

```
Query → IntentClassifier → QueryRewriter
  → RetrievalOrchestrator (4 faser)
    ├─ Fas 1: Parallell sökning i alla collections
    ├─ Fas 2: Query-dekontextualisering
    ├─ Fas 3: RAG-Fusion (multi-query + RRF-merge)
    └─ Fas 4: Adaptiv retrieval (confidence-baserad eskalering)
  → Reranking (Jina cross-encoder)
  → GraderService (Gemma 3 12B, 3-vägs relevansgradering per dokument)
  → LLM (Gemma 3 12B, streamas via SSE)
  → GuardrailService (blockerar hallucinationer i EVIDENCE-läge)
  → CriticService (Critic-Revise loop)
  → Svar till frontend
```

### Frågelägen

| Läge | Temperatur | Syfte |
|------|-----------|-------|
| EVIDENCE | 0.15 | Strikt källbaserat, hög precision |
| ASSIST | 0.4 | Guidat svar med källor som kontext |
| CHAT | 0.7 | Konversationellt, friare |

## Datakällor

### ChromaDB-collections (alla suffixade `_jina_v3_1024`)

| Collection | Dokument | Innehåll |
|------------|----------|----------|
| `swedish_gov_docs` | 304K | Myndighetstexter, SOU |
| `riksdag_documents_p1` | 230K | Motioner, riksdagstryck |
| `sfs_lagtext` | — | Svensk författningssamling |
| `procedural_guides` | — | Handläggningsguider |
| DiVA-collections | 829K | Forskningspublikationer (KTH, LU, SU, UU, Chalmers, LiU m.fl.) |
| **Totalt** | **1,37M+** | |

### Scrapers

**Rot-scrapers:** Bolagsverket, Boverket, DO, Elsäkerhetsverket, Energimyndigheten, IMY, Jordbruksverket, Livsmedelsverket, Migrationsverket, MSB, PTS, SCB, SFS (Riksdagen), plus OCR-processor.

**Myndighets-scrapers (`scrapers/myndigheter/`):** Arbetsförmedlingen, ARN, Finansinspektionen, Kronofogden, PRV, Riksbanken, ESV, Folkhälsomyndigheten, Försäkringskassan, JK, Kemikalieinspektionen, Konjunkturinstitutet, Konsumentverket, Naturvårdsverket, Skatteverket, Socialstyrelsen, Spelinspektionen, Statskontoret, Trafikanalys, Trafikverket, Vetenskapsrådet, Skolverket, SMHI, Tillväxtverket.

## Kom igång

### Förutsättningar

- Python 3.12+, Node.js 20+
- [Ollama](https://ollama.ai) installerat med `gemma3:12b` nedladdat
- ChromaDB-data (inte inkluderat i repot — se `indexers/` för att bygga eget)

### Backend

```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # justera efter behov
uvicorn app.main:app --host 0.0.0.0 --port 8900
```

### Frontend

```bash
cd apps/konstitutionell-frontend
npm install
npm run dev                   # dev server :3003
```

### API-dokumentation

Swagger UI: `http://localhost:8900/docs`

### API-endpoints

| Metod | Route | Syfte |
|-------|-------|-------|
| GET | `/api/constitutional/health` | Hälsokontroll |
| GET | `/api/constitutional/ready` | Djup readiness-check |
| GET | `/api/constitutional/stats/overview` | Statistik över collections |
| POST | `/api/constitutional/agent/query` | RAG-fråga (JSON) |
| POST | `/api/constitutional/agent/query/stream` | RAG-fråga (SSE-streaming) |
| POST | `/api/constitutional/search` | Dokumentsökning |

## Portar

| Tjänst | Port |
|--------|------|
| Frontend (Vite dev) | 3003 |
| Backend (FastAPI) | 8900 |
| Ollama | 11434 |

## Tester

```bash
cd backend
pytest tests/ -v                               # alla unit-tester
pytest -m "not integration and not slow"       # snabbkörning
RUN_INTEGRATION_TESTS=1 pytest -m integration  # integrationstester
RUN_OLLAMA_TESTS=1 pytest -m ollama            # ollama-tester
```

16 testfiler, ~4 700 rader.

## Konfiguration

Backend-inställningar i `backend/app/config.py` via pydantic-settings. Alla miljövariabler prefixade med `CONST_`:

| Variabel | Default | Syfte |
|----------|---------|-------|
| `CONST_PORT` | 8900 | Backend-port |
| `CONST_LLM_BASE_URL` | `http://localhost:11434` | Ollama URL |
| `CONST_CRAG_ENABLED` | false | Aktivera CRAG |
| `CONST_CRAG_ENABLE_SELF_REFLECTION` | false | CRAG self-reflection |
| `CONST_DEBUG` | false | Debug-läge |
| `CONST_LOG_LEVEL` | INFO | Loggnivå |

## Licens

MIT — se [LICENSE](LICENSE).

<div align="center">

# RAG-system för svenska offentliga dokument

### Svensk Ragg - personligt lärande- och portföljprojekt

[![CI](https://github.com/itsimonfredlingjack/rag-project/actions/workflows/ci.yml/badge.svg)](https://github.com/itsimonfredlingjack/rag-project/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React 19](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)](https://react.dev/)

**Inte en produkt. Inte en publik tjänst. Ett tekniskt portföljcase.**

</div>

---

Det här repot visar ett end-to-end RAG-system byggt för svenska offentliga dokument. Projektet är ett personligt lärandeprojekt som knyter ihop datainsamling, indexering, hybrid retrieval, lokal LLM-inferens, källhänvisade svar, backend, frontend, tester och CI.

Målet är att visa praktisk förståelse för hur ett RAG-system faktiskt sätts ihop: från dokumentkorpus och retrieval-strategier till osäkerhet, källurval, streaming och användargränssnitt.

![Screenshot från tidigare lokal körning med matchade källor](docs/assets/portfolio-query-with-sources.png)

_Screenshoten visar en tidigare lokal körning av frontendens källpanel. Full lokal retrieval kräver ChromaDB-/BM25-data och LLM-runtime som inte ingår i repot._

---

## Vad Projektet Visar

- End-to-end RAG-flöde: fråga, retrieval, reranking, generation och källvisning.
- Hybrid retrieval med ChromaDB-vektorsökning och BM25/SQLite FTS5.
- Lokal LLM-integration via konfigurerad `CONST_LLM_BASE_URL`.
- Källhänvisade svar och frontendpanel för källor/citations.
- FastAPI-backend med SSE-streaming till React/TypeScript/Vite-frontend.
- Eval- och teststruktur för retrieval, prompts, API-kontrakt och pipelinebeteende.
- GitHub Actions för docs-check, backendtester och frontend lint/build.
- Praktisk hantering av retrievalkvalitet, avgränsningar, osäkerhet och hallucinationsrisk.

## Vad Det Inte Är

- Inte en färdig produkt eller en publik tjänst.
- Inte en komplett eller auktoritativ databas över svenska offentliga dokument.
- Inte ett löfte om juridiskt korrekta svar.
- Inte en distribuerad demo med färdig ChromaDB, BM25-index eller modellvikter.
- Inte ett benchmarkat system med verifierade precision-/recall-värden i detta repo.

Lokala datavolymer som nämns i projektet beskriver en tidigare projektmiljö, inte data som följer med repot. Bygger du ett eget corpus kan antal dokument, lagringsstorlek och resultat skilja sig mycket.

## Teknisk Översikt

| Del | Teknik |
|-----|--------|
| Backend | FastAPI, Uvicorn, Pydantic v2 |
| Frontend | React 19, TypeScript, Vite, Tailwind CSS |
| 3D/UI | Three.js, React Three Fiber, Drei, Framer Motion |
| Vector DB | ChromaDB, lokal persistent lagring |
| Sparse search | BM25 via SQLite FTS5 |
| Embeddings | `jinaai/jina-embeddings-v3` |
| Reranking | `jinaai/jina-reranker-v2-base-multilingual` |
| Lokal LLM | Konfigurerad via `CONST_LLM_BASE_URL` (till exempel Ollama eller llama-server) |
| Pipeline | Retrieval orchestration, RAG-Fusion/RRF, CRAG-inspirerad gradering |
| Streaming | Server-Sent Events från backend till frontend |
| CI | GitHub Actions: docs-check, pytest, ruff, mypy, eslint, TypeScript build |

## Arkitektur

```mermaid
graph TD
    A["Användare"] --> B["React/Vite frontend"]
    B -->|"POST /api/svensk-ragg/agent/query/stream"| C["FastAPI backend"]

    C --> D["Intent classification"]
    D --> E["Query rewriting / decontextualization"]
    E --> F["Retrieval orchestrator"]

    F --> G["ChromaDB vector search"]
    F --> H["BM25 / SQLite FTS5"]
    G --> I["RAG-Fusion / RRF"]
    H --> I
    I --> J["Jina reranking"]
    J --> K["Document grading / confidence signals"]
    K --> L["Local LLM via CONST_LLM_BASE_URL"]
    L --> M["Response shaping and citations"]
    M -->|"SSE events"| B
    B --> N["Answer, pipeline status and sources"]
```

Se [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) för mer teknisk detalj.

## Repo-Karta

```text
rag-project/
├── backend/                         FastAPI-backend, services, API-routes och tester
├── apps/svensk-ragg-frontend/   React/TypeScript/Vite-frontend
├── eval/                            Eval-skript, testfrågor och retrieval-analyser
├── backend/eval/                    Backendnära eval-dataset och körskript
├── indexers/                        Skript för ChromaDB-indexering
├── scripts/                         Pipeline-, BM25-, reindexerings- och utility-skript
├── scrapers/                        Scrapers för offentliga svenska dokumentkällor
├── docs/                            Publik dokumentation och screenshots
└── .github/workflows/               CI för docs, backend och frontend
```

## Datakorpus Och Begränsningar

Projektet har utvecklats mot en större lokal korpus av svenska offentliga dokument. I tidigare lokal miljö har dokumentationen beskrivit ungefär 1,37M indexerade poster, inklusive myndighets-/riksdagsmaterial och DiVA-metadata. Den siffran ska läsas som historik från utvecklingsmiljön, inte som något som kan verifieras direkt efter klon.

Det som finns i repot är kod, dokumentation, testdata och eval-struktur. Det som inte finns i repot är:

- ChromaDB-data.
- BM25/FTS5-index.
- Lokala modellvikter.
- PDF-cache eller skrapad rådata.
- Lokala secrets, tokens eller runtimefiler.

Det största lärandet i projektet är att kvaliteten i ett RAG-system avgörs lika mycket av retrieval, källurval, avgränsningar och eval som av modellen.

## Kom Igång

Se även [docs/QUICK_START.md](docs/QUICK_START.md) för en kortare körguide.
För full publik demo, se även [docs/PUBLIC_RIKSDAG_DEMO.md](docs/PUBLIC_RIKSDAG_DEMO.md).

### Installationsguide: Svensk RAGG/Riksdag-demo (publik)

- **Repo:** `https://github.com/itsimonfredlingjack/rag-project.git`
- **Backend:** FastAPI/Uvicorn på `127.0.0.1:8900`
- **Frontend:** Vite-app på `http://localhost:3003`
- **Demo-profil:** `public-riksdag-demo`
- **LLM:** Ollama med `gemma3:4b`
- **Corpus/index:** hämtas separat från GitHub Release och innehåller `docs.jsonl` och `bm25.db`
- **Standardplats för data:** `/home/ai-server2/rag/local-data-public`

`degraded_but_usable` är väntat i denna demo, eftersom Chroma är avstängt och public-demo:n kör BM25-only.

1. **Klona repo:t**

   ```bash
   git clone https://github.com/itsimonfredlingjack/rag-project.git
   cd rag-project
   ```

2. **Installera backend**

   ```bash
   cd backend
   python3 -m venv .venv
   ./.venv/bin/pip install -r requirements.txt
   cd ..
   ```

3. **Installera frontend**

   ```bash
   cd apps/svensk-ragg-frontend
   npm install
   cd ../..
   ```

4. **Ladda ner corpus/index**

   ```bash
   curl -L \
     -o /tmp/public-riksdag-corpus-20260602.tar.zst \
     https://github.com/itsimonfredlingjack/rag-project/releases/download/public-riksdag-corpus-20260602/public-riksdag-corpus-20260602.tar.zst
   ```

   Verifiera checksum:

   ```bash
   echo "e2f9154e122b01cd93133888fa0476f274cd8f00b6a3fbce822bb946e8b0bbac  /tmp/public-riksdag-corpus-20260602.tar.zst" \
     | sha256sum -c -
   ```

   Packa upp till standardplats:

   ```bash
   mkdir -p /home/ai-server2/rag/local-data-public
   tar -I zstd -xf /tmp/public-riksdag-corpus-20260602.tar.zst \
     -C /home/ai-server2/rag/local-data-public
   ```

5. **Starta LLM**

   ```bash
   ollama pull gemma3:4b
   ollama serve
   ```

   Om `ollama serve` redan kör som service behöver du inte starta den manuellt.

6. **Starta backend**

   ```bash
   cd rag-project/backend
   export CONST_PROFILE=public-riksdag-demo
   ./.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8900
   ```

   Kolla readiness:

   ```bash
   curl -s http://127.0.0.1:8900/api/svensk-ragg/ready | python3 -m json.tool
   ```

   Förväntat läge:

   ```json
   {
     "status": "degraded_but_usable",
     "can_answer": true,
     "profile": "public-riksdag-demo"
   }
   ```

7. **Starta frontend**

   ```bash
   cd rag-project/apps/svensk-ragg-frontend
   npm run dev
   ```

   Öppna: `http://localhost:3003`

8. **Snabb API-test**

   ```bash
   curl -X POST http://127.0.0.1:8900/api/svensk-ragg/agent/query \
     -H "Content-Type: application/json" \
     -d '{"question":"Vilka dokument i Riksdagen nämner offentlighetsprincipen?","mode":"evidence"}'
   ```

**Viktigt:** Koden ligger i repot, men corpus/index hämtas separat från GitHub Release där `docs.jsonl` och `bm25.db` finns.

**Snabb felsökning**

- Om checksum-verifieringen misslyckas: ladda ner `.tar.zst`-filen igen och kör verifieringen på nytt.
- Om readiness inte visar `can_answer: true`: kontrollera att `CONST_PROFILE=public-riksdag-demo` är satt och att corpus/index ligger på standardplatsen.
- Om frontend inte öppnas på `localhost:3003`: kontrollera att `npm run dev` körs i `apps/svensk-ragg-frontend`.
- Om API-testet inte svarar: kontrollera att backend lyssnar på `127.0.0.1:8900` och att Ollama är igång.

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --host 127.0.0.1 --port 8900
```

Health check:

```bash
curl http://127.0.0.1:8900/api/svensk-ragg/health
```

Readiness check:

```bash
curl http://127.0.0.1:8900/api/svensk-ragg/ready
```

Backenden kan starta utan privat corpus, men full privat RAG-retrieval kräver att `CONST_CHROMADB_PATH` pekar på ett lokalt ChromaDB-index och att en lokal LLM-runtime är igång. Den publika Riksdagen-demoprofilen (`CONST_PROFILE=public-riksdag-demo`) använder public BM25 och `gemma3:4b`; operator-/legacy-ytor som `/mcp`, `/sse`, `/ws/harvest`, och generated docs är avstängda där som standard.

### Frontend

```bash
cd apps/svensk-ragg-frontend
npm ci
npm run lint
npm run build
npm run dev
```

Frontend kör normalt på `http://localhost:3003` och använder `VITE_BACKEND_URL` för att hitta backend. Se [apps/svensk-ragg-frontend/README.md](apps/svensk-ragg-frontend/README.md).

### Tester

```bash
cd backend
python -m pytest tests/ -v -m "not integration and not ollama and not slow" --tb=short
```

Integrationstester och LLM-tester kräver lokala tjänster och körs bara när motsvarande miljö finns.

## Dokumentation

| Dokument | Innehåll |
|----------|----------|
| [docs/PORTFOLIO_CASE.md](docs/PORTFOLIO_CASE.md) | Kort case-sida för snabb överblick |
| [docs/QUICK_START.md](docs/QUICK_START.md) | Lokal snabbstart utan privat databas |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Teknisk arkitektur och pipeline |
| [docs/TESTING_GUIDE.md](docs/TESTING_GUIDE.md) | Teststrategi och körkommandon |
| [apps/svensk-ragg-frontend/README.md](apps/svensk-ragg-frontend/README.md) | Frontendens körning, miljövariabler och komponenter |

## Licens

MIT - se [LICENSE](LICENSE).

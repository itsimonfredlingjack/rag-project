# Quick Start

Den här guiden visar hur repot kan köras lokalt så långt det går utan privat ChromaDB-data, BM25-index och modellvikter. Full RAG-funktion kräver att du själv bygger eller pekar ut ett lokalt corpus.

## Förutsättningar

- Python 3.12+
- Node.js 20+
- Git
- Valfritt för full privat RAG: ChromaDB-data, BM25/FTS5-index och lokal LLM-runtime,
  till exempel Ollama med `gemma4:e2b`
- För den publika Riksdagen-demoprofilen: public BM25/FTS5-index och Ollama med
  `gemma4:e2b`

## 1. Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
```

Utan privat corpus kan du ändå köra delar av backend och tester. För full retrieval behöver `backend/.env` peka på lokala index:

```dotenv
CONST_CHROMADB_PATH=/path/to/local/chromadb_data
CONST_BM25_INDEX_PATH=/path/to/local/bm25_fts5/bm25.db
CONST_LLM_BASE_URL=http://localhost:11434
CONST_SVENSK_RAGG_MODEL=gemma4:e2b
```

Om du använder Ollama-profilen:

```bash
ollama pull gemma4:e2b
./start_rag_server_ollama.sh
```

Starta backend privat/lokalt:

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8900
```

Kontrollera health endpoint:

```bash
curl http://127.0.0.1:8900/api/svensk-ragg/health
```

Swagger UI finns på `http://127.0.0.1:8900/docs` i privat/lokal profil. I
`CONST_PROFILE=public-riksdag-demo` är `/docs`, `/redoc`, `/openapi.json`,
`/mcp`, `/sse`, `/sse/message`, och `/ws/harvest` avstängda som standard.
Aktivera docs tillfälligt med `CONST_API_DOCS_ENABLED=true` vid lokal granskning.

Publik demoprofil:

```bash
export CONST_PROFILE=public-riksdag-demo
ollama pull gemma4:e2b
cd backend
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8900
```

Kontrollera den verkliga svarberedskapen:

```bash
curl http://127.0.0.1:8900/api/svensk-ragg/ready | python3 -m json.tool
```

`degraded_but_usable` är förväntat i public profile när public BM25 och LLM är
redo men Chroma är avsiktligt avstängt.

## 2. Frontend

```bash
cd apps/svensk-ragg-frontend
npm ci
npm run lint
npm run build
npm run dev
```

Frontend kör normalt på `http://localhost:3003`.

Om backend kör på annan adress:

```bash
cp .env.example .env
```

Ändra sedan:

```dotenv
VITE_BACKEND_URL=http://localhost:8900
```

## 3. Tester

Backendtester som inte uttryckligen kräver integration/LLM kan köras så här:

```bash
cd backend
source .venv/bin/activate
CONST_CHROMADB_PATH=/tmp/test_chromadb \
python -m pytest tests/ -v -m "not integration and not ollama and not slow" --tb=short
```

Frontend:

```bash
cd apps/svensk-ragg-frontend
npm run lint
npm run build
```

Docs-check:

```bash
python3 scripts/check_docs_canonical.py
```

## 4. Vad Du Kan Förvänta Dig Utan Corpus

Du kan verifiera att koden installerar, att frontend bygger, att backend importerar och att unit-tester körs. Däremot kan full fråga-till-svar med riktiga källor inte verifieras utan:

- lokal ChromaDB-data,
- lokalt BM25/FTS5-index,
- tillgänglig lokal LLM-runtime,
- rätt miljövariabler i `backend/.env`.

Det är avsiktligt: stora databaser, PDF-cache och lokala runtimeartefakter ska inte ligga i Git.

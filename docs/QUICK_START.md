# Quick Start

Den här guiden visar hur repot kan köras lokalt så långt det går utan privat ChromaDB-data, BM25-index och modellvikter. Full RAG-funktion kräver att du själv bygger eller pekar ut ett lokalt corpus.

## Förutsättningar

- Python 3.12+
- Node.js 20+
- Git
- Valfritt för full RAG: ChromaDB-data, BM25/FTS5-index och lokal LLM-runtime, till exempel Ollama eller llama-server

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
CONST_LLM_BASE_URL=http://localhost:11434
```

Starta backend:

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8900
```

Kontrollera health endpoint:

```bash
curl http://127.0.0.1:8900/api/constitutional/health
```

Swagger UI finns på `http://127.0.0.1:8900/docs` när backend kör.

## 2. Frontend

```bash
cd apps/konstitutionell-frontend
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
cd apps/konstitutionell-frontend
npm run lint
npm run build
```

Docs-check:

```bash
python scripts/check_docs_canonical.py
```

## 4. Vad Du Kan Förvänta Dig Utan Corpus

Du kan verifiera att koden installerar, att frontend bygger, att backend importerar och att unit-tester körs. Däremot kan full fråga-till-svar med riktiga källor inte verifieras utan:

- lokal ChromaDB-data,
- lokalt BM25/FTS5-index,
- tillgänglig lokal LLM-runtime,
- rätt miljövariabler i `backend/.env`.

Det är avsiktligt: stora databaser, PDF-cache och lokala runtimeartefakter ska inte ligga i Git.

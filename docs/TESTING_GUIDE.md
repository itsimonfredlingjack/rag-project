# Testing Guide

Den här guiden beskriver hur testsviten kan köras från en färsk klon och vad som kräver lokal runtime.

## Snabb Körning

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
CONST_CHROMADB_PATH=/tmp/test_chromadb \
python -m pytest tests/ -v -m "not integration and not ollama and not slow" --tb=short
```

Detta är den rekommenderade första verifieringen för portföljgenomgången. Den försöker undvika tester som kräver lokal ChromaDB-data eller LLM.

## Frontend

```bash
cd apps/svensk-ragg-frontend
npm ci
npm run lint
npm run build
```

`npm run build` kör TypeScript build och Vite build.

## Docs-Check

```bash
python3 scripts/check_docs_canonical.py
```

Checken fångar vissa gamla modellreferenser i aktiva docs. Historiska research- och internal-docs kan fortfarande nämna äldre val, men ska inte presenteras som aktuell publik sanning.

## Publik Route- och Readiness-Kontrakt

Public profile-kontraktet testas utan att bygga om corpus:

```bash
cd backend
python -m pytest \
  tests/test_public_route_surface.py \
  tests/test_public_readiness.py \
  tests/test_public_runtime_profile.py \
  tests/test_chatgpt_app_server.py \
  -q
```

Detta verifierar bland annat att public profile inte registrerar `/mcp`, legacy
`/sse`, `/sse/message`, `/ws/harvest`, eller generated docs som standard, att
dokumentwrites är avstängda, att public facets inte läcker private-lab-källor,
och att readiness kräver både public BM25 och tillgänglig public LLM-modell.

## Testkategorier

| Markör | Betydelse |
|--------|-----------|
| `integration` | Kräver externa/lokala tjänster eller verkligare systemkoppling |
| `ollama` | Kräver körande LLM-runtime |
| `slow` | Tyngre tester som inte bör vara första snabbkörning |

## Vad Som Kan Verifieras Utan Privat Databas

- Import och initiering av många backendkomponenter.
- API-kontrakt och pydanticmodeller.
- Prompt-, citation-, intent-, routing- och utilitylogik.
- BM25-servicebeteende där tester mockar eller bygger testdata.
- Frontend lint/build och TypeScript-kontrakt.
- Docs canonicality check i CI.

## Vad Som Kräver Lokal Runtime

Full RAG-fråga med verkliga svar och källor kräver:

- `CONST_CHROMADB_PATH` till ett lokalt ChromaDB-index.
- BM25/FTS5-index om hybrid retrieval ska testas realistiskt.
- Lokal LLM-runtime på `CONST_LLM_BASE_URL`.
- Tillräckliga resurser för embeddings/reranking/modellkörning.

Public Riksdagen-demo kräver inte Chroma, embeddings eller reranking, men kräver
det förberedda public BM25-indexet och en lokal `gemma3:4b`-modell i Ollama.

Om dessa saknas ska testresultat och README beskriva det som en blockerad lokal verifiering, inte som passerad end-to-end-funktion.

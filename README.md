<div align="center">

# Svensk RAG

### RAG-system för svenska offentliga dokument

[![CI](https://github.com/itsimonfredlingjack/rag-project/actions/workflows/ci.yml/badge.svg)](https://github.com/itsimonfredlingjack/rag-project/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React 19](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)](https://react.dev/)

**Personligt lärande- och portföljprojekt** — inte en produkt eller tjänst.

</div>

---

Svensk RAG är ett lokalt kört Retrieval-Augmented Generation-system för svenska myndighets- och juridiska dokument.

## Arkitektur och systemstatus (källa till sanning)

- **System snapshot:** [`docs/SYSTEM_SNAPSHOT.md`](docs/SYSTEM_SNAPSHOT.md)
- **Nuvarande arkitektur (Mermaid):** [`docs/architecture/current-system.mmd`](docs/architecture/current-system.mmd)
- **Avsedd arkitektur (Mermaid):** [`docs/architecture/intended-system.mmd`](docs/architecture/intended-system.mmd)

Regenerera snapshot:

```bash
python scripts/generate_system_snapshot.py
```

## Snabbstart

### Backend

```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8900
```

### Frontend

```bash
cd apps/konstitutionell-frontend
npm install
npm run dev
```

## API

- Primär prefix: `/api/svensk-rag/*`
- Legacy-kompatibilitet: `/api/constitutional/*` (behålls tillfälligt för bakåtkompatibilitet)

## Migration note

Projektet har bytt publik branding från "Svensk RAG" till **Svensk RAG**.
Interna legacy-namn (t.ex. vissa filnamn, env-prefix `CONST_`, och `constitutional` i kodstrukturer) är kvar tills vidare för att undvika brytande ändringar.

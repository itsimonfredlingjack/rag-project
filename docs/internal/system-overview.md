# Historical Runtime Overview

> Internal/historical operations note. This file is not part of the public first-read documentation.

> Svenska myndighetsdokument - sökning, analys och RAG

**Status:** Historical operations snapshot
**Dokument:** Historical local runtime numbers, not verified from a fresh clone
**Updated:** 2026-02-07

---

## Document status

This page is a historical operations overview for one local runtime stack.

- **Status:** Historical
- **Last reviewed:** February 13, 2026
- **Canonical public docs:** `docs/PORTFOLIO_CASE.md`, `docs/QUICK_START.md`, `docs/ARCHITECTURE.md`
- **Documentation map:** `docs/README_DOCS_AND_RAG_INSTRUCTIONS.md`

---

## Quick Stats

| Metric | Value |
|--------|-------|
| Total Documents | Historical local runtime number; re-verify before citing |
| Vector Dimensions | 1024 |
| Embedding Model | jinaai/jina-embeddings-v3 |
| Storage | ChromaDB |
| LLM | Ministral-3-14B-Instruct-2512-Q4_K_M.gguf via llama-server |

---

## Data Sources

### Riksdagen (Parliament)
- **Dokument:** ~230K
- **Typer:** prop, mot, sou, bet, ds
- **API:** data.riksdagen.se
- **Collection:** `riksdag_documents_p1`

### Swedish Government Docs
- **Dokument:** ~305K
- **Typer:** SFS, propositioner, remisser
- **Collection:** `swedish_gov_docs`

### DiVA (Academic)
- **Dokument:** ~960K metadata (ej indexerat)
- **Källa:** DiVA Portal JSON exports

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     constitutional-cli                       │
│         search | status | harvest | embed | ingest          │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                       RAG API (8900)                         │
│              /search /health /embed                          │
└─────────────────────────────────────────────────────────────┘
         │                    │                    │
         ▼                    ▼                    ▼
┌─────────────┐      ┌─────────────┐      ┌─────────────┐
│  ChromaDB   │      │llama-server │      │ automation  │
│    (local)  │      │   (8080)    │      │   (5678)    │
│ local docs  │      │Ministral-3  │      │  Workflows  │
└─────────────┘      └─────────────┘      └─────────────┘
```

---

## Services

| Service | Port | Status | Purpose |
|---------|------|--------|---------|
| Svensk Ragg Backend | 8900 | 🟢 Active | FastAPI RAG API |
| ChromaDB | local | Active | Vector database |
| llama-server | 8080 | Running | Local LLM inference (OpenAI-compatible) |
| Ollama | 11434 | Optional | Optional fallback only |
| Automation | local | Historical | Workflow automation |

### Backend Service Status

| Tjänst                    | Status     | Port | Autostart   |
|---------------------------|------------|------|-------------|
| Svensk Ragg Backend | 🟢 Active  | 8900 | ✅ Enabled  |
| Simons AI Backend         | 🔴 Removed | -    | ❌ Disabled |

**Bekräftade Ändringar:**
1. ✅ simons-ai-backend.service borttagen från systemd
2. ✅ Port 8900 ägs av svensk-ragg-backend (uvicorn binds 8000, exposed as 8900)
3. ✅ Health endpoint svarar korrekt
4. ✅ RAG queries fungerar (Ministral-3-14B-Instruct-2512 via llama-server, CRAG enabled)

**System Commands:**
```bash
# Status
systemctl --user status svensk-ragg-backend

# Restart
systemctl --user restart svensk-ragg-backend

# Live logs
journalctl --user -u svensk-ragg-backend -f
```

**API Base URL:** `http://localhost:8900/api/svensk-ragg`

All Svensk Ragg-logik är nu fristående i `09_CONSTITUTIONAL-AI/backend/` med egen systemd service! 🚀

---

## Collections (ChromaDB)

All collections are suffixed with `_jina_v3_1024`.

| Collection | Documents | Dimensions | Use Case |
|------------|-----------|------------|----------|
| riksdag_documents_p1_jina_v3_1024 | 230K | 1024 | Riksdagen docs |
| swedish_gov_docs_jina_v3_1024 | 308K | 1024 | Swedish gov docs |
| diva_research_jina_v3_1024 | historical local count | 1024 | DiVA research metadata |

---

## Key Files

```
09_CONSTITUTIONAL-AI/
├── backend/                   # Backend application (NEW)
│   ├── app/
│   │   ├── main.py            # FastAPI application
│   │   ├── config.py           # Configuration
│   │   ├── api/               # API routes
│   │   ├── services/          # Business logic services
│   │   ├── core/              # Core utilities (exceptions, handlers)
│   │   └── utils/             # Utility functions
│   ├── requirements.txt       # Python dependencies
│   └── pyproject.toml         # Project configuration
├── constitutional_cli.py      # Unified CLI
├── constitutional              # Bash wrapper
├── rag_benchmark.py           # Quality testing
├── chromadb_to_qdrant.py      # Migration tool (historical, Qdrant fully deprecated)
├── corpus_bridge.py           # Corpus → Second Brain
├── chromadb_data/             # Original ChromaDB (backup)
├── systemd/                   # Systemd service files
│   └── svensk-ragg-backend.service
└── docs/                      # Documentation
    ├── constitutional-cli.md
    ├── system-overview.md
    └── migration-log.md
```

---

## Benchmark Results (2025-12-15)

**Grade: A**

| Metric | Value |
|--------|-------|
| Queries | 19/20 successful |
| Mean Score | 0.7302 |
| Keyword Hit Rate | 81% |
| Mean Latency | 113s (with LLM) |

### By Category
- Social: 0.783
- Municipal: 0.773
- Health: 0.748
- Administrative: 0.740
- Education: 0.737

---

## Common Tasks

### Search Documents
```bash
constitutional search "GDPR personuppgifter" --top-k 10
```

### Check System Status
```bash
constitutional status
```

### Run Benchmark
```bash
constitutional benchmark --quick
```

### Ingest New Documents
```bash
constitutional ingest ./nya_dokument/ --recursive
```

---

## Related

- [[constitutional-cli]] - CLI documentation
- [[migration-log]] - Migration history (ChromaDB is current, Qdrant fully deprecated)
- [[rag-benchmark]] - Benchmark methodology
- [[second-brain-architecture]] - Memory engine design

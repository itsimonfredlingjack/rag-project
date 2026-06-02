# Project-local Codex agents

This directory contains project-specific Codex custom agents for the Swedish public-document RAG system.
They are intentionally narrower than the global VoltAgent library in `~/.codex/agents/`.

Use these when the task depends on this repository's real runtime paths, readiness gates, or data stores:

- `rag_runtime_architect`: backend API, retrieval orchestration, prompts, model wiring, response contracts.
- `corpus_indexing_engineer`: Chroma/Jina, BM25/FTS5, parent store, recovered JSONL, scrapers, indexers.
- `rag_eval_quality_engineer`: golden sets, citation correctness, faithfulness, retrieval quality, regression gates.
- `frontend_experience_engineer`: React/Vite/Electron UI, SSE state flow, citations, source panels, pipeline visualization, accessibility, backend contract alignment.
- `ops_readiness_engineer`: local bring-up, ports, logs, Docker/systemd, host prerequisites, `/api/svensk-ragg/ready`.
- `docs_canonicality_curator`: public docs and architecture notes aligned with verified runtime truth.
- `security_guardrails_engineer`: auth, rate limits, prompt injection, write endpoints, CORS, SSE leakage.

The global VoltAgent agents are still useful for generic work. Prefer these project-local agents when the answer needs to know this repo's exact files, commands, or local readiness semantics.

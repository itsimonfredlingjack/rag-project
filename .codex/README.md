# Project-local Codex agents

This directory contains project-specific Codex custom agents for the constitutional RAG system.
They are intentionally narrower than the global VoltAgent library in `~/.codex/agents/`.

Use these when the task depends on this repository's real runtime paths, readiness gates, or data stores:

- `constitutional_rag_runtime_architect`: backend API, retrieval orchestration, prompts, model wiring, response contracts.
- `constitutional_corpus_indexing_engineer`: Chroma/Jina, BM25/FTS5, parent store, recovered JSONL, scrapers, indexers.
- `constitutional_frontend_client_engineer`: React/Vite UI, Zustand/SSE state, document reader, Electron shell.
- `constitutional_eval_quality_engineer`: golden sets, citation correctness, faithfulness, retrieval quality, regression gates.
- `constitutional_ops_readiness_engineer`: local bring-up, ports, logs, Docker/systemd, host prerequisites, `/api/constitutional/ready`.
- `constitutional_docs_canonicality_curator`: public docs and architecture notes aligned with verified runtime truth.
- `constitutional_security_guardrails_engineer`: auth, rate limits, prompt injection, write endpoints, CORS, SSE leakage.

The global VoltAgent agents are still useful for generic work. Prefer these project-local agents when the answer needs to know this repo's exact files, commands, or local readiness semantics.

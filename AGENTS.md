# Repository Guidelines

## Project structure & module organization
This repository combines a FastAPI backend and data pipelines for scraping,
indexing, and evaluation.

- `backend/`: API and RAG orchestration (`backend/app/` for runtime code,
  `backend/tests/` for backend-focused tests).
- `scrapers/`: Source collection scripts (`myndigheter/`, `kommuner/`,
  `media/`).
- `indexers/`: ChromaDB indexing and ingestion utilities.
- `tests/`: Root-level integration and contract-style tests.
- `docs/`: Architecture, operations, and evaluation documentation.

## Build, test, and development commands
Use these commands from the repository root unless noted otherwise.

- Backend dev server: `cd backend && uvicorn app.main:app --host 0.0.0.0 --port 8900`
- Python lint/format: `ruff check .`, `ruff check --fix .`, `ruff format .`
- Backend tests (fast path): `cd backend && pytest tests/ -v -m "not integration and not ollama and not slow"`
- Full local stack: `docker compose up`

## Coding style & naming conventions
Follow the configured tooling instead of ad hoc formatting.

- Python: Ruff + MyPy, line length 100, spaces for indentation, double quotes.
- Naming: `snake_case` for Python functions and variables, `PascalCase` for
  classes, `UPPER_SNAKE_CASE` for constants.
- Keep modules focused. Place new backend business logic in
  `backend/app/services/` and API route wiring in `backend/app/api/`.

## Testing guidelines
Pytest is the canonical test runner for Python code.

- Test file naming: `test_*.py` or `*_test.py`.
- Mark long-running or environment-dependent tests with existing markers
  (`integration`, `slow`, `ollama`).
- Add unit tests for new logic and at least one integration-level test when
  behavior crosses service boundaries.

## Project-local Codex subagents
This checkout has project-specific Codex agents in `.codex/agents/`. Use them
when work depends on this repository's live RAG paths, data stores, or runtime
truth rather than generic framework behavior.

- `rag_runtime_architect`: backend API contracts, retrieval
  orchestration, prompts, model wiring, citations, structured output, and
  streaming response contracts.
- `corpus_indexing_engineer`: raw files vs indexed documents,
  Chroma/Jina, BM25/FTS5, parent store, recovered JSONL, scrapers, and
  ingestion utilities.
- `rag_eval_quality_engineer`: golden sets, retrieval quality,
  citation correctness, answer faithfulness, regression thresholds, and
  build/test gates.
- `frontend_experience_engineer`: React/Vite/Electron UI,
  SSE state flow, citations, source panels, pipeline visualization,
  accessibility, and backend contract alignment.
- `ops_readiness_engineer`: local bring-up, ports, logs,
  Docker/systemd, host prerequisites, and `/api/svensk-ragg/ready`.
- `docs_canonicality_curator`: public docs and architecture
  notes aligned with verified runtime truth; historical notes under
  `docs/internal/` are non-canonical unless re-verified.
- `security_guardrails_engineer`: auth, rate limits, CORS,
  write endpoints, prompt injection, SSE leakage, and Swedish
  refusal/guardrail behavior.

Operational truth order for this repo: inspect
`backend/app/services/config_service.py`, then live readiness through
`/api/svensk-ragg/ready`, then logs/tests. Treat historical docs and restored
files on disk as evidence to verify, not proof that documents are indexed into
active retrieval stores.

## Commit & pull request guidelines
History follows Conventional Commits, for example:
`feat(eval): add chunk quality analysis`.

- Format commits as `<type>(<scope>): <description>`.
- Before opening a PR, run relevant lint/tests locally.
- PRs should include: what changed, why it changed, and impacted paths.

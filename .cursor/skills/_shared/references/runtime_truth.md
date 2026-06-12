# Runtime truth hierarchy

When optimizing or verifying the public Riksdagen demo, read sources in this order:

1. **`backend/app/services/config_service.py`** — profile overrides and `PUBLIC_RIKSDAG_MODEL`
2. **Live `GET /api/svensk-ragg/ready`** — BM25, LLM model, `can_answer`
3. **`logs/backend.log`** — runtime errors and pipeline timing
4. **`backend/tests/test_public_runtime_profile.py`** — expected public defaults
5. **Docs** (`MODEL_POLICY.md`, `PUBLIC_RIKSDAG_DEMO.md`) — informative; WARN on drift, do not treat as runtime truth
6. **GitHub main** — never use as sole source; local uncommitted tuning is valid until pushed

Public profile scope: `public-riksdag-demo`, corpus `riksdagen_open_data_only`, BM25-only retrieval.
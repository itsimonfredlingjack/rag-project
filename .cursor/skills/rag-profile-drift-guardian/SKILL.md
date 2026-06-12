---
name: rag-profile-drift-guardian
description: Detect configuration drift for the public-riksdag-demo RAG profile by comparing config_service.py, start_system.sh, status.sh, docs, and live /ready. Use before commit, when the user mentions profile drift, config mismatch, 2048 vs 4096 context, model inconsistency, or public profile sanity checks.
---

# RAG Profile Drift Guardian

Fail-closed drift detection for `public-riksdag-demo`. Runtime truth order: see `_shared/references/runtime_truth.md`.

## Run

```bash
python3 .cursor/skills/rag-profile-drift-guardian/scripts/check_public_profile_drift.py \
  --json-out /tmp/rag-profile-drift.json
```

Exit code `1` only on **DRIFT** (not WARN).

## Checks

- `corpus_scope == riksdagen_open_data_only`
- Chroma off, BM25 on, CRAG/rerank/critic off
- Public data paths under `local-data-public/riksdag` — no private leak
- Model ID matches: `config_service.py`, `start_system.sh`, `status.sh`, `/ready`
- Warmup `num_ctx` in `start_system.sh` matches `ollama_num_ctx` from config
- Docs WARN (not block) if model/context text lags code

## Output

Report `DRIFT` / `WARN` / `OK` per check. Never auto-patch — list exact files to fix.

## When to run

- Before any optimization commit
- After manual edits to `config_service.py` or startup scripts
- When GitHub main and local config may differ (read local code, not remote)
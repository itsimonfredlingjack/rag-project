---
name: rag-coldstart-warmup-sentinel
description: Verify Ollama warmup matches public profile model and num_ctx, compare cold vs warm query latency, and detect loaded-model VRAM drift. Use when the first query is slow, warmup misaligned, ollama ps shows wrong model, or keep_alive/cold-load issues appear.
---

# RAG Coldstart Warmup Sentinel

## Run

```bash
bash .cursor/skills/rag-coldstart-warmup-sentinel/scripts/check_warmup_alignment.sh
```

Writes `/tmp/rag-warmup-check.json`.

## Checks

- `start_system.sh` warmup `num_ctx` == `config_service.py` `ollama_num_ctx`
- `ollama ps` loaded model == `PUBLIC_RIKSDAG_MODEL`
- `/ready` LLM model matches config
- Cold vs warm short-chat latency (indicative)

## Fix guidance (no auto-patch)

- Align warmup JSON in `start_system.sh` with config ctx
- Remove extra Ollama models eating VRAM
- Ensure `start_system.sh` runs before user-facing queries

## Fail

Exit `1` on warmup ctx mismatch (DRIFT).
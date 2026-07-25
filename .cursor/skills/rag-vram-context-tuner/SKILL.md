---
name: rag-vram-context-tuner
description: Benchmark Ollama num_ctx settings for public-riksdag-demo on RTX 2060 6GB VRAM, analyze CPU/GPU split and rag_sv latency, and recommend a safe context window. Use when the user mentions RAG latency, num_ctx, KV-cache, context window, CPU/GPU split, p50/p95, gemma slow, or comparing 1024/2048/4096 context.
---

# RAG VRAM Context Tuner

Bounded context sweep for local Ollama on 6 GB GPU. **Never patch config directly** — recommend, then require eval bouncer.

## Run

```bash
# Full sweep (~10–25 min)
python3 .cursor/skills/rag-vram-context-tuner/scripts/run_context_sweep.py

# Quick smoke (2048 vs 4096)
python3 .cursor/skills/rag-vram-context-tuner/scripts/run_context_sweep.py --contexts 2048,4096

# Plan only
python3 .cursor/skills/rag-vram-context-tuner/scripts/run_context_sweep.py --dry-run
```

Uses [`scripts/benchmark_ollama_models.py`](../../scripts/benchmark_ollama_models.py). See `references/context_sweep_matrix.md`.

## Required output format

```text
Recommended: ollama_num_ctx=<N>
Reason: ...
Do not use: 4096 on RTX 2060 6GB unless ...
Required follow-up: quick eval 5Q → full eval 30Q
Rollback: config_service.py + start_system.sh warmup num_ctx
```

## Rules

- Read current ctx from `ConfigSettings(profile=public-riksdag-demo)` — not docs
- Do not enable Chroma, CRAG, or reranking
- Any recommended change requires `rag-eval-regression-bouncer` Level 2 before merge

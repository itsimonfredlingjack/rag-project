---
name: rag-token-budget-profiler
description: Profile per-question token usage and latency from public demo eval rows to decide whether num_predict, context window, or source payload should change. Use when output is verbose, tokens_generated is high, num_predict tuning is considered, or latency is high despite short answers.
---

# RAG Token Budget Profiler

Analyze eval artifacts — do not change config without evidence.

## Run

```bash
cd backend
.venv/bin/python scripts/run_public_demo_eval.py --limit 5 --output /tmp/rag-token-profile.json
python3 ../.cursor/skills/rag-token-budget-profiler/scripts/profile_tokens.py /tmp/rag-token-profile.json
```

## Decision rules

1. Read `mode_evidence_num_predict` from `ConfigSettings(public-riksdag-demo)`
2. Per-row: `tokens_generated`, `citation_count`, `source_count`, `latency_ms`
3. **Lower num_predict** only if median output tokens > 60% of budget (see `references/token_breakdown_schema.md`)
4. If output tokens are low but latency high → recommend ctx/source trimming, **not** num_predict cut

## Never

- Reflex 1024→768 without token profile proof
- Patch orchestrator or prompts in this skill — report only
# Token breakdown schema

## Per-question fields (eval rows)

| Field | Use |
| --- | --- |
| `tokens_generated` | LLM output size |
| `tokens_generated_source` | `llm_stats` vs approximation |
| `citation_count` | Citation density |
| `source_count` | Retrieved source payload |
| `latency_ms` | End-to-end cost |

## Config budget

- `mode_evidence_num_predict` — default 1024; public profile may inherit without override
- `ollama_num_ctx` — affects prompt+KV, not output cap

## num_predict cut rule

Only recommend lowering `mode_evidence_num_predict` when:

```text
median(tokens_generated) > 0.60 * mode_evidence_num_predict
```

If `median(tokens_generated) < 0.30 * budget` but latency is high → investigate ctx and source assembly in orchestrator, not output cap.

# Context sweep matrix

Default sweep: `1024, 1536, 2048, 3072, 4096`

## Interpretation (RTX 2060 6 GB)

| ctx | Typical pattern |
| --- | --- |
| 1024–2048 | Lower KV pressure; often better rag_sv wall time |
| 3072 | Middle ground — verify citations on full eval |
| 4096 | Often 70%+ CPU offload for gemma4:e2b; higher p50 in pipeline |

## Decision criteria

1. Lowest `rag_sv` `wall_s` with `ok=True`
2. Prefer lower `processor` CPU share when wall times are close
3. Never recommend ctx change without eval invariants pass
4. If recommended ctx != current ctx, list exact patch lines + rollback

## Hardware note

Embeddings default to CPU (`CONST_EMBEDDING_DEVICE=cpu`) — full VRAM budget goes to Ollama.
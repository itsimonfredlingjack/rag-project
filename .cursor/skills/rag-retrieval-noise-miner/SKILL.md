---
name: rag-retrieval-noise-miner
description: Analyze public BM25 retrieval misses from eval JSON rows, classify noise types (wrong chunk, wrong doc, duplicates, weak metadata), and recommend corpus or index fixes not LLM prompt changes. Use when retrieval_hit is low, BM25 noise, wrong chunks, or duplicate hits appear in public-riksdag-demo.
---

# RAG Retrieval Noise Miner

Public profile is BM25-only — optimize retrieval/index, not LLM prompts.

## Run

```bash
cd backend
.venv/bin/python scripts/run_public_demo_eval.py --limit 10 --output /tmp/rag-retrieval-miner.json
python3 ../.cursor/skills/rag-retrieval-noise-miner/scripts/analyze_retrieval_noise.py /tmp/rag-retrieval-miner.json
```

## Noise taxonomy

See `references/noise_taxonomy.md`.

## Recommendations allowed

- Query normalization tweaks (`public_bm25_query_service`)
- BM25 index rebuild via `scripts/build_bm25_fts5.py` — **only with explicit user order**
- Chunk/metadata fixes in corpus pipeline

## Not allowed

- Enable Chroma/reranking/CRAG in public profile
- Prompt or model changes as first-line fix for retrieval miss

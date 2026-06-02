# Active Scripts

This folder intentionally contains only scripts that are part of the current public demo and repo maintenance surface.

- `build_public_riksdag_jsonl.py` builds the public Riksdag JSONL corpus source.
- `build_bm25_fts5.py` builds the BM25/FTS5 search artifact used by the public profile.
- `benchmark_ollama_models.py` runs local Ollama model probes.
- `check_docs_canonical.py` enforces canonical documentation references.
- `check_port_consistency.sh` verifies that documented ports match runtime configuration.

Historical one-off scrapers, DiVA/SGU/KI/Chalmers harvesters, Chroma recovery jobs, and Ministral benchmarks were removed from this root folder. Source collection code that is still kept lives under `scrapers/` or `indexers/`.

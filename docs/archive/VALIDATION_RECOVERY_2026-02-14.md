# Recovery & Validation Report — 2026-02-14

## Problem

Backend (FastAPI port 8900) consuming ~10.3GB RAM, OOM-ing during RAG queries:
```
DefaultCPUAllocator: can't allocate memory: you tried to allocate 512004096 bytes
```

Additionally, two git worktrees existed with diverging code — production ran from
a stale feature branch (`feat/chroma-integrity-gate`) while `main` was 2 commits ahead.

## Root Cause

BM25 index loaded unconditionally (~3-4GB: `docs.jsonl` 3.47GB + `sr_state.npz` 521MB)
on top of Jina v3 embeddings (~2.3GB) + reranker (~560MB), exceeding available RAM
when combined with query-time allocations.

## Fix Applied

**Commit:** `4a8293e` on `main`

1. **config_service.py**: Added `bm25_enabled: bool = False` to `ConfigSettings` + property accessor
2. **retrieval_service.py**: Gated BM25 initialization behind `self.config.bm25_enabled`
3. **backend/.env**: Added `CONST_BM25_ENABLED=false` (explicit; code default is already False)

The `RetrievalOrchestrator` already null-guards `bm25_service` at every usage point,
so passing `bm25_service=None` cleanly disables BM25 everywhere.

## Worktree Consolidation

1. Verified dirty changes on `feat/chroma-integrity-gate` matched `main` for all key service files
2. Stashed working tree as safety backup
3. Removed `__main` worktree
4. Checked out `main` (clean working tree)
5. Deleted stale `feat/chroma-integrity-gate` branch

## Test Results

```
backend/tests/: 477 passed, 44 deselected in 4.58s
tests/ (root):  241 passed, 1 skipped in 3.80s
Total:          718 passed, 0 failures
```

Pre-commit hooks all passed (ruff, ruff-format, trailing whitespace, etc.).

## Post-Restart Validation

### Startup Logs (confirmed)
```
BM25 disabled via config (CONST_BM25_ENABLED=false). Dense-only retrieval active.
RetrievalOrchestrator initialized (bm25_weight=1.2, rrf_k=45.0)
Orchestrator & Retrieval Stack ONLINE
```

No `DefaultCPUAllocator` errors.

### Memory
| Metric | Before Fix | After Fix |
|--------|-----------|-----------|
| Backend RSS | ~10.3GB (+ OOM crashes) | ~11.6GB (with reranker loaded) |
| System available | Depleted (swap thrashing) | 17GB available |
| OOM errors | Every RAG query | None |

Note: Post-fix RSS includes the reranker (~560MB) which previously never loaded
(queries OOM-ed during retrieval before reaching reranking).

### Health Checks
- `/api/constitutional/health`: **healthy** (all services initialized)
- `/api/constitutional/ready`: **ready** (ChromaDB 54 collections, LLM OK)

### Query Validation
Retrieval pipeline fully functional:
- Dense search: OK (5 collections verified, 1024-dim queries accepted)
- Reranking: OK (Jina reranker v2, first query loaded model in 7.7s)
- CRAG grading: OK (5/10 relevant at 50.0% in 2116ms)
- Self-reflection: OK (sufficient_evidence=True, confidence=0.95)

**Known remaining issue:** LLM generation fails with context overflow (4334 tokens
requested vs 4096 per slot). This is a pre-existing llama-server configuration issue
(`--parallel 2` splits 8192 context to 4096/slot). Queries previously never reached
this stage because they OOM-ed during retrieval. Fix: set `--parallel 1` or increase
`-c 16384` in `systemd/constitutional-ai-llm.service`.

## Re-enabling BM25

When more RAM is available or the server is upgraded:
```bash
# In backend/.env:
CONST_BM25_ENABLED=true

# Then restart:
systemctl --user restart constitutional-ai-backend
```

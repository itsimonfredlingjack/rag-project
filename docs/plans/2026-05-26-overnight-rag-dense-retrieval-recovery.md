# Overnight RAG Dense Retrieval Recovery Implementation Plan

> **For agent:** REQUIRED SUB-SKILL: Use executing-plans to implement this plan task-by-task.

**Goal:** Restore the active dense Jina/Chroma retrieval layer, then measure readiness and retrieval quality before changing model, prompt, or ranking settings.

**Architecture:** The backend reads `backend/.env`, expects five `_jina_v3_1024` Chroma collections under `/home/ai-server2/rag/local-data/chromadb`, and already has a working BM25/FTS5 sidecar at `/home/ai-server2/rag/local-data/bm25_fts5/bm25.db`. The overnight run streams restored BM25 JSONL into Chroma with Jina v3 `retrieval.passage` embeddings, using the importer checkpoint to resume safely.

**Tech Stack:** FastAPI backend, ChromaDB persistent store, SQLite FTS5 BM25, `sentence-transformers`, `jinaai/jina-embeddings-v3`, Ollama `gemma4:e2b`, pytest/eval scripts.

---

## Goal Brief

**Goal**
By the next morning, the local RAG should have non-empty active dense Chroma collections compatible with the configured Jina v3 embedding model, plus logs/checkpoints showing exactly how far the import and validation got.

**Success Criteria**
- Active Chroma path `/home/ai-server2/rag/local-data/chromadb` contains the configured collections:
  `sfs_lagtext_jina_v3_1024`, `riksdag_documents_p1_jina_v3_1024`, `swedish_gov_docs_jina_v3_1024`, `diva_research_jina_v3_1024`, and `procedural_guides_jina_v3_1024`.
- Import checkpoint at `migration_checkpoints/jsonl_to_jina_chroma.json` records progress and can be reused after interruption.
- BM25 remains readable at `/home/ai-server2/rag/local-data/bm25_fts5/bm25.db`.
- After import, `scripts/chroma_integrity_check.py` can query the active collections.
- After backend startup, `/api/svensk-ragg/ready` is the go/no-go signal for benchmark work.

**Scope**
- In: active Chroma import from restored JSONL, checkpointing, logs, Chroma integrity, readiness, retrieval-quality benchmark.
- Out: deleting/rebuilding BM25, changing model policy, enabling reranking/CRAG/critic, raising context window, Docker/systemd migration, frontend redesign.

**Constraints**
- Existing dirty worktree must be preserved.
- Backend and frontend should stay down during GPU import to leave VRAM for embeddings.
- Use explicit `/home/ai-server2/...` paths; do not rely on stale `/home/simon/...` defaults.
- Treat `/api/svensk-ragg/health` as process health only; `/api/svensk-ragg/ready` is the real RAG gate.
- Long-running writes must be checkpointed and logged.

**Open Questions**
- None blocking. The user approved overnight work, and dry-run/write-test evidence confirms the importer path.

**First Action**
Launch the checkpointed Chroma import with explicit `CONST_CHROMADB_PATH` and `CONST_BM25_INDEX_PATH`.

## Evidence Collected

- `./status.sh` showed Ollama reachable, backend/frontend down, and no loaded Ollama model.
- `backend/.env` points active Chroma to `/home/ai-server2/rag/local-data/chromadb` and active BM25 to `/home/ai-server2/rag/local-data/bm25_fts5/bm25.db`.
- Active Chroma is currently about `188K`, with no useful collections.
- Active BM25 is about `3.8G` with `1,372,290` rows according to subagent inspection.
- Restored input JSONL exists at `/home/ai-server2/rag/RAG_TRANSFER/constitutional-ai-preservation-2026-04-10-selected/bm25_index/docs.jsonl` with `1,372,290` rows.
- GPU dry-run succeeded for 16 JSONL rows plus 7 procedural guides.
- Tiny `/tmp` write test failed once because the manifest fallback used stale `/home/simon/...`; rerun with `CONST_BM25_INDEX_PATH=/home/ai-server2/rag/local-data/bm25_fts5/bm25.db` succeeded.
- Tiny `/tmp` write test produced counts: `sfs_lagtext_jina_v3_1024: 16`, `procedural_guides_jina_v3_1024: 7`, other collections `0` as expected for a 16-line SFS-only slice.

## Task 1: Start Checkpointed Dense Import

**Files:**
- Read: `scripts/import_jsonl_to_jina_chroma.py`
- Write data: `/home/ai-server2/rag/local-data/chromadb`
- Write checkpoint: `migration_checkpoints/jsonl_to_jina_chroma.json`
- Write log: `logs/import_jsonl_to_jina_chroma_<RUN_ID>.log`

**Step 1: Confirm GPU and services**

Run:

```bash
cd /home/ai-server2/rag/rag-project
nvidia-smi --query-gpu=name,memory.used,memory.total,temperature.gpu,utilization.gpu --format=csv,noheader,nounits
curl -fsS --max-time 5 http://127.0.0.1:11434/api/ps
lsof -i :8900 -i :3003 2>/dev/null || true
```

Expected:
- GPU has free VRAM.
- Ollama has no loaded model, or at least no active generation.
- Backend/frontend ports are free.

**Step 2: Start import**

Run:

```bash
cd /home/ai-server2/rag/rag-project
mkdir -p logs migration_checkpoints
RUN_ID=$(date +%Y%m%d_%H%M%S)

CONST_CHROMADB_PATH=/home/ai-server2/rag/local-data/chromadb \
CONST_BM25_INDEX_PATH=/home/ai-server2/rag/local-data/bm25_fts5/bm25.db \
nohup backend/.venv/bin/python scripts/import_jsonl_to_jina_chroma.py \
  --input /home/ai-server2/rag/RAG_TRANSFER/constitutional-ai-preservation-2026-04-10-selected/bm25_index/docs.jsonl \
  --procedural /home/ai-server2/rag/rag-project/backend/data/procedural_guides.json \
  --chroma /home/ai-server2/rag/local-data/chromadb \
  --checkpoint-file /home/ai-server2/rag/rag-project/migration_checkpoints/jsonl_to_jina_chroma.json \
  --device gpu \
  --batch-size 8 \
  > "logs/import_jsonl_to_jina_chroma_${RUN_ID}.log" 2>&1 &

echo "$!" > logs/import_jsonl_to_jina_chroma.pid
echo "RUN_ID=${RUN_ID}"
echo "PID=$(cat logs/import_jsonl_to_jina_chroma.pid)"
```

Expected:
- Process remains running.
- Log starts with row counting, model loading, and `Starting import`.
- Checkpoint file updates after batches.

**Step 3: Monitor without interrupting**

Run:

```bash
cd /home/ai-server2/rag/rag-project
PID=$(cat logs/import_jsonl_to_jina_chroma.pid)
ps -p "$PID" -o pid,stat,etime,%mem,%cpu,cmd
tail -40 "$(ls -t logs/import_jsonl_to_jina_chroma_*.log | head -1)"
cat migration_checkpoints/jsonl_to_jina_chroma.json
du -sh /home/ai-server2/rag/local-data/chromadb
```

Expected:
- `last_jsonl_line` and `written_total` increase over time.
- Chroma directory grows.

## Task 2: Validate Dense Store After Import Stops Or Completes

**Files:**
- Read data: `/home/ai-server2/rag/local-data/chromadb`
- Write logs: `logs/chroma_integrity_<RUN_ID>.log`, `logs/chroma_integrity_<RUN_ID>.json`

**Step 1: Inspect collection counts**

Run:

```bash
cd /home/ai-server2/rag/rag-project
backend/.venv/bin/python - <<'PY'
import chromadb
client = chromadb.PersistentClient(path="/home/ai-server2/rag/local-data/chromadb")
for col in sorted(client.list_collections(), key=lambda c: c.name):
    print(f"{col.name}: {col.count()}")
PY
```

Expected:
- Collections exist and counts reflect import progress.

**Step 2: Run Chroma integrity gate**

Run:

```bash
cd /home/ai-server2/rag/rag-project
RUN_ID=$(date +%Y%m%d_%H%M%S)
backend/.venv/bin/python scripts/chroma_integrity_check.py \
  --path /home/ai-server2/rag/local-data/chromadb \
  --collections sfs_lagtext_jina_v3_1024,riksdag_documents_p1_jina_v3_1024,swedish_gov_docs_jina_v3_1024,diva_research_jina_v3_1024,procedural_guides_jina_v3_1024 \
  --loops 3 \
  --n-results 3 \
  --log "logs/chroma_integrity_${RUN_ID}.log" \
  --output-json "logs/chroma_integrity_${RUN_ID}.json"
```

Expected:
- Exit `0` only when all listed collections exist and respond to query probes.

## Task 3: Start Runtime And Capture Readiness

**Files:**
- Read: `start_system.sh`, `status.sh`, `backend/.env`
- Write logs: `logs/start_system_<RUN_ID>.log`, `logs/status_<RUN_ID>.log`, `logs/ready_<RUN_ID>.json`

**Step 1: Start system after import validation**

Run:

```bash
cd /home/ai-server2/rag/rag-project
RUN_ID=$(date +%Y%m%d_%H%M%S)
OLLAMA_MODEL=gemma4:e2b \
BACKEND_PORT=8900 \
FRONTEND_PORT=3003 \
LOG_DIR=logs \
./start_system.sh > "logs/start_system_${RUN_ID}.log" 2>&1
```

Expected:
- Backend health endpoint responds.
- Frontend responds.

**Step 2: Capture readiness**

Run:

```bash
cd /home/ai-server2/rag/rag-project
RUN_ID=$(date +%Y%m%d_%H%M%S)
./status.sh 2>&1 | tee "logs/status_${RUN_ID}.log"
curl -fsS http://localhost:8900/api/svensk-ragg/ready | tee "logs/ready_${RUN_ID}.json"
```

Expected:
- `/ready` reports `ready` only if Chroma, BM25, embedding service, and LLM are all usable.

## Task 4: Benchmark Retrieval Quality Before Tuning

**Files:**
- Read: `scripts/compare_retrieval_quality.py`, `backend/eval/datasets/golden_v1.json`
- Write logs: `logs/retrieval_quality_<RUN_ID>.log`, `logs/retrieval_quality_<RUN_ID>.json`

**Step 1: Run operational benchmark**

Run:

```bash
cd /home/ai-server2/rag/rag-project
RUN_ID=$(date +%Y%m%d_%H%M%S)
backend/.venv/bin/python scripts/compare_retrieval_quality.py \
  --enforce-gates \
  --output-json "logs/retrieval_quality_${RUN_ID}.json" \
  2>&1 | tee "logs/retrieval_quality_${RUN_ID}.log"
```

Expected:
- Produces dense/BM25 hit counts, pipeline latency, live success rate, and SFS gates.

**Step 2: Only then consider tuning**

Promote tuning only if dense import and baseline benchmark produce interpretable results. Candidate knobs for later:
- `CONST_RRF_BM25_WEIGHT`
- `CONST_RRF_K`
- `CONST_SCORE_THRESHOLD`
- `CONST_GGUF_CONTEXT_WINDOW` and `CONST_OLLAMA_NUM_CTX`

Do not change reranking, CRAG, critic, or model family in the first overnight pass.

## Resume Instructions

If the importer stops:

```bash
cd /home/ai-server2/rag/rag-project
cat migration_checkpoints/jsonl_to_jina_chroma.json
```

Rerun Task 1 Step 2 with the same checkpoint file. The importer resumes from `last_jsonl_line`.

If GPU memory becomes a problem, rerun with:

```bash
--device cpu --batch-size 32
```

If the manifest step fails with `/home/simon/...`, ensure the command includes:

```bash
CONST_BM25_INDEX_PATH=/home/ai-server2/rag/local-data/bm25_fts5/bm25.db
```

# Safe Jina/Chroma Rebuild Slice

Status: validated on temporary Chroma only.
Date: 2026-05-28.

## What Was Validated

Temporary paths used:

- Chroma: `/tmp/rag-import-next-slice.cXRoZK/chroma`
- Checkpoint: `/tmp/rag-import-next-slice.cXRoZK/checkpoint.json`
- Manifest: `/tmp/rag-import-next-slice.cXRoZK/manifest.json`

Validated command shape:

```bash
PYTHONUNBUFFERED=1 backend/.venv/bin/python scripts/import_jsonl_to_jina_chroma.py \
  --input /home/ai-server2/rag/RAG_TRANSFER/constitutional-ai-preservation-2026-04-10-selected/bm25_index/docs.jsonl \
  --procedural backend/data/procedural_guides.json \
  --chroma /tmp/rag-import-next-slice.cXRoZK/chroma \
  --checkpoint-file /tmp/rag-import-next-slice.cXRoZK/checkpoint.json \
  --manifest-file /tmp/rag-import-next-slice.cXRoZK/manifest.json \
  --device cpu \
  --batch-size 3 \
  --encode-batch-size 1 \
  --max-text-chars 800 \
  --model-max-seq-length 256 \
  --limit 12
```

Resume validation used the same temp paths with `--limit 3`. Expected result:

- `sfs_lagtext_jina_v3_1024`: `15`
- `procedural_guides_jina_v3_1024`: `7`
- total temp embeddings: `22`
- checkpoint `last_jsonl_line`: `15`
- checkpoint `procedural_done`: `true`

## Safe Real Rebuild Plan

Do not rebuild directly into `/home/ai-server2/rag/local-data/chromadb`.
Create a staged Chroma directory, checkpoint, and manifest, then validate before any cutover.

```bash
cd /home/ai-server2/rag/rag-project
RUN_ID=$(date +%Y%m%d_%H%M%S)
STAGING_ROOT="/home/ai-server2/rag/local-data/chromadb-rebuild-${RUN_ID}"
CHECKPOINT="migration_checkpoints/jsonl_to_jina_chroma_rebuild_${RUN_ID}.json"
MANIFEST="logs/rag_corpus_manifest_rebuild_${RUN_ID}.json"
LOG="logs/import_jsonl_to_jina_chroma_rebuild_${RUN_ID}.log"

mkdir -p "$STAGING_ROOT" logs migration_checkpoints

PYTHONUNBUFFERED=1 \
CONST_BM25_INDEX_PATH=/home/ai-server2/rag/local-data/bm25_fts5/bm25.db \
nohup backend/.venv/bin/python scripts/import_jsonl_to_jina_chroma.py \
  --input /home/ai-server2/rag/RAG_TRANSFER/constitutional-ai-preservation-2026-04-10-selected/bm25_index/docs.jsonl \
  --procedural backend/data/procedural_guides.json \
  --chroma "$STAGING_ROOT" \
  --checkpoint-file "$CHECKPOINT" \
  --manifest-file "$MANIFEST" \
  --device cpu \
  --batch-size 3 \
  --encode-batch-size 1 \
  --max-text-chars 12000 \
  --model-max-seq-length 1024 \
  > "$LOG" 2>&1 &

echo "$!" > "logs/import_jsonl_to_jina_chroma_rebuild_${RUN_ID}.pid"
echo "RUN_ID=$RUN_ID"
echo "STAGING_ROOT=$STAGING_ROOT"
echo "CHECKPOINT=$CHECKPOINT"
echo "MANIFEST=$MANIFEST"
echo "LOG=$LOG"
```

## Required Validation Before Cutover

Run these against the staged path only:

```bash
backend/.venv/bin/python scripts/chroma_integrity_check.py \
  --path "$STAGING_ROOT" \
  --collections sfs_lagtext_jina_v3_1024,riksdag_documents_p1_jina_v3_1024,swedish_gov_docs_jina_v3_1024,diva_research_jina_v3_1024,procedural_guides_jina_v3_1024 \
  --loops 3 \
  --n-results 3

cat "$CHECKPOINT"
cat "$MANIFEST"
```

Cutover to `/home/ai-server2/rag/local-data/chromadb` requires explicit approval and a rollback copy of the current Chroma directory.

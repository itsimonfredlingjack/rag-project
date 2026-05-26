#!/usr/bin/env python3
"""
Import restored BM25 JSONL text into Jina-v3 Chroma collections.

This is a recovery importer for the local RAG transfer where Chroma is empty
but the text-bearing BM25 export is available. It streams docs.jsonl, embeds
with jinaai/jina-embeddings-v3 using retrieval.passage, and writes the five
runtime collections expected by the backend.
"""

from __future__ import annotations

import argparse
import gc
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Iterable

import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer
from tqdm import tqdm

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

EXPECTED_JSONL_DOCS = 1_372_290

COLLECTION_SFS = "sfs_lagtext_jina_v3_1024"
COLLECTION_RIKSDAG = "riksdag_documents_p1_jina_v3_1024"
COLLECTION_GOV = "swedish_gov_docs_jina_v3_1024"
COLLECTION_DIVA = "diva_research_jina_v3_1024"
COLLECTION_PROCEDURAL = "procedural_guides_jina_v3_1024"
ALL_COLLECTIONS = [
    COLLECTION_SFS,
    COLLECTION_RIKSDAG,
    COLLECTION_GOV,
    COLLECTION_DIVA,
    COLLECTION_PROCEDURAL,
]

# The restored docs.jsonl is ordered by the original export pipeline.
LINE_BANDS = [
    (1, 7_841, COLLECTION_SFS, "sfs"),
    (7_842, 237_984, COLLECTION_RIKSDAG, "riksdag"),
    (237_985, 542_855, COLLECTION_GOV, "government"),
    (542_856, 1_372_290, COLLECTION_DIVA, "academic"),
]


def log(message: str) -> None:
    print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}", flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import restored JSONL into Jina Chroma.")
    parser.add_argument(
        "--input",
        default=str(
            Path("/home/simon/rag/RAG_TRANSFER")
            / "constitutional-ai-preservation-2026-04-10"
            / "bm25_index"
            / "docs.jsonl"
        ),
        help="Input docs.jsonl path with {id,text} rows.",
    )
    parser.add_argument(
        "--procedural",
        default=str(REPO_ROOT / "backend" / "data" / "procedural_guides.json"),
        help="Procedural guide JSON path.",
    )
    parser.add_argument(
        "--chroma",
        default=os.environ.get("CONST_CHROMADB_PATH", str(REPO_ROOT / "chromadb_data")),
        help="Output Chroma persistent directory.",
    )
    parser.add_argument(
        "--checkpoint-file",
        default=str(REPO_ROOT / "migration_checkpoints" / "jsonl_to_jina_chroma.json"),
        help="Checkpoint JSON path.",
    )
    parser.add_argument("--model", default="jinaai/jina-embeddings-v3", help="Embedding model.")
    parser.add_argument(
        "--device",
        choices=["auto", "cpu", "gpu"],
        default="auto",
        help="Embedding device. Use gpu only when Ollama/backend are stopped.",
    )
    parser.add_argument("--batch-size", type=int, default=32, help="Embedding batch size.")
    parser.add_argument(
        "--allow-count-mismatch",
        action="store_true",
        help="Continue even if input line count is not the expected restored corpus count.",
    )
    parser.add_argument("--limit", type=int, default=0, help="Process at most N JSONL rows.")
    parser.add_argument("--dry-run", action="store_true", help="Embed but do not write.")
    return parser.parse_args()


def load_checkpoint(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_checkpoint(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def count_lines(path: Path) -> int:
    with path.open("rb") as f:
        return sum(1 for _ in f)


def resolve_device(requested: str) -> str:
    if requested == "cpu":
        return "cpu"
    try:
        import torch

        if requested == "gpu":
            if not torch.cuda.is_available():
                raise SystemExit("GPU requested but CUDA is not available.")
            return "cuda"
        return "cuda" if torch.cuda.is_available() else "cpu"
    except ImportError:
        if requested == "gpu":
            raise SystemExit("GPU requested but torch is not importable.")
        return "cpu"


def load_model(model_name: str, device: str) -> SentenceTransformer:
    log(f"Loading embedding model {model_name} on {device}")
    try:
        return SentenceTransformer(model_name, device=device, trust_remote_code=True)
    except TypeError:
        return SentenceTransformer(model_name, device=device)


def encode_passages(model: SentenceTransformer, texts: list[str]) -> list[list[float]]:
    try:
        embeddings = model.encode(
            texts,
            task="retrieval.passage",
            convert_to_numpy=True,
            show_progress_bar=False,
        )
    except TypeError:
        embeddings = model.encode(texts, convert_to_numpy=True, show_progress_bar=False)
    return embeddings.tolist()


def classify_line(line_no: int) -> tuple[str, str]:
    for start, end, collection, doc_type in LINE_BANDS:
        if start <= line_no <= end:
            return collection, doc_type
    raise ValueError(f"Line {line_no} is outside expected restored corpus bands")


def derive_title(doc_id: str, text: str) -> str:
    first_line = (text or "").strip().splitlines()[0] if text else doc_id
    for marker in (" <dokumentstatus>", " Titel:", " Abstract:", " Sammanfattning:"):
        if marker in first_line:
            first_line = first_line.split(marker, 1)[0]
    return first_line[:240] if first_line else doc_id


def metadata_for(line_no: int, doc_id: str, text: str, collection: str, doc_type: str) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "source_doc_id": str(doc_id),
        "collection": collection,
        "line_no": int(line_no),
        "import_source": "restored_bm25_jsonl",
        "doc_type": doc_type,
        "title": derive_title(doc_id, text),
    }
    if doc_id.startswith("sfs_"):
        parts = doc_id.split("_")
        if len(parts) >= 3:
            metadata["sfs_nummer"] = f"{parts[1]}:{parts[2]}"
        if len(parts) >= 4:
            metadata["kapitel"] = parts[3]
        if len(parts) >= 5:
            metadata["paragraf"] = parts[4]
    return metadata


def collection_metadata(collection_name: str) -> dict[str, Any]:
    return {
        "hnsw:space": "cosine",
        "embedding_model": "jinaai/jina-embeddings-v3",
        "embedding_dim": 1024,
        "recovery_import": True,
        "collection_family": collection_name.removesuffix("_jina_v3_1024"),
    }


def get_collections(client: chromadb.PersistentClient) -> dict[str, Any]:
    return {
        name: client.get_or_create_collection(
            name=name,
            metadata=collection_metadata(name),
        )
        for name in ALL_COLLECTIONS
    }


def flush_batch(
    *,
    model: SentenceTransformer,
    collections: dict[str, Any],
    batch: list[dict[str, Any]],
    dry_run: bool,
) -> int:
    if not batch:
        return 0

    written = 0
    by_collection: dict[str, list[dict[str, Any]]] = {}
    for item in batch:
        by_collection.setdefault(item["collection"], []).append(item)

    for collection_name, items in by_collection.items():
        texts = [item["text"] for item in items]
        embeddings = encode_passages(model, texts)
        if not dry_run:
            collections[collection_name].upsert(
                ids=[item["id"] for item in items],
                documents=texts,
                metadatas=[item["metadata"] for item in items],
                embeddings=embeddings,
            )
        written += len(items)

    gc.collect()
    return written


def iter_jsonl(path: Path, start_after_line: int, limit: int) -> Iterable[tuple[int, dict[str, Any]]]:
    emitted = 0
    with path.open(encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            if line_no <= start_after_line:
                continue
            if limit and emitted >= limit:
                break
            stripped = line.strip()
            if not stripped:
                continue
            emitted += 1
            yield line_no, json.loads(stripped)


def import_procedural_guides(
    *,
    model: SentenceTransformer,
    collection: Any,
    procedural_path: Path,
    dry_run: bool,
) -> int:
    guides = json.loads(procedural_path.read_text(encoding="utf-8"))
    if not isinstance(guides, list):
        raise ValueError(f"Expected procedural guide list in {procedural_path}")
    ids = [str(item["id"]) for item in guides]
    documents = [str(item.get("content", "")) for item in guides]
    metadatas = [
        {
            "source_doc_id": str(item["id"]),
            "collection": COLLECTION_PROCEDURAL,
            "import_source": "backend/data/procedural_guides.json",
            "doc_type": str(item.get("doc_type", "procedural_guide")),
            "source": str(item.get("source", "procedural_guides")),
            "title": str(item.get("title", item["id"])),
        }
        for item in guides
    ]
    embeddings = encode_passages(model, documents)
    if not dry_run:
        collection.upsert(ids=ids, documents=documents, metadatas=metadatas, embeddings=embeddings)
    return len(guides)


def write_manifest(
    *,
    chroma_path: Path,
    input_path: Path,
    procedural_path: Path,
    checkpoint_path: Path,
    model_name: str,
    collections: dict[str, Any],
    total_jsonl_count: int,
) -> None:
    counts = {}
    for name, collection in collections.items():
        try:
            counts[name] = int(collection.count())
        except Exception:
            counts[name] = None

    bm25_path = Path(
        os.environ.get("CONST_BM25_INDEX_PATH", "/home/simon/rag/local-data/bm25_fts5/bm25.db")
    )
    parent_path = REPO_ROOT / "data" / "parent_store" / "parents.db"
    manifest = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "embedding_model": model_name,
        "embedding_dim": 1024,
        "chroma_path": str(chroma_path),
        "input_jsonl": {"path": str(input_path), "bytes": input_path.stat().st_size, "rows": total_jsonl_count},
        "procedural_guides": {
            "path": str(procedural_path),
            "bytes": procedural_path.stat().st_size,
        },
        "bm25": {
            "path": str(bm25_path),
            "bytes": bm25_path.stat().st_size if bm25_path.exists() else 0,
        },
        "parent_store": {
            "path": str(parent_path),
            "bytes": parent_path.stat().st_size if parent_path.exists() else 0,
        },
        "collections": counts,
        "checkpoint": str(checkpoint_path),
    }
    out = REPO_ROOT / "logs" / "rag_corpus_manifest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"Wrote manifest: {out}")


def main() -> None:
    args = parse_args()
    input_path = Path(args.input)
    procedural_path = Path(args.procedural)
    chroma_path = Path(args.chroma)
    checkpoint_path = Path(args.checkpoint_file)

    if not input_path.exists():
        raise SystemExit(f"Input JSONL not found: {input_path}")
    if not procedural_path.exists():
        raise SystemExit(f"Procedural guide file not found: {procedural_path}")

    log(f"Counting input rows: {input_path}")
    total_rows = count_lines(input_path)
    log(f"Input rows: {total_rows:,}")
    if total_rows != EXPECTED_JSONL_DOCS and not args.allow_count_mismatch:
        raise SystemExit(
            f"Expected {EXPECTED_JSONL_DOCS:,} rows, found {total_rows:,}. "
            "Pass --allow-count-mismatch only if this is intentional."
        )

    checkpoint = load_checkpoint(checkpoint_path) if not args.dry_run else {}
    start_after_line = int(checkpoint.get("last_jsonl_line", 0))
    procedural_done = bool(checkpoint.get("procedural_done", False))
    written_total = int(checkpoint.get("written_total", 0))

    device = resolve_device(args.device)
    model = load_model(args.model, device)
    client = chromadb.PersistentClient(
        path=str(chroma_path),
        settings=Settings(anonymized_telemetry=False),
    )
    collections = get_collections(client)

    log(
        f"Starting import at line>{start_after_line:,}, batch={args.batch_size}, "
        f"dry_run={args.dry_run}, chroma={chroma_path}"
    )

    batch: list[dict[str, Any]] = []
    last_line = start_after_line
    start_time = time.perf_counter()
    target_rows = min(args.limit, total_rows - start_after_line) if args.limit else total_rows - start_after_line
    with tqdm(total=target_rows, unit="docs", desc="Importing JSONL") as pbar:
        for line_no, obj in iter_jsonl(input_path, start_after_line, args.limit):
            doc_id = str(obj["id"])
            text = str(obj.get("text", ""))
            collection_name, doc_type = classify_line(line_no)
            batch.append(
                {
                    "id": doc_id,
                    "text": text,
                    "collection": collection_name,
                    "metadata": metadata_for(line_no, doc_id, text, collection_name, doc_type),
                }
            )
            last_line = line_no

            if len(batch) >= args.batch_size:
                written = flush_batch(
                    model=model,
                    collections=collections,
                    batch=batch,
                    dry_run=args.dry_run,
                )
                written_total += written
                pbar.update(written)
                batch = []
                if not args.dry_run:
                    save_checkpoint(
                        checkpoint_path,
                        {
                            "last_jsonl_line": last_line,
                            "written_total": written_total,
                            "procedural_done": procedural_done,
                            "completed": False,
                        },
                    )

        if batch:
            written = flush_batch(
                model=model,
                collections=collections,
                batch=batch,
                dry_run=args.dry_run,
            )
            written_total += written
            pbar.update(written)

    if not procedural_done and not args.dry_run:
        count = import_procedural_guides(
            model=model,
            collection=collections[COLLECTION_PROCEDURAL],
            procedural_path=procedural_path,
            dry_run=args.dry_run,
        )
        log(f"Imported procedural guides: {count}")
        procedural_done = True
    elif not procedural_done and args.dry_run:
        count = import_procedural_guides(
            model=model,
            collection=collections[COLLECTION_PROCEDURAL],
            procedural_path=procedural_path,
            dry_run=True,
        )
        log(f"Dry-run embedded procedural guides: {count}")

    elapsed = time.perf_counter() - start_time
    log(f"Import pass complete: {written_total:,} JSONL docs handled in {elapsed / 60:.1f} min")

    if not args.dry_run:
        save_checkpoint(
            checkpoint_path,
            {
                "last_jsonl_line": last_line,
                "written_total": written_total,
                "procedural_done": procedural_done,
                "completed": last_line >= total_rows and procedural_done,
            },
        )
        write_manifest(
            chroma_path=chroma_path,
            input_path=input_path,
            procedural_path=procedural_path,
            checkpoint_path=checkpoint_path,
            model_name=args.model,
            collections=collections,
            total_jsonl_count=total_rows,
        )


if __name__ == "__main__":
    main()

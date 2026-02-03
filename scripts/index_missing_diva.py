#!/usr/bin/env python3
"""
Quick indexer for missing DiVA universities and myndigheter.
Handles both old and new JSON formats.
"""

import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

import chromadb

DATA_DIR = Path("/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/data")
CHROMADB_PATH = Path("/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/chromadb_data")
LOG_FILE = DATA_DIR / "missing_diva_indexer.log"

COLLECTION_NAME = "diva_research_bge_m3_1024"
BATCH_SIZE = 32
EMBED_BATCH_SIZE = 16

# Files to index
MISSING_UNIS = ["fhs", "gih", "esh", "shh", "kmh", "konstfack", "uniarts", "rkh", "kkh"]
MYNDIGHETER = ["naturvardsverket", "ri", "smhi", "trafikverket"]


def log(msg: str, level: str = "INFO"):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] [{level}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def get_gpu_temp():
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=temperature.gpu", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return int(result.stdout.strip())
    except Exception:
        return None


def thermal_check():
    temp = get_gpu_temp()
    if temp and temp >= 80:
        log(f"GPU HOT: {temp}°C - Pausing 30s", "WARN")
        time.sleep(30)
    elif temp and temp >= 75:
        time.sleep(5)


def get_embedding_function():
    from sentence_transformers import SentenceTransformer

    log("Loading BGE-M3 model via sentence-transformers (CPU)...")
    model = SentenceTransformer("BAAI/bge-m3", device="cuda")
    log("BGE-M3 loaded on CPU (slower but GPU is busy with LLM)")

    def embed_fn(texts):
        embeddings = model.encode(
            texts, batch_size=8, show_progress_bar=False
        )  # Smaller batch for CPU
        return embeddings.tolist()

    return embed_fn


def normalize_document(doc: dict, source_code: str) -> dict:
    """Normalize different DiVA formats to common structure."""
    # Skip deleted records
    if doc.get("status") == "deleted":
        return None

    normalized = {
        "source_code": source_code,
        "title": doc.get("title", ""),
        "description": "",
        "subjects": [],
        "creators": [],
        "date": "",
        "language": "",
        "url": "",
        "oai_id": "",
    }

    # Handle description/abstract
    normalized["description"] = doc.get("description") or doc.get("abstract") or ""

    # Handle subjects
    if doc.get("subjects") and isinstance(doc["subjects"], list):
        normalized["subjects"] = doc["subjects"][:10]

    # Handle authors/creators
    if doc.get("creators"):
        normalized["creators"] = doc["creators"][:5]
    elif doc.get("authors"):
        # New format: list of dicts
        authors = []
        for a in doc["authors"][:5]:
            if isinstance(a, dict):
                name = f"{a.get('given', '')} {a.get('family', '')}".strip()
                if name:
                    authors.append(name)
            elif isinstance(a, str):
                authors.append(a)
        normalized["creators"] = authors

    # Handle date
    normalized["date"] = str(doc.get("date") or doc.get("date_issued") or "")

    # Handle language
    normalized["language"] = doc.get("language", "")

    # Handle URL/identifiers
    if doc.get("identifiers"):
        ids = doc["identifiers"]
        if isinstance(ids, list):
            normalized["url"] = ids[0] if ids else ""
        elif isinstance(ids, dict):
            normalized["url"] = ids.get("uri", "") or ids.get("url", "")

    # Handle OAI ID
    normalized["oai_id"] = doc.get("oai_id") or doc.get("identifier") or ""

    # Skip if no title
    if not normalized["title"]:
        return None

    return normalized


def create_chunk_text(doc: dict) -> str:
    parts = []
    if doc.get("title"):
        parts.append(f"Titel: {doc['title']}")
    if doc.get("description"):
        # Strip HTML
        desc = doc["description"]
        import re

        desc = re.sub(r"<[^>]+>", "", desc)
        parts.append(f"\n{desc[:2000]}")
    if doc.get("subjects"):
        parts.append(f"\nÄmnen: {', '.join(doc['subjects'])}")
    if doc.get("creators"):
        parts.append(f"\nFörfattare: {', '.join(doc['creators'])}")
    return "\n".join(parts)


def create_metadata(doc: dict) -> dict:
    return {
        "source": "diva",
        "university": doc.get("source_code", ""),
        "title": (doc.get("title") or "")[:500],
        "date": str(doc.get("date", "")),
        "language": doc.get("language", ""),
        "url": (doc.get("url") or "")[:500],
        "oai_id": doc.get("oai_id", ""),
    }


def get_documents_from_file(file_path: Path):
    with open(file_path) as f:
        data = json.load(f)
    if isinstance(data, list):
        return data
    elif isinstance(data, dict):
        return data.get("documents", data.get("records", []))
    return []


def check_resources():
    """Check disk and memory."""
    import shutil

    disk = shutil.disk_usage("/")
    disk_free_gb = disk.free / (1024**3)

    with open("/proc/meminfo") as f:
        for line in f:
            if "MemAvailable" in line:
                mem_free_gb = int(line.split()[1]) / (1024**2)
                break

    return disk_free_gb, mem_free_gb


def main():
    log("=" * 60)
    log("Missing DiVA Indexer Starting")
    log("=" * 60)

    # Check resources
    disk_gb, mem_gb = check_resources()
    log(f"Resources: {disk_gb:.1f}GB disk free, {mem_gb:.1f}GB RAM free")

    if disk_gb < 10:
        log("ERROR: Less than 10GB disk space!", "ERROR")
        return

    # Connect to ChromaDB
    client = chromadb.PersistentClient(path=str(CHROMADB_PATH))
    collection = client.get_collection(COLLECTION_NAME)
    log(f"Collection {COLLECTION_NAME}: {collection.count():,} docs")

    # Load embedding model
    embed_fn = get_embedding_function()

    total_indexed = 0
    total_skipped = 0

    # Process missing universities
    files_to_process = []
    for uni in MISSING_UNIS:
        path = DATA_DIR / f"diva_full_{uni}.json"
        if path.exists():
            files_to_process.append((path, uni))

    # Process myndigheter
    for myn in MYNDIGHETER:
        path = DATA_DIR / f"diva_myndighet_{myn}.json"
        if path.exists():
            files_to_process.append((path, myn))

    log(f"Files to process: {len(files_to_process)}")

    for file_path, source_code in files_to_process:
        log(f"\nProcessing {source_code}...")

        docs = get_documents_from_file(file_path)
        log(f"  Loaded {len(docs)} raw documents")

        batch_texts = []
        batch_ids = []
        batch_metadatas = []
        file_indexed = 0

        for _i, doc in enumerate(docs):
            # Normalize document
            norm_doc = normalize_document(doc, source_code)
            if norm_doc is None:
                total_skipped += 1
                continue

            # Create text and metadata
            text = create_chunk_text(norm_doc)
            if len(text) < 50:
                total_skipped += 1
                continue

            doc_id = f"diva_{source_code}_{norm_doc['oai_id'].replace(':', '_').replace('/', '_')}"
            metadata = create_metadata(norm_doc)

            batch_texts.append(text)
            batch_ids.append(doc_id)
            batch_metadatas.append(metadata)

            # Process batch
            if len(batch_texts) >= BATCH_SIZE:
                thermal_check()

                try:
                    embeddings = embed_fn(batch_texts)
                    collection.add(
                        ids=batch_ids,
                        embeddings=embeddings,
                        documents=batch_texts,
                        metadatas=batch_metadatas,
                    )
                    file_indexed += len(batch_ids)
                    total_indexed += len(batch_ids)
                except Exception as e:
                    log(f"  Batch error: {e}", "ERROR")

                batch_texts = []
                batch_ids = []
                batch_metadatas = []

                # Progress
                if file_indexed % 500 == 0:
                    log(f"  Progress: {file_indexed}/{len(docs)}")

                    # Check resources periodically
                    disk_gb, mem_gb = check_resources()
                    if disk_gb < 5:
                        log("STOPPING: Low disk space!", "ERROR")
                        return

        # Final batch
        if batch_texts:
            thermal_check()
            try:
                embeddings = embed_fn(batch_texts)
                collection.add(
                    ids=batch_ids,
                    embeddings=embeddings,
                    documents=batch_texts,
                    metadatas=batch_metadatas,
                )
                file_indexed += len(batch_ids)
                total_indexed += len(batch_ids)
            except Exception as e:
                log(f"  Final batch error: {e}", "ERROR")

        log(f"  Completed {source_code}: {file_indexed} indexed")

    log("\n" + "=" * 60)
    log("INDEXING COMPLETE")
    log("=" * 60)
    log(f"Total indexed: {total_indexed:,}")
    log(f"Total skipped: {total_skipped:,}")
    log(f"Collection size: {collection.count():,}")


if __name__ == "__main__":
    main()

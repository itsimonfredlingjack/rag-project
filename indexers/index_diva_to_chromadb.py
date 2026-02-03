#!/usr/bin/env python3
"""
DiVA Indexer - Indexerar svenska universitetsforskningspublikationer till ChromaDB.

Features:
- Checkpoint/resume - kan fortsätta efter avbrott
- Thermal pacing - pausar vid hög GPU-temperatur
- Batch processing - effektiv embedding
- Progress tracking - visar status
- Error handling - hoppar över trasiga dokument

Användning:
    python index_diva_to_chromadb.py                    # Indexera alla
    python index_diva_to_chromadb.py --university lu    # Bara Lunds universitet
    python index_diva_to_chromadb.py --resume           # Fortsätt från checkpoint
    python index_diva_to_chromadb.py --dry-run          # Testa utan att skriva
"""

import argparse
import json
import pickle
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

import chromadb
from chromadb.config import Settings

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

DATA_DIR = Path("/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/data")
CHROMADB_PATH = Path("/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/chromadb_data")
CHECKPOINT_FILE = DATA_DIR / "diva_indexer_checkpoint.pkl"
LOG_FILE = DATA_DIR / "diva_indexer.log"

COLLECTION_NAME = "diva_research_bge_m3_1024"
EMBEDDING_DIM = 1024
BATCH_SIZE = 32  # Documents per batch
EMBED_BATCH_SIZE = 16  # Embeddings per GPU call

# Thermal pacing thresholds (Celsius)
TEMP_WARN = 75
TEMP_PAUSE = 80
TEMP_CRITICAL = 85
PAUSE_DURATION = 30  # Seconds to pause when hot

# University priority order (juridik-relevanta först)
UNIVERSITY_PRIORITY = [
    "lu",  # Lunds universitet - stark juridik
    "uu",  # Uppsala universitet - stark juridik
    "su",  # Stockholms universitet - stark juridik
    "gu",  # Göteborgs universitet
    "umu",  # Umeå universitet
    "liu",  # Linköpings universitet
    "kth",  # KTH
    "ki",  # Karolinska (medicin, relevant för hälsorätt)
    "lnu",  # Linnéuniversitetet
    "mau",  # Malmö universitet
    "kau",  # Karlstads universitet
    "oru",  # Örebro universitet
    "hig",  # Högskolan i Gävle
    "mdh",  # Mälardalens högskola
    "ltu",  # Luleå tekniska universitet
    "hh",  # Högskolan i Halmstad
    "hb",  # Högskolan i Borås
    "sh",  # Södertörns högskola
    "his",  # Högskolan i Skövde
    "chalmers",
    "hkr",  # Högskolan Kristianstad
    "hv",  # Högskolan Väst
    "du",  # Dalarna
    "fhs",  # Försvarshögskolan
    "gih",  # GIH
    "esh",  # Ersta Sköndal
    "shh",  # Sophiahemmet
    "kmh",  # Musikhögskolan
    "konstfack",
    "uniarts",
    "rkh",  # Röda Korsets högskola
    "kkh",  # Kungl. Konsthögskolan
]


@dataclass
class IndexerState:
    """Checkpoint state for resume capability."""

    processed_files: dict[str, int] = field(default_factory=dict)  # file -> last_index
    total_indexed: int = 0
    total_skipped: int = 0
    total_errors: int = 0
    start_time: str = ""
    last_update: str = ""

    def save(self, path: Path):
        with open(path, "wb") as f:
            pickle.dump(self, f)

    @classmethod
    def load(cls, path: Path) -> "IndexerState":
        if path.exists():
            with open(path, "rb") as f:
                return pickle.load(f)
        return cls()


def log(msg: str, level: str = "INFO"):
    """Log message to file and stdout."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] [{level}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def get_gpu_temp() -> Optional[int]:
    """Get GPU temperature in Celsius."""
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
    """Check GPU temperature and pause if needed."""
    temp = get_gpu_temp()
    if temp is None:
        return

    if temp >= TEMP_CRITICAL:
        log(f"GPU CRITICAL: {temp}°C - Pausing {PAUSE_DURATION * 2}s", "CRITICAL")
        time.sleep(PAUSE_DURATION * 2)
    elif temp >= TEMP_PAUSE:
        log(f"GPU HOT: {temp}°C - Pausing {PAUSE_DURATION}s", "WARN")
        time.sleep(PAUSE_DURATION)
    elif temp >= TEMP_WARN:
        log(f"GPU WARM: {temp}°C", "WARN")
        time.sleep(5)


def get_embedding_function():
    """Initialize BGE-M3 embedding function."""
    try:
        from FlagEmbedding import BGEM3FlagModel

        log("Loading BGE-M3 model...")
        model = BGEM3FlagModel(
            "BAAI/bge-m3",
            use_fp16=True,
            device="cuda",
        )
        log("BGE-M3 loaded successfully")

        def embed_fn(texts: list[str]) -> list[list[float]]:
            embeddings = model.encode(
                texts,
                batch_size=EMBED_BATCH_SIZE,
                max_length=512,
            )["dense_vecs"]
            return embeddings.tolist()

        return embed_fn

    except ImportError:
        log("FlagEmbedding not found, using sentence-transformers fallback", "WARN")
        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer("BAAI/bge-m3", device="cuda")

        def embed_fn(texts: list[str]) -> list[list[float]]:
            return model.encode(texts, batch_size=EMBED_BATCH_SIZE).tolist()

        return embed_fn


def create_chunk_text(doc: dict) -> str:
    """Create searchable text from DiVA document."""
    parts = []

    # Title (important)
    if doc.get("title"):
        parts.append(f"Titel: {doc['title']}")

    # University context
    if doc.get("university"):
        parts.append(f"Universitet: {doc['university']}")

    # Abstract/description (main content)
    if doc.get("description"):
        parts.append(f"\n{doc['description']}")

    # Subjects/keywords
    if doc.get("subjects"):
        subjects = doc["subjects"][:10]  # Limit to 10
        parts.append(f"\nÄmnen: {', '.join(subjects)}")

    # Authors
    if doc.get("creators"):
        creators = doc["creators"][:5]  # Limit to 5
        parts.append(f"\nFörfattare: {', '.join(creators)}")

    return "\n".join(parts)


def create_metadata(doc: dict, university_code: str) -> dict:
    """Create ChromaDB metadata from DiVA document."""
    # Get first identifier as URL
    identifiers = doc.get("identifiers", [])
    url = identifiers[0] if identifiers else ""

    return {
        "source": "diva",
        "university": university_code,
        "university_name": doc.get("university", ""),
        "title": (doc.get("title") or "")[:500],  # Limit length
        "date": str(doc.get("date", "")),
        "language": doc.get("language", ""),
        "doc_type": doc.get("types", [""])[0] if doc.get("types") else "",
        "url": url[:500],
        "oai_id": doc.get("oai_id", ""),
    }


def get_documents_from_file(file_path: Path) -> list[dict]:
    """Extract documents from DiVA file (handles different formats)."""
    with open(file_path) as f:
        data = json.load(f)

    if isinstance(data, list):
        return data
    elif isinstance(data, dict):
        return data.get("documents", data.get("records", []))
    return []


def find_diva_files() -> list[Path]:
    """Find all DiVA JSON files in priority order."""
    files = []

    # First add files in priority order (only diva_full_* files)
    for uni in UNIVERSITY_PRIORITY:
        path = DATA_DIR / f"diva_full_{uni}.json"
        if path.exists():
            # Skip empty files
            docs = get_documents_from_file(path)
            if len(docs) > 0:
                files.append(path)

    # Then add any remaining diva_full_* files not in priority list
    for path in sorted(DATA_DIR.glob("diva_full_*.json")):
        if path not in files:
            docs = get_documents_from_file(path)
            if len(docs) > 0:
                files.append(path)

    return files


def process_file(
    file_path: Path,
    collection,
    embed_fn,
    state: IndexerState,
    dry_run: bool = False,
) -> int:
    """Process a single DiVA JSON file."""

    university_code = file_path.stem.replace("diva_full_", "")

    # Load JSON
    log(f"Loading {file_path.name}...")
    documents = get_documents_from_file(file_path)
    total_docs = len(documents)

    # Get resume point
    start_idx = state.processed_files.get(str(file_path), 0)
    if start_idx > 0:
        log(f"Resuming from document {start_idx}/{total_docs}")

    indexed_count = 0
    batch_texts = []
    batch_ids = []
    batch_metadatas = []

    for i, doc in enumerate(documents[start_idx:], start=start_idx):
        # Create chunk
        text = create_chunk_text(doc)

        # Skip empty documents
        if len(text.strip()) < 50:
            state.total_skipped += 1
            continue

        # Create ID and metadata
        doc_id = f"diva_{university_code}_{doc.get('oai_id', str(i))}"
        metadata = create_metadata(doc, university_code)

        batch_texts.append(text)
        batch_ids.append(doc_id)
        batch_metadatas.append(metadata)

        # Process batch when full
        if len(batch_texts) >= BATCH_SIZE:
            if not dry_run:
                thermal_check()

                try:
                    embeddings = embed_fn(batch_texts)
                    collection.add(
                        ids=batch_ids,
                        embeddings=embeddings,
                        metadatas=batch_metadatas,
                        documents=batch_texts,
                    )
                    indexed_count += len(batch_ids)
                    state.total_indexed += len(batch_ids)
                except Exception as e:
                    log(f"Batch error at {i}: {e}", "ERROR")
                    state.total_errors += len(batch_ids)
            else:
                indexed_count += len(batch_ids)

            # Update checkpoint
            state.processed_files[str(file_path)] = i + 1
            state.last_update = datetime.now().isoformat()
            state.save(CHECKPOINT_FILE)

            # Progress
            progress = ((i + 1) / total_docs) * 100
            log(
                f"  {university_code}: {i + 1}/{total_docs} ({progress:.1f}%) - {indexed_count} indexed"
            )

            # Clear batch
            batch_texts = []
            batch_ids = []
            batch_metadatas = []

    # Process remaining batch
    if batch_texts:
        if not dry_run:
            thermal_check()
            try:
                embeddings = embed_fn(batch_texts)
                collection.add(
                    ids=batch_ids,
                    embeddings=embeddings,
                    metadatas=batch_metadatas,
                    documents=batch_texts,
                )
                indexed_count += len(batch_ids)
                state.total_indexed += len(batch_ids)
            except Exception as e:
                log(f"Final batch error: {e}", "ERROR")
                state.total_errors += len(batch_ids)
        else:
            indexed_count += len(batch_ids)

    # Mark file as complete
    state.processed_files[str(file_path)] = total_docs
    state.save(CHECKPOINT_FILE)

    return indexed_count


def main():
    parser = argparse.ArgumentParser(description="Index DiVA research publications to ChromaDB")
    parser.add_argument(
        "--university", "-u", help="Only index specific university (e.g., 'lu', 'uu')"
    )
    parser.add_argument("--resume", "-r", action="store_true", help="Resume from checkpoint")
    parser.add_argument(
        "--dry-run", "-n", action="store_true", help="Don't actually write to ChromaDB"
    )
    parser.add_argument("--reset", action="store_true", help="Reset checkpoint and start fresh")
    args = parser.parse_args()

    log("=" * 60)
    log("DiVA Indexer Starting")
    log("=" * 60)

    # Load or create state
    if args.reset and CHECKPOINT_FILE.exists():
        CHECKPOINT_FILE.unlink()
        log("Checkpoint reset")

    state = IndexerState.load(CHECKPOINT_FILE) if args.resume else IndexerState()
    state.start_time = state.start_time or datetime.now().isoformat()

    # Find files to process
    files = find_diva_files()
    if args.university:
        files = [f for f in files if args.university in f.name]

    if not files:
        log("No DiVA files found!", "ERROR")
        return 1

    log(f"Found {len(files)} DiVA files to process")

    # Count total documents
    total_docs = 0
    for f in files:
        total_docs += len(get_documents_from_file(f))
    log(f"Total documents: {total_docs:,}")

    if args.dry_run:
        log("DRY RUN - No data will be written")
        return 0

    # Initialize ChromaDB
    log(f"Connecting to ChromaDB at {CHROMADB_PATH}")
    client = chromadb.PersistentClient(
        path=str(CHROMADB_PATH),
        settings=Settings(anonymized_telemetry=False),
    )

    # Get or create collection
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine", "dimension": EMBEDDING_DIM},
    )
    log(f"Collection '{COLLECTION_NAME}' ready (existing: {collection.count()} docs)")

    # Initialize embedding function
    embed_fn = get_embedding_function()

    # Process files
    start_time = time.time()

    for file_path in files:
        university = file_path.stem.replace("diva_full_", "")

        # Skip if already fully processed
        file_total = len(get_documents_from_file(file_path))

        if state.processed_files.get(str(file_path), 0) >= file_total:
            log(f"Skipping {university} (already complete)")
            continue

        log(f"\nProcessing {university} ({file_total:,} documents)...")

        try:
            indexed = process_file(file_path, collection, embed_fn, state, args.dry_run)
            log(f"Completed {university}: {indexed:,} documents indexed")
        except Exception as e:
            log(f"Failed processing {university}: {e}", "ERROR")
            import traceback

            traceback.print_exc()
            continue

    # Final stats
    elapsed = time.time() - start_time
    log("")
    log("=" * 60)
    log("INDEXING COMPLETE")
    log("=" * 60)
    log(f"Total indexed: {state.total_indexed:,}")
    log(f"Total skipped: {state.total_skipped:,}")
    log(f"Total errors: {state.total_errors:,}")
    log(f"Time elapsed: {elapsed / 3600:.1f} hours")
    log(f"Collection size: {collection.count():,}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

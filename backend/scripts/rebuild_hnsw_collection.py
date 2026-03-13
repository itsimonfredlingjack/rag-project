"""
Rebuild a ChromaDB collection from its broken HNSW segment files.

Extracts vectors from data_level0.bin, maps labels to IDs via pickle,
reads metadata from SQLite, then creates a fresh collection with the same data.

Usage:
    python scripts/rebuild_hnsw_collection.py swedish_gov_docs_jina_v3_1024
"""

import os
import pickle
import sqlite3
import struct
import sys
import time
from collections import defaultdict

import numpy as np

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CHROMADB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "..",
    "chromadb_data",
)

BATCH_SIZE = 500  # ChromaDB batch limit


def extract_vectors(segment_dir: str, dim: int = 1024) -> dict[int, np.ndarray]:
    """Extract all vectors from data_level0.bin, keyed by label."""

    header_path = os.path.join(segment_dir, "header.bin")
    data_path = os.path.join(segment_dir, "data_level0.bin")

    # Parse header
    with open(header_path, "rb") as f:
        header = f.read()
    vals = struct.unpack("<25I", header[:100])
    size_per_elem = vals[7]  # size_data_per_element

    # Read offsets from header (u32 pairs at indices 9 and 11)
    label_offset = vals[9]  # offset of label within each element
    offset_data = vals[11]  # offset of vector data within each element
    print(
        f"  size_per_element={size_per_elem}, offset_data={offset_data}, "
        f"label_offset={label_offset}, dim={dim}"
    )

    file_size = os.path.getsize(data_path)
    num_elements = file_size // size_per_elem
    print(f"  data_level0.bin: {file_size:,} bytes, {num_elements:,} elements")

    vectors = {}
    with open(data_path, "rb") as f:
        for i in range(num_elements):
            elem = f.read(size_per_elem)
            if len(elem) < size_per_elem:
                break

            # Vector at offset_data, dim*4 bytes
            vec_bytes = elem[offset_data : offset_data + dim * 4]
            vec = np.frombuffer(vec_bytes, dtype=np.float32).copy()

            # Label at label_offset
            label = struct.unpack("<I", elem[label_offset : label_offset + 4])[0]
            vectors[label] = vec

            if (i + 1) % 50000 == 0:
                print(f"  Read {i + 1:,}/{num_elements:,} vectors...")

    print(f"  Extracted {len(vectors):,} vectors")
    return vectors


def load_label_to_id(segment_dir: str) -> dict[int, str]:
    """Load label→embedding_id mapping from pickle."""
    pickle_path = os.path.join(segment_dir, "index_metadata.pickle")
    with open(pickle_path, "rb") as f:
        meta = pickle.load(f)
    return meta.get("label_to_id", {})


def load_metadata_from_sqlite(
    db_path: str, metadata_segment_id: str
) -> tuple[dict[str, dict], dict[str, str]]:
    """Load metadata and documents for all embeddings in the metadata segment."""

    conn = sqlite3.connect(db_path)

    # Get all embedding IDs
    rows = conn.execute(
        "SELECT id, embedding_id FROM embeddings WHERE segment_id = ?",
        (metadata_segment_id,),
    ).fetchall()

    internal_id_to_embedding_id = {r[0]: r[1] for r in rows}
    print(f"  {len(internal_id_to_embedding_id):,} embeddings in metadata segment")

    # Get all metadata
    metadata_map: dict[str, dict] = defaultdict(dict)
    documents_map: dict[str, str] = {}

    meta_rows = conn.execute(
        """
        SELECT em.id, em.key, em.string_value, em.int_value, em.float_value
        FROM embedding_metadata em
        WHERE em.id IN (SELECT id FROM embeddings WHERE segment_id = ?)
        """,
        (metadata_segment_id,),
    ).fetchall()

    for row in meta_rows:
        internal_id = row[0]
        key = row[1]
        embedding_id = internal_id_to_embedding_id.get(internal_id)
        if not embedding_id:
            continue

        # chroma:document is the document text
        if key == "chroma:document":
            documents_map[embedding_id] = row[2] or ""
            continue

        # Regular metadata
        value = row[2] if row[2] is not None else (row[3] if row[3] is not None else row[4])
        metadata_map[embedding_id][key] = value

    conn.close()
    print(f"  Loaded metadata for {len(metadata_map):,} embeddings")
    print(f"  Loaded documents for {len(documents_map):,} embeddings")
    return dict(metadata_map), documents_map


def rebuild_collection(
    collection_name: str,
    vectors: dict[int, np.ndarray],
    label_to_id: dict[int, str],
    metadata_map: dict[str, dict],
    documents_map: dict[str, str],
    dim: int = 1024,
):
    """Delete and recreate the collection with all data."""
    import chromadb

    client = chromadb.PersistentClient(path=CHROMADB_PATH)

    # Get collection metadata before deleting
    try:
        old_col = client.get_collection(collection_name)
        col_metadata = old_col.metadata or {}
        print(f"  Existing collection metadata: {col_metadata}")
    except Exception:
        col_metadata = {}

    # Prepare all records: match vectors (by label) → embedding_ids → metadata
    records = []
    missing_id = 0
    missing_meta = 0
    for label, vec in vectors.items():
        embedding_id = label_to_id.get(label)
        if not embedding_id:
            missing_id += 1
            continue

        meta = metadata_map.get(embedding_id, {})
        doc = documents_map.get(embedding_id)

        if not meta and not doc:
            missing_meta += 1

        records.append(
            {
                "id": embedding_id,
                "embedding": vec.tolist(),
                "metadata": meta if meta else None,
                "document": doc,
            }
        )

    print(f"  Prepared {len(records):,} records")
    print(f"  Skipped: {missing_id} missing label→id, {missing_meta} missing metadata")

    # Delete old collection
    print(f"\n  Deleting broken collection '{collection_name}'...")
    try:
        client.delete_collection(collection_name)
        print("  Deleted successfully")
    except Exception as e:
        print(f"  Delete failed: {e}")
        print("  Trying manual SQLite cleanup...")
        manual_delete_collection(collection_name)

    # Create new collection
    print(f"\n  Creating fresh collection '{collection_name}'...")
    col_metadata["hnsw:space"] = "cosine"
    new_col = client.get_or_create_collection(
        name=collection_name,
        metadata=col_metadata,
    )
    print(f"  Created. Current count: {new_col.count()}")

    # Add in batches
    total_batches = (len(records) + BATCH_SIZE - 1) // BATCH_SIZE
    start_time = time.time()

    for batch_idx in range(0, len(records), BATCH_SIZE):
        batch = records[batch_idx : batch_idx + BATCH_SIZE]
        batch_num = batch_idx // BATCH_SIZE + 1

        ids = [r["id"] for r in batch]
        embeddings = [r["embedding"] for r in batch]
        metadatas = [r["metadata"] for r in batch]
        documents = [r["document"] for r in batch]

        # Filter out None documents
        has_docs = any(d is not None for d in documents)

        kwargs = {"ids": ids, "embeddings": embeddings}
        if any(m is not None for m in metadatas):
            # Replace None with empty dict
            kwargs["metadatas"] = [m if m else {} for m in metadatas]
        if has_docs:
            kwargs["documents"] = [d if d else "" for d in documents]

        try:
            new_col.add(**kwargs)
        except Exception as e:
            print(f"  ERROR on batch {batch_num}: {e}")
            # Try without documents (they might have issues)
            try:
                kwargs.pop("documents", None)
                new_col.add(**kwargs)
                print(f"  Retried batch {batch_num} without documents: OK")
            except Exception as e2:
                print(f"  RETRY FAILED: {e2}")
                continue

        if batch_num % 50 == 0 or batch_num == total_batches:
            elapsed = time.time() - start_time
            rate = batch_num / elapsed if elapsed > 0 else 0
            eta = (total_batches - batch_num) / rate if rate > 0 else 0
            print(
                f"  Batch {batch_num}/{total_batches} "
                f"({batch_num * BATCH_SIZE:,}/{len(records):,}) "
                f"- {elapsed:.0f}s elapsed, ~{eta:.0f}s remaining"
            )

    final_count = new_col.count()
    total_time = time.time() - start_time
    print(f"\n  Rebuild complete! Final count: {final_count:,} in {total_time:.0f}s")

    # Verify with a query
    try:
        result = new_col.query(query_embeddings=[records[0]["embedding"]], n_results=3)
        print(f"  Query test: OK ({len(result['ids'][0])} results)")
    except Exception as e:
        print(f"  Query test: FAILED: {e}")


def manual_delete_collection(collection_name: str):
    """Manually remove a collection from SQLite when ChromaDB can't delete it."""
    db_path = os.path.join(CHROMADB_PATH, "chroma.sqlite3")
    conn = sqlite3.connect(db_path)

    col = conn.execute("SELECT id FROM collections WHERE name = ?", (collection_name,)).fetchone()
    if not col:
        print(f"  Collection '{collection_name}' not found in SQLite")
        return

    col_id = col[0]

    # Get segment IDs
    segments = conn.execute(
        "SELECT id, type FROM segments WHERE collection = ?", (col_id,)
    ).fetchall()

    for seg_id, seg_type in segments:
        # Delete embeddings and metadata for metadata segments
        if "metadata" in seg_type:
            count = conn.execute(
                "DELETE FROM embedding_metadata WHERE id IN "
                "(SELECT id FROM embeddings WHERE segment_id = ?)",
                (seg_id,),
            ).rowcount
            print(f"  Deleted {count:,} embedding_metadata rows")

            count = conn.execute("DELETE FROM embeddings WHERE segment_id = ?", (seg_id,)).rowcount
            print(f"  Deleted {count:,} embeddings rows")

        # Delete segment metadata
        conn.execute("DELETE FROM segment_metadata WHERE segment_id = ?", (seg_id,))
        # Delete max_seq_id
        conn.execute("DELETE FROM max_seq_id WHERE segment_id = ?", (seg_id,))

    # Delete segments
    conn.execute("DELETE FROM segments WHERE collection = ?", (col_id,))
    # Delete collection metadata
    conn.execute("DELETE FROM collection_metadata WHERE collection_id = ?", (col_id,))
    # Delete collection
    conn.execute("DELETE FROM collections WHERE id = ?", (col_id,))
    # Delete queue entries
    conn.execute(
        "DELETE FROM embeddings_queue WHERE topic LIKE ?",
        (f"%{col_id}%",),
    )

    conn.commit()
    conn.close()

    # Remove HNSW segment directories
    import shutil

    for seg_id, seg_type in segments:
        if "hnsw" in seg_type:
            seg_dir = os.path.join(CHROMADB_PATH, seg_id)
            if os.path.exists(seg_dir):
                # Rename instead of delete for safety
                backup_dir = seg_dir + ".broken"
                if os.path.exists(backup_dir):
                    shutil.rmtree(backup_dir)
                os.rename(seg_dir, backup_dir)
                print(f"  Moved {seg_id} → {seg_id}.broken")

    print("  Manual cleanup complete")


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/rebuild_hnsw_collection.py <collection_name>")
        sys.exit(1)

    collection_name = sys.argv[1]
    db_path = os.path.join(CHROMADB_PATH, "chroma.sqlite3")

    print(f"=== Rebuilding collection: {collection_name} ===\n")

    # Step 1: Find segments
    conn = sqlite3.connect(db_path)
    col = conn.execute("SELECT id FROM collections WHERE name = ?", (collection_name,)).fetchone()
    if not col:
        print(f"ERROR: Collection '{collection_name}' not found")
        sys.exit(1)

    col_id = col[0]
    segments = conn.execute(
        "SELECT id, type FROM segments WHERE collection = ?", (col_id,)
    ).fetchall()

    hnsw_seg = None
    meta_seg = None
    for seg_id, seg_type in segments:
        if "hnsw" in seg_type:
            hnsw_seg = seg_id
        elif "metadata" in seg_type:
            meta_seg = seg_id

    conn.close()

    if not hnsw_seg or not meta_seg:
        print("ERROR: Could not find HNSW and metadata segments")
        sys.exit(1)

    print(f"HNSW segment: {hnsw_seg}")
    print(f"Metadata segment: {meta_seg}")

    hnsw_dir = os.path.join(CHROMADB_PATH, hnsw_seg)
    if not os.path.exists(hnsw_dir):
        print(f"ERROR: HNSW directory not found: {hnsw_dir}")
        sys.exit(1)

    # Step 2: Extract vectors
    print("\n[1/4] Extracting vectors from HNSW binary...")
    vectors = extract_vectors(hnsw_dir)

    # Step 3: Load label→id mapping
    print("\n[2/4] Loading label→id mapping...")
    label_to_id = load_label_to_id(hnsw_dir)
    print(f"  {len(label_to_id):,} mappings loaded")

    # Step 4: Load metadata from SQLite
    print("\n[3/4] Loading metadata from SQLite...")
    metadata_map, documents_map = load_metadata_from_sqlite(db_path, meta_seg)

    # Step 5: Rebuild
    print("\n[4/4] Rebuilding collection...")
    rebuild_collection(collection_name, vectors, label_to_id, metadata_map, documents_map)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Remove legacy BGE and stub collections from ChromaDB.

These collections have been superseded by Jina v3 equivalents and are
no longer referenced by any code path.  The script lists candidates,
asks for confirmation, then deletes them.

Usage:
    cd backend && source venv/bin/activate
    python ../scripts/cleanup_legacy_collections.py
"""

import sys

import chromadb

CHROMADB_PATH = "chromadb_data"

# Collections confirmed safe to remove (all have Jina v3 replacements)
LEGACY_COLLECTIONS = {
    "sfs_lagtext_bge_m3_1024",
    "riksdag_documents_bge_m3_1024",
    "procedural_guides_bge_m3_1024",
    "praxis_bge_m3_1024",
    "riksdag_documents_jina_v3_1024",  # 10-doc stub, real one is _p1_
    "constitutional_examples",  # test data
}


def main() -> None:
    print(f"Connecting to ChromaDB at {CHROMADB_PATH} ...")
    client = chromadb.PersistentClient(path=CHROMADB_PATH)

    all_collections = client.list_collections()
    print(f"\nFound {len(all_collections)} total collections:\n")

    to_delete = []
    for coll in sorted(all_collections, key=lambda c: c.name):
        try:
            count = coll.count()
        except Exception:
            count = -1
        is_legacy = coll.name in LEGACY_COLLECTIONS
        is_empty_test = coll.name.startswith("test_") and count == 0
        should_delete = is_legacy or is_empty_test
        marker = " *** WILL DELETE" if should_delete else ""
        print(f"  {coll.name:50s}  ({count:>8} docs){marker}")
        if should_delete:
            to_delete.append(coll.name)

    if not to_delete:
        print("\nNo legacy collections found. Nothing to do.")
        return

    print(f"\n{len(to_delete)} collection(s) marked for deletion:")
    for name in to_delete:
        print(f"  - {name}")

    answer = input("\nProceed with deletion? [y/N] ").strip().lower()
    if answer != "y":
        print("Aborted.")
        sys.exit(0)

    for name in to_delete:
        print(f"  Deleting {name} ...", end=" ")
        client.delete_collection(name)
        print("done")

    # Final state
    remaining = client.list_collections()
    print(f"\nDone. {len(remaining)} collections remain.")


if __name__ == "__main__":
    main()

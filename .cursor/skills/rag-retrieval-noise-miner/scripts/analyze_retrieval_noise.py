#!/usr/bin/env python3
"""Classify retrieval misses from public demo eval JSON."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path


def classify_row(row: dict) -> str:
    if row.get("retrieval_hit_5") is True or row.get("retrieval_hit_10") is True:
        return "hit"
    expected = set(row.get("expected_document_ids") or [])
    retrieved = set(row.get("retrieved_document_ids_top10") or [])
    if not retrieved:
        return "no_results"
    if expected and retrieved & expected:
        return "partial_overlap"
    if retrieved:
        return "wrong_doc_right_terms_possible"
    return "unknown_miss"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("eval_json", type=Path)
    args = parser.parse_args()

    payload = json.loads(args.eval_json.read_text(encoding="utf-8"))
    rows = payload.get("rows", [])
    if not rows:
        print("No rows in eval artifact.")
        return 1

    classes = Counter(classify_row(r) for r in rows)
    misses = [r for r in rows if classify_row(r) != "hit"]

    print("=== Retrieval noise summary ===")
    for label, count in classes.most_common():
        print(f"  {label}: {count}")

    hit5 = payload.get("summary", {}).get("retrieval_hit@5")
    hit10 = payload.get("summary", {}).get("retrieval_hit@10")
    if hit5 is not None:
        print(f"retrieval_hit@5: {hit5}")
    if hit10 is not None:
        print(f"retrieval_hit@10: {hit10}")

    if misses:
        print("\nSample misses (up to 5):")
        for row in misses[:5]:
            print(
                f"  - id={row.get('question_id')} category={row.get('category')} "
                f"class={classify_row(row)} expected={row.get('expected_document_ids')}"
            )

    print("\nRecommendations:")
    if classes.get("no_results", 0):
        print("  - Check BM25 index path and query normalization")
    if classes.get("wrong_doc_right_terms_possible", 0):
        print("  - Review BM25 ranking / chunk boundaries — not LLM prompt")
    if classes.get("partial_overlap", 0):
        print("  - Golden doc in corpus but outside top-k — tune top_k or chunking")
    if not misses:
        print("  - No retrieval misses in sample")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
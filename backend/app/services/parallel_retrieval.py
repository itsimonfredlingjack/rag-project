"""
Parallel Retrieval — Phase 1 parallel collection search with timeout handling.

Extracted from retrieval_orchestrator.py (Sprint 2, P2-14).
Contains standalone async functions for searching ChromaDB collections in parallel.
"""

import asyncio
import logging
import math
import re
import time
from typing import Dict, List, Optional, Tuple

from .retrieval_models import RetrievalMetrics

logger = logging.getLogger("constitutional.retrieval")

# Pre-compiled regex for stripping re-index suffixes (_v2, _v3, etc.)
_REINDEX_SUFFIX_RE = re.compile(r"_v\d+$")


def get_canonical_doc_id(doc_id: str) -> str:
    """
    Normalize a document ID for deduplication.

    Strips re-index suffixes (_v2/_v3), chunk indices (_chunk_N),
    and numeric colon-suffixes (id:42) while preserving SFS numbers
    like "2001:453_4_kap_1_§".

    Args:
        doc_id: Raw document ID from ChromaDB

    Returns:
        Canonical document ID for dedup comparison
    """
    canonical = _REINDEX_SUFFIX_RE.sub("", doc_id)
    if "_chunk_" in canonical:
        canonical = canonical.split("_chunk_")[0]
    elif ":" in canonical:
        # Only strip ":" suffix if the right side is purely numeric (chunk index)
        # SFS IDs like "2001:453_4_kap_1_§" contain ":" as part of the number
        parts = canonical.rsplit(":", 1)
        if len(parts) == 2 and parts[1].isdigit():
            canonical = parts[0]

    if canonical != doc_id:
        logger.debug(f"Canonical doc ID: '{doc_id}' → '{canonical}'")

    return canonical


def get_collection_with_fallback(client, requested_name: str, emit_log: bool = True):
    """
    Resolve a collection by name. No fallback; Jina v3 collections only.
    """
    candidates = [requested_name]
    last_error = None
    for candidate in candidates:
        try:
            collection = client.get_collection(name=candidate)
            if emit_log and candidate != requested_name:
                logger.warning(
                    "Collection fallback active: requested=%s resolved=%s",
                    requested_name,
                    candidate,
                )
            return candidate, collection
        except Exception as exc:  # pragma: no cover - defensive path
            last_error = exc

    if emit_log:
        logger.warning(f"Collection {requested_name} not found: {last_error}")
    return None


async def search_single_collection(
    collection,
    query_embedding: List[float],
    n_results: int,
    where_filter: Optional[Dict] = None,
    timeout_seconds: float = 5.0,
) -> Tuple[List[Dict], float, bool]:
    """
    Search a single ChromaDB collection with timeout.

    Returns:
        Tuple of (results, latency_ms, timed_out)
    """
    start = time.perf_counter()
    timed_out = False
    results = []

    try:
        # Wrap synchronous ChromaDB call in executor for true async
        loop = asyncio.get_event_loop()

        def _query():
            return collection.query(
                query_embeddings=[query_embedding],
                n_results=n_results,
                where=where_filter if where_filter else None,
                include=["metadatas", "documents", "distances"],
            )

        # Run with timeout
        query_results = await asyncio.wait_for(
            loop.run_in_executor(None, _query), timeout=timeout_seconds
        )

        # Parse results
        if query_results and query_results.get("ids") and len(query_results["ids"]) > 0:
            # Detect distance metric from collection metadata
            space = collection.metadata.get("hnsw:space", "l2") if collection.metadata else "l2"

            for i in range(len(query_results["ids"][0])):
                doc_id = query_results["ids"][0][i]
                metadata = (
                    query_results["metadatas"][0][i] if query_results.get("metadatas") else {}
                )
                document = (
                    query_results["documents"][0][i] if query_results.get("documents") else ""
                )
                distance = (
                    query_results["distances"][0][i] if query_results.get("distances") else 1.0
                )

                # Convert distance to score (0-1, higher is better)
                if space == "cosine":
                    score = 1.0 - distance  # cosine distance -> similarity
                elif space == "ip":
                    score = distance  # inner product already similarity-like
                else:  # l2
                    score = 1.0 / (1.0 + distance)

                # Use page_content from metadata if available (for contextual retrieval),
                # otherwise fallback to document field
                display_text = metadata.get("page_content", document)
                snippet = display_text[:1200] + "..." if len(display_text) > 1200 else display_text

                results.append(
                    {
                        "id": doc_id,
                        "title": metadata.get("title", "Untitled"),
                        "snippet": snippet,
                        "score": score,
                        "source": metadata.get("source", collection.name),
                        "doc_type": metadata.get("doc_type"),
                        "date": metadata.get("date"),
                        "collection": collection.name,
                        "_space": space,
                    }
                )

    except asyncio.TimeoutError:
        timed_out = True
        logger.warning(f"Collection {collection.name} timed out after {timeout_seconds}s")
    except Exception as e:
        logger.error(f"Error searching {collection.name}: {e}")

    latency_ms = (time.perf_counter() - start) * 1000
    return results, latency_ms, timed_out


async def parallel_collection_search(
    client,
    query_embedding: List[float],
    collection_names: List[str],
    n_results_per_collection: int = 10,
    where_filter: Optional[Dict] = None,
    timeout_seconds: float = 5.0,
) -> Tuple[List[Dict], RetrievalMetrics]:
    """
    Search multiple collections in parallel with graceful degradation.

    If any collection times out, we still return results from successful ones.
    """
    start_total = time.perf_counter()
    metrics = RetrievalMetrics(strategy="parallel_v1")

    # Get all collections
    collections = []
    for name in collection_names:
        resolved = get_collection_with_fallback(client, name)
        if resolved is None:
            continue
        resolved_name, collection = resolved
        collections.append((name, resolved_name, collection))

    if not collections:
        return [], metrics

    # Create tasks for parallel execution
    tasks = [
        search_single_collection(
            collection=coll,
            query_embedding=query_embedding,
            n_results=n_results_per_collection,
            where_filter=where_filter,
            timeout_seconds=timeout_seconds,
        )
        for _, _, coll in collections
    ]

    # Execute all in parallel
    results_list = await asyncio.gather(*tasks, return_exceptions=True)

    # Merge results
    all_results = []
    collection_latencies = []

    for i, result in enumerate(results_list):
        requested_name, resolved_name, _ = collections[i]
        coll_name = resolved_name

        if isinstance(result, Exception):
            logger.error(
                "Collection %s (requested as %s) failed: %s",
                coll_name,
                requested_name,
                result,
            )
            continue

        results, latency_ms, timed_out = result
        collection_latencies.append(latency_ms)

        if timed_out:
            if "dense" in coll_name.lower() or "sfs" in coll_name.lower():
                metrics.dense_timeout = True
            else:
                metrics.bm25_timeout = True
        else:
            all_results.extend(results)

            # Track counts (simplified - assume first collection is "dense-like")
            if i == 0:
                metrics.dense_result_count = len(results)
                metrics.dense_latency_ms = latency_ms
            else:
                metrics.bm25_result_count += len(results)
                metrics.bm25_latency_ms = max(metrics.bm25_latency_ms, latency_ms)

    # Calculate total latency (should be ~max, not sum, due to parallelism)
    metrics.total_latency_ms = (time.perf_counter() - start_total) * 1000

    # OPTIMIZED: Deduplicate by doc ID using set for O(1) lookup
    seen_ids = {}  # Keep dict to track highest score
    seen_set = set()  # Fast O(1) membership check
    for r in all_results:
        doc_id = r["id"]
        if doc_id not in seen_set:
            seen_set.add(doc_id)
            seen_ids[doc_id] = r
        elif r["score"] > seen_ids[doc_id]["score"]:
            seen_ids[doc_id] = r

    unique_results = list(seen_ids.values())
    metrics.unique_docs_total = len(unique_results)

    # Calculate overlap (docs found in multiple collections - approximate)
    total_before_dedup = len(all_results)
    metrics.doc_overlap_count = total_before_dedup - len(unique_results)

    # Sort by score (RRF would go here in Phase 3)
    unique_results.sort(key=lambda x: x["score"], reverse=True)

    # Calculate score statistics for Phase 4
    if unique_results:
        scores = [r["score"] for r in unique_results]
        metrics.top_score = scores[0]
        metrics.mean_score = sum(scores) / len(scores)

        if len(scores) > 1:
            mean = metrics.mean_score
            variance = sum((s - mean) ** 2 for s in scores) / len(scores)
            metrics.score_std = variance**0.5

            # Simplified entropy (normalized)
            if metrics.top_score > 0:
                normalized_scores = [s / sum(scores) for s in scores]
                entropy = -sum(p * math.log(p + 1e-10) for p in normalized_scores if p > 0)
                max_entropy = math.log(len(scores))
                metrics.score_entropy = entropy / max_entropy if max_entropy > 0 else 0

    logger.info(
        f"Parallel search: {len(unique_results)} results in {metrics.total_latency_ms:.1f}ms "
        f"(dense: {metrics.dense_latency_ms:.1f}ms, bm25: {metrics.bm25_latency_ms:.1f}ms)"
    )

    return unique_results, metrics

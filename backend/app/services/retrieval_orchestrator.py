"""
Retrieval Orchestrator - Phase 1, 2, 3 & 4: Complete Smarter Retrieval Stack
=============================================================================

Centralized retrieval logic for Svensk Ragg.
Supports parallel search, graceful degradation, query rewriting, and instrumentation.

Phase 1: Parallel collection search with timeout handling ✓
Phase 2: Query rewriting with decontextualization ✓
Phase 3: RAG-Fusion multi-query with RRF merge ✓
Phase 4: Adaptive retrieval with confidence-based escalation ✓

Adaptive Retrieval (Phase 4):
- Computes confidence signals (top_score, margin, must_include_hit_rate, etc.)
- Escalates in cheap steps: A→B→C→D
- Step A: rag_fusion 2 queries
- Step B: increase k_pre_rerank, search more collections
- Step C: rag_fusion 3 queries
- Step D: fallback (ask for clarification)
"""

import asyncio
import json
import logging
import re
import time
from typing import Any, Dict, List, Optional

from ..shared.public_source_guard import PublicSourceGuardError, validate_public_records

# Phase 4: Confidence signals for adaptive retrieval
from .confidence_signals import (
    ConfidenceCalculator,
    EscalationPolicy,
)

# Phase 3: RAG-Fusion imports
from .rag_fusion import (
    QueryExpander,
    calculate_fusion_metrics,
    hybrid_reciprocal_rank_fusion,
)

# BM25 Sidecar for hybrid search
from .bm25_service import BM25Service
from .query_expansion_service import QueryExpansionService

# EPR: Evidence Policy Routing (Phase 5)
from .source_hierarchy import SourceHierarchy, SourceTier
from .intent_classifier import IntentClassifier, QueryIntent, llm_classify_intent
from .intent_routing import get_routing_for_intent

# Extracted modules (Sprint 2, P2-14) — re-exported for backward compatibility
from .retrieval_models import (  # noqa: F401
    RetrievalMetrics,
    RetrievalResult,
    RetrievalStrategy,
    SearchResult,
)
from .parallel_retrieval import (  # noqa: F401
    get_canonical_doc_id,
    get_collection_with_fallback as _get_collection_with_fallback,
    parallel_collection_search,
    search_single_collection,
)

logger = logging.getLogger("constitutional.retrieval")


# ═══════════════════════════════════════════════════════════════════════════
# DATA MODELS & UTILITIES — now in retrieval_models.py and parallel_retrieval.py
# Re-exported above for backward compatibility.
# ═══════════════════════════════════════════════════════════════════════════


# The following classes/functions have been extracted to separate modules:
# - RetrievalMetrics → retrieval_models.py
# - SearchResult → retrieval_models.py
# - RetrievalResult → retrieval_models.py
# - RetrievalStrategy → retrieval_models.py
# - get_canonical_doc_id() → parallel_retrieval.py
# - _get_collection_with_fallback() → parallel_retrieval.py
# - search_single_collection() → parallel_retrieval.py
# - parallel_collection_search() → parallel_retrieval.py


# Sentinel to mark where the old inline definitions were (for git blame):
_MODELS_EXTRACTED = True  # noqa: F841

# ═══════════════════════════════════════════════════════════════════════════
# MAIN ORCHESTRATOR
# ═══════════════════════════════════════════════════════════════════════════


class RetrievalOrchestrator:
    """
    Main orchestrator for retrieval strategies.

    Usage:
        orchestrator = RetrievalOrchestrator(chromadb_client, embed_fn)
        result = await orchestrator.search("GDPR personuppgifter", k=10)

        # With query rewriting (Phase 2):
        from .query_rewriter import QueryRewriter
        rewriter = QueryRewriter()
        orchestrator = RetrievalOrchestrator(client, embed_fn, query_rewriter=rewriter)
        result = await orchestrator.search(
            "Vad säger den?",
            history=["Berätta om GDPR"],
            strategy=RetrievalStrategy.REWRITE_V1
        )
    """

    # Fallback only - prefer passing default_collections from config
    DEFAULT_COLLECTIONS = [
        "sfs_lagtext_jina_v3_1024",
        "riksdag_documents_p1_jina_v3_1024",
        "swedish_gov_docs_jina_v3_1024",
    ]

    # Concurrency control for multi-query (Phase 3)
    MAX_CONCURRENT_QUERIES = 3

    def __init__(
        self,
        chromadb_client,
        embedding_function,
        default_timeout: float = 5.0,
        query_rewriter=None,  # Phase 2: Optional QueryRewriter instance
        query_expander=None,  # Phase 3: Optional QueryExpander instance
        default_collections: Optional[
            List[str]
        ] = None,  # From config.effective_default_collections
        bm25_service: Optional[BM25Service] = None,  # Hybrid search: BM25 sidecar
        bm25_weight: float = 1.5,  # Weight for BM25 in RRF (1.0 = equal, 1.5 = favor exact terms)
        rrf_k: float = 30.0,  # RRF k constant (lower = top results dominate)
        score_threshold: float = 0.35,  # Min similarity score for EPR results
        query_expansion_service: Optional[QueryExpansionService] = None,
        query_expansion_enabled: bool = True,
        query_expansion_count: int = 3,
        use_epr_fusion: bool = True,
        epr_fusion_num_queries: int = 3,
        embedding_model_name: Optional[str] = None,
        reranker_model_name: Optional[str] = None,
        cutover_enforce_jina_collections: bool = False,
        cutover_allowed_fallback_collections: Optional[List[str]] = None,
        query_expansion_confidence_gate: bool = True,
        query_expansion_confidence_threshold: float = 0.5,
        # LLM intent fallback (zero-shot classification for ambiguous queries)
        llm_service: Optional[Any] = None,
        intent_llm_fallback_enabled: bool = False,
        intent_llm_fallback_timeout: float = 3.0,
        intent_llm_fallback_confidence_threshold: float = 0.50,
        public_guard_enabled: bool = False,
    ):
        self.client = chromadb_client
        self.embed_fn = embedding_function
        self.default_timeout = default_timeout
        self.rewriter = query_rewriter
        self.expander = query_expander or QueryExpander(max_queries=3)
        self._query_semaphore = asyncio.Semaphore(self.MAX_CONCURRENT_QUERIES)
        # Use passed collections or fall back to class default
        self._default_collections = default_collections or self.DEFAULT_COLLECTIONS
        # BM25 sidecar for hybrid search (lazy load if not provided)
        self._bm25_service = bm25_service
        self._bm25_weight = bm25_weight
        self._rrf_k = rrf_k
        self._score_threshold = score_threshold
        self._query_expansion_service = query_expansion_service
        self._query_expansion_enabled = query_expansion_enabled
        self._query_expansion_count = query_expansion_count
        self._query_expansion_confidence_gate = query_expansion_confidence_gate
        self._query_expansion_confidence_threshold = query_expansion_confidence_threshold
        # EPR RAG-Fusion settings
        self._use_epr_fusion = use_epr_fusion
        self._epr_fusion_num_queries = epr_fusion_num_queries
        self._embedding_model_name = embedding_model_name or "unknown"
        self._reranker_model_name = reranker_model_name or "unknown"
        self._cutover_enforce_jina_collections = cutover_enforce_jina_collections
        self._cutover_allowed_fallback_collections = {
            value.casefold() for value in (cutover_allowed_fallback_collections or [])
        }
        # LLM intent fallback
        self._llm_service = llm_service
        self._intent_llm_fallback_enabled = intent_llm_fallback_enabled
        self._intent_llm_fallback_timeout = intent_llm_fallback_timeout
        self._intent_llm_fallback_confidence_threshold = intent_llm_fallback_confidence_threshold
        self._public_guard_enabled = public_guard_enabled

    def _guard_public_records(self, records: List[Any], *, stage: str) -> None:
        validate_public_records(records, stage=stage, enabled=self._public_guard_enabled)

    def _get_bm25_index_size_bytes(self) -> int:
        """Return on-disk BM25 index size in bytes (best-effort)."""
        if not self._bm25_service or not self._bm25_service.index_path.exists():
            return 0
        try:
            p = self._bm25_service.index_path
            if p.is_file():
                return p.stat().st_size
            return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
        except Exception:
            return 0

    def _get_bm25_observability(self) -> Dict[str, Any]:
        """Return best-effort BM25 observability payload for structured logs."""
        if not self._bm25_service:
            return {
                "available": False,
                "loaded": False,
                "doc_count": 0,
                "index_path": None,
                "index_size_bytes": 0,
            }

        try:
            stats = dict(self._bm25_service.get_stats())
        except Exception:
            # Defensive fallback if bm25 service doesn't expose stats for any reason.
            stats = {
                "available": bool(getattr(self._bm25_service, "is_available", lambda: False)()),
                "loaded": bool(getattr(self._bm25_service, "is_loaded", lambda: False)()),
                "index_path": str(getattr(self._bm25_service, "index_path", "")) or None,
                "doc_count": 0,
            }

        stats["index_size_bytes"] = self._get_bm25_index_size_bytes()
        return stats

    def _resolve_collection_pairs(self, requested_collections: List[str]) -> List[Dict[str, Any]]:
        """Resolve requested collections and capture fallback mapping."""
        pairs: List[Dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for requested in requested_collections:
            resolved = _get_collection_with_fallback(self.client, requested, emit_log=False)
            if resolved is None:
                pair = (requested, "__missing__")
                if pair in seen:
                    continue
                seen.add(pair)
                pairs.append(
                    {
                        "requested": requested,
                        "resolved": None,
                        "fallback_used": False,
                        "exists": False,
                    }
                )
                continue

            resolved_name, _ = resolved
            pair = (requested, resolved_name)
            if pair in seen:
                continue
            seen.add(pair)
            pairs.append(
                {
                    "requested": requested,
                    "resolved": resolved_name,
                    "fallback_used": requested != resolved_name,
                    "exists": True,
                }
            )

        return pairs

    def _enforce_cutover_policy(
        self,
        requested_collections: List[str],
        metrics: Optional[RetrievalMetrics] = None,
    ) -> None:
        """
        Enforce collection cutover policy.

        When enabled, retrieval fails closed if requested Jina collections are missing.
        """
        pairs = self._resolve_collection_pairs(requested_collections)
        violations: List[str] = []

        for pair in pairs:
            requested = str(pair.get("requested") or "")
            if not requested:
                continue
            if requested.casefold() in self._cutover_allowed_fallback_collections:
                continue
            if pair.get("fallback_used") or not pair.get("exists", False):
                violations.append(requested)

        if metrics:
            metrics.cutover_enforced = self._cutover_enforce_jina_collections
            metrics.cutover_violation = bool(violations)
            metrics.cutover_violation_collections = sorted(set(violations))

        if self._cutover_enforce_jina_collections and violations:
            unique_violations = sorted(set(violations))
            raise RuntimeError(
                "CUTOVER_VIOLATION: fallback/missing collection detected while "
                f"cutover enforcement is enabled: {unique_violations}"
            )

    def _log_observability(
        self,
        *,
        query: str,
        metrics: RetrievalMetrics,
        requested_collections: List[str],
    ) -> None:
        """Emit structured JSON observability log for each retrieval request."""
        payload = {
            "event": "retrieval_request_observability",
            "strategy": metrics.strategy,
            "query": query,
            "embedding_model_name": self._embedding_model_name,
            "reranker_model_name": self._reranker_model_name,
            "requested_collections": requested_collections,
            "bm25": self._get_bm25_observability(),
            "resolved_collection": self._resolve_collection_pairs(requested_collections),
            "query_expansions": metrics.llm_query_expansions,
            "expansion_grammar_used": metrics.llm_query_expansion_grammar_used,
            "expansion_parsing_method": metrics.llm_query_expansion_parsing_method,
            "cutover_enforced": metrics.cutover_enforced,
            "cutover_violation": metrics.cutover_violation,
            "cutover_violation_collections": metrics.cutover_violation_collections,
        }
        logger.info(json.dumps(payload, ensure_ascii=False))

    async def _get_llm_expansions(
        self,
        query: str,
        metrics: Optional[RetrievalMetrics] = None,
    ) -> List[str]:
        """Generate extra lexical query variants via one LLM call (fail-open)."""
        if not (
            self._query_expansion_enabled
            and self._query_expansion_service
            and query
            and query.strip()
        ):
            return []

        try:
            result = await self._query_expansion_service.expand(
                query=query,
                count=self._query_expansion_count,
            )
            if metrics:
                metrics.llm_query_expansion_latency_ms = result.latency_ms
                metrics.llm_query_expansion_count = len(result.queries)
                metrics.llm_query_expansion_used = bool(result.queries)
                metrics.llm_query_expansions = list(result.queries)
                metrics.llm_query_expansion_grammar_used = bool(result.grammar_applied)
                metrics.llm_query_expansion_parsing_method = result.parsing_method
            return result.queries
        except Exception as exc:
            logger.warning(f"LLM query expansion failed (continuing without expansion): {exc}")
            if metrics:
                metrics.llm_query_expansion_used = False
                metrics.llm_query_expansion_grammar_used = False
                metrics.llm_query_expansion_parsing_method = "none"
            return []

    def _build_bm25_query(
        self,
        base_query: str,
        rewrite_result=None,
        llm_expansions: Optional[List[str]] = None,
    ) -> str:
        """Build BM25 lexical query from rewrite output plus optional LLM expansions."""
        query_parts: List[str] = []
        seen: set[str] = set()

        lexical = base_query
        if rewrite_result and hasattr(rewrite_result, "lexical_query"):
            lexical = rewrite_result.lexical_query or base_query

        for candidate in [lexical, *(llm_expansions or [])]:
            cleaned = re.sub(r"\s+", " ", (candidate or "")).strip()
            if not cleaned:
                continue
            key = cleaned.casefold()
            if key in seen:
                continue
            seen.add(key)
            query_parts.append(cleaned)

        if not query_parts:
            return base_query

        return " ".join(query_parts)

    async def search(
        self,
        query: str,
        k: int = 10,
        strategy: RetrievalStrategy = RetrievalStrategy.PARALLEL_V1,
        where_filter: Optional[Dict] = None,
        collections: Optional[List[str]] = None,
        history: Optional[List[str]] = None,  # Phase 2: Conversation history
    ) -> RetrievalResult:
        """
        Execute search with specified strategy.

        Args:
            query: Search query
            k: Number of results to return
            strategy: Which retrieval strategy to use
            where_filter: Optional ChromaDB where filter
            collections: Collections to search (default: all)
            history: Conversation history for decontextualization (Phase 2)

        Returns:
            RetrievalResult with results and metrics
        """
        start = time.perf_counter()

        try:
            # Phase 2: Handle query rewriting if strategy is REWRITE_V1
            search_query = query
            rewrite_result = None

            if strategy == RetrievalStrategy.REWRITE_V1 and self.rewriter:
                rewrite_result = self.rewriter.rewrite(query, history)
                # Använd expanded_query (med förkortningar utskrivna) för bättre embedding-matchning
                search_query = rewrite_result.expanded_query
                logger.info(
                    f"Query rewritten: '{query}' → '{search_query}' "
                    f"(expanded: {rewrite_result.expanded_abbreviations}, "
                    f"latency: {rewrite_result.rewrite_latency_ms:.2f}ms)"
                )

            # Generate embedding for the (possibly rewritten) query
            query_embedding = self.embed_fn([search_query])[0]

            # Execute parallel search (for both PARALLEL_V1 and REWRITE_V1)
            if strategy in (RetrievalStrategy.PARALLEL_V1, RetrievalStrategy.REWRITE_V1):
                requested_collections = collections or self._default_collections
                self._enforce_cutover_policy(requested_collections)
                results, metrics = await parallel_collection_search(
                    client=self.client,
                    query_embedding=query_embedding,
                    collection_names=requested_collections,
                    n_results_per_collection=k,
                    where_filter=where_filter,
                    timeout_seconds=self.default_timeout,
                )

                # Update strategy in metrics
                metrics.strategy = strategy.value

                self._guard_public_records(results, stage="retrieval_parallel_results")

                # Add rewrite metrics if used
                if rewrite_result:
                    metrics.rewrite_used = rewrite_result.rewrite_used
                    metrics.rewrite_latency_ms = rewrite_result.rewrite_latency_ms
                    metrics.original_query = query
                    metrics.rewritten_query = search_query

                # Convert to SearchResult objects
                search_results = [
                    SearchResult(
                        id=r["id"],
                        title=r["title"],
                        snippet=r["snippet"],
                        score=r["score"],
                        source=r["source"],
                        source_scope=r.get("source_scope"),
                        doc_type=r.get("doc_type"),
                        date=r.get("date"),
                        retriever="dense",
                    )
                    for r in results[:k]  # Limit to k
                ]

                # FIX: Override total_latency_ms to include embedding time + rewrite time
                metrics.total_latency_ms = (time.perf_counter() - start) * 1000
                self._enforce_cutover_policy(requested_collections, metrics)
                self._log_observability(
                    query=query,
                    metrics=metrics,
                    requested_collections=requested_collections,
                )

                return RetrievalResult(
                    results=search_results,
                    metrics=metrics,
                    success=True,
                )

            # Phase 3: RAG-Fusion
            elif strategy == RetrievalStrategy.RAG_FUSION:
                return await self._search_rag_fusion(
                    query=query,
                    k=k,
                    history=history,
                    collections=collections,
                    where_filter=where_filter,
                )

            # Phase 4: Adaptive Retrieval
            elif strategy == RetrievalStrategy.ADAPTIVE:
                return await self._search_adaptive(
                    query=query,
                    k=k,
                    history=history,
                    collections=collections,
                    where_filter=where_filter,
                )

            # Unknown strategy
            else:
                raise NotImplementedError(f"Strategy {strategy} not yet implemented")

        except Exception as e:
            logger.error(f"Retrieval failed: {e}")
            return RetrievalResult(
                results=[],
                metrics=RetrievalMetrics(
                    total_latency_ms=(time.perf_counter() - start) * 1000,
                    strategy=strategy.value,
                ),
                success=False,
                error=str(e),
            )

    async def _search_rag_fusion(
        self,
        query: str,
        k: int,
        history: Optional[List[str]],
        collections: Optional[List[str]],
        where_filter: Optional[Dict],
    ) -> RetrievalResult:
        """
        Phase 3: RAG-Fusion multi-query retrieval with RRF merge.

        Flow:
        1. Rewrite query (Phase 2) if rewriter available
        2. Expand to multiple query variants (Q0, Q1, Q2)
        3. Batch embed all queries
        4. Search each embedding in parallel (with semaphore)
        5. Merge results with RRF (k=configurable, default 30)
        6. Return with fusion metrics
        """
        start_total = time.perf_counter()
        metrics = RetrievalMetrics(strategy="rag_fusion")

        # Step 1: Rewrite query if rewriter available
        search_query = query
        rewrite_result = None

        if self.rewriter:
            rewrite_result = self.rewriter.rewrite(query, history)
            # Använd expanded_query för bättre embedding-matchning
            search_query = rewrite_result.expanded_query
            metrics.rewrite_used = rewrite_result.rewrite_used
            metrics.rewrite_latency_ms = rewrite_result.rewrite_latency_ms
            metrics.original_query = query
            metrics.rewritten_query = search_query
            if rewrite_result.expanded_abbreviations:
                logger.info(f"Expanded abbreviations: {rewrite_result.expanded_abbreviations}")

        # Step 2: Expand to multiple query variants
        if rewrite_result:
            expanded = self.expander.expand(search_query, rewrite_result)
        else:
            # Create a minimal rewrite result for expansion
            from dataclasses import dataclass

            @dataclass
            class MinimalRewriteResult:
                standalone_query: str = ""
                lexical_query: str = ""
                detected_entities: list = None

                def __post_init__(self):
                    if self.detected_entities is None:
                        self.detected_entities = []

            minimal_result = MinimalRewriteResult(
                standalone_query=search_query,
                lexical_query="",
                detected_entities=[],
            )
            expanded = self.expander.expand(search_query, minimal_result)

        metrics.expansion_latency_ms = expanded.expansion_latency_ms
        metrics.num_queries = len(expanded.queries)
        metrics.query_variants = expanded.queries

        # Step 3+4: Embed+dense search and BM25 search in parallel
        collection_names = collections or self._default_collections
        self._enforce_cutover_policy(collection_names, metrics)
        llm_expansions = await self._get_llm_expansions(query, metrics)

        async def _embed_and_dense_search():
            """Embed queries and run dense search."""
            embed_start = time.perf_counter()
            query_embeddings = self.embed_fn(expanded.queries)
            embed_latency = (time.perf_counter() - embed_start) * 1000
            logger.info(
                f"Batch embedding: {len(expanded.queries)} queries in {embed_latency:.1f}ms"
            )

            async def search_single_embedding(embedding):
                async with self._query_semaphore:
                    results, _ = await parallel_collection_search(
                        client=self.client,
                        query_embedding=embedding,
                        collection_names=collection_names,
                        n_results_per_collection=k,
                        where_filter=where_filter,
                        timeout_seconds=self.default_timeout,
                    )
                    return results

            tasks = [search_single_embedding(emb) for emb in query_embeddings]
            result_sets = await asyncio.gather(*tasks, return_exceptions=True)

            valid_result_sets = []
            for i, result in enumerate(result_sets):
                if isinstance(result, Exception):
                    logger.error(f"Query {i} failed: {result}")
                    valid_result_sets.append([])
                else:
                    valid_result_sets.append(result)

            metrics.per_query_result_counts = [len(rs) for rs in valid_result_sets]
            return valid_result_sets

        async def _bm25_search_async():
            """Run BM25 search (doesn't need embeddings)."""
            if not (self._bm25_service and self._bm25_service.is_available()):
                return []
            try:
                bm25_start = time.perf_counter()
                bm25_query = self._build_bm25_query(search_query, rewrite_result, llm_expansions)
                loop = asyncio.get_event_loop()
                results = await loop.run_in_executor(
                    None,
                    lambda: self._bm25_service.search(
                        bm25_query,
                        k=k * 2,
                        return_docs=True,
                    ),
                )
                metrics.bm25_latency_ms = (time.perf_counter() - bm25_start) * 1000
                metrics.bm25_result_count = len(results)
                logger.info(
                    f"BM25 search: '{bm25_query[:30]}...' → {len(results)} results "
                    f"in {metrics.bm25_latency_ms:.1f}ms"
                )
                return results
            except PublicSourceGuardError:
                raise
            except Exception as e:
                logger.warning(f"BM25 search failed (continuing with dense only): {e}")
                metrics.bm25_timeout = True
                return []

        # Run embed+dense and BM25 in parallel
        valid_result_sets, bm25_results = await asyncio.gather(
            _embed_and_dense_search(),
            _bm25_search_async(),
        )

        # Step 5: Merge with Hybrid RRF (dense + BM25)
        rrf_start = time.perf_counter()
        merged_results = hybrid_reciprocal_rank_fusion(
            dense_result_sets=valid_result_sets,
            bm25_results=bm25_results if bm25_results else None,
            k=self._rrf_k,
            bm25_weight=self._bm25_weight,
            public_guard_enabled=self._public_guard_enabled,
        )
        metrics.rrf_latency_ms = (time.perf_counter() - rrf_start) * 1000

        # Step 6: Calculate fusion metrics
        fusion_metrics = calculate_fusion_metrics(
            result_sets=valid_result_sets,
            merged_results=merged_results,
            expanded_queries=expanded,
        )

        metrics.fusion_used = True
        metrics.unique_docs_before_fusion = fusion_metrics.unique_docs_before_fusion
        metrics.unique_docs_after_fusion = fusion_metrics.unique_docs_after_fusion
        metrics.overlap_ratio = fusion_metrics.overlap_ratio
        metrics.fusion_gain = fusion_metrics.fusion_gain

        # Calculate total latency
        metrics.total_latency_ms = (time.perf_counter() - start_total) * 1000

        # Determine retriever type (hybrid if BM25 was used)
        retriever_type = "hybrid" if bm25_results else "fusion"

        # Convert to SearchResult objects
        search_results = [
            SearchResult(
                id=r["id"],
                title=r.get("title", "Untitled"),
                snippet=r.get("snippet", ""),
                score=r.get("rrf_score", r.get("score", 0.0)),
                source=r.get("source", "unknown"),
                source_scope=r.get("source_scope"),
                doc_type=r.get("doc_type"),
                date=r.get("date"),
                retriever=retriever_type,
            )
            for r in merged_results[:k]
        ]

        bm25_info = f", bm25: {metrics.bm25_result_count}" if bm25_results else ""
        logger.info(
            f"RAG-Fusion complete: {len(search_results)} results in {metrics.total_latency_ms:.1f}ms "
            f"(queries: {metrics.num_queries}{bm25_info}, gain: {metrics.fusion_gain:.1%})"
        )
        self._log_observability(
            query=query,
            metrics=metrics,
            requested_collections=collection_names,
        )

        return RetrievalResult(
            results=search_results,
            metrics=metrics,
            success=True,
        )

    async def _search_adaptive(
        self,
        query: str,
        k: int,
        history: Optional[List[str]],
        collections: Optional[List[str]],
        where_filter: Optional[Dict],
    ) -> RetrievalResult:
        """
        Phase 4: Adaptive retrieval with confidence-based escalation.

        Policy: Escalate in cheap, clear steps (Self-RAG inspired):
          Step A: rag_fusion with 2 queries → return if confidence OK
          Step B: increase k_pre_rerank, search all collections → return if OK
          Step C: rag_fusion with 3 queries → return if OK
          Step D: fallback (ask for clarification, or HyDE later)

        No additional LLM calls - confidence computed from retrieval signals:
          - top_score, margin (ranking certainty)
          - must_include_hit_rate (coverage)
          - overlap_ratio, fusion_gain (query agreement)
          - near_duplicate_ratio (diversity)
        """
        start_total = time.perf_counter()
        metrics = RetrievalMetrics(strategy="adaptive")
        metrics.adaptive_used = True

        # Initialize confidence calculator
        confidence_calc = ConfidenceCalculator(rrf_k=self._rrf_k)

        # Get must_include tokens from rewriter (if available)
        must_include = []
        rewrite_result = None
        if self.rewriter:
            rewrite_result = self.rewriter.rewrite(query, history)
            must_include = rewrite_result.must_include or []
            metrics.rewrite_used = rewrite_result.rewrite_used
            metrics.rewrite_latency_ms = rewrite_result.rewrite_latency_ms
            metrics.original_query = query
            # Visa expanded_query i metrics (med förkortningar utskrivna)
            metrics.rewritten_query = rewrite_result.expanded_query
            if rewrite_result.expanded_abbreviations:
                logger.info(f"Adaptive search - expanded: {rewrite_result.expanded_abbreviations}")

        # Defer LLM expansion: skip for Step A, only invoke during escalation (Step B+)
        if self._query_expansion_confidence_gate:
            llm_expansions = []
        else:
            llm_expansions = await self._get_llm_expansions(query, metrics)
        bm25_query_override = self._build_bm25_query(query, rewrite_result, llm_expansions)
        self._enforce_cutover_policy(collections or self._default_collections, metrics)

        # Track escalation path and reason codes for decision trace
        escalation_path = []
        reason_codes = []  # NEW: Decision trace
        final_results = []
        final_signals = None

        # === STEP A: rag_fusion with 2 queries ===
        escalation_path.append("A")
        step_config = EscalationPolicy.get_step_config("A")

        result_a = await self._execute_fusion_step(
            query=query,
            k=k,
            num_queries=step_config["num_queries"],
            k_multiplier=step_config["k_multiplier"],
            collections=collections,
            where_filter=where_filter,
            rewrite_result=rewrite_result,
            bm25_query_override=bm25_query_override,
        )

        # Compute confidence signals - NOW with original_query for lexical overlap
        fusion_metrics_dict = {
            "fusion_gain": result_a.metrics.fusion_gain,
            "overlap_ratio": result_a.metrics.overlap_ratio,
        }
        signals_a = confidence_calc.compute(
            results=[r.__dict__ if hasattr(r, "__dict__") else r for r in result_a.results],
            must_include=must_include,
            fusion_metrics=fusion_metrics_dict,
            original_query=query,  # NEW: Pass query for lexical overlap
        )

        should_escalate, reason = confidence_calc.should_escalate(signals_a)
        reason_codes.append(f"A: {reason}")

        if not should_escalate:
            # Step A is sufficient
            logger.info(f"Adaptive: Step A OK (confidence={signals_a.overall_confidence:.2f})")
            final_results = result_a.results
            final_signals = signals_a
        else:
            logger.info(f"Adaptive: Escalating from A ({reason})")

            # Confidence too low — now invoke LLM expansion for escalation steps
            if self._query_expansion_confidence_gate and not llm_expansions:
                llm_expansions = await self._get_llm_expansions(query, metrics)
                bm25_query_override = self._build_bm25_query(query, rewrite_result, llm_expansions)

            # === STEP B: increase k, search more collections ===
            escalation_path.append("B")
            step_config = EscalationPolicy.get_step_config("B")

            result_b = await self._execute_fusion_step(
                query=query,
                k=k,
                num_queries=step_config["num_queries"],
                k_multiplier=step_config["k_multiplier"],
                collections=None,  # Search all available
                where_filter=where_filter,
                rewrite_result=rewrite_result,
                bm25_query_override=bm25_query_override,
            )

            fusion_metrics_dict = {
                "fusion_gain": result_b.metrics.fusion_gain,
                "overlap_ratio": result_b.metrics.overlap_ratio,
            }
            signals_b = confidence_calc.compute(
                results=[r.__dict__ if hasattr(r, "__dict__") else r for r in result_b.results],
                must_include=must_include,
                fusion_metrics=fusion_metrics_dict,
                original_query=query,  # NEW: Pass query for lexical overlap
            )

            should_escalate, reason = confidence_calc.should_escalate(signals_b)
            reason_codes.append(f"B: {reason}")

            if not should_escalate:
                logger.info(f"Adaptive: Step B OK (confidence={signals_b.overall_confidence:.2f})")
                final_results = result_b.results
                final_signals = signals_b
            else:
                logger.info(f"Adaptive: Escalating from B ({reason})")

                # === STEP C: rag_fusion with 3 queries ===
                escalation_path.append("C")
                step_config = EscalationPolicy.get_step_config("C")

                result_c = await self._execute_fusion_step(
                    query=query,
                    k=k,
                    num_queries=step_config["num_queries"],
                    k_multiplier=step_config["k_multiplier"],
                    collections=None,
                    where_filter=where_filter,
                    rewrite_result=rewrite_result,
                    bm25_query_override=bm25_query_override,
                )

                fusion_metrics_dict = {
                    "fusion_gain": result_c.metrics.fusion_gain,
                    "overlap_ratio": result_c.metrics.overlap_ratio,
                }
                signals_c = confidence_calc.compute(
                    results=[r.__dict__ if hasattr(r, "__dict__") else r for r in result_c.results],
                    must_include=must_include,
                    fusion_metrics=fusion_metrics_dict,
                    original_query=query,  # NEW: Pass query for lexical overlap
                )

                should_escalate, reason = confidence_calc.should_escalate(signals_c)
                reason_codes.append(f"C: {reason}")

                if not should_escalate:
                    logger.info(
                        f"Adaptive: Step C OK (confidence={signals_c.overall_confidence:.2f})"
                    )
                    final_results = result_c.results
                    final_signals = signals_c
                else:
                    logger.warning(f"Adaptive: Escalating to fallback D ({reason})")

                    # === STEP D: Fallback ===
                    escalation_path.append("D")
                    reason_codes.append("D: fallback triggered")
                    metrics.fallback_triggered = True

                    # Use Step C results but mark as low confidence
                    final_results = result_c.results
                    final_signals = signals_c
                    final_signals.confidence_tier = "very_low"

        # === NO-ANSWER POLICY ===
        # Check if we should abstain after final step (gibberish detection, very low confidence)
        is_final = escalation_path[-1] == "D" if escalation_path else False
        if final_signals:
            should_abstain, abstain_reason = confidence_calc.should_abstain(
                final_signals, is_final_step=is_final
            )
            if should_abstain:
                final_signals.should_abstain = True
                final_signals.abstain_reason = abstain_reason
                reason_codes.append(f"ABSTAIN: {abstain_reason}")
                logger.warning(
                    f"Adaptive: Abstaining from answer ({abstain_reason}), "
                    f"lexical_overlap={final_signals.lexical_overlap:.2f}"
                )

        # Build final metrics
        metrics.total_latency_ms = (time.perf_counter() - start_total) * 1000
        metrics.escalation_path = escalation_path
        metrics.final_step = escalation_path[-1] if escalation_path else ""
        metrics.confidence_signals = final_signals.to_dict() if final_signals else None
        metrics.reason_codes = reason_codes  # Decision trace for debugging

        conf_score = final_signals.overall_confidence if final_signals else 0.0
        lexical_score = final_signals.lexical_overlap if final_signals else 0.0
        abstain_flag = final_signals.should_abstain if final_signals else False

        logger.info(
            f"Adaptive complete: {len(final_results)} results in {metrics.total_latency_ms:.1f}ms "
            f"(path: {'→'.join(escalation_path)}, conf: {conf_score:.2f}, "
            f"lexical: {lexical_score:.2f}, abstain: {abstain_flag})"
        )
        self._log_observability(
            query=query,
            metrics=metrics,
            requested_collections=collections or self._default_collections,
        )

        return RetrievalResult(
            results=final_results,
            metrics=metrics,
            success=True,
        )

    async def _execute_fusion_step(
        self,
        query: str,
        k: int,
        num_queries: int,
        k_multiplier: float,
        collections: Optional[List[str]],
        where_filter: Optional[Dict],
        rewrite_result,
        bm25_query_override: Optional[str] = None,
    ) -> RetrievalResult:
        """
        Execute a single fusion retrieval step.

        This is a helper for _search_adaptive that runs rag_fusion
        with configurable num_queries and k_multiplier.
        """
        metrics = RetrievalMetrics(strategy="adaptive_step")

        # Use expanded query (med förkortningar) if available
        search_query = query
        if rewrite_result:
            search_query = rewrite_result.expanded_query

        # Expand queries (limit to num_queries)
        if rewrite_result:
            expanded = self.expander.expand(search_query, rewrite_result, num_queries=num_queries)
        else:
            from dataclasses import dataclass

            @dataclass
            class MinimalRewriteResult:
                standalone_query: str = ""
                lexical_query: str = ""
                detected_entities: list = None

                def __post_init__(self):
                    if self.detected_entities is None:
                        self.detected_entities = []

            minimal = MinimalRewriteResult(standalone_query=search_query)
            expanded = self.expander.expand(search_query, minimal, num_queries=num_queries)

        metrics.num_queries = len(expanded.queries)
        metrics.query_variants = expanded.queries

        # Batch embed
        query_embeddings = self.embed_fn(expanded.queries)

        # Adjusted k for this step
        adjusted_k = int(k * k_multiplier)
        collection_names = collections or self._default_collections

        # Search each embedding in parallel
        async def search_single_embedding(embedding: List[float]) -> List[Dict]:
            async with self._query_semaphore:
                results, _ = await parallel_collection_search(
                    client=self.client,
                    query_embedding=embedding,
                    collection_names=collection_names,
                    n_results_per_collection=adjusted_k,
                    where_filter=where_filter,
                    timeout_seconds=self.default_timeout,
                )
                return results

        # BM25 search in parallel with dense (hybrid retrieval)
        async def _bm25_search_async():
            if not (self._bm25_service and self._bm25_service.is_available()):
                return None
            try:
                bm25_start = time.perf_counter()
                bm25_query = bm25_query_override or self._build_bm25_query(
                    search_query,
                    rewrite_result,
                    None,
                )
                loop = asyncio.get_event_loop()
                results = await loop.run_in_executor(
                    None,
                    lambda: self._bm25_service.search(
                        bm25_query,
                        k=adjusted_k * 2,
                        return_docs=True,
                    ),
                )
                metrics.bm25_latency_ms = (time.perf_counter() - bm25_start) * 1000
                logger.info(
                    f"Adaptive BM25: '{bm25_query[:30]}...' → {len(results)} results "
                    f"in {metrics.bm25_latency_ms:.1f}ms"
                )
                return results
            except PublicSourceGuardError:
                raise
            except Exception as e:
                logger.warning(f"Adaptive BM25 failed (continuing dense only): {e}")
                return None

        # Run dense + BM25 in parallel
        dense_tasks = [search_single_embedding(emb) for emb in query_embeddings]
        *result_sets, bm25_results = await asyncio.gather(*dense_tasks, _bm25_search_async())

        # Filter exceptions from dense results
        valid_result_sets = []
        for result in result_sets:
            if isinstance(result, Exception):
                valid_result_sets.append([])
            else:
                valid_result_sets.append(result)

        metrics.per_query_result_counts = [len(rs) for rs in valid_result_sets]
        metrics.bm25_result_count = len(bm25_results) if bm25_results else 0

        # Hybrid RRF merge (dense + BM25)
        merged_results = hybrid_reciprocal_rank_fusion(
            dense_result_sets=valid_result_sets,
            bm25_results=bm25_results,
            k=self._rrf_k,
            bm25_weight=self._bm25_weight,
            public_guard_enabled=self._public_guard_enabled,
        )

        # Calculate fusion metrics
        fusion_metrics = calculate_fusion_metrics(
            result_sets=valid_result_sets,
            merged_results=merged_results,
            expanded_queries=expanded,
        )

        metrics.fusion_used = True
        metrics.unique_docs_before_fusion = fusion_metrics.unique_docs_before_fusion
        metrics.unique_docs_after_fusion = fusion_metrics.unique_docs_after_fusion
        metrics.overlap_ratio = fusion_metrics.overlap_ratio
        metrics.fusion_gain = fusion_metrics.fusion_gain

        # Convert to SearchResult objects
        search_results = [
            SearchResult(
                id=r["id"],
                title=r.get("title", "Untitled"),
                snippet=r.get("snippet", ""),
                score=r.get("rrf_score", r.get("score", 0.0)),
                source=r.get("source", "unknown"),
                source_scope=r.get("source_scope"),
                doc_type=r.get("doc_type"),
                date=r.get("date"),
                retriever="adaptive",
            )
            for r in merged_results[:k]
        ]

        return RetrievalResult(
            results=search_results,
            metrics=metrics,
            success=True,
        )

    # ═══════════════════════════════════════════════════════════════════════════
    # SFS CONTEXT EXPANSION (parent-child retrieval)
    # ═══════════════════════════════════════════════════════════════════════════

    async def _expand_sfs_context(
        self,
        results: List[SearchResult],
        max_siblings: int = 1,
    ) -> List[SearchResult]:
        """
        Expand SFS results with sibling paragraf text and chapter context.

        Only expands results where doc_type == "sfs" and sibling IDs exist.
        Fetches prev/next paragraf chunks by ID from ChromaDB and appends
        their text to the snippet for richer LLM context.

        Args:
            results: List of SearchResult objects
            max_siblings: Max siblings to fetch on each side (default 1)

        Returns:
            Same list with expanded snippets for SFS results
        """
        if not results:
            return results

        # Collect sibling IDs to fetch
        sibling_ids_to_fetch: set[str] = set()
        sfs_result_indices: list[int] = []

        for idx, r in enumerate(results):
            if r.doc_type != "sfs":
                continue
            sfs_result_indices.append(idx)

        if not sfs_result_indices:
            return results

        # We need the collection to fetch sibling chunks by ID
        # Find the SFS collection
        sfs_collection_name = "sfs_lagtext_jina_v3_1024"
        resolved = _get_collection_with_fallback(self.client, sfs_collection_name, emit_log=False)
        if resolved is None:
            logger.debug("SFS collection not found for context expansion")
            return results

        _, sfs_collection = resolved

        # For each SFS result, we need its metadata to get sibling IDs
        # Since SearchResult doesn't carry full metadata, fetch by ID
        sfs_ids = [results[idx].id for idx in sfs_result_indices]

        try:
            loop = asyncio.get_event_loop()
            fetched = await loop.run_in_executor(
                None,
                lambda: sfs_collection.get(
                    ids=sfs_ids,
                    include=["metadatas", "documents"],
                ),
            )
        except Exception as e:
            logger.warning(f"SFS context expansion fetch failed: {e}")
            return results

        if not fetched or not fetched.get("ids"):
            return results

        # Build ID→metadata map
        id_to_meta = {}
        id_to_doc = {}
        for i, doc_id in enumerate(fetched["ids"]):
            if fetched.get("metadatas") and i < len(fetched["metadatas"]):
                id_to_meta[doc_id] = fetched["metadatas"][i]
            if fetched.get("documents") and i < len(fetched["documents"]):
                id_to_doc[doc_id] = fetched["documents"][i]

        # Collect sibling IDs
        for doc_id in sfs_ids:
            meta = id_to_meta.get(doc_id, {})
            for key in ("prev_paragraf_id", "next_paragraf_id"):
                sibling_id = meta.get(key, "")
                if sibling_id:
                    sibling_ids_to_fetch.add(sibling_id)

        if not sibling_ids_to_fetch:
            return results

        # Fetch sibling chunks
        try:
            sibling_ids_list = list(sibling_ids_to_fetch)
            sibling_fetched = await loop.run_in_executor(
                None,
                lambda: sfs_collection.get(
                    ids=sibling_ids_list,
                    include=["metadatas", "documents"],
                ),
            )
        except Exception as e:
            logger.warning(f"SFS sibling fetch failed: {e}")
            return results

        sibling_docs = {}
        if sibling_fetched and sibling_fetched.get("ids"):
            for i, sid in enumerate(sibling_fetched["ids"]):
                if sibling_fetched.get("documents") and i < len(sibling_fetched["documents"]):
                    sibling_docs[sid] = sibling_fetched["documents"][i]

        # Expand snippets
        expanded_count = 0
        for idx in sfs_result_indices:
            r = results[idx]
            meta = id_to_meta.get(r.id, {})

            context_parts = []

            # Prepend chapter rubrik if available
            kap_rubrik = meta.get("kapitel_rubrik", "")
            kapitel = meta.get("kapitel", "")
            if kap_rubrik and kapitel:
                context_parts.append(f"[{kapitel} {kap_rubrik}]")

            # Prepend prev sibling
            prev_id = meta.get("prev_paragraf_id", "")
            if prev_id and prev_id in sibling_docs:
                prev_text = sibling_docs[prev_id]
                # Truncate sibling to ~400 chars
                if len(prev_text) > 400:
                    prev_text = prev_text[:400] + "..."
                context_parts.append(f"[Föregående §] {prev_text}")

            # Original snippet
            context_parts.append(r.snippet)

            # Append next sibling
            next_id = meta.get("next_paragraf_id", "")
            if next_id and next_id in sibling_docs:
                next_text = sibling_docs[next_id]
                if len(next_text) > 400:
                    next_text = next_text[:400] + "..."
                context_parts.append(f"[Efterföljande §] {next_text}")

            expanded_snippet = "\n\n".join(context_parts)
            if expanded_snippet != r.snippet:
                r.snippet = expanded_snippet
                expanded_count += 1

        if expanded_count:
            logger.info(f"SFS context expansion: expanded {expanded_count} results with siblings")

        return results

    # Pre-compiled regex for parsing ChromaDB SFS chunk IDs into parent IDs.
    # Matches: sfs_{year}_{number}_{chapter}kap_{paragraf}§_{hash}
    _SFS_CHUNK_WITH_KAP_RE = re.compile(r"^sfs_(\d{4})_(\d+)_(.+?)_\d+[a-z]*§_")
    # Matches: sfs_{year}_{number}_{paragraf}§_{hash}  (no kapitel)
    _SFS_CHUNK_NO_KAP_RE = re.compile(r"^sfs_(\d{4})_(\d+)_\d+[a-z]*§_")

    @staticmethod
    def _chunk_id_to_parent_id(chunk_id: str) -> str | None:
        """
        Parse a ChromaDB SFS chunk ID into a parent store parent_id.

        ChromaDB format:  sfs_1974_152_2kap_3§_5f0cb3fa
        Parent store:     1974:152_2_kap

        ChromaDB format:  sfs_1915_218_1§_a3b2c1d4
        Parent store:     1915:218_root
        """
        # Try with-kapitel pattern first
        m = RetrievalOrchestrator._SFS_CHUNK_WITH_KAP_RE.match(chunk_id)
        if m:
            year, number, kap_part = m.group(1), m.group(2), m.group(3)
            # kap_part is e.g. "2kap" or "2akap" — normalize to "2_kap" or "2a_kap"
            kap_normalized = kap_part.replace("kap", "_kap")
            return f"{year}:{number}_{kap_normalized}"

        # Try no-kapitel pattern
        m = RetrievalOrchestrator._SFS_CHUNK_NO_KAP_RE.match(chunk_id)
        if m:
            year, number = m.group(1), m.group(2)
            return f"{year}:{number}_root"

        return None

    async def _expand_parent_context(
        self,
        results: List[SearchResult],
        metrics: Optional[RetrievalMetrics] = None,
    ) -> List[SearchResult]:
        """
        Expand SFS results with kapitel-level parent context from SQLite store.

        Complements _expand_sfs_context() (sibling-based). The parent store
        provides full kapitel text, while _expand_sfs_context adds ±1 adjacent §§.

        Parent context entries are appended with is_parent_context=True and
        go to the LLM prompt but do NOT count as primary search results for citations.

        Constructs parent_ids directly from ChromaDB chunk IDs to bypass the
        child_parent_map table (which uses scraper-format IDs, not ChromaDB IDs).

        Args:
            results: List of SearchResult objects
            metrics: Optional RetrievalMetrics to record parent store stats

        Returns:
            Original results + parent context entries appended
        """
        start = time.perf_counter()

        if not results:
            return results

        try:
            from .parent_store_service import get_parent_store_service

            parent_service = get_parent_store_service()
        except Exception:
            if metrics:
                metrics.parent_store_failed = True
                metrics.parent_store_ms = (time.perf_counter() - start) * 1000
            return results

        available = parent_service.is_available()
        if metrics:
            metrics.parent_store_available = available

        if not available:
            if metrics:
                metrics.parent_store_ms = (time.perf_counter() - start) * 1000
            return results

        # Collect SFS chunk IDs from results and parse into parent IDs
        parent_id_set: set[str] = set()
        for r in results:
            if r.doc_type != "sfs":
                continue
            parent_id = self._chunk_id_to_parent_id(r.id)
            if parent_id:
                parent_id_set.add(parent_id)

        if not parent_id_set:
            if metrics:
                metrics.parent_store_ms = (time.perf_counter() - start) * 1000
            return results

        parent_ids = list(parent_id_set)
        if metrics:
            metrics.parent_store_parents_requested = len(parent_ids)

        try:
            loop = asyncio.get_event_loop()
            parents = await loop.run_in_executor(
                None, lambda: parent_service.get_parents_by_ids(parent_ids)
            )
        except Exception as e:
            logger.warning(f"Parent context expansion failed: {e}")
            if metrics:
                metrics.parent_store_failed = True
                metrics.parent_store_ms = (time.perf_counter() - start) * 1000
            return results

        if not parents:
            if metrics:
                metrics.parent_store_ms = (time.perf_counter() - start) * 1000
            return results

        # Deduplicate: skip parents that overlap with existing result IDs
        existing_ids = {r.id for r in results}
        added = 0

        for parent in parents:
            parent_id = parent["parent_id"]
            if parent_id in existing_ids:
                continue

            # Truncate parent full_text to reasonable size for LLM context
            full_text = parent.get("full_text", "")
            if len(full_text) > 3000:
                full_text = full_text[:3000] + "..."

            kapitel = parent.get("kapitel", "")
            kapitel_rubrik = parent.get("kapitel_rubrik", "")
            header = f"[Kapitelkontext: {kapitel} {kapitel_rubrik}]".strip()
            snippet = f"{header}\n{full_text}"

            results.append(
                SearchResult(
                    id=parent_id,
                    title=f"{parent.get('kortnamn', '')} {kapitel}".strip(),
                    snippet=snippet,
                    score=0.0,  # Not a ranked result
                    source=f"sfs_parent_{parent.get('sfs_nummer', '')}",
                    doc_type="sfs_parent",
                    retriever="parent_store",
                )
            )
            added += 1

        if metrics:
            metrics.parent_store_parents_added = added
            metrics.parent_store_ms = (time.perf_counter() - start) * 1000

        if added:
            latency_str = f" ({metrics.parent_store_ms:.1f}ms)" if metrics else ""
            logger.info(
                f"Parent context expansion: added {added} kapitel parents "
                f"for {len(parent_ids)} parent IDs{latency_str}"
            )

        return results

    # ═══════════════════════════════════════════════════════════════════════════
    # EPR: TWO-PASS RETRIEVAL WITH INTENT ROUTING (Phase 5)
    # ═══════════════════════════════════════════════════════════════════════════

    async def search_with_routing(
        self,
        query: str,
        k: int = 10,
        where_filter: Optional[Dict] = None,
        history: Optional[List[str]] = None,
    ) -> RetrievalResult:
        """
        Execute two-pass retrieval with Evidence Policy Routing (EPR).

        This method implements EPR by:
        1. Classifying query intent using IntentClassifier
        2. Getting routing config via get_routing_for_intent()
        3. Pass 1: Search primary + support collections
        4. Pass 2: If secondary_budget > 0, search secondary collections
        5. Merge results using SourceHierarchy.sort_by_priority()
        6. Return RetrievalResult with intent and routing metadata

        Args:
            query: User query string
            k: Number of results to return
            where_filter: Optional ChromaDB where filter
            history: Conversation history for intent classification context

        Returns:
            RetrievalResult with results sorted by tier, intent, and routing metadata
        """
        start_total = time.perf_counter()
        metrics = RetrievalMetrics(strategy="epr_two_pass")

        # Initialize EPR components
        intent_classifier = IntentClassifier()
        source_hierarchy = SourceHierarchy()

        # Step 1: Classify query intent (rule-based)
        intent_result = intent_classifier.classify(query)
        detected_intent = intent_result.intent
        logger.info(
            f"EPR: Classified intent={detected_intent.value} "
            f"(confidence={intent_result.confidence:.2f}, patterns={intent_result.matched_patterns})"
        )

        # Step 1b: LLM intent fallback for low-confidence / ambiguous queries
        if (
            self._intent_llm_fallback_enabled
            and self._llm_service
            and intent_result.confidence < self._intent_llm_fallback_confidence_threshold
        ):
            try:
                llm_intent = await asyncio.wait_for(
                    llm_classify_intent(
                        query, self._llm_service, self._intent_llm_fallback_timeout
                    ),
                    timeout=self._intent_llm_fallback_timeout + 1.0,
                )
                if llm_intent is not None:
                    logger.info(
                        f"EPR: LLM fallback upgraded intent "
                        f"{intent_result.intent.value}→{llm_intent.intent.value} "
                        f"(conf {intent_result.confidence:.2f}→{llm_intent.confidence:.2f})"
                    )
                    intent_result = llm_intent
                    detected_intent = llm_intent.intent
                else:
                    logger.debug("EPR: LLM fallback returned None, keeping rule-based result")
            except (asyncio.TimeoutError, Exception) as e:
                logger.warning(
                    f"EPR: LLM intent fallback failed ({type(e).__name__}), keeping rule-based result"
                )

        # Step 2: Get routing configuration
        routing_config = get_routing_for_intent(detected_intent)

        routing_metadata = {
            "primary": routing_config.primary,
            "support": routing_config.support,
            "secondary": routing_config.secondary,
            "secondary_budget": routing_config.secondary_budget,
            "require_separation": routing_config.require_separation,
        }

        logger.info(
            f"EPR: Routing primary={routing_config.primary}, "
            f"secondary={routing_config.secondary}, budget={routing_config.secondary_budget}"
        )

        requested_collections = routing_config.primary + routing_config.support
        if routing_config.secondary_budget > 0 and routing_config.secondary:
            requested_collections += routing_config.secondary
        self._enforce_cutover_policy(requested_collections, metrics)

        # Generate query embedding(s) - multi-query if RAG-Fusion enabled
        use_fusion = getattr(self, "_use_epr_fusion", True)
        rewrite_result = None

        if use_fusion and self.rewriter:
            # RAG-Fusion: expand to multiple query variants for better recall
            rewrite_result = self.rewriter.rewrite(query, history)
            search_query = rewrite_result.expanded_query

            num_queries = getattr(self, "_epr_fusion_num_queries", 3)
            expanded = self.expander.expand(search_query, rewrite_result, num_queries=num_queries)
            query_embeddings = self.embed_fn(expanded.queries)

            metrics.fusion_used = True
            metrics.num_queries = len(expanded.queries)
            metrics.query_variants = expanded.queries
            metrics.expansion_latency_ms = expanded.expansion_latency_ms
            logger.info(
                f"EPR RAG-Fusion: expanded to {len(expanded.queries)} queries: "
                f"{[q[:40] for q in expanded.queries]}"
            )
        else:
            # Single query fallback
            query_embeddings = [self.embed_fn([query])[0]]

        # Gate LLM expansion: skip for initial pass when confidence gate is on
        if self._query_expansion_confidence_gate:
            llm_expansions = []
        else:
            llm_expansions = await self._get_llm_expansions(query, metrics)

        # BM25 search (runs in parallel with Pass 1 dense search)
        async def _epr_bm25_search():
            if not (self._bm25_service and self._bm25_service.is_available()):
                return None
            try:
                bm25_start = time.perf_counter()
                bm25_query = self._build_bm25_query(query, rewrite_result, llm_expansions)
                loop = asyncio.get_event_loop()
                results = await loop.run_in_executor(
                    None,
                    lambda: self._bm25_service.search(
                        bm25_query,
                        k=k * 2,
                        return_docs=True,
                    ),
                )
                metrics.bm25_latency_ms = (time.perf_counter() - bm25_start) * 1000
                logger.info(
                    f"EPR BM25: '{bm25_query[:30]}...' → {len(results)} results "
                    f"in {metrics.bm25_latency_ms:.1f}ms"
                )
                return results
            except PublicSourceGuardError:
                raise
            except Exception as e:
                logger.warning(f"EPR BM25 failed (continuing dense only): {e}")
                return None

        # Step 3: Pass 1 - Search primary + support collections (multi-query)
        # Run dense search and BM25 in parallel
        pass1_collections = routing_config.primary + routing_config.support

        async def _pass1_dense_search():
            result_sets = []
            last_metrics = None
            if pass1_collections:
                for emb in query_embeddings:
                    raw_results, last_metrics = await parallel_collection_search(
                        client=self.client,
                        query_embedding=emb,
                        collection_names=pass1_collections,
                        n_results_per_collection=k,
                        where_filter=where_filter,
                        timeout_seconds=self.default_timeout,
                    )
                    result_sets.append(raw_results)
            return result_sets, last_metrics

        pass1_dense_result, bm25_results = await asyncio.gather(
            _pass1_dense_search(),
            _epr_bm25_search(),
        )
        # Unpack pass1 tuple
        pass1_result_sets, pass1_metrics = pass1_dense_result

        if pass1_metrics:
            metrics.dense_latency_ms = pass1_metrics.dense_latency_ms
        total_pass1 = sum(len(rs) for rs in pass1_result_sets)
        metrics.dense_result_count = total_pass1
        metrics.bm25_result_count = len(bm25_results) if bm25_results else 0
        if pass1_collections:
            logger.info(
                f"EPR Pass 1: {total_pass1} results from {pass1_collections} "
                f"({len(query_embeddings)} queries)"
            )

        # Step 4: Pass 2 - Search secondary collections (if budget > 0)
        pass2_result_sets = []

        if routing_config.secondary_budget > 0 and routing_config.secondary:
            for emb in query_embeddings[:1]:  # Only first query for secondary (budget)
                secondary_raw, pass2_metrics = await parallel_collection_search(
                    client=self.client,
                    query_embedding=emb,
                    collection_names=routing_config.secondary,
                    n_results_per_collection=routing_config.secondary_budget,
                    where_filter=where_filter,
                    timeout_seconds=self.default_timeout,
                )
                pass2_result_sets.append(secondary_raw[: routing_config.secondary_budget])
            logger.info(
                f"EPR Pass 2: {sum(len(rs) for rs in pass2_result_sets)} results "
                f"from {routing_config.secondary} (budget={routing_config.secondary_budget})"
            )

        # Step 5: Merge results using RRF (multi-query fusion + BM25)
        all_result_sets = pass1_result_sets + pass2_result_sets

        if len(all_result_sets) > 1 or bm25_results:
            # Use hybrid RRF to merge multi-query + BM25 results
            merged_results = hybrid_reciprocal_rank_fusion(
                dense_result_sets=all_result_sets,
                bm25_results=bm25_results,
                k=self._rrf_k,
                bm25_weight=self._bm25_weight,
                public_guard_enabled=self._public_guard_enabled,
            )
            # Use rrf_score as the primary score
            all_results = []
            for r in merged_results:
                r["score"] = r.get("rrf_score", r.get("score", 0.0))
                all_results.append(r)
            metrics.rrf_latency_ms = 0.0  # RRF is fast, included in total
            logger.info(
                f"EPR RRF merge: {len(all_results)} unique results from {len(all_result_sets)} sets"
            )
        else:
            # Single query - flatten
            all_results = []
            for rs in all_result_sets:
                all_results.extend(rs)

        # PRECISION TUNING: Filter out low-score results
        # When RRF fusion is used, filter on original_score (ChromaDB similarity, 0-1 range)
        # because rrf_score is on a different scale (~0.01-0.04 for k=45)
        min_score = self._score_threshold
        if len(all_result_sets) > 1:
            # RRF path: use original ChromaDB similarity score for filtering
            all_results = [
                r for r in all_results if r.get("original_score", r.get("score", 0.0)) >= min_score
            ]
        else:
            all_results = [r for r in all_results if r.get("score", 0.0) >= min_score]
        logger.info(f"EPR: After min_score filter: {len(all_results)} results")
        self._guard_public_records(all_results, stage="epr_retrieval_results")

        # Convert to SearchResult with tier annotation
        search_results = []
        for r in all_results:
            source = r.get("source", r.get("collection", "unknown"))
            tier = source_hierarchy.get_tier(source)
            tier_label = {SourceTier.A: "A", SourceTier.B: "B", SourceTier.C: "C"}.get(tier, "C")

            search_results.append(
                SearchResult(
                    id=r["id"],
                    title=r.get("title", "Untitled"),
                    snippet=r.get("snippet", ""),
                    score=r.get("score", 0.0),
                    source=source,
                    source_scope=r.get("source_scope"),
                    doc_type=r.get("doc_type"),
                    date=r.get("date"),
                    retriever="epr",
                    tier=tier_label,
                )
            )

        # Sort by tier priority (A before B before C), then by score within tier
        # INTENT-SPECIFIC BOOST: For PRACTICAL_PROCESS, boost procedural_guides to Tier A
        if detected_intent == QueryIntent.PRACTICAL_PROCESS:
            for r in search_results:
                if "procedural_guides" in r.source:
                    r.tier = "A"  # Boost to Tier A for this intent

        def sort_key(result: SearchResult):
            tier_order = {"A": 1, "B": 2, "C": 3}
            return (tier_order.get(result.tier, 99), -result.score)

        search_results.sort(key=sort_key)

        # Limit to k results
        search_results = search_results[:k]

        # PRECISION TUNING: Deduplicate by canonical doc_id (keep first = best tier)
        seen_doc_ids = set()
        unique_results = []
        for r in search_results:
            canonical = get_canonical_doc_id(r.id)
            if canonical not in seen_doc_ids:
                seen_doc_ids.add(canonical)
                unique_results.append(r)

        logger.info(
            f"EPR: After dedupe: {len(unique_results)} unique docs (from {len(search_results)} chunks)"
        )

        # SFS Context Expansion: enrich SFS results with sibling paragraf text
        unique_results = await self._expand_sfs_context(unique_results)

        # Parent-child retrieval: append kapitel-level context for SFS results
        unique_results = await self._expand_parent_context(unique_results, metrics=metrics)
        self._guard_public_records(unique_results, stage="epr_final_results")

        metrics.total_latency_ms = (time.perf_counter() - start_total) * 1000
        metrics.unique_docs_total = len(unique_results)

        logger.info(
            f"EPR complete: {len(unique_results)} results in {metrics.total_latency_ms:.1f}ms "
            f"(intent={detected_intent.value})"
        )
        self._log_observability(
            query=query,
            metrics=metrics,
            requested_collections=requested_collections,
        )

        return RetrievalResult(
            results=unique_results,
            metrics=metrics,
            success=True,
            intent=detected_intent.value,
            routing_used=routing_metadata,
        )

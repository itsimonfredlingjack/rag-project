"""
Retrieval Data Models — Data classes for the retrieval pipeline.

Extracted from retrieval_orchestrator.py (Sprint 2, P2-14).
Contains RetrievalMetrics, SearchResult, RetrievalResult, RetrievalStrategy.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


# ═══════════════════════════════════════════════════════════════════════════
# METRICS & INSTRUMENTATION
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class RetrievalMetrics:
    """Metrics for a single retrieval operation - designed for Phase 4 confidence."""

    total_latency_ms: float = 0.0
    dense_latency_ms: float = 0.0
    bm25_latency_ms: float = 0.0

    # Per-retriever results
    dense_result_count: int = 0
    bm25_result_count: int = 0

    # Score distribution (for Phase 4 confidence)
    top_score: float = 0.0
    mean_score: float = 0.0
    score_std: float = 0.0
    score_entropy: float = 0.0

    # Overlap metrics
    doc_overlap_count: int = 0  # Docs found by both retrievers
    unique_docs_total: int = 0

    # Timeout tracking
    dense_timeout: bool = False
    bm25_timeout: bool = False

    # Strategy used
    strategy: str = "parallel_v1"

    # Phase 2: Query rewriting metrics
    rewrite_used: bool = False
    rewrite_latency_ms: float = 0.0
    original_query: str = ""
    rewritten_query: str = ""
    delta_topk_overlap: float = 0.0  # How different are rewritten results?

    # Phase 3: RAG-Fusion metrics
    fusion_used: bool = False
    num_queries: int = 1
    query_variants: List[str] = field(default_factory=list)
    per_query_result_counts: List[int] = field(default_factory=list)
    unique_docs_before_fusion: int = 0
    unique_docs_after_fusion: int = 0
    overlap_ratio: float = 0.0
    fusion_gain: float = 0.0
    rrf_latency_ms: float = 0.0
    expansion_latency_ms: float = 0.0
    llm_query_expansion_used: bool = False
    llm_query_expansion_latency_ms: float = 0.0
    llm_query_expansion_count: int = 0
    llm_query_expansion_grammar_used: bool = False
    llm_query_expansion_parsing_method: str = "none"
    llm_query_expansions: List[str] = field(default_factory=list)

    # Cutover guardrails (fail-closed once enforced)
    cutover_enforced: bool = False
    cutover_violation: bool = False
    cutover_violation_collections: List[str] = field(default_factory=list)

    # Phase 4: Adaptive retrieval metrics
    adaptive_used: bool = False
    confidence_signals: Optional[Dict] = None
    escalation_path: List[str] = field(default_factory=list)
    final_step: str = ""
    fallback_triggered: bool = False
    reason_codes: List[str] = field(default_factory=list)  # Decision trace for debugging

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dict for logging/API response."""
        return {
            "latency": {
                "total_ms": round(self.total_latency_ms, 2),
                "dense_ms": round(self.dense_latency_ms, 2),
                "bm25_ms": round(self.bm25_latency_ms, 2),
            },
            "results": {
                "dense_count": self.dense_result_count,
                "bm25_count": self.bm25_result_count,
                "overlap": self.doc_overlap_count,
                "unique_total": self.unique_docs_total,
            },
            "scores": {
                "top": round(self.top_score, 4),
                "mean": round(self.mean_score, 4),
                "std": round(self.score_std, 4),
                "entropy": round(self.score_entropy, 4),
            },
            "timeouts": {
                "dense": self.dense_timeout,
                "bm25": self.bm25_timeout,
            },
            "strategy": self.strategy,
            "rewrite": {
                "used": self.rewrite_used,
                "latency_ms": round(self.rewrite_latency_ms, 2),
                "original_query": self.original_query,
                "rewritten_query": self.rewritten_query,
                "delta_topk_overlap": round(self.delta_topk_overlap, 4),
            },
            "fusion": {
                "used": self.fusion_used,
                "num_queries": self.num_queries,
                "query_variants": self.query_variants,
                "per_query_result_counts": self.per_query_result_counts,
                "unique_docs_before": self.unique_docs_before_fusion,
                "unique_docs_after": self.unique_docs_after_fusion,
                "overlap_ratio": round(self.overlap_ratio, 4),
                "fusion_gain": round(self.fusion_gain, 4),
                "rrf_latency_ms": round(self.rrf_latency_ms, 2),
                "expansion_latency_ms": round(self.expansion_latency_ms, 2),
            },
            "query_expansion": {
                "used": self.llm_query_expansion_used,
                "latency_ms": round(self.llm_query_expansion_latency_ms, 2),
                "count": self.llm_query_expansion_count,
                "grammar_used": self.llm_query_expansion_grammar_used,
                "parsing_method": self.llm_query_expansion_parsing_method,
                "queries": self.llm_query_expansions,
            },
            "cutover": {
                "enforced": self.cutover_enforced,
                "violation": self.cutover_violation,
                "violation_collections": self.cutover_violation_collections,
            },
            "adaptive": {
                "used": self.adaptive_used,
                "signals": self.confidence_signals,
                "escalation_path": self.escalation_path,
                "final_step": self.final_step,
                "fallback_triggered": self.fallback_triggered,
                "reason_codes": self.reason_codes,
            },
        }


@dataclass
class SearchResult:
    """Individual search result with score and metadata."""

    id: str
    title: str
    snippet: str
    score: float
    source: str
    doc_type: Optional[str] = None
    date: Optional[str] = None
    retriever: str = "unknown"  # 'dense', 'bm25', or 'both'
    tier: Optional[str] = None  # EPR: Source tier (A/B/C)


@dataclass
class RetrievalResult:
    """Complete result from retrieval orchestrator."""

    results: List[SearchResult]
    metrics: RetrievalMetrics
    success: bool = True
    error: Optional[str] = None
    intent: Optional[str] = None  # EPR: Classified query intent
    routing_used: Optional[Dict] = None  # EPR: Routing config used


# ═══════════════════════════════════════════════════════════════════════════
# RETRIEVAL STRATEGIES
# ═══════════════════════════════════════════════════════════════════════════


class RetrievalStrategy(Enum):
    """Available retrieval strategies."""

    LEGACY = "legacy"  # Original sequential search
    PARALLEL_V1 = "parallel_v1"  # Phase 1: Parallel dense + collections
    REWRITE_V1 = "rewrite_v1"  # Phase 2: Query rewriting + parallel search
    RAG_FUSION = "rag_fusion"  # Phase 3
    ADAPTIVE = "adaptive"  # Phase 4

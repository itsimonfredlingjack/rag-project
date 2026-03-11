"""
Reranking Service - Jina Reranker v2 Cross-Encoder Wrapper
Wrapper for Jina reranker-v2-base-multilingual cross-encoder model.

GPU-accelerated (fp16) when CUDA available — fits alongside Ollama LLM in VRAM.
Reranker ~0.3GB fp16 + Qwen 3.5 9B ~6.6GB = ~6.9GB / 12GB RTX 4070.
"""

import asyncio
import gc
import os
from dataclasses import dataclass
from functools import lru_cache
from typing import List, Optional, Tuple

import torch

from ..core.exceptions import RerankingError
from ..utils.logging import get_logger
from .base_service import BaseService
from .config_service import ConfigService, get_config_service

logger = get_logger(__name__)


def _resolve_device(requested: str) -> str:
    """Resolve device string, falling back to CPU if CUDA unavailable."""
    if requested == "auto":
        return "cuda" if torch.cuda.is_available() else "cpu"
    if requested.startswith("cuda") and not torch.cuda.is_available():
        logger.warning("CUDA requested but unavailable — falling back to CPU")
        return "cpu"
    return requested


@dataclass
class RerankingConfig:
    """
    Configuration for Jina Reranker v2 service.
    """

    model: str = "jinaai/jina-reranker-v2-base-multilingual"
    max_length: int = 1024  # Jina supports 1024 tokens (upgraded from 512)
    batch_size: int = 8  # Smaller batches for GPU memory efficiency
    device: str = "auto"  # auto = CUDA if available, else CPU


@dataclass
class RerankingResult:
    """
    Result of reranking operation.

    Attributes:
        original_docs: Original documents before reranking
        reranked_docs: Documents after reranking (sorted by new scores)
        original_scores: Original relevance scores (from embedding similarity)
        reranked_scores: New relevance scores (from cross-encoder)
        latency_ms: Time taken for reranking
    """

    original_docs: List[dict]
    reranked_docs: List[dict]
    original_scores: List[float]
    reranked_scores: List[float]
    latency_ms: float


class RerankingService(BaseService):
    """
    Reranking Service - Jina Reranker v2 cross-encoder wrapper.

    Features:
    - Cross-encoder reranking (query, doc) pairs
    - GPU-accelerated with fp16 (falls back to CPU)
    - Scores are pre-normalized (0-1 range, no sigmoid needed)

    Model Info:
    - jinaai/jina-reranker-v2-base-multilingual (XLM-RoBERTa, 278M params)
    - GPU fp16: ~0.3GB VRAM, ~1-3s for 14 docs
    - CPU fp32: ~0.6GB RAM, ~90-100s for 14 docs
    - Max length: 1024 tokens
    - License: CC-BY-NC-4.0
    """

    # Global model cache (lazy-loaded)
    _reranker_model = None
    _model_config: Optional[RerankingConfig] = None

    def __init__(self, config: ConfigService):
        super().__init__(config)
        self._model = None
        self._is_loaded = False
        self._device = "cpu"
        self.logger.info(f"Reranking Service initialized (model: {config.reranking_model})")

    def _load_model(self) -> None:
        """
        Load Jina reranker model (lazy loading).

        Loads on GPU (fp16) if available, otherwise CPU (fp32).
        Env var CONST_RERANKING_DEVICE overrides: "cpu", "cuda", "auto" (default).
        """
        if self._is_loaded:
            return

        try:
            from sentence_transformers import CrossEncoder

            # Resolve device: env var > config > auto-detect
            requested = os.environ.get(
                "CONST_RERANKING_DEVICE",
                self._model_config.device if self._model_config else "auto",
            )
            self._device = _resolve_device(requested)
            use_fp16 = self._device.startswith("cuda")

            self.logger.info(
                f"Loading Jina reranker: {self.config.reranking_model} "
                f"on {self._device} ({'fp16' if use_fp16 else 'fp32'})"
            )

            self._model = CrossEncoder(
                self.config.reranking_model,
                max_length=1024,
                device=self._device,
                trust_remote_code=True,
                model_kwargs={"dtype": torch.float16 if use_fp16 else "auto"},
            )
            self._is_loaded = True

            mem_info = ""
            if use_fp16 and torch.cuda.is_available():
                allocated = torch.cuda.memory_allocated() / 1024**2
                mem_info = f", VRAM: {allocated:.0f}MB"
            self.logger.info(f"Reranker loaded on {self._device}{mem_info}")

        except Exception as e:
            self.logger.error(f"Failed to load reranker on {self._device}: {e}")
            # If GPU failed, retry on CPU
            if self._device != "cpu":
                self.logger.warning("Retrying reranker load on CPU...")
                self._device = "cpu"
                try:
                    from sentence_transformers import CrossEncoder

                    self._model = CrossEncoder(
                        self.config.reranking_model,
                        max_length=1024,
                        device="cpu",
                        trust_remote_code=True,
                        model_kwargs={"dtype": "auto"},
                    )
                    self._is_loaded = True
                    self.logger.info("Reranker loaded on CPU (fallback)")
                    return
                except Exception as e2:
                    self.logger.error(f"CPU fallback also failed: {e2}")
            raise RerankingError(f"Failed to load reranker: {str(e)}")

    async def initialize(self) -> None:
        """
        Initialize reranking service.

        Loads model config from ConfigService.
        Model is lazy-loaded on first reranking operation.
        """
        self._model_config = RerankingConfig(
            model=self.config.reranking_model,
            max_length=1024,
            batch_size=8,
            device=os.environ.get("CONST_RERANKING_DEVICE", "auto"),
        )

        self._mark_initialized()

    async def health_check(self) -> bool:
        """
        Check if reranking service is healthy.

        Returns:
            True if service is initialized, False otherwise
        """
        return self._is_loaded  # Only loaded if we've attempted

    async def close(self) -> None:
        """
        Unload reranker model to free memory (including GPU VRAM).

        Clears the singleton, so next rerank() will reload model.
        """
        if self._model is not None:
            self.logger.info(f"Unloading Jina reranker model from {self._device}")
            del self._model
            self._model = None
            self._is_loaded = False
            gc.collect()
            if self._device.startswith("cuda") and torch.cuda.is_available():
                torch.cuda.empty_cache()

        self._mark_uninitialized()

    async def ensure_initialized(self) -> None:
        """
        Ensure service is initialized.

        Raises:
            ServiceNotInitializedError: If service is not initialized
        """
        await super().ensure_initialized()

        # Lazy-load model if not already loaded
        if not self._is_loaded:
            self._load_model()

    def _predict_pairs(self, pairs: list) -> list:
        """
        Score (query, doc) pairs with torch.no_grad() and gc cleanup.

        Uses autocast for fp16 on GPU for faster inference.
        """
        device_type = "cuda" if self._device.startswith("cuda") else "cpu"
        with torch.no_grad():
            if device_type == "cuda":
                with torch.amp.autocast(device_type="cuda"):
                    scores = self._model.predict(pairs)
            else:
                scores = self._model.predict(pairs)
        gc.collect()
        return scores

    async def rerank(
        self,
        query: str,
        documents: List[dict],
        top_k: Optional[int] = None,
    ) -> RerankingResult:
        """
        Rerank documents for a query using Jina cross-encoder.

        Scores each (query, document) pair and sorts by score.

        Args:
            query: The search query
            documents: List of document dictionaries with 'id', 'title', 'snippet', 'score'
            top_k: Number of results to return (default: all)

        Returns:
            RerankingResult with reranked documents and scores

        Raises:
            RerankingError: If reranking fails
            ServiceNotInitializedError: If service is not initialized
        """
        await self.ensure_initialized()

        if not documents:
            self.logger.warning("No documents to rerank")
            return RerankingResult(
                original_docs=documents,
                reranked_docs=documents,
                original_scores=[],
                reranked_scores=[],
                latency_ms=0.0,
            )

        import time

        start_time = time.perf_counter()

        try:
            # Extract document IDs and texts
            doc_texts = [f"{doc.get('title', '')}\n{doc.get('snippet', '')}" for doc in documents]
            original_scores = [doc.get("score", 0.0) for doc in documents]

            # Create (query, doc) pairs for cross-encoder
            pairs = list(zip([query] * len(documents), doc_texts))

            self.logger.info(f"Reranking {len(documents)} documents for query: '{query[:50]}...'")

            # Run inference in executor (blocking call) with memory cleanup
            loop = asyncio.get_event_loop()
            scores = await loop.run_in_executor(
                None,
                self._predict_pairs,
                pairs,
            )

            # Jina returns pre-normalized scores (0-1 range), no sigmoid needed
            normalized_scores = list(scores)

            latency_ms = (time.perf_counter() - start_time) * 1000

            # Sort by new scores (highest first)
            scored_docs = list(zip(documents, normalized_scores))
            scored_docs.sort(key=lambda x: -x[1])  # Sort by score descending

            # Extract reranked results
            reranked_docs = [doc for doc, _ in scored_docs]
            reranked_scores = [score for _, score in scored_docs]

            # Apply top_k limit
            if top_k and top_k < len(reranked_docs):
                reranked_docs = reranked_docs[:top_k]
                reranked_scores = reranked_scores[:top_k]

            top_score = reranked_scores[0] if reranked_scores else 0.0
            self.logger.info(
                f"Reranking complete: {len(reranked_docs)} docs in {latency_ms:.1f}ms (top: {top_score:.4f})"
            )

            return RerankingResult(
                original_docs=documents,
                reranked_docs=reranked_docs,
                original_scores=original_scores,
                reranked_scores=reranked_scores,
                latency_ms=latency_ms,
            )

        except Exception as e:
            self.logger.error(f"Reranking failed: {e}")
            raise RerankingError(f"Reranking failed: {str(e)}")

    async def rerank_batch(
        self,
        queries: List[Tuple[str, List[dict]]],
        top_k: Optional[int] = None,
    ) -> List[RerankingResult]:
        """
        Batch rerank multiple (query, documents) pairs.

        Useful for multi-query retrieval (RAG-Fusion).
        Processes all queries in parallel for efficiency.

        Args:
            queries: List of (query, documents) tuples
            top_k: Number of results to return per query (default: all)

        Returns:
            List of RerankingResult (one per query)
        """
        await self.ensure_initialized()

        if not queries:
            return []

        results = []

        # Process all queries in parallel
        tasks = [self.rerank(query, docs, top_k) for query, docs in queries]

        # Run all reranking operations in parallel
        rerank_results = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter out exceptions and collect results
        for i, result in enumerate(rerank_results):
            if isinstance(result, Exception):
                self.logger.error(f"Reranking failed for query {i}: {result}")
                continue
            results.append(result)

        return results

    def get_model_info(self) -> dict:
        """
        Get information about the loaded model.

        Returns:
            Dictionary with model name, status, and configuration
        """
        info = {
            "model": self._model_config.model,
            "loaded": self._is_loaded,
            "max_length": self._model_config.max_length,
            "device": self._device if self._is_loaded else self._model_config.device,
        }
        if self._is_loaded and self._device.startswith("cuda") and torch.cuda.is_available():
            info["vram_mb"] = round(torch.cuda.memory_allocated() / 1024**2)
        return info


# Dependency injection function for FastAPI


@lru_cache()
def get_reranking_service(config: Optional[ConfigService] = None) -> RerankingService:
    """
    Get singleton RerankingService instance.

    Args:
        config: Optional ConfigService (uses default if not provided)

    Returns:
        Cached RerankingService instance
    """
    if config is None:
        config = get_config_service()

    return RerankingService(config)

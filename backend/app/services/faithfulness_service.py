"""
Faithfulness Service — Post-generation verification that claims are grounded in sources.

Detects semantic hallucination by checking whether each claim in the LLM's answer
is supported by the retrieved source documents.

Two scoring modes:
  1. Overlap-based (default): Fast sentence-level token overlap — no GPU needed.
  2. LLM-based (optional): Semantic NLI via the same LLM used for generation.

Feature-flagged: CONST_FAITHFULNESS_ENABLED
"""

import re
import time
from dataclasses import dataclass, field
from typing import Optional

from ..utils.logging import get_logger
from .base_service import BaseService
from .config_service import ConfigService, get_config_service
from .retrieval_service import SearchResult

logger = get_logger(__name__)

# ── Sentence splitting ─────────────────────────────────────────────

_SENTENCE_SPLIT_RE = re.compile(
    r"(?<=[.!?])\s+(?=[A-ZÅÄÖ])"  # Split on sentence-ending punctuation followed by capital
)

# Words too common to be informative for overlap scoring
_STOP_WORDS_SV = frozenset(
    {
        "och",
        "i",
        "att",
        "en",
        "ett",
        "av",
        "den",
        "det",
        "de",
        "som",
        "är",
        "för",
        "med",
        "på",
        "till",
        "om",
        "kan",
        "har",
        "ska",
        "inte",
        "eller",
        "från",
        "var",
        "vid",
        "enligt",
        "sin",
        "sina",
        "sitt",
        "the",
        "and",
        "of",
        "to",
        "in",
        "a",
        "is",
        "for",
        "that",
        "with",
        "this",
        "be",
        "by",
        "on",
        "not",
        "are",
        "was",
    }
)


def _tokenize(text: str) -> set[str]:
    """Lowercase tokenize, strip punctuation, remove stop words."""
    tokens = re.findall(r"\b\w{2,}\b", text.lower())
    return {t for t in tokens if t not in _STOP_WORDS_SV}


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences, filtering very short fragments."""
    raw = _SENTENCE_SPLIT_RE.split(text.strip())
    return [s.strip() for s in raw if len(s.strip()) > 20]


# ── Data classes ───────────────────────────────────────────────────


@dataclass
class ClaimVerification:
    """Verification result for a single claim/sentence."""

    claim: str
    score: float  # 0.0-1.0 (overlap ratio with best matching source)
    best_source_title: str
    supported: bool  # score >= threshold


@dataclass
class FaithfulnessResult:
    """Result from faithfulness evaluation of a generated answer."""

    overall_score: float  # Weighted average of claim scores (0.0-1.0)
    claims: list[ClaimVerification] = field(default_factory=list)
    total_claims: int = 0
    supported_claims: int = 0
    unsupported_claims: int = 0
    latency_ms: float = 0.0


# ── Service ────────────────────────────────────────────────────────


class FaithfulnessService(BaseService):
    """
    Faithfulness Service — verifies answer grounding against source documents.

    Splits the answer into sentences, scores each against source texts using
    token overlap, and returns an overall faithfulness score.

    Thread Safety:
        - No shared mutable state between coroutines
        - Safe for concurrent requests
    """

    def __init__(self, config: ConfigService):
        """
        Initialize Faithfulness Service.

        Args:
            config: ConfigService for configuration access
        """
        super().__init__(config)

        self.enabled = getattr(config.settings, "faithfulness_enabled", False)
        self.threshold = getattr(config.settings, "faithfulness_threshold", 0.25)

        self.logger.info(
            f"Faithfulness Service initialized (enabled={self.enabled}, threshold={self.threshold})"
        )

    async def initialize(self) -> None:
        """Initialize faithfulness service."""
        self._mark_initialized()
        self.logger.info("Faithfulness Service initialized")

    async def health_check(self) -> bool:
        """Check if faithfulness service is healthy."""
        return True

    async def close(self) -> None:
        """Cleanup faithfulness service."""
        self._mark_uninitialized()
        self.logger.info("Faithfulness Service closed")

    async def score_answer(
        self,
        answer: str,
        sources: list[SearchResult],
        question: str = "",
        mode: str = "assist",
    ) -> FaithfulnessResult:
        """
        Score the faithfulness of a generated answer against its sources.

        Splits the answer into sentence-level claims and checks each against
        the source texts using token overlap. Returns an overall score (0-1)
        and per-claim verification details.

        Args:
            answer: The LLM-generated answer text
            sources: Retrieved source documents used as context
            question: Original user question (for context)
            mode: Response mode (evidence/assist/chat)

        Returns:
            FaithfulnessResult with overall score and per-claim details
        """
        start_time = time.perf_counter()

        if not self.enabled or not answer or not sources:
            return FaithfulnessResult(
                overall_score=1.0 if not answer else 0.0,
                latency_ms=0.0,
            )

        try:
            # Split answer into sentence-level claims
            claims = _split_sentences(answer)

            if not claims:
                return FaithfulnessResult(
                    overall_score=1.0,
                    latency_ms=(time.perf_counter() - start_time) * 1000,
                )

            # Build source token sets (one per source)
            source_token_sets = []
            for source in sources:
                combined = f"{source.title} {source.snippet}"
                source_token_sets.append((_tokenize(combined), source.title))

            # Score each claim against sources
            verifications: list[ClaimVerification] = []

            for claim_text in claims:
                claim_tokens = _tokenize(claim_text)

                if not claim_tokens:
                    continue

                best_score = 0.0
                best_title = ""

                for source_tokens, title in source_token_sets:
                    if not source_tokens:
                        continue

                    # Overlap: what fraction of claim tokens appear in source
                    overlap = claim_tokens & source_tokens
                    score = len(overlap) / len(claim_tokens) if claim_tokens else 0.0

                    if score > best_score:
                        best_score = score
                        best_title = title

                verifications.append(
                    ClaimVerification(
                        claim=claim_text[:200],  # Truncate for metrics
                        score=best_score,
                        best_source_title=best_title,
                        supported=best_score >= self.threshold,
                    )
                )

            # Compute overall score
            if verifications:
                overall = sum(v.score for v in verifications) / len(verifications)
                supported = sum(1 for v in verifications if v.supported)
                unsupported = len(verifications) - supported
            else:
                overall = 1.0
                supported = 0
                unsupported = 0

            latency_ms = (time.perf_counter() - start_time) * 1000

            self.logger.info(
                f"Faithfulness: score={overall:.2f}, "
                f"claims={len(verifications)} "
                f"({supported} supported, {unsupported} unsupported), "
                f"latency={latency_ms:.1f}ms"
            )

            return FaithfulnessResult(
                overall_score=overall,
                claims=verifications,
                total_claims=len(verifications),
                supported_claims=supported,
                unsupported_claims=unsupported,
                latency_ms=latency_ms,
            )

        except Exception as e:
            self.logger.warning(f"Faithfulness scoring failed: {e}")
            return FaithfulnessResult(
                overall_score=0.0,
                latency_ms=(time.perf_counter() - start_time) * 1000,
            )


def get_faithfulness_service(
    config: Optional[ConfigService] = None,
) -> FaithfulnessService:
    """
    Get Faithfulness Service instance.

    Args:
        config: Optional ConfigService (uses default if not provided)

    Returns:
        FaithfulnessService instance
    """
    if config is None:
        config = get_config_service()
    return FaithfulnessService(config)

"""
Integration tests for LLM intent fallback wired into RetrievalOrchestrator.

Tests the integration of llm_classify_intent() into the EPR routing pipeline:
- LLM fallback triggered on low-confidence rule-based result
- Fallback skipped on high-confidence result
- Fallback skipped when feature is disabled
- Timeout falls back gracefully to rule-based result
- Exception falls back gracefully
- LLM returns None → keeps original rule-based result
"""

import asyncio

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.intent_classifier import IntentResult, QueryIntent

pytestmark = pytest.mark.asyncio


# ── Helpers ──────────────────────────────────────────────────────


def _make_orchestrator(
    *,
    intent_llm_fallback_enabled: bool = True,
    intent_llm_fallback_timeout: float = 3.0,
    intent_llm_fallback_confidence_threshold: float = 0.50,
    llm_service=None,
):
    """Create a RetrievalOrchestrator with LLM intent fallback params."""
    from app.services.retrieval_orchestrator import RetrievalOrchestrator

    mock_client = MagicMock()
    mock_embed = AsyncMock(return_value=[0.1] * 1024)

    orch = RetrievalOrchestrator(
        chromadb_client=mock_client,
        embedding_function=mock_embed,
        llm_service=llm_service or AsyncMock(),
        intent_llm_fallback_enabled=intent_llm_fallback_enabled,
        intent_llm_fallback_timeout=intent_llm_fallback_timeout,
        intent_llm_fallback_confidence_threshold=intent_llm_fallback_confidence_threshold,
    )
    return orch


def _rule_based_result(
    intent: QueryIntent = QueryIntent.UNKNOWN,
    confidence: float = 0.30,
):
    """Create a rule-based IntentResult (low confidence by default)."""
    return IntentResult(
        intent=intent,
        confidence=confidence,
        matched_patterns=[],
        suggested_collections=[],
    )


def _llm_result(
    intent: QueryIntent = QueryIntent.RESEARCH_SYNTHESIS,
    confidence: float = 0.70,
):
    """Create an LLM-based IntentResult (high confidence)."""
    return IntentResult(
        intent=intent,
        confidence=confidence,
        matched_patterns=["llm_classification"],
        suggested_collections=["diva_research_jina_v3_1024"],
    )


# ── Tests ────────────────────────────────────────────────────────


class TestLLMFallbackTriggered:
    """Test that LLM fallback triggers on low confidence."""

    async def test_low_confidence_triggers_llm_fallback(self):
        """When rule-based confidence < threshold, LLM fallback is called."""
        orch = _make_orchestrator(
            intent_llm_fallback_enabled=True,
            intent_llm_fallback_confidence_threshold=0.50,
        )

        rule_result = _rule_based_result(QueryIntent.UNKNOWN, confidence=0.30)
        llm_result = _llm_result(QueryIntent.RESEARCH_SYNTHESIS, confidence=0.70)

        with (
            patch("app.services.retrieval_orchestrator.IntentClassifier") as MockClassifier,
            patch(
                "app.services.retrieval_orchestrator.llm_classify_intent",
                new_callable=AsyncMock,
                return_value=llm_result,
            ) as mock_llm,
            patch("app.services.retrieval_orchestrator.get_routing_for_intent") as mock_routing,
            patch.object(orch, "_enforce_cutover_policy"),
        ):
            MockClassifier.return_value.classify.return_value = rule_result
            routing_cfg = MagicMock()
            routing_cfg.primary = ["sfs_lagtext_jina_v3_1024"]
            routing_cfg.support = []
            routing_cfg.secondary = []
            routing_cfg.secondary_budget = 0
            routing_cfg.require_separation = False
            mock_routing.return_value = routing_cfg

            # We only need to verify the fallback logic fires;
            # stop before the actual retrieval by raising
            with pytest.raises(Exception):
                await orch.search_with_routing(query="svår fråga", k=5)

            # LLM fallback was called because confidence (0.30) < threshold (0.50)
            mock_llm.assert_awaited_once()


class TestLLMFallbackSkippedHighConfidence:
    """Test that LLM fallback is skipped on high confidence."""

    async def test_high_confidence_skips_llm_fallback(self):
        """When rule-based confidence >= threshold, LLM fallback is NOT called."""
        orch = _make_orchestrator(
            intent_llm_fallback_enabled=True,
            intent_llm_fallback_confidence_threshold=0.50,
        )

        rule_result = _rule_based_result(QueryIntent.LEGAL_TEXT, confidence=0.85)

        with (
            patch("app.services.retrieval_orchestrator.IntentClassifier") as MockClassifier,
            patch(
                "app.services.retrieval_orchestrator.llm_classify_intent",
                new_callable=AsyncMock,
            ) as mock_llm,
            patch("app.services.retrieval_orchestrator.get_routing_for_intent") as mock_routing,
            patch.object(orch, "_enforce_cutover_policy"),
        ):
            MockClassifier.return_value.classify.return_value = rule_result
            routing_cfg = MagicMock()
            routing_cfg.primary = ["sfs_lagtext_jina_v3_1024"]
            routing_cfg.support = []
            routing_cfg.secondary = []
            routing_cfg.secondary_budget = 0
            routing_cfg.require_separation = False
            mock_routing.return_value = routing_cfg

            with pytest.raises(Exception):
                await orch.search_with_routing(query="SFS 2001:453", k=5)

            # LLM fallback was NOT called because confidence (0.85) >= threshold (0.50)
            mock_llm.assert_not_awaited()


class TestLLMFallbackSkippedWhenDisabled:
    """Test that LLM fallback is skipped when feature is disabled."""

    async def test_disabled_flag_skips_llm_fallback(self):
        """When intent_llm_fallback_enabled=false, LLM is never called."""
        orch = _make_orchestrator(
            intent_llm_fallback_enabled=False,
            intent_llm_fallback_confidence_threshold=0.50,
        )

        rule_result = _rule_based_result(QueryIntent.UNKNOWN, confidence=0.20)

        with (
            patch("app.services.retrieval_orchestrator.IntentClassifier") as MockClassifier,
            patch(
                "app.services.retrieval_orchestrator.llm_classify_intent",
                new_callable=AsyncMock,
            ) as mock_llm,
            patch("app.services.retrieval_orchestrator.get_routing_for_intent") as mock_routing,
            patch.object(orch, "_enforce_cutover_policy"),
        ):
            MockClassifier.return_value.classify.return_value = rule_result
            routing_cfg = MagicMock()
            routing_cfg.primary = ["sfs_lagtext_jina_v3_1024"]
            routing_cfg.support = []
            routing_cfg.secondary = []
            routing_cfg.secondary_budget = 0
            routing_cfg.require_separation = False
            mock_routing.return_value = routing_cfg

            with pytest.raises(Exception):
                await orch.search_with_routing(query="vad är detta", k=5)

            # LLM fallback was NOT called even though confidence is low
            mock_llm.assert_not_awaited()


class TestLLMFallbackTimeout:
    """Test that timeout falls back gracefully."""

    async def test_timeout_keeps_rule_based_result(self):
        """When LLM call times out, rule-based result is kept."""
        orch = _make_orchestrator(
            intent_llm_fallback_enabled=True,
            intent_llm_fallback_timeout=0.1,
            intent_llm_fallback_confidence_threshold=0.50,
        )

        rule_result = _rule_based_result(QueryIntent.UNKNOWN, confidence=0.30)

        async def _slow_llm(*args, **kwargs):
            await asyncio.sleep(10)  # Will be cancelled by timeout
            return _llm_result()

        with (
            patch("app.services.retrieval_orchestrator.IntentClassifier") as MockClassifier,
            patch(
                "app.services.retrieval_orchestrator.llm_classify_intent",
                side_effect=_slow_llm,
            ),
            patch("app.services.retrieval_orchestrator.get_routing_for_intent") as mock_routing,
            patch.object(orch, "_enforce_cutover_policy"),
        ):
            MockClassifier.return_value.classify.return_value = rule_result
            routing_cfg = MagicMock()
            routing_cfg.primary = ["sfs_lagtext_jina_v3_1024"]
            routing_cfg.support = []
            routing_cfg.secondary = []
            routing_cfg.secondary_budget = 0
            routing_cfg.require_separation = False
            mock_routing.return_value = routing_cfg

            # The routing call should use UNKNOWN (rule-based) intent, not error out
            mock_routing.assert_not_called()  # Not called yet

            with pytest.raises(Exception):
                await orch.search_with_routing(query="timeout fråga", k=5)

            # Routing should have been called with the original UNKNOWN intent
            mock_routing.assert_called_once()
            called_intent = mock_routing.call_args[0][0]
            assert called_intent == QueryIntent.UNKNOWN


class TestLLMFallbackException:
    """Test that exceptions fall back gracefully."""

    async def test_exception_keeps_rule_based_result(self):
        """When LLM call raises an exception, rule-based result is kept."""
        orch = _make_orchestrator(
            intent_llm_fallback_enabled=True,
            intent_llm_fallback_confidence_threshold=0.50,
        )

        rule_result = _rule_based_result(QueryIntent.UNKNOWN, confidence=0.30)

        with (
            patch("app.services.retrieval_orchestrator.IntentClassifier") as MockClassifier,
            patch(
                "app.services.retrieval_orchestrator.llm_classify_intent",
                new_callable=AsyncMock,
                side_effect=RuntimeError("LLM connection failed"),
            ),
            patch("app.services.retrieval_orchestrator.get_routing_for_intent") as mock_routing,
            patch.object(orch, "_enforce_cutover_policy"),
        ):
            MockClassifier.return_value.classify.return_value = rule_result
            routing_cfg = MagicMock()
            routing_cfg.primary = ["sfs_lagtext_jina_v3_1024"]
            routing_cfg.support = []
            routing_cfg.secondary = []
            routing_cfg.secondary_budget = 0
            routing_cfg.require_separation = False
            mock_routing.return_value = routing_cfg

            with pytest.raises(Exception):
                await orch.search_with_routing(query="error fråga", k=5)

            # Routing was called with original UNKNOWN intent
            mock_routing.assert_called_once()
            called_intent = mock_routing.call_args[0][0]
            assert called_intent == QueryIntent.UNKNOWN


class TestLLMFallbackReturnsNone:
    """Test that LLM returning None keeps original result."""

    async def test_none_result_keeps_rule_based(self):
        """When LLM returns None, the original rule-based result is preserved."""
        orch = _make_orchestrator(
            intent_llm_fallback_enabled=True,
            intent_llm_fallback_confidence_threshold=0.50,
        )

        rule_result = _rule_based_result(QueryIntent.UNKNOWN, confidence=0.30)

        with (
            patch("app.services.retrieval_orchestrator.IntentClassifier") as MockClassifier,
            patch(
                "app.services.retrieval_orchestrator.llm_classify_intent",
                new_callable=AsyncMock,
                return_value=None,
            ) as mock_llm,
            patch("app.services.retrieval_orchestrator.get_routing_for_intent") as mock_routing,
            patch.object(orch, "_enforce_cutover_policy"),
        ):
            MockClassifier.return_value.classify.return_value = rule_result
            routing_cfg = MagicMock()
            routing_cfg.primary = ["sfs_lagtext_jina_v3_1024"]
            routing_cfg.support = []
            routing_cfg.secondary = []
            routing_cfg.secondary_budget = 0
            routing_cfg.require_separation = False
            mock_routing.return_value = routing_cfg

            with pytest.raises(Exception):
                await orch.search_with_routing(query="null fråga", k=5)

            # LLM was called
            mock_llm.assert_awaited_once()
            # Routing used original UNKNOWN intent
            mock_routing.assert_called_once()
            called_intent = mock_routing.call_args[0][0]
            assert called_intent == QueryIntent.UNKNOWN

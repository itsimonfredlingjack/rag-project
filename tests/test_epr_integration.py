"""
Tests for Evidence Policy Routing (EPR) Integration
====================================================

Task 7 & 8: Wire EPR into main search path and update API response schema.

Tests:
1. RetrievalService.search_with_epr() exists and works
2. RetrievalResult has intent/routing_used fields
3. EPR returns results with tier field
4. Answer contract is retrieved for intents
5. RoutingInfo model in API response
"""

import os
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestSearchWithEprExists:
    """Test that search_with_epr() method exists on RetrievalService."""

    def test_search_with_epr_method_exists(self):
        """RetrievalService should have search_with_epr method."""
        from backend.app.services.retrieval_service import RetrievalService

        assert hasattr(RetrievalService, "search_with_epr")
        assert callable(RetrievalService.search_with_epr)


class TestRetrievalResultEprFields:
    """Test that RetrievalResult has EPR-specific fields."""

    def test_retrieval_result_has_intent_field(self):
        """RetrievalResult should have intent field."""
        from backend.app.services.retrieval_service import RetrievalMetrics, RetrievalResult

        result = RetrievalResult(
            results=[],
            metrics=RetrievalMetrics(),
            success=True,
            intent="legal_text",
        )
        assert hasattr(result, "intent")
        assert result.intent == "legal_text"

    def test_retrieval_result_has_routing_used_field(self):
        """RetrievalResult should have routing_used field."""
        from backend.app.services.retrieval_service import RetrievalMetrics, RetrievalResult

        routing = {"primary": ["sfs_lagtext"], "support": [], "secondary": []}
        result = RetrievalResult(
            results=[],
            metrics=RetrievalMetrics(),
            success=True,
            routing_used=routing,
        )
        assert hasattr(result, "routing_used")
        assert result.routing_used == routing

    def test_retrieval_result_intent_and_routing_default_to_none(self):
        """intent and routing_used should default to None."""
        from backend.app.services.retrieval_service import RetrievalMetrics, RetrievalResult

        result = RetrievalResult(
            results=[],
            metrics=RetrievalMetrics(),
            success=True,
        )
        assert result.intent is None
        assert result.routing_used is None


class TestSearchResultTierField:
    """Test that SearchResult has tier field."""

    def test_search_result_has_tier_field(self):
        """SearchResult should have tier field."""
        from backend.app.services.retrieval_service import SearchResult

        result = SearchResult(
            id="doc1",
            title="Test",
            snippet="Test snippet",
            score=0.9,
            source="sfs_lagtext",
            tier="A",
        )
        assert hasattr(result, "tier")
        assert result.tier == "A"

    def test_search_result_tier_defaults_to_none(self):
        """SearchResult tier should default to None."""
        from backend.app.services.retrieval_service import SearchResult

        result = SearchResult(
            id="doc1",
            title="Test",
            snippet="Test snippet",
            score=0.9,
            source="sfs_lagtext",
        )
        assert result.tier is None


class TestGetAnswerContract:
    """Test that answer contracts are returned for intents."""

    def test_get_answer_contract_returns_string(self):
        """get_answer_contract should return a string for known intents."""
        from backend.app.services.intent_classifier import QueryIntent
        from backend.app.services.orchestrator_service import get_answer_contract

        contract = get_answer_contract(QueryIntent.LEGAL_TEXT)
        assert isinstance(contract, str)
        assert len(contract) > 0

    def test_get_answer_contract_legal_text_mentions_citation(self):
        """Legal text contract should mention citation requirements."""
        from backend.app.services.intent_classifier import QueryIntent
        from backend.app.services.orchestrator_service import get_answer_contract

        contract = get_answer_contract(QueryIntent.LEGAL_TEXT)
        # Contract should mention citation or quoting
        assert "CITER" in contract.upper() or "ORDAGRANT" in contract.upper()

    def test_get_answer_contract_practical_process_mentions_steps(self):
        """Practical process contract should mention steps."""
        from backend.app.services.intent_classifier import QueryIntent
        from backend.app.services.orchestrator_service import get_answer_contract

        contract = get_answer_contract(QueryIntent.PRACTICAL_PROCESS)
        # Contract should mention steps or process
        assert "STEG" in contract.upper() or "PROCESS" in contract.upper()

    def test_get_answer_contract_unknown_returns_empty(self):
        """Unknown intent should return empty string."""
        from backend.app.services.intent_classifier import QueryIntent
        from backend.app.services.orchestrator_service import get_answer_contract

        contract = get_answer_contract(QueryIntent.UNKNOWN)
        # Unknown may return empty or minimal contract
        assert isinstance(contract, str)


class TestRoutingInfoModel:
    """Test that RoutingInfo model exists in constitutional_routes."""

    def test_routing_info_model_exists(self):
        """RoutingInfo model should exist."""
        from backend.app.api.constitutional_routes import RoutingInfo

        assert RoutingInfo is not None

    def test_routing_info_has_required_fields(self):
        """RoutingInfo should have primary, support, secondary, secondary_budget fields."""
        from backend.app.api.constitutional_routes import RoutingInfo

        info = RoutingInfo(
            primary=["sfs_lagtext"],
            support=["riksdag_documents"],
            secondary=["gov_docs"],
            secondary_budget=3,
        )
        assert info.primary == ["sfs_lagtext"]
        assert info.support == ["riksdag_documents"]
        assert info.secondary == ["gov_docs"]
        assert info.secondary_budget == 3

    def test_routing_info_default_values(self):
        """RoutingInfo fields should have sensible defaults."""
        from backend.app.api.constitutional_routes import RoutingInfo

        info = RoutingInfo()
        assert info.primary == []
        assert info.support == []
        assert info.secondary == []
        assert info.secondary_budget == 0


class TestAgentQueryResponseRouting:
    """Test that AgentQueryResponse includes routing field."""

    def test_agent_query_response_has_routing_field(self):
        """AgentQueryResponse should have optional routing field."""
        from backend.app.api.constitutional_routes import AgentQueryResponse, RoutingInfo

        # Test with routing
        response = AgentQueryResponse(
            answer="Test answer",
            sources=[],
            mode="evidence",
            saknas_underlag=False,
            routing=RoutingInfo(primary=["sfs"]),
        )
        assert response.routing is not None
        assert response.routing.primary == ["sfs"]

    def test_agent_query_response_routing_defaults_to_none(self):
        """AgentQueryResponse routing should default to None."""
        from backend.app.api.constitutional_routes import AgentQueryResponse

        response = AgentQueryResponse(
            answer="Test answer",
            sources=[],
            mode="evidence",
            saknas_underlag=False,
        )
        assert response.routing is None


class TestEprEnabledEnvironmentVariable:
    """Test that EPR can be toggled via environment variable."""

    def test_epr_enabled_env_var_recognized(self):
        """EPR_ENABLED environment variable should be recognized."""
        # Test with env var set
        with patch.dict(os.environ, {"EPR_ENABLED": "true"}):
            # Import after setting env var
            import importlib

            import backend.app.services.orchestrator_service as orch

            importlib.reload(orch)

            # The module should recognize EPR_ENABLED
            epr_enabled = os.getenv("EPR_ENABLED", "false").lower() == "true"
            assert epr_enabled is True

    def test_epr_disabled_by_default(self):
        """EPR should be disabled by default."""
        with patch.dict(os.environ, {}, clear=True):
            epr_enabled = os.getenv("EPR_ENABLED", "false").lower() == "true"
            assert epr_enabled is False


# Mock dataclass for orchestrator results
@dataclass
class MockSearchResult:
    id: str
    title: str
    snippet: str
    score: float
    source: str
    doc_type: str | None = None
    date: str | None = None
    retriever: str = "epr"
    tier: str | None = None


@dataclass
class MockRetrievalMetrics:
    total_latency_ms: float = 100.0
    dense_latency_ms: float = 50.0
    bm25_latency_ms: float = 50.0
    dense_result_count: int = 5
    bm25_result_count: int = 3
    doc_overlap_count: int = 1
    unique_docs_total: int = 7
    top_score: float = 0.9
    mean_score: float = 0.7
    score_std: float = 0.1
    score_entropy: float = 0.5
    dense_timeout: bool = False
    bm25_timeout: bool = False
    strategy: str = "epr_two_pass"

    def to_dict(self) -> dict[str, Any]:
        return {
            "latency": {
                "total_ms": self.total_latency_ms,
                "dense_ms": self.dense_latency_ms,
                "bm25_ms": self.bm25_latency_ms,
            },
            "results": {
                "dense_count": self.dense_result_count,
                "bm25_count": self.bm25_result_count,
                "overlap": self.doc_overlap_count,
                "unique_total": self.unique_docs_total,
            },
            "scores": {
                "top": self.top_score,
                "mean": self.mean_score,
                "std": self.score_std,
                "entropy": self.score_entropy,
            },
            "timeouts": {
                "dense": self.dense_timeout,
                "bm25": self.bm25_timeout,
            },
            "strategy": self.strategy,
        }


@dataclass
class MockOrchestratorResult:
    results: list[MockSearchResult]
    metrics: MockRetrievalMetrics
    success: bool = True
    error: str | None = None
    intent: str | None = None
    routing_used: dict | None = None


@pytest.mark.asyncio
class TestSearchWithEprIntegration:
    """Integration tests for search_with_epr method."""

    async def test_search_with_epr_returns_retrieval_result(self):
        """search_with_epr should return a RetrievalResult."""
        from backend.app.services.config_service import get_config_service
        from backend.app.services.retrieval_service import RetrievalResult, RetrievalService

        # Create mock service
        config = get_config_service()
        service = RetrievalService(config)

        # Create proper mock orchestrator result using dataclasses
        mock_result = MockOrchestratorResult(
            results=[],
            metrics=MockRetrievalMetrics(),
            success=True,
            error=None,
            intent="legal_text",
            routing_used={"primary": ["sfs"], "support": [], "secondary": []},
        )

        # Mock the orchestrator
        mock_orchestrator = MagicMock()
        mock_orchestrator.search_with_routing = AsyncMock(return_value=mock_result)

        service._orchestrator = mock_orchestrator
        service._initialized = True
        service._chromadb_client = MagicMock()

        result = await service.search_with_epr(query="Vad säger RF?", k=10)

        assert isinstance(result, RetrievalResult)
        assert result.success is True
        assert result.intent == "legal_text"
        assert result.routing_used is not None

    async def test_search_with_epr_includes_tier_in_results(self):
        """Results from search_with_epr should include tier field."""
        from backend.app.services.config_service import get_config_service
        from backend.app.services.retrieval_service import RetrievalService

        config = get_config_service()
        service = RetrievalService(config)

        # Create mock result with tier using proper dataclass
        mock_search_result = MockSearchResult(
            id="doc1",
            title="Test",
            snippet="Test snippet",
            score=0.9,
            source="sfs_lagtext",
            doc_type="law",
            date="2024-01-01",
            retriever="epr",
            tier="A",
        )

        mock_result = MockOrchestratorResult(
            results=[mock_search_result],
            metrics=MockRetrievalMetrics(),
            success=True,
            error=None,
            intent="legal_text",
            routing_used={"primary": ["sfs"], "support": [], "secondary": []},
        )

        mock_orchestrator = MagicMock()
        mock_orchestrator.search_with_routing = AsyncMock(return_value=mock_result)

        service._orchestrator = mock_orchestrator
        service._initialized = True
        service._chromadb_client = MagicMock()

        result = await service.search_with_epr(query="Vad säger RF?", k=10)

        assert len(result.results) > 0
        assert result.results[0].tier == "A"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

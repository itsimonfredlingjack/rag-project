"""
3-Way CRAG Filtering Tests

Tests for the 3-way document grading (RELEVANT/AMBIGUOUS/IRRELEVANT)
filtering logic in crag_service.process_crag_grading().
"""

import time
from unittest.mock import AsyncMock, Mock

import pytest

from app.services.crag_service import process_crag_grading
from app.services.grader_service import GradeResult, GradingMetrics, GradingResult
from app.services.query_processor_service import ResponseMode
from app.services.retrieval_service import RetrievalMetrics, RetrievalResult, SearchResult

pytestmark = pytest.mark.integration


def _make_sources(n: int) -> list[SearchResult]:
    return [
        SearchResult(
            id=f"doc_{i}",
            title=f"Document {i}",
            snippet=f"Content of document {i}",
            score=0.9 - i * 0.05,
            source="test",
            doc_type="regulation",
            retriever="dense",
        )
        for i in range(n)
    ]


def _make_grade(doc_id: str, status: str, confidence: float = 0.8) -> GradeResult:
    relevant = status == "RELEVANT"
    if relevant:
        score = confidence
    elif status == "AMBIGUOUS":
        score = confidence * 0.5
    else:
        score = 0.0
    return GradeResult(
        doc_id=doc_id,
        relevant=relevant,
        status=status,
        reason=status.lower(),
        score=score,
        confidence=confidence,
        latency_ms=10.0,
    )


def _make_grading_result(
    grades: list[GradeResult],
) -> GradingResult:
    total = len(grades)
    relevant = sum(1 for g in grades if g.status == "RELEVANT")
    ambiguous = sum(1 for g in grades if g.status == "AMBIGUOUS")
    irrelevant = sum(1 for g in grades if g.status == "IRRELEVANT")
    return GradingResult(
        grades=grades,
        metrics=GradingMetrics(
            total_documents=total,
            relevant_count=relevant,
            ambiguous_count=ambiguous,
            irrelevant_count=irrelevant,
            relevant_percentage=(relevant / total * 100) if total else 0.0,
            avg_score=sum(g.score for g in grades) / total if total else 0.0,
            total_latency_ms=50.0,
            per_doc_latency_ms=50.0 / total if total else 0.0,
        ),
        success=True,
    )


def _make_config(crag_enabled=True, self_reflection=False):
    config = Mock()
    config.settings.crag_enabled = crag_enabled
    config.settings.crag_enable_self_reflection = self_reflection
    config.structured_output_effective_enabled = True
    return config


def _make_retrieval_result(sources: list[SearchResult]) -> RetrievalResult:
    return RetrievalResult(
        results=sources,
        metrics=RetrievalMetrics(strategy="parallel_v1", top_score=0.9),
        success=True,
    )


class TestThreeWayFilteringKeepsOnlyRelevant:
    """>=3 RELEVANT should drop AMBIGUOUS documents."""

    @pytest.mark.asyncio
    async def test_3_relevant_drops_ambiguous(self):
        sources = _make_sources(5)
        grades = [
            _make_grade("doc_0", "RELEVANT"),
            _make_grade("doc_1", "RELEVANT"),
            _make_grade("doc_2", "RELEVANT"),
            _make_grade("doc_3", "AMBIGUOUS"),
            _make_grade("doc_4", "IRRELEVANT"),
        ]
        grader = Mock()
        grader.grade_documents = AsyncMock(return_value=_make_grading_result(grades))

        result = await process_crag_grading(
            config=_make_config(),
            grader=grader,
            critic=None,
            question="test",
            search_query="test",
            retrieval_result=_make_retrieval_result(sources),
            resolved_mode=ResponseMode.EVIDENCE,
            reasoning_steps=[],
            start_time=time.perf_counter(),
            query_classification_ms=0.0,
            decontextualization_ms=0.0,
            retrieval_ms=0.0,
        )

        assert not result.early_return
        assert len(result.sources) == 3
        assert all(s.id in ("doc_0", "doc_1", "doc_2") for s in result.sources)
        assert result.relevant_count == 3


class TestThreeWayFilteringIncludesAmbiguous:
    """1-2 RELEVANT should include AMBIGUOUS as supplementary."""

    @pytest.mark.asyncio
    async def test_2_relevant_includes_ambiguous(self):
        sources = _make_sources(5)
        grades = [
            _make_grade("doc_0", "RELEVANT"),
            _make_grade("doc_1", "AMBIGUOUS"),
            _make_grade("doc_2", "RELEVANT"),
            _make_grade("doc_3", "AMBIGUOUS"),
            _make_grade("doc_4", "IRRELEVANT"),
        ]
        grader = Mock()
        grader.grade_documents = AsyncMock(return_value=_make_grading_result(grades))

        result = await process_crag_grading(
            config=_make_config(),
            grader=grader,
            critic=None,
            question="test",
            search_query="test",
            retrieval_result=_make_retrieval_result(sources),
            resolved_mode=ResponseMode.ASSIST,
            reasoning_steps=[],
            start_time=time.perf_counter(),
            query_classification_ms=0.0,
            decontextualization_ms=0.0,
            retrieval_ms=0.0,
        )

        assert not result.early_return
        assert len(result.sources) == 4  # 2 RELEVANT + 2 AMBIGUOUS
        source_ids = {s.id for s in result.sources}
        assert "doc_4" not in source_ids  # IRRELEVANT dropped

    @pytest.mark.asyncio
    async def test_1_relevant_includes_ambiguous(self):
        sources = _make_sources(3)
        grades = [
            _make_grade("doc_0", "RELEVANT"),
            _make_grade("doc_1", "AMBIGUOUS"),
            _make_grade("doc_2", "IRRELEVANT"),
        ]
        grader = Mock()
        grader.grade_documents = AsyncMock(return_value=_make_grading_result(grades))

        result = await process_crag_grading(
            config=_make_config(),
            grader=grader,
            critic=None,
            question="test",
            search_query="test",
            retrieval_result=_make_retrieval_result(sources),
            resolved_mode=ResponseMode.EVIDENCE,
            reasoning_steps=[],
            start_time=time.perf_counter(),
            query_classification_ms=0.0,
            decontextualization_ms=0.0,
            retrieval_ms=0.0,
        )

        assert not result.early_return
        assert len(result.sources) == 2  # 1 RELEVANT + 1 AMBIGUOUS


class TestThreeWayFilteringAmbiguousOnly:
    """0 RELEVANT should use AMBIGUOUS documents."""

    @pytest.mark.asyncio
    async def test_0_relevant_uses_ambiguous(self):
        sources = _make_sources(3)
        grades = [
            _make_grade("doc_0", "AMBIGUOUS"),
            _make_grade("doc_1", "IRRELEVANT"),
            _make_grade("doc_2", "AMBIGUOUS"),
        ]
        grader = Mock()
        grader.grade_documents = AsyncMock(return_value=_make_grading_result(grades))

        result = await process_crag_grading(
            config=_make_config(),
            grader=grader,
            critic=None,
            question="test",
            search_query="test",
            retrieval_result=_make_retrieval_result(sources),
            resolved_mode=ResponseMode.ASSIST,
            reasoning_steps=[],
            start_time=time.perf_counter(),
            query_classification_ms=0.0,
            decontextualization_ms=0.0,
            retrieval_ms=0.0,
        )

        assert not result.early_return
        assert len(result.sources) == 2  # 2 AMBIGUOUS
        source_ids = {s.id for s in result.sources}
        assert source_ids == {"doc_0", "doc_2"}


class TestThreeWayFilteringEmptyResult:
    """0 RELEVANT + 0 AMBIGUOUS: EVIDENCE mode early returns, ASSIST returns empty."""

    @pytest.mark.asyncio
    async def test_evidence_mode_early_return(self):
        sources = _make_sources(2)
        grades = [
            _make_grade("doc_0", "IRRELEVANT"),
            _make_grade("doc_1", "IRRELEVANT"),
        ]
        grader = Mock()
        grader.grade_documents = AsyncMock(return_value=_make_grading_result(grades))

        result = await process_crag_grading(
            config=_make_config(),
            grader=grader,
            critic=None,
            question="test",
            search_query="test",
            retrieval_result=_make_retrieval_result(sources),
            resolved_mode=ResponseMode.EVIDENCE,
            reasoning_steps=[],
            start_time=time.perf_counter(),
            query_classification_ms=0.0,
            decontextualization_ms=0.0,
            retrieval_ms=0.0,
        )

        assert result.early_return is True
        assert result.result is not None
        assert len(result.sources) == 0

    @pytest.mark.asyncio
    async def test_assist_mode_empty_sources(self):
        sources = _make_sources(2)
        grades = [
            _make_grade("doc_0", "IRRELEVANT"),
            _make_grade("doc_1", "IRRELEVANT"),
        ]
        grader = Mock()
        grader.grade_documents = AsyncMock(return_value=_make_grading_result(grades))

        result = await process_crag_grading(
            config=_make_config(),
            grader=grader,
            critic=None,
            question="test",
            search_query="test",
            retrieval_result=_make_retrieval_result(sources),
            resolved_mode=ResponseMode.ASSIST,
            reasoning_steps=[],
            start_time=time.perf_counter(),
            query_classification_ms=0.0,
            decontextualization_ms=0.0,
            retrieval_ms=0.0,
        )

        # ASSIST with no sources does not early return, just returns empty
        assert result.early_return is False
        assert len(result.sources) == 0


class TestCragDisabledPassthrough:
    """CRAG off = all sources pass through unfiltered."""

    @pytest.mark.asyncio
    async def test_crag_disabled(self):
        sources = _make_sources(5)

        result = await process_crag_grading(
            config=_make_config(crag_enabled=False),
            grader=None,
            critic=None,
            question="test",
            search_query="test",
            retrieval_result=_make_retrieval_result(sources),
            resolved_mode=ResponseMode.EVIDENCE,
            reasoning_steps=[],
            start_time=time.perf_counter(),
            query_classification_ms=0.0,
            decontextualization_ms=0.0,
            retrieval_ms=0.0,
        )

        assert not result.early_return
        assert len(result.sources) == 5
        assert result.grade_count == 0
        assert result.grade_ms == 0.0

    @pytest.mark.asyncio
    async def test_chat_mode_skips_crag(self):
        sources = _make_sources(3)
        grader = Mock()

        result = await process_crag_grading(
            config=_make_config(),
            grader=grader,
            critic=None,
            question="test",
            search_query="test",
            retrieval_result=_make_retrieval_result(sources),
            resolved_mode=ResponseMode.CHAT,
            reasoning_steps=[],
            start_time=time.perf_counter(),
            query_classification_ms=0.0,
            decontextualization_ms=0.0,
            retrieval_ms=0.0,
        )

        assert not result.early_return
        assert len(result.sources) == 3
        grader.grade_documents.assert_not_called()


class TestCragMetrics:
    """Metrics should be correctly populated."""

    @pytest.mark.asyncio
    async def test_metrics_populated(self):
        sources = _make_sources(4)
        grades = [
            _make_grade("doc_0", "RELEVANT"),
            _make_grade("doc_1", "AMBIGUOUS"),
            _make_grade("doc_2", "IRRELEVANT"),
            _make_grade("doc_3", "RELEVANT"),
        ]
        grader = Mock()
        grader.grade_documents = AsyncMock(return_value=_make_grading_result(grades))

        result = await process_crag_grading(
            config=_make_config(),
            grader=grader,
            critic=None,
            question="test",
            search_query="test",
            retrieval_result=_make_retrieval_result(sources),
            resolved_mode=ResponseMode.EVIDENCE,
            reasoning_steps=[],
            start_time=time.perf_counter(),
            query_classification_ms=0.0,
            decontextualization_ms=0.0,
            retrieval_ms=0.0,
        )

        assert result.grade_count == 4
        assert result.relevant_count == 2
        assert result.grade_ms > 0
        assert result.thought_chain is None  # No self-reflection
        assert result.self_reflection_ms == 0.0

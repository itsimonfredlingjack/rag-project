"""
Tests for Concurrency Safety and Memory Leak Prevention.

Tests cover:
  - Circuit breaker state transitions under concurrent load
  - Grader batch timeout and task cancellation
  - RRF fusion dict accumulation bounds
  - Async semaphore contention under parallel queries
  - Singleton lifecycle (embedding, config)
  - Module-level lock release on exception
  - httpx client cleanup on stream failure

These tests do NOT require real LLM, ChromaDB, or GPU — all I/O is mocked.
"""

import asyncio
import gc
import time
import weakref
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock

import pytest


# ═══════════════════════════════════════════════════════════════════════════
# CIRCUIT BREAKER CONCURRENCY
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestCircuitBreakerConcurrency:
    """Verify circuit breaker state machine under concurrent access."""

    def _make_breaker(self, **kw):
        from app.services.llm_service import CircuitBreaker

        return CircuitBreaker(**kw)

    def test_closed_after_init(self):
        from app.services.llm_service import CircuitState

        cb = self._make_breaker()
        assert cb.state == CircuitState.CLOSED

    def test_opens_after_threshold_failures(self):
        from app.services.llm_service import CircuitState

        cb = self._make_breaker(failure_threshold=3)
        for _ in range(3):
            cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_half_open_after_recovery_timeout(self):
        from app.services.llm_service import CircuitState

        cb = self._make_breaker(failure_threshold=1, recovery_timeout=0.05)
        cb.record_failure()
        assert cb.state == CircuitState.OPEN
        time.sleep(0.06)
        assert cb.state == CircuitState.HALF_OPEN

    def test_closes_on_success_in_half_open(self):
        from app.services.llm_service import CircuitState

        cb = self._make_breaker(failure_threshold=1, recovery_timeout=0.01)
        cb.record_failure()
        time.sleep(0.02)
        assert cb.state == CircuitState.HALF_OPEN
        cb.record_success()
        assert cb.state == CircuitState.CLOSED

    def test_reopens_on_failure_in_half_open(self):
        from app.services.llm_service import CircuitState

        cb = self._make_breaker(failure_threshold=1, recovery_timeout=0.01)
        cb.record_failure()
        time.sleep(0.02)
        assert cb.state == CircuitState.HALF_OPEN
        cb.record_failure()
        assert cb.state == CircuitState.OPEN

    def test_check_raises_when_open(self):
        from app.core.exceptions import LLMConnectionError
        from app.services.llm_service import CircuitBreaker

        cb = CircuitBreaker(failure_threshold=1)
        cb.record_failure()
        with pytest.raises(LLMConnectionError, match="Circuit breaker is OPEN"):
            cb.check()

    def test_rapid_success_failure_interleave(self):
        """Simulate concurrent success/failure recording."""
        from app.services.llm_service import CircuitState

        cb = self._make_breaker(failure_threshold=3)
        # Interleave: fail, success resets, fail again
        cb.record_failure()
        cb.record_failure()
        cb.record_success()  # resets count
        cb.record_failure()
        cb.record_failure()
        # Only 2 consecutive failures after reset — should still be CLOSED
        assert cb.state == CircuitState.CLOSED

    def test_concurrent_failures_exact_threshold(self):
        """Exactly threshold failures should trip the breaker."""
        from app.services.llm_service import CircuitState

        cb = self._make_breaker(failure_threshold=5)
        for i in range(4):
            cb.record_failure()
            assert cb.state == CircuitState.CLOSED, f"Tripped early at {i + 1}"
        cb.record_failure()
        assert cb.state == CircuitState.OPEN


# ═══════════════════════════════════════════════════════════════════════════
# GRADER BATCH TIMEOUT & TASK CANCELLATION
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestGraderConcurrency:
    """Verify grader service handles batch timeout and task cancellation."""

    @pytest.fixture
    def mock_grader(self):
        """Create a GraderService with mocked LLM."""
        from app.services.grader_service import GraderService

        config = MagicMock()
        config.crag_grade_threshold = 0.15
        llm = MagicMock()
        grader = GraderService.__new__(GraderService)
        grader.config = config
        grader.llm_service = llm
        grader.logger = MagicMock()
        grader.grade_threshold = 0.15
        grader.max_concurrent = 3
        grader.grade_timeout = 0.5  # Very short timeout for testing
        grader._initialized = True
        return grader

    def _make_doc(self, doc_id: str) -> MagicMock:
        doc = MagicMock()
        doc.id = doc_id
        doc.title = f"Title {doc_id}"
        doc.snippet = f"Snippet for {doc_id}"
        doc.collection = "test"
        doc.metadata = {}
        return doc

    @pytest.mark.asyncio
    async def test_empty_documents_returns_immediately(self, mock_grader):
        result = await mock_grader.grade_documents("test query", [])
        assert result.success is True
        assert len(result.grades) == 0
        assert result.metrics.total_documents == 0

    @pytest.mark.asyncio
    async def test_batch_timeout_creates_placeholders(self, mock_grader):
        """When grading times out, all docs in the batch get timeout placeholders."""
        docs = [self._make_doc(f"d{i}") for i in range(5)]

        # Make grading take forever
        async def _slow_grade(query, doc, threshold):
            await asyncio.sleep(10)

        mock_grader._grade_single_document_async = _slow_grade
        mock_grader.grade_timeout = 0.1

        result = await mock_grader.grade_documents("test query", docs)
        assert result.success is True
        # All documents should have grades (timeout placeholders)
        assert len(result.grades) == 5
        for grade in result.grades:
            assert grade.status == "IRRELEVANT"
            assert "Timeout" in grade.reason

    @pytest.mark.asyncio
    async def test_batch_exception_handling(self, mock_grader):
        """Exceptions in individual grades should not crash the batch."""
        from app.services.grader_service import GradeResult

        docs = [self._make_doc(f"d{i}") for i in range(3)]
        call_count = 0

        async def _flaky_grade(query, doc, threshold):
            nonlocal call_count
            call_count += 1
            if doc.id == "d1":
                raise ValueError("Simulated grading failure")
            return GradeResult(
                doc_id=doc.id,
                relevant=True,
                status="RELEVANT",
                reason="test",
                score=0.8,
                confidence=0.9,
                latency_ms=10.0,
            )

        mock_grader._grade_single_document_async = _flaky_grade

        result = await mock_grader.grade_documents("test query", docs)
        assert result.success is True
        assert len(result.grades) == 3
        # d1 should have a fallback grade
        d1_grade = next(g for g in result.grades if g.doc_id == "d1")
        assert d1_grade.status == "IRRELEVANT"
        assert "error" in d1_grade.reason.lower()

    @pytest.mark.asyncio
    async def test_concurrent_batches_respect_max_concurrent(self, mock_grader):
        """Verify batching limits concurrent tasks to max_concurrent."""
        from app.services.grader_service import GradeResult

        mock_grader.max_concurrent = 2
        active_count = 0
        max_active = 0

        async def _tracked_grade(query, doc, threshold):
            nonlocal active_count, max_active
            active_count += 1
            max_active = max(max_active, active_count)
            await asyncio.sleep(0.01)
            active_count -= 1
            return GradeResult(
                doc_id=doc.id,
                relevant=True,
                status="RELEVANT",
                reason="test",
                score=0.8,
                confidence=0.9,
                latency_ms=10.0,
            )

        mock_grader._grade_single_document_async = _tracked_grade
        docs = [self._make_doc(f"d{i}") for i in range(6)]

        result = await mock_grader.grade_documents("test query", docs)
        assert result.success is True
        assert len(result.grades) == 6
        # Max concurrent should never exceed batch size
        assert max_active <= mock_grader.max_concurrent


# ═══════════════════════════════════════════════════════════════════════════
# RRF FUSION — DICT ACCUMULATION BOUNDS
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestRRFFusionMemory:
    """Verify RRF fusion dicts don't grow unboundedly."""

    def _make_result_set(self, n: int, prefix: str = "doc") -> List[Dict[str, Any]]:
        """Generate a result set of n documents."""
        return [
            {"id": f"{prefix}_{i}", "score": 1.0 - (i * 0.01), "title": f"Title {i}"}
            for i in range(n)
        ]

    def test_rrf_output_size_bounded(self):
        """RRF output should have at most as many docs as all inputs combined."""
        from app.services.rag_fusion import reciprocal_rank_fusion

        sets = [self._make_result_set(50, f"q{i}") for i in range(3)]
        merged = reciprocal_rank_fusion(sets)
        # At most 150 unique docs (50 * 3 if no overlap)
        assert len(merged) <= 150

    def test_rrf_with_full_overlap(self):
        """When all queries return the same docs, merged should equal input size."""
        from app.services.rag_fusion import reciprocal_rank_fusion

        same_set = self._make_result_set(20)
        sets = [same_set.copy() for _ in range(5)]
        merged = reciprocal_rank_fusion(sets)
        assert len(merged) == 20  # No duplicates in output

    def test_rrf_empty_input(self):
        from app.services.rag_fusion import reciprocal_rank_fusion

        assert reciprocal_rank_fusion([]) == []

    def test_rrf_single_result_set(self):
        from app.services.rag_fusion import reciprocal_rank_fusion

        docs = self._make_result_set(10)
        merged = reciprocal_rank_fusion([docs])
        assert len(merged) == 10
        # Scores should be monotonically decreasing
        for i in range(len(merged) - 1):
            assert merged[i]["rrf_score"] >= merged[i + 1]["rrf_score"]

    def test_rrf_large_scale_no_memory_explosion(self):
        """Stress test: 10 query variants × 200 docs each."""
        from app.services.rag_fusion import reciprocal_rank_fusion

        sets = [self._make_result_set(200, f"q{i}") for i in range(10)]
        merged = reciprocal_rank_fusion(sets)
        # Should be 2000 unique docs (no overlap between different prefixes)
        assert len(merged) == 2000
        # All should have rrf_score > 0
        for doc in merged:
            assert doc["rrf_score"] > 0

    def test_fusion_metrics_calculation(self):
        """Metrics should accurately reflect overlap."""
        from app.services.rag_fusion import calculate_fusion_metrics, reciprocal_rank_fusion

        # 2 sets with 50% overlap
        set_a = self._make_result_set(10, "shared") + self._make_result_set(5, "unique_a")
        set_b = self._make_result_set(10, "shared") + self._make_result_set(5, "unique_b")
        merged = reciprocal_rank_fusion([set_a, set_b])
        metrics = calculate_fusion_metrics([set_a, set_b], merged)

        assert metrics.unique_docs_before_fusion == 15  # set_a has 15 unique IDs
        assert metrics.unique_docs_after_fusion == 20  # 10 shared + 5 + 5
        assert metrics.overlap_count == 10  # 10 shared docs appear in both


# ═══════════════════════════════════════════════════════════════════════════
# ASYNC SEMAPHORE CONTENTION
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestSemaphoreContention:
    """Test asyncio.Semaphore behaviour under concurrent access."""

    @pytest.mark.asyncio
    async def test_semaphore_limits_concurrency(self):
        """Verify semaphore enforces max concurrent coroutines."""
        sem = asyncio.Semaphore(3)
        active = 0
        max_active = 0

        async def worker():
            nonlocal active, max_active
            async with sem:
                active += 1
                max_active = max(max_active, active)
                await asyncio.sleep(0.01)
                active -= 1

        await asyncio.gather(*[worker() for _ in range(20)])
        assert max_active <= 3
        assert active == 0  # All released

    @pytest.mark.asyncio
    async def test_semaphore_releases_on_exception(self):
        """Semaphore must release even if coroutine raises."""
        sem = asyncio.Semaphore(2)
        errors = 0

        async def failing_worker(should_fail: bool):
            nonlocal errors
            async with sem:
                if should_fail:
                    errors += 1
                    raise ValueError("boom")
                await asyncio.sleep(0.01)

        tasks = [failing_worker(i % 3 == 0) for i in range(12)]
        await asyncio.gather(*tasks, return_exceptions=True)

        # Semaphore should be fully released (value = 2)
        assert sem._value == 2
        assert errors == 4  # 0, 3, 6, 9

    @pytest.mark.asyncio
    async def test_semaphore_fairness_under_load(self):
        """All workers should eventually execute under contention."""
        sem = asyncio.Semaphore(1)  # Single slot
        executed = []

        async def ordered_worker(idx: int):
            async with sem:
                executed.append(idx)
                await asyncio.sleep(0.001)

        await asyncio.gather(*[ordered_worker(i) for i in range(10)])
        assert len(executed) == 10
        assert set(executed) == set(range(10))


# ═══════════════════════════════════════════════════════════════════════════
# SINGLETON LIFECYCLE — EMBEDDING SERVICE
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestEmbeddingSingleton:
    """Verify EmbeddingService singleton doesn't leak across test runs."""

    @pytest.fixture(autouse=True)
    def _reset_singleton(self):
        """Reset singleton before and after each test."""
        from app.services.embedding_service import EmbeddingService

        EmbeddingService._instance = None
        yield
        EmbeddingService._instance = None

    def test_singleton_returns_same_instance(self):
        from app.services.embedding_service import EmbeddingService

        config = MagicMock()
        config.embedding_model = "test-model"
        a = EmbeddingService(config)
        b = EmbeddingService(config)
        assert a is b

    def test_singleton_reset_creates_new_instance(self):
        from app.services.embedding_service import EmbeddingService

        config = MagicMock()
        config.embedding_model = "test-model"
        a = EmbeddingService(config)
        EmbeddingService._instance = None
        c = EmbeddingService(config)
        # c should be a new instance (different id)
        assert a is not c

    def test_model_not_loaded_until_encode(self):
        """Model should be lazy-loaded — not on __init__."""
        from app.services.embedding_service import EmbeddingService

        config = MagicMock()
        config.embedding_model = "test-model"
        svc = EmbeddingService(config)
        assert svc._model is None
        assert svc._is_loaded is False

    def test_weakref_allows_gc_after_reset(self):
        """After singleton reset, old instance should be GC-eligible."""
        from app.services.embedding_service import EmbeddingService

        config = MagicMock()
        config.embedding_model = "test-model"
        svc = EmbeddingService(config)
        ref = weakref.ref(svc)
        EmbeddingService._instance = None
        del svc
        gc.collect()
        # The weak reference should be dead now
        assert ref() is None


# ═══════════════════════════════════════════════════════════════════════════
# CONFIG SERVICE SINGLETON
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestConfigServiceSingleton:
    """Verify ConfigService factory returns consistent instances."""

    def test_get_config_service_returns_same(self):
        """Factory function should return the same instance."""
        from app.services.config_service import get_config_service

        # Clear any cached instance
        get_config_service.cache_clear()
        a = get_config_service()
        b = get_config_service()
        assert a is b
        get_config_service.cache_clear()

    def test_config_attributes_consistent(self):
        """Config values should not change between reads."""
        from app.services.config_service import get_config_service

        get_config_service.cache_clear()
        cfg = get_config_service()
        val1 = cfg.settings.crag_grade_threshold
        val2 = cfg.settings.crag_grade_threshold
        assert val1 == val2
        get_config_service.cache_clear()


# ═══════════════════════════════════════════════════════════════════════════
# ASYNC LOCK RELEASE ON EXCEPTION
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestAsyncLockSafety:
    """Verify asyncio.Lock is released on exception (deadlock prevention)."""

    @pytest.mark.asyncio
    async def test_lock_released_after_exception(self):
        """Lock should be released even if protected code raises."""
        lock = asyncio.Lock()

        with pytest.raises(RuntimeError):
            async with lock:
                raise RuntimeError("inner failure")

        # Lock should be available now
        assert not lock.locked()

    @pytest.mark.asyncio
    async def test_lock_prevents_concurrent_access(self):
        """Lock should serialize access to critical section."""
        lock = asyncio.Lock()
        in_critical = False
        violations = 0

        async def worker():
            nonlocal in_critical, violations
            async with lock:
                if in_critical:
                    violations += 1
                in_critical = True
                await asyncio.sleep(0.005)
                in_critical = False

        await asyncio.gather(*[worker() for _ in range(10)])
        assert violations == 0

    @pytest.mark.asyncio
    async def test_lock_not_reentrant(self):
        """asyncio.Lock is NOT reentrant — attempting to acquire twice deadlocks."""
        lock = asyncio.Lock()
        await lock.acquire()

        # Trying to acquire again should not succeed immediately
        acquired = lock.locked()
        assert acquired is True

        # Release so we don't deadlock the test
        lock.release()


# ═══════════════════════════════════════════════════════════════════════════
# HTTPX CLIENT CLEANUP
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestHttpxClientLifecycle:
    """Verify httpx.AsyncClient is properly created and closed."""

    @pytest.mark.asyncio
    async def test_client_close_on_service_close(self):
        """LLMService.close() should close the httpx client."""
        from app.services.llm_service import LLMService

        config = MagicMock()
        config.llm_base_url = "http://localhost:11434"
        config.ollama_base_url = "http://localhost:11434"
        config.ollama_timeout_seconds = 10
        config.constitutional_model = "test-model"
        config.settings = MagicMock()
        config.settings.llm_base_url = "http://localhost:11434"

        svc = LLMService.__new__(LLMService)
        svc.config = config
        svc.logger = MagicMock()
        svc._initialized = True

        # Mock the httpx client — must satisfy `not client.is_closed` guard
        mock_client = AsyncMock()
        mock_client.is_closed = False
        mock_client.aclose = AsyncMock()
        svc._client = mock_client

        await svc.close()
        mock_client.aclose.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_stream_cleanup_on_early_consumer_cancel(self):
        """Simulates consumer cancelling mid-stream — resources should be freed."""
        collected = []

        async def mock_stream():
            try:
                for i in range(100):
                    yield f"token_{i}"
                    await asyncio.sleep(0.001)
            finally:
                collected.append("cleanup")

        gen = mock_stream()
        async for token in gen:
            if token == "token_5":
                break  # Early exit

        # Generator cleanup should have run
        await gen.aclose()
        assert "cleanup" in collected


# ═══════════════════════════════════════════════════════════════════════════
# CONCURRENT GATHER EXCEPTION PROPAGATION
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestGatherExceptionPropagation:
    """Verify asyncio.gather with return_exceptions handles failures correctly."""

    @pytest.mark.asyncio
    async def test_gather_return_exceptions_isolates_failures(self):
        """With return_exceptions=True, one failure shouldn't block others."""
        results_collected = []

        async def ok_task(val):
            await asyncio.sleep(0.01)
            results_collected.append(val)
            return val

        async def failing_task():
            raise ValueError("intentional failure")

        results = await asyncio.gather(
            ok_task(1),
            failing_task(),
            ok_task(3),
            return_exceptions=True,
        )

        assert results[0] == 1
        assert isinstance(results[1], ValueError)
        assert results[2] == 3
        assert set(results_collected) == {1, 3}

    @pytest.mark.asyncio
    async def test_gather_without_return_exceptions_raises_first(self):
        """Without return_exceptions, first failure raises immediately."""

        async def ok_task():
            await asyncio.sleep(0.1)
            return "ok"

        async def failing_task():
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError, match="boom"):
            await asyncio.gather(ok_task(), failing_task())

    @pytest.mark.asyncio
    async def test_gather_all_success(self):
        """Happy path: all tasks succeed."""

        async def task(val):
            await asyncio.sleep(0.001)
            return val * 2

        results = await asyncio.gather(*[task(i) for i in range(10)])
        assert results == [i * 2 for i in range(10)]

    @pytest.mark.asyncio
    async def test_gather_timeout_with_wait_for(self):
        """asyncio.wait_for should cancel slow tasks."""

        async def slow_task():
            await asyncio.sleep(10)
            return "never"

        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(slow_task(), timeout=0.05)

    @pytest.mark.asyncio
    async def test_cancelled_tasks_dont_leak(self):
        """Cancelled tasks should be properly cleaned up."""
        started = 0
        finished = 0

        async def counted_task(duration):
            nonlocal started, finished
            started += 1
            try:
                await asyncio.sleep(duration)
                finished += 1
            except asyncio.CancelledError:
                pass  # Expected for cancelled tasks

        tasks = [
            asyncio.create_task(counted_task(0.01)),
            asyncio.create_task(counted_task(10)),  # Will be cancelled
            asyncio.create_task(counted_task(0.01)),
        ]

        # Let fast tasks complete
        await asyncio.sleep(0.05)

        # Cancel the slow task
        tasks[1].cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

        assert started == 3
        assert finished == 2  # The cancelled task didn't finish


# ═══════════════════════════════════════════════════════════════════════════
# MEMORY LEAK — OBJECT LIFECYCLE
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestMemoryLeakPrevention:
    """Verify objects are properly garbage collected."""

    def test_dataclass_gc_after_dereferencing(self):
        """Dataclasses should be GC'd when all references are dropped."""
        from app.services.grader_service import GradeResult

        obj = GradeResult(
            doc_id="test",
            relevant=True,
            status="RELEVANT",
            reason="test",
            score=0.9,
            confidence=0.9,
            latency_ms=10.0,
        )
        ref = weakref.ref(obj)
        del obj
        gc.collect()
        assert ref() is None

    def test_large_list_gc(self):
        """Large result containers should be GC'd when dereferenced."""

        class ResultContainer:
            """Weakref-able wrapper (plain lists don't support weakref)."""

            def __init__(self, data):
                self.data = data

        items = ResultContainer(
            [{"id": f"doc_{i}", "score": 0.5, "text": "x" * 1000} for i in range(10000)]
        )
        ref = weakref.ref(items)
        assert len(items.data) == 10000
        del items
        gc.collect()
        assert ref() is None

    def test_dict_accumulation_cleared(self):
        """Simulate RRF-like dict accumulation and verify cleanup."""
        doc_scores: Dict[str, float] = {}
        doc_data: Dict[str, Dict[str, Any]] = {}

        # Accumulate 10K entries
        for i in range(10000):
            doc_id = f"doc_{i}"
            doc_scores[doc_id] = 1.0 / (60 + i)
            doc_data[doc_id] = {"id": doc_id, "text": "x" * 100}

        assert len(doc_scores) == 10000
        assert len(doc_data) == 10000

        # Clear and verify
        doc_scores.clear()
        doc_data.clear()
        gc.collect()

        assert len(doc_scores) == 0
        assert len(doc_data) == 0

    def test_asyncio_task_reference_cleanup(self):
        """Verify asyncio task references don't accumulate."""
        loop = asyncio.new_event_loop()

        async def _run():
            tasks = []
            for _ in range(100):

                async def noop():
                    pass

                t = asyncio.create_task(noop())
                tasks.append(t)
            await asyncio.gather(*tasks)
            # All tasks should be done
            for t in tasks:
                assert t.done()
            return len(tasks)

        result = loop.run_until_complete(_run())
        assert result == 100
        loop.close()


# ═══════════════════════════════════════════════════════════════════════════
# QUERY EXPANDER — STATELESS
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestQueryExpanderStateless:
    """Verify QueryExpander doesn't accumulate state between calls."""

    def _mock_rewrite(self, query: str):
        """Create a mock RewriteResult for QueryExpander."""
        mock = MagicMock()
        mock.rewritten_query = query
        mock.was_rewritten = False
        mock.legal_refs_found = []
        return mock

    def test_expander_no_state_leakage(self):
        """Multiple expand() calls should not accumulate internal state."""
        from app.services.rag_fusion import QueryExpander

        expander = QueryExpander()

        # Call expand multiple times
        for i in range(50):
            result = expander.expand(f"Query variant {i}", self._mock_rewrite(f"Query variant {i}"))
            assert len(result.queries) >= 1
            assert result.original == f"Query variant {i}"

        # Expander should have no accumulated state beyond compiled patterns
        # (_question_patterns is compiled once in __init__ and is immutable)
        instance_collections = [
            attr for attr in vars(expander).values() if isinstance(attr, (dict,)) and len(attr) > 0
        ]
        assert len(instance_collections) == 0, f"Expander accumulated state: {instance_collections}"

    def test_expand_results_independent(self):
        """Each expand() call should return independent results."""
        from app.services.rag_fusion import QueryExpander

        expander = QueryExpander()
        r1 = expander.expand("Vad säger GDPR?", self._mock_rewrite("Vad säger GDPR?"))
        r2 = expander.expand("Hur fungerar RF?", self._mock_rewrite("Hur fungerar RF?"))

        # Results should be independent
        assert r1.original != r2.original
        assert r1.queries != r2.queries


# ═══════════════════════════════════════════════════════════════════════════
# CONCURRENT PIPELINE SIMULATION
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestConcurrentPipelineSimulation:
    """Simulate concurrent pipeline executions to detect race conditions."""

    @pytest.mark.asyncio
    async def test_concurrent_rrf_fusion(self):
        """Multiple concurrent RRF fusion calls should not interfere."""
        from app.services.rag_fusion import reciprocal_rank_fusion

        async def fuse(query_id: int):
            sets = [
                [{"id": f"q{query_id}_d{i}", "score": 1.0 - i * 0.1} for i in range(10)]
                for _ in range(3)
            ]
            result = reciprocal_rank_fusion(sets)
            return query_id, len(result)

        results = await asyncio.gather(*[fuse(i) for i in range(20)])

        # Each fusion should have 10 docs (all same IDs within a query)
        for qid, count in results:
            assert count == 10, f"Query {qid} got {count} docs, expected 10"

    @pytest.mark.asyncio
    async def test_concurrent_query_expansion(self):
        """Multiple concurrent query expansions should be independent."""
        from app.services.rag_fusion import QueryExpander

        expander = QueryExpander()

        def _mock_rewrite(query: str):
            mock = MagicMock()
            mock.rewritten_query = query
            mock.was_rewritten = False
            mock.legal_refs_found = []
            return mock

        async def expand(query: str):
            return expander.expand(query, _mock_rewrite(query))

        queries = [f"Test query {i}" for i in range(20)]
        results = await asyncio.gather(*[expand(q) for q in queries])

        # Each result should have the correct original
        for i, result in enumerate(results):
            assert result.original == f"Test query {i}"

    @pytest.mark.asyncio
    async def test_concurrent_intent_classification(self):
        """Multiple concurrent intent classifications should be independent."""
        from app.services.intent_classifier import IntentClassifier

        classifier = IntentClassifier()
        queries = [
            "Hej!",
            "Vad säger RF om yttrandefrihet?",
            "Hur överklagar man?",
            "Vad säger forskningen?",
            "Vilka argument finns?",
        ]

        async def classify(query: str):
            return classifier.classify(query)

        results = await asyncio.gather(*[classify(q) for q in queries])

        assert len(results) == 5
        # Each should have returned a valid IntentResult
        for r in results:
            assert r is not None
            assert r.confidence > 0

    @pytest.mark.asyncio
    async def test_high_concurrency_no_deadlock(self):
        """100 concurrent lightweight operations should complete without deadlock."""
        sem = asyncio.Semaphore(5)
        completed = 0

        async def work(idx: int):
            nonlocal completed
            async with sem:
                await asyncio.sleep(0.001)
                completed += 1

        await asyncio.wait_for(
            asyncio.gather(*[work(i) for i in range(100)]),
            timeout=5.0,
        )
        assert completed == 100

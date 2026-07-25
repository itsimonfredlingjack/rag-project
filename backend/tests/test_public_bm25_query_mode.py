"""AIS-153 BM25-only public query mode tests."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from starlette.requests import Request

from app.api.constitutional_routes import AgentQueryRequest, agent_query
from app.services.config_service import (
    PRIVATE_CORPUS_SCOPE,
    PRIVATE_LAB_PROFILE,
    PUBLIC_RIKSDAG_CORPUS_SCOPE,
    PUBLIC_RIKSDAG_PROFILE,
)
from app.services.guardrail_service import WardenStatus
from app.services.llm_service import StreamStats
from app.services.orchestrator_service import OrchestratorService
from app.services.query_processor_service import ResponseMode
from app.services.rag_models import RAGPipelineMetrics, RAGResult
from app.shared.public_corpus_manifest import SOURCE_ATTRIBUTION_TEXT
from app.shared.public_source_guard import PUBLIC_SOURCE, PUBLIC_SOURCE_SCOPE


class FakeBM25Service:
    def __init__(self, results: list[dict]) -> None:
        self.results = results
        self.calls: list[dict] = []

    def search(self, query: str, *, k: int, return_docs: bool, use_compound_splitting: bool):
        self.calls.append(
            {
                "query": query,
                "k": k,
                "return_docs": return_docs,
                "use_compound_splitting": use_compound_splitting,
            }
        )
        return self.results


class FakeLLMService:
    def __init__(self) -> None:
        self.messages: list[dict] | None = None
        self.config_override: dict | None = None

    async def chat_complete(self, messages, model=None, config_override=None):
        self.messages = messages
        self.config_override = config_override
        return "Det här är ett offentligt Riksdagssvar med källor.", StreamStats(
            tokens_generated=11,
            model_used="gemma4:e2b",
        )


class FakeGuardrail:
    def __init__(self) -> None:
        self.checked_queries: list[str] = []

    def check_query_safety(self, question: str) -> tuple[bool, str | None]:
        self.checked_queries.append(question)
        return True, None


class FakeRetrieval:
    def __init__(self) -> None:
        self.search_with_epr = AsyncMock()


def _public_config() -> SimpleNamespace:
    settings = SimpleNamespace(
        profile=PUBLIC_RIKSDAG_PROFILE,
        corpus_scope=PUBLIC_RIKSDAG_CORPUS_SCOPE,
        bm25_index_path="/tmp/public/bm25.db",
        bm25_enabled=True,
        chromadb_enabled=False,
        crag_enabled=False,
        reranking_enabled=False,
        evidence_refusal_template="Underlag saknas.",
    )
    return SimpleNamespace(
        profile=PUBLIC_RIKSDAG_PROFILE,
        corpus_scope=PUBLIC_RIKSDAG_CORPUS_SCOPE,
        bm25_index_path=settings.bm25_index_path,
        bm25_enabled=True,
        chromadb_enabled=False,
        settings=settings,
        critic_revise_effective_enabled=False,
        structured_output_effective_enabled=False,
    )


def _private_config() -> SimpleNamespace:
    settings = SimpleNamespace(
        profile=PRIVATE_LAB_PROFILE,
        corpus_scope=PRIVATE_CORPUS_SCOPE,
        crag_enabled=False,
        reranking_enabled=False,
        evidence_refusal_template="Underlag saknas.",
    )
    return SimpleNamespace(
        profile=PRIVATE_LAB_PROFILE,
        corpus_scope=PRIVATE_CORPUS_SCOPE,
        settings=settings,
        critic_revise_effective_enabled=False,
        structured_output_effective_enabled=False,
    )


def _public_row(
    idx: int,
    *,
    document_id: str | None = None,
    source: str = PUBLIC_SOURCE,
    source_scope: str = PUBLIC_SOURCE_SCOPE,
    text: str | None = None,
) -> dict:
    doc_id = document_id or f"H{idx:06d}"
    return {
        "id": f"{doc_id}-{idx}",
        "document_id": doc_id,
        "source": source,
        "source_scope": source_scope,
        "title": f"Riksdag document {doc_id}",
        "date": "2024-01-01",
        "url": f"https://data.riksdagen.se/dokument/{doc_id}",
        "text": text or f"Riksdagen behandlar offentlighetsprincipen i dokument {doc_id}.",
        "score": 10.0 - idx,
        "retriever_source": "bm25",
        "metadata": {
            "document_id": doc_id,
            "source": source,
            "source_scope": source_scope,
        },
    }


def _make_public_orchestrator(llm: FakeLLMService | None = None) -> OrchestratorService:
    return OrchestratorService(
        config=_public_config(),
        llm_service=llm or FakeLLMService(),
        query_processor=Mock(),
        guardrail=FakeGuardrail(),
        retrieval=FakeRetrieval(),
        reranker=Mock(),
        structured_output=Mock(),
        critic=Mock(),
        grader=Mock(),
        faithfulness=Mock(),
    )


def _make_request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/constitutional/agent/query",
            "headers": [],
            "query_string": b"",
            "root_path": "",
            "app": None,
            "client": ("127.0.0.1", 12345),
        }
    )


@pytest.fixture
def public_ready(monkeypatch):
    async def fake_readiness(orchestrator):
        return {
            "status": "degraded_but_usable",
            "can_answer": True,
            "profile": PUBLIC_RIKSDAG_PROFILE,
            "corpus_scope": PUBLIC_SOURCE_SCOPE,
        }

    monkeypatch.setattr(
        "app.services.orchestrator_service.build_dependency_readiness",
        fake_readiness,
        raising=False,
    )


@pytest.mark.asyncio
async def test_public_mode_uses_bm25_when_chroma_is_disabled(monkeypatch, public_ready) -> None:
    bm25 = FakeBM25Service([_public_row(1), _public_row(2)])
    monkeypatch.setattr(
        "app.services.public_bm25_query_service.get_bm25_service",
        lambda **kwargs: bm25,
    )
    orchestrator = _make_public_orchestrator()

    result = await orchestrator.process_query("  Offentlighetsprincipen?  ", mode="evidence")

    assert result.success is True
    assert result.metrics.retrieval_strategy == "public_bm25_only"
    assert len(bm25.calls) == 1
    assert bm25.calls[0]["query"] == "offentlighetsprincipen?"
    assert bm25.calls[0]["return_docs"] is True
    assert orchestrator.retrieval.search_with_epr.await_count == 0
    assert getattr(result, "retrieval_metadata")["mode"] == "public_bm25_only"


@pytest.mark.asyncio
async def test_public_mode_blocks_when_readiness_cannot_answer(monkeypatch) -> None:
    async def not_ready(orchestrator):
        return {"status": "not_ready", "can_answer": False}

    monkeypatch.setattr(
        "app.services.orchestrator_service.build_dependency_readiness",
        not_ready,
        raising=False,
    )
    bm25 = FakeBM25Service([_public_row(1)])
    monkeypatch.setattr(
        "app.services.public_bm25_query_service.get_bm25_service",
        lambda **kwargs: bm25,
    )

    result = await _make_public_orchestrator().process_query("Riksdagen?", mode="evidence")

    assert result.success is False
    assert result.sources == []
    assert getattr(result, "refusal_reason") == "readiness_not_answerable"
    assert bm25.calls == []


@pytest.mark.asyncio
async def test_public_sources_keep_public_provenance(monkeypatch, public_ready) -> None:
    monkeypatch.setattr(
        "app.services.public_bm25_query_service.get_bm25_service",
        lambda **kwargs: FakeBM25Service([_public_row(1), _public_row(2)]),
    )

    result = await _make_public_orchestrator().process_query("Riksdagen?", mode="evidence")

    assert result.sources
    assert all(source.source == PUBLIC_SOURCE for source in result.sources)
    assert all(source.source_scope == PUBLIC_SOURCE_SCOPE for source in result.sources)
    assert all(source.retriever == "bm25" for source in result.sources)


@pytest.mark.asyncio
async def test_bad_public_bm25_result_is_rejected_by_guard(monkeypatch, public_ready) -> None:
    monkeypatch.setattr(
        "app.services.public_bm25_query_service.get_bm25_service",
        lambda **kwargs: FakeBM25Service([_public_row(1, source="bm25")]),
    )

    with pytest.raises(ValueError, match="PUBLIC_SOURCE_GUARD"):
        await _make_public_orchestrator().process_query("Riksdagen?", mode="evidence")


@pytest.mark.asyncio
async def test_public_results_are_deduplicated_by_document_id(monkeypatch, public_ready) -> None:
    rows = [
        _public_row(1, document_id="H123456"),
        _public_row(2, document_id="H123456"),
        _public_row(3, document_id="H654321"),
    ]
    monkeypatch.setattr(
        "app.services.public_bm25_query_service.get_bm25_service",
        lambda **kwargs: FakeBM25Service(rows),
    )

    result = await _make_public_orchestrator().process_query("Riksdagen?", mode="evidence")

    document_ids = [getattr(source, "document_id") for source in result.sources]
    assert document_ids == ["H123456", "H654321"]
    assert getattr(result, "retrieval_metadata")["deduplicated_documents"] == 2


@pytest.mark.asyncio
async def test_public_context_is_capped_at_8_chunks(monkeypatch, public_ready) -> None:
    rows = [_public_row(idx) for idx in range(12)]
    monkeypatch.setattr(
        "app.services.public_bm25_query_service.get_bm25_service",
        lambda **kwargs: FakeBM25Service(rows),
    )

    result = await _make_public_orchestrator().process_query("Riksdagen?", mode="evidence")

    assert len(result.sources) == 8
    assert getattr(result, "retrieval_metadata")["chunks_used"] == 8


@pytest.mark.asyncio
async def test_public_response_includes_latency_metadata(monkeypatch, public_ready) -> None:
    monkeypatch.setattr(
        "app.services.public_bm25_query_service.get_bm25_service",
        lambda **kwargs: FakeBM25Service([_public_row(1)]),
    )
    orchestrator = _make_public_orchestrator()

    response = await agent_query(
        _make_request(),
        AgentQueryRequest(question="Vad sa riksdagen?", mode="evidence"),
        x_retrieval_strategy=None,
        orchestrator=orchestrator,
    )
    payload = response.model_dump()

    assert payload["latency_ms"] >= 0
    assert payload["retrieval"]["mode"] == "public_bm25_only"
    assert payload["retrieval"]["chunks_used"] == 1
    assert payload["sources"][0]["document_id"] == "H000001"
    assert payload["sources"][0]["source_scope"] == PUBLIC_SOURCE_SCOPE
    assert payload["sources"][0]["retriever_source"] == "bm25"


@pytest.mark.asyncio
async def test_private_lab_query_path_is_not_routed_to_public_bm25(monkeypatch) -> None:
    bm25 = FakeBM25Service([_public_row(1)])
    monkeypatch.setattr(
        "app.services.public_bm25_query_service.get_bm25_service",
        lambda **kwargs: bm25,
    )
    result = RAGResult(
        answer="Privat labbsvar",
        sources=[],
        reasoning_steps=[],
        metrics=RAGPipelineMetrics(retrieval_strategy="parallel_v1"),
        mode=ResponseMode.ASSIST,
        guardrail_status=WardenStatus.UNCHANGED,
        evidence_level="NONE",
    )

    class PrivateOrchestrator(OrchestratorService):
        async def _process_chat_mode(self, question, start_time, reasoning_steps):
            return result

    query_processor = Mock()
    query_processor.classify_query.return_value = SimpleNamespace(
        mode=ResponseMode.CHAT,
        reason="unit test",
    )
    orchestrator = PrivateOrchestrator(
        config=_private_config(),
        llm_service=FakeLLMService(),
        query_processor=query_processor,
        guardrail=FakeGuardrail(),
        retrieval=FakeRetrieval(),
        reranker=Mock(),
        structured_output=Mock(),
        critic=Mock(),
        grader=Mock(),
        faithfulness=Mock(),
    )

    actual = await orchestrator.process_query("Hej", mode="auto")

    assert actual.answer == "Privat labbsvar"
    assert bm25.calls == []


@pytest.mark.asyncio
async def test_public_initialize_does_not_require_chroma() -> None:
    orchestrator = _make_public_orchestrator()
    orchestrator.llm_service.initialize = AsyncMock()
    orchestrator.query_processor.initialize = AsyncMock()
    orchestrator.guardrail.initialize = AsyncMock()
    orchestrator.retrieval.initialize = AsyncMock(side_effect=AssertionError("Chroma used"))
    orchestrator.reranker.initialize = AsyncMock()
    orchestrator.structured_output.initialize = AsyncMock()
    orchestrator.critic.initialize = AsyncMock()
    orchestrator.grader.initialize = AsyncMock()

    await orchestrator.initialize()

    assert orchestrator.retrieval.initialize.await_count == 0


@pytest.mark.asyncio
async def test_public_answer_includes_source_ids_and_citation_metadata(
    monkeypatch,
    public_ready,
) -> None:
    monkeypatch.setattr(
        "app.services.public_bm25_query_service.get_bm25_service",
        lambda **kwargs: FakeBM25Service([_public_row(1)]),
    )

    result = await _make_public_orchestrator().process_query(
        "Vad säger riksdagsdokument om offentlighetsprincipen?",
        mode="evidence",
    )

    assert result.success is True
    assert "H000001" in result.answer
    assert result.citations
    assert result.citations[0].source_id == "H000001"
    assert result.citations[0].source_collection == PUBLIC_SOURCE_SCOPE
    assert getattr(result, "data_source_attribution") == SOURCE_ATTRIBUTION_TEXT


@pytest.mark.asyncio
async def test_public_api_response_includes_data_source_attribution(
    monkeypatch,
    public_ready,
) -> None:
    monkeypatch.setattr(
        "app.services.public_bm25_query_service.get_bm25_service",
        lambda **kwargs: FakeBM25Service([_public_row(1)]),
    )

    response = await agent_query(
        _make_request(),
        AgentQueryRequest(question="Vad säger riksdagsdokument?", mode="evidence"),
        x_retrieval_strategy=None,
        orchestrator=_make_public_orchestrator(),
    )
    payload = response.model_dump()

    assert payload["data_source_attribution"] == SOURCE_ATTRIBUTION_TEXT
    assert payload["citations"][0]["source_id"] == "H000001"
    assert payload.get("refusal_reason") is None


@pytest.mark.asyncio
async def test_public_no_bm25_hits_refuses_with_no_context(monkeypatch, public_ready) -> None:
    monkeypatch.setattr(
        "app.services.public_bm25_query_service.get_bm25_service",
        lambda **kwargs: FakeBM25Service([]),
    )

    result = await _make_public_orchestrator().process_query(
        "Vad säger riksdagsdokument om sak som saknas?",
        mode="evidence",
    )

    assert result.success is False
    assert result.sources == []
    assert getattr(result, "refusal_reason") == "no_context"
    assert getattr(result, "data_source_attribution") == SOURCE_ATTRIBUTION_TEXT


@pytest.mark.asyncio
async def test_public_weak_context_refuses_with_weak_context(monkeypatch, public_ready) -> None:
    monkeypatch.setattr(
        "app.services.public_bm25_query_service.get_bm25_service",
        lambda **kwargs: FakeBM25Service([_public_row(1, text="kort")]),
    )

    result = await _make_public_orchestrator().process_query(
        "Sammanfatta propositionen om offentlighetsprincipen utifrån källorna.",
        mode="evidence",
    )

    assert result.success is False
    assert result.sources == []
    assert result.refusal_reason == "weak_context"


@pytest.mark.asyncio
async def test_public_legal_advice_question_refuses_without_search(
    monkeypatch, public_ready
) -> None:
    bm25 = FakeBM25Service([_public_row(1)])
    monkeypatch.setattr(
        "app.services.public_bm25_query_service.get_bm25_service",
        lambda **kwargs: bm25,
    )

    result = await _make_public_orchestrator().process_query(
        "Kan jag stämma kommunen och vad ska jag göra juridiskt?",
        mode="evidence",
    )

    assert result.success is False
    assert result.refusal_reason == "legal_advice"
    assert bm25.calls == []


@pytest.mark.asyncio
async def test_public_source_boundary_question_refuses_without_search(
    monkeypatch,
    public_ready,
) -> None:
    bm25 = FakeBM25Service([_public_row(1)])
    monkeypatch.setattr(
        "app.services.public_bm25_query_service.get_bm25_service",
        lambda **kwargs: bm25,
    )

    result = await _make_public_orchestrator().process_query(
        "Sök i DiVA och privata PDF:er om offentlighetsprincipen.",
        mode="evidence",
    )

    assert result.success is False
    assert result.refusal_reason == "source_boundary"
    assert bm25.calls == []


@pytest.mark.asyncio
async def test_public_stream_emits_answer_contract_metadata(monkeypatch, public_ready) -> None:
    monkeypatch.setattr(
        "app.services.public_bm25_query_service.get_bm25_service",
        lambda **kwargs: FakeBM25Service([_public_row(1), _public_row(2)]),
    )

    events = []
    async for raw_event in _make_public_orchestrator().stream_query(
        "Vad säger Riksdagen om offentlighetsprincipen?",
        mode="evidence",
    ):
        payload = raw_event.removeprefix("data: ").strip()
        events.append(json.loads(payload))

    metadata = next(event for event in events if event["type"] == "metadata")
    done = next(event for event in events if event["type"] == "done")

    assert metadata["mode"] == "public_bm25_only"
    assert metadata["data_source_attribution"] == SOURCE_ATTRIBUTION_TEXT
    assert metadata["retrieval"]["mode"] == "public_bm25_only"
    assert metadata["citations"][0]["source_id"] == "H000001"
    assert metadata["sources"][0]["source"] == PUBLIC_SOURCE
    assert metadata["sources"][0]["source_scope"] == PUBLIC_SOURCE_SCOPE
    assert metadata["sources"][0]["retriever_source"] == "bm25"
    assert metadata["sources"][0]["document_id"] == "H000001"
    assert metadata["sources"][0]["url"].startswith("https://data.riksdagen.se/")
    assert done["total_time_ms"] >= 0


@pytest.mark.asyncio
async def test_public_stream_emits_refusal_reason(monkeypatch) -> None:
    async def not_ready(orchestrator):
        return {"status": "not_ready", "can_answer": False}

    monkeypatch.setattr(
        "app.services.orchestrator_service.build_dependency_readiness",
        not_ready,
        raising=False,
    )

    events = []
    async for raw_event in _make_public_orchestrator().stream_query(
        "Vad säger Riksdagen?",
        mode="evidence",
    ):
        payload = raw_event.removeprefix("data: ").strip()
        events.append(json.loads(payload))

    metadata = next(event for event in events if event["type"] == "metadata")

    assert metadata["mode"] == "public_bm25_only"
    assert metadata["refusal_reason"] == "readiness_not_answerable"
    assert metadata["sources"] == []
    assert metadata["data_source_attribution"] == SOURCE_ATTRIBUTION_TEXT

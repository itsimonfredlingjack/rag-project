"""AIS-151 guard coverage for public retrieval/context/API boundaries."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.chatgpt_app.adapters import build_query_tool_payload
from app.services.bm25_service import BM25Service
from app.services.prompt_service import build_llm_context
from app.services.rag_fusion import hybrid_reciprocal_rank_fusion
from app.services.rag_models import RAGPipelineMetrics, RAGResult
from app.services.query_processor_service import ResponseMode
from app.services.retrieval_service import SearchResult
from app.shared.public_source_guard import (
    PUBLIC_SOURCE,
    PUBLIC_SOURCE_SCOPE,
    PublicSourceGuardError,
)


def _write_public_schema_bm25_db(
    db_path: Path,
    *,
    source: str = PUBLIC_SOURCE,
    source_scope: str = PUBLIC_SOURCE_SCOPE,
    text: str = "Riksdagen behandlar offentlighetsprincipen.",
) -> None:
    conn = sqlite3.connect(str(db_path))
    conn.execute("""
        CREATE TABLE documents (
            id TEXT PRIMARY KEY,
            document_id TEXT NOT NULL,
            source TEXT NOT NULL,
            source_scope TEXT NOT NULL,
            title TEXT NOT NULL,
            date TEXT NOT NULL,
            url TEXT NOT NULL,
            text TEXT NOT NULL,
            metadata_json TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE VIRTUAL TABLE docs_fts USING fts5(
            doc_id UNINDEXED,
            content,
            tokenize='unicode61 remove_diacritics 2',
            detail='column'
        )
    """)
    conn.execute(
        """
        INSERT INTO documents(
            id, document_id, source, source_scope, title, date, url, text, metadata_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "H803222",
            "H803222",
            source,
            source_scope,
            "Riksdagen testar offentlighetsprincipen",
            "2021-09-13",
            "https://data.riksdagen.se/dokument/H803222",
            text,
            f'{{"source":"{source}","source_scope":"{source_scope}"}}',
        ),
    )
    conn.execute("INSERT INTO docs_fts(doc_id, content) VALUES (?, ?)", ("H803222", text))
    conn.commit()
    conn.close()


def _search_result(
    *,
    source: str = PUBLIC_SOURCE,
    source_scope: str | None = PUBLIC_SOURCE_SCOPE,
    snippet: str = "Riksdagen behandlar offentlighetsprincipen.",
) -> SearchResult:
    return SearchResult(
        id="H803222",
        title="Riksdagen testar offentlighetsprincipen",
        snippet=snippet,
        score=0.9,
        source=source,
        source_scope=source_scope,
        doc_type="prop",
        date="2021-09-13",
        retriever="bm25",
    )


def test_public_bm25_result_passes_guard(tmp_path: Path) -> None:
    db_path = tmp_path / "bm25.db"
    _write_public_schema_bm25_db(db_path)
    service = BM25Service(index_path=str(db_path), public_guard_enabled=True)

    results = service.search("offentlighetsprincipen", k=1, return_docs=True)

    assert results[0]["source"] == PUBLIC_SOURCE
    assert results[0]["source_scope"] == PUBLIC_SOURCE_SCOPE
    assert results[0]["retriever_source"] == "bm25"


def test_public_bm25_result_with_source_bm25_fails(tmp_path: Path) -> None:
    db_path = tmp_path / "bm25.db"
    _write_public_schema_bm25_db(db_path, source="bm25")
    service = BM25Service(index_path=str(db_path), public_guard_enabled=True)

    with pytest.raises(PublicSourceGuardError, match="FORBIDDEN_SOURCE"):
        service.search("offentlighetsprincipen", k=1, return_docs=True)


def test_public_bm25_result_with_missing_source_scope_fails(tmp_path: Path) -> None:
    db_path = tmp_path / "bm25.db"
    _write_public_schema_bm25_db(db_path, source_scope="")
    service = BM25Service(index_path=str(db_path), public_guard_enabled=True)

    with pytest.raises(PublicSourceGuardError, match="INVALID_SCOPE"):
        service.search("offentlighetsprincipen", k=1, return_docs=True)


def test_public_bm25_result_with_private_scope_fails(tmp_path: Path) -> None:
    db_path = tmp_path / "bm25.db"
    _write_public_schema_bm25_db(db_path, source_scope="mixed_recovered_corpus")
    service = BM25Service(index_path=str(db_path), public_guard_enabled=True)

    with pytest.raises(PublicSourceGuardError, match="INVALID_SCOPE"):
        service.search("offentlighetsprincipen", k=1, return_docs=True)


def test_public_bm25_result_with_forbidden_marker_fails(tmp_path: Path) -> None:
    db_path = tmp_path / "bm25.db"
    _write_public_schema_bm25_db(
        db_path,
        text="Riksdagen behandlar offentlighetsprincipen men innehåller FULLTEXT.",
    )
    service = BM25Service(index_path=str(db_path), public_guard_enabled=True)

    with pytest.raises(PublicSourceGuardError, match="FORBIDDEN_MARKER"):
        service.search("offentlighetsprincipen", k=1, return_docs=True)


def test_private_lab_bm25_mode_does_not_use_public_guard(tmp_path: Path) -> None:
    db_path = tmp_path / "bm25.db"
    _write_public_schema_bm25_db(db_path, source="bm25", source_scope="")
    service = BM25Service(index_path=str(db_path), public_guard_enabled=False)

    results = service.search("offentlighetsprincipen", k=1, return_docs=True)

    assert results[0]["source"] == "bm25"


def test_public_retrieval_aggregation_rejects_bad_record() -> None:
    with pytest.raises(PublicSourceGuardError, match="FORBIDDEN_SOURCE"):
        hybrid_reciprocal_rank_fusion(
            dense_result_sets=[],
            bm25_results=[
                {
                    "id": "H803222",
                    "source": "bm25",
                    "source_scope": PUBLIC_SOURCE_SCOPE,
                    "text": "Riksdagen behandlar offentlighetsprincipen.",
                }
            ],
            public_guard_enabled=True,
        )


def test_context_assembly_rejects_bad_public_record() -> None:
    with pytest.raises(PublicSourceGuardError, match="INVALID_SCOPE"):
        build_llm_context(
            [_search_result(source_scope="mixed_recovered_corpus")],
            public_guard_enabled=True,
        )


def test_api_serialization_rejects_bad_public_record() -> None:
    result = RAGResult(
        answer="Svar",
        sources=[_search_result(source="bm25")],
        reasoning_steps=[],
        metrics=RAGPipelineMetrics(),
        mode=ResponseMode.EVIDENCE,
        guardrail_status=SimpleNamespace(value="unchanged"),
        evidence_level="HIGH",
        citations=[],
        success=True,
    )

    with pytest.raises(PublicSourceGuardError, match="FORBIDDEN_SOURCE"):
        build_query_tool_payload(result, public_guard_enabled=True)

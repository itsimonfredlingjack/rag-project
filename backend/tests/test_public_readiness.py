"""AIS-152 public readiness truth-layer tests."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.config_service import (
    PRIVATE_CORPUS_SCOPE,
    PRIVATE_LAB_PROFILE,
    PUBLIC_RIKSDAG_CORPUS_SCOPE,
    PUBLIC_RIKSDAG_PROFILE,
)
from app.services.readiness_service import build_dependency_readiness
from app.shared.public_corpus_manifest import (
    PUBLIC_CHROMA_COLLECTION,
    PUBLIC_EMBEDDING_MODEL,
    SOURCE_ATTRIBUTION_TEXT,
)
from app.shared.public_source_guard import PUBLIC_SOURCE, PUBLIC_SOURCE_SCOPE


def _public_config(public_root: Path) -> SimpleNamespace:
    return SimpleNamespace(
        profile=PUBLIC_RIKSDAG_PROFILE,
        corpus_scope=PUBLIC_RIKSDAG_CORPUS_SCOPE,
        bm25_enabled=True,
        bm25_index_path=str(public_root / "bm25_fts5" / "bm25.db"),
        chromadb_enabled=False,
        chromadb_path=str(public_root / "chromadb"),
        constitutional_model="gemma4:e2b",
        constitutional_fallback="gemma4:e2b",
        effective_default_collections=["riksdag_documents_p1_jina_v3_1024"],
        settings=SimpleNamespace(
            profile=PUBLIC_RIKSDAG_PROFILE,
            corpus_scope=PUBLIC_RIKSDAG_CORPUS_SCOPE,
            bm25_enabled=True,
            bm25_index_path=str(public_root / "bm25_fts5" / "bm25.db"),
            chromadb_enabled=False,
            chromadb_path=str(public_root / "chromadb"),
            constitutional_model="gemma4:e2b",
            constitutional_fallback="gemma4:e2b",
        ),
    )


def _llm_service(
    *,
    healthy: bool = True,
    models: list[str] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        health_check=AsyncMock(return_value=healthy),
        list_models=AsyncMock(return_value=models or ["gemma4:e2b"]),
    )


def _orchestrator(
    config: SimpleNamespace,
    *,
    llm_service: SimpleNamespace | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(config=config, llm_service=llm_service or _llm_service())


def _write_manifest_and_checkpoint(
    public_root: Path, *, source_scope: str = PUBLIC_SOURCE_SCOPE
) -> None:
    public_root.mkdir(parents=True, exist_ok=True)
    docs_path = public_root / "docs.jsonl"
    docs_path.write_text("{}", encoding="utf-8")
    bm25_path = public_root / "bm25_fts5" / "bm25.db"
    manifest = {
        "manifest_version": 1,
        "profile": PUBLIC_RIKSDAG_PROFILE,
        "source_scope": source_scope,
        "allowed_sources": [PUBLIC_SOURCE],
        "forbidden_sources": [
            "diva",
            "private_pdf",
            "mixed_recovered_corpus",
            "government_non_riksdag",
        ],
        "requires_source_attribution": True,
        "source_attribution_text": SOURCE_ATTRIBUTION_TEXT,
        "created_at": "2026-05-29T00:00:00+00:00",
        "output_path": str(docs_path),
        "document_count": 2,
        "chunk_count": 2,
        "bm25_path": str(bm25_path),
        "chroma_collection": PUBLIC_CHROMA_COLLECTION,
        "embedding_model": PUBLIC_EMBEDDING_MODEL,
    }
    checkpoint = {
        "checkpoint_version": 1,
        "profile": PUBLIC_RIKSDAG_PROFILE,
        "source_scope": PUBLIC_SOURCE_SCOPE,
        "input_path": "/tmp/recovered/docs.jsonl",
        "output_path": str(docs_path),
        "start_row": 1,
        "end_row": 2,
        "row_bounds": {"start_row": 1, "end_row": 2},
        "scanned_rows": 2,
        "kept_rows": 2,
        "skipped_non_riksdag_rows": 0,
        "forbidden_marker_scan": {"status": "clean", "hits": 0},
    }
    (public_root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (public_root / "docs.checkpoint.json").write_text(
        json.dumps(checkpoint),
        encoding="utf-8",
    )


def _write_bm25_db(
    public_root: Path,
    *,
    rows: int = 2,
    source: str = PUBLIC_SOURCE,
    source_scope: str = PUBLIC_SOURCE_SCOPE,
) -> None:
    db_path = public_root / "bm25_fts5" / "bm25.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
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
        for idx in range(rows):
            doc_id = f"H{idx:06d}"
            text = f"Riksdagen offentlighetsprincipen {idx}"
            conn.execute(
                """
                INSERT INTO documents(
                    id, document_id, source, source_scope, title, date, url, text, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    doc_id,
                    doc_id,
                    source,
                    source_scope,
                    f"Title {idx}",
                    "2021-09-13",
                    f"https://data.riksdagen.se/dokument/{doc_id}",
                    text,
                    json.dumps({"source": source, "source_scope": source_scope}),
                ),
            )
            conn.execute("INSERT INTO docs_fts(doc_id, content) VALUES (?, ?)", (doc_id, text))


@pytest.mark.asyncio
async def test_valid_public_bm25_manifest_and_chroma_disabled_is_degraded_but_usable(
    tmp_path: Path,
) -> None:
    public_root = tmp_path / "public" / "riksdag"
    _write_manifest_and_checkpoint(public_root)
    _write_bm25_db(public_root)

    readiness = await build_dependency_readiness(_orchestrator(_public_config(public_root)))

    assert readiness["status"] == "degraded_but_usable"
    assert readiness["can_answer"] is True
    assert readiness["profile"] == PUBLIC_RIKSDAG_PROFILE
    assert readiness["corpus_scope"] == PUBLIC_RIKSDAG_CORPUS_SCOPE
    assert readiness["manifest"]["status"] == "ready"
    assert readiness["manifest"]["document_count"] == 2
    assert readiness["manifest"]["source_scope"] == PUBLIC_SOURCE_SCOPE
    assert readiness["bm25"]["status"] == "ready"
    assert readiness["bm25"]["documents_count"] == 2
    assert readiness["bm25"]["fts_count"] == 2
    assert readiness["bm25"]["provenance_status"] == "clean"
    assert readiness["chroma"] == {"enabled": False, "status": "disabled"}


@pytest.mark.asyncio
async def test_missing_public_bm25_blocks_answering(tmp_path: Path) -> None:
    public_root = tmp_path / "public" / "riksdag"
    _write_manifest_and_checkpoint(public_root)

    readiness = await build_dependency_readiness(_orchestrator(_public_config(public_root)))

    assert readiness["status"] == "not_ready"
    assert readiness["can_answer"] is False
    assert readiness["bm25"]["status"] == "missing"


@pytest.mark.asyncio
async def test_public_readiness_requires_llm_model_available(tmp_path: Path) -> None:
    public_root = tmp_path / "public" / "riksdag"
    _write_manifest_and_checkpoint(public_root)
    _write_bm25_db(public_root)
    llm_service = _llm_service(healthy=True, models=["gemma3:4b"])

    readiness = await build_dependency_readiness(
        _orchestrator(_public_config(public_root), llm_service=llm_service)
    )

    assert readiness["status"] == "not_ready"
    assert readiness["can_answer"] is False
    assert readiness["checks"]["llm_service"]["status"] == "error"
    assert readiness["checks"]["llm_service"]["details"]["primary_available"] is False


@pytest.mark.asyncio
async def test_public_readiness_requires_llm_service_health(tmp_path: Path) -> None:
    public_root = tmp_path / "public" / "riksdag"
    _write_manifest_and_checkpoint(public_root)
    _write_bm25_db(public_root)
    llm_service = _llm_service(healthy=False, models=["gemma4:e2b"])

    readiness = await build_dependency_readiness(
        _orchestrator(_public_config(public_root), llm_service=llm_service)
    )

    assert readiness["status"] == "not_ready"
    assert readiness["can_answer"] is False
    assert readiness["checks"]["llm_service"]["status"] == "error"


@pytest.mark.asyncio
async def test_public_bm25_sqlite_cannot_open_blocks_answering(tmp_path: Path) -> None:
    public_root = tmp_path / "public" / "riksdag"
    _write_manifest_and_checkpoint(public_root)
    bm25_path = public_root / "bm25_fts5" / "bm25.db"
    bm25_path.parent.mkdir(parents=True)
    bm25_path.write_text("not sqlite", encoding="utf-8")

    readiness = await build_dependency_readiness(_orchestrator(_public_config(public_root)))

    assert readiness["status"] == "not_ready"
    assert readiness["can_answer"] is False
    assert readiness["bm25"]["status"] == "error"


@pytest.mark.asyncio
async def test_public_bm25_zero_rows_blocks_answering(tmp_path: Path) -> None:
    public_root = tmp_path / "public" / "riksdag"
    _write_manifest_and_checkpoint(public_root)
    _write_bm25_db(public_root, rows=0)

    readiness = await build_dependency_readiness(_orchestrator(_public_config(public_root)))

    assert readiness["status"] == "not_ready"
    assert readiness["can_answer"] is False
    assert readiness["bm25"]["status"] == "empty"


@pytest.mark.asyncio
async def test_missing_public_manifest_blocks_answering(tmp_path: Path) -> None:
    public_root = tmp_path / "public" / "riksdag"
    _write_bm25_db(public_root)

    readiness = await build_dependency_readiness(_orchestrator(_public_config(public_root)))

    assert readiness["status"] == "not_ready"
    assert readiness["can_answer"] is False
    assert readiness["manifest"]["status"] == "missing"


@pytest.mark.asyncio
async def test_public_manifest_wrong_source_scope_blocks_answering(tmp_path: Path) -> None:
    public_root = tmp_path / "public" / "riksdag"
    _write_manifest_and_checkpoint(public_root, source_scope="mixed_recovered_corpus")
    _write_bm25_db(public_root)

    readiness = await build_dependency_readiness(_orchestrator(_public_config(public_root)))

    assert readiness["status"] == "not_ready"
    assert readiness["can_answer"] is False
    assert readiness["manifest"]["status"] == "invalid"


@pytest.mark.asyncio
async def test_public_bm25_non_public_provenance_blocks_answering(tmp_path: Path) -> None:
    public_root = tmp_path / "public" / "riksdag"
    _write_manifest_and_checkpoint(public_root)
    _write_bm25_db(public_root, source="bm25", source_scope=PUBLIC_SOURCE_SCOPE)

    readiness = await build_dependency_readiness(_orchestrator(_public_config(public_root)))

    assert readiness["status"] == "not_ready"
    assert readiness["can_answer"] is False
    assert readiness["bm25"]["status"] == "invalid"
    assert readiness["bm25"]["provenance_status"] == "dirty"


@pytest.mark.asyncio
async def test_private_lab_readiness_stays_on_generic_path() -> None:
    orchestrator = SimpleNamespace(
        config=SimpleNamespace(
            profile=PRIVATE_LAB_PROFILE,
            corpus_scope=PRIVATE_CORPUS_SCOPE,
            bm25_enabled=False,
            settings=SimpleNamespace(
                profile=PRIVATE_LAB_PROFILE,
                constitutional_model="gemma4:e2b",
                constitutional_fallback="gemma4:e2b",
            ),
            effective_default_collections=[],
            embedding_model="jinaai/jina-embeddings-v3",
            expected_embedding_dim=1024,
        ),
        retrieval=None,
        llm_service=None,
    )

    readiness = await build_dependency_readiness(orchestrator)

    assert readiness["status"] == "not_ready"
    assert readiness["can_answer"] is False
    assert "checks" in readiness
    assert readiness["profile"] == PRIVATE_LAB_PROFILE

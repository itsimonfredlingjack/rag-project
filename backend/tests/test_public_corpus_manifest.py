"""Tests for the public corpus manifest/checkpoint contract."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.shared.public_corpus_manifest import (
    EXPECTED_FORBIDDEN_SOURCES,
    PUBLIC_PROFILE,
    PUBLIC_SOURCE_SCOPE,
    PublicCorpusManifestError,
    load_checkpoint,
    load_manifest,
    validate_public_checkpoint,
    validate_public_manifest,
)


def _valid_manifest() -> dict:
    return {
        "manifest_version": 1,
        "profile": PUBLIC_PROFILE,
        "source_scope": PUBLIC_SOURCE_SCOPE,
        "allowed_sources": ["riksdagen"],
        "forbidden_sources": list(EXPECTED_FORBIDDEN_SOURCES),
        "requires_source_attribution": True,
        "source_attribution_text": "Data source: Sveriges riksdag / Riksdagens öppna data",
        "document_count": 230143,
        "chunk_count": 230143,
        "bm25_path": "/home/ai-server2/rag/local-data-public/riksdag/bm25_fts5/bm25.db",
        "chroma_collection": "riksdag_documents_p1_jina_v3_1024",
        "embedding_model": "jinaai/jina-embeddings-v3",
        "created_at": "2026-05-29T00:00:00+00:00",
        "output_path": "/home/ai-server2/rag/local-data-public/riksdag/docs.jsonl",
    }


def _valid_checkpoint() -> dict:
    return {
        "checkpoint_version": 1,
        "profile": PUBLIC_PROFILE,
        "source_scope": PUBLIC_SOURCE_SCOPE,
        "input_path": "/home/ai-server2/rag/RAG_TRANSFER/source/docs.jsonl",
        "output_path": "/home/ai-server2/rag/local-data-public/riksdag/docs.jsonl",
        "start_row": 7842,
        "end_row": 237984,
        "row_bounds": {"start_row": 7842, "end_row": 237984},
        "scanned_rows": 230143,
        "kept_rows": 230143,
        "skipped_non_riksdag_rows": 0,
        "forbidden_marker_scan": {"status": "clean", "hits": 0},
    }


def test_load_manifest_and_validate_valid_manifest(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(_valid_manifest()), encoding="utf-8")

    manifest = load_manifest(path)

    assert validate_public_manifest(manifest, PUBLIC_PROFILE, PUBLIC_SOURCE_SCOPE) == manifest


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("profile", "private-swedish-legal-lab", "profile"),
        ("source_scope", "mixed_recovered_corpus", "source_scope"),
        ("requires_source_attribution", False, "requires_source_attribution"),
        ("allowed_sources", ["riksdagen", "diva"], "allowed_sources"),
    ],
)
def test_validate_public_manifest_rejects_wrong_core_fields(
    field: str,
    value,
    expected: str,
) -> None:
    manifest = _valid_manifest()
    manifest[field] = value

    with pytest.raises(PublicCorpusManifestError, match=expected):
        validate_public_manifest(manifest, PUBLIC_PROFILE, PUBLIC_SOURCE_SCOPE)


def test_validate_public_manifest_rejects_missing_attribution_text() -> None:
    manifest = _valid_manifest()
    manifest.pop("source_attribution_text")

    with pytest.raises(PublicCorpusManifestError, match="source_attribution_text"):
        validate_public_manifest(manifest, PUBLIC_PROFILE, PUBLIC_SOURCE_SCOPE)


def test_validate_public_manifest_rejects_missing_forbidden_sources() -> None:
    manifest = _valid_manifest()
    manifest["forbidden_sources"] = ["diva"]

    with pytest.raises(PublicCorpusManifestError, match="forbidden_sources"):
        validate_public_manifest(manifest, PUBLIC_PROFILE, PUBLIC_SOURCE_SCOPE)


def test_load_checkpoint_and_validate_valid_checkpoint(tmp_path: Path) -> None:
    path = tmp_path / "docs.checkpoint.json"
    path.write_text(json.dumps(_valid_checkpoint()), encoding="utf-8")

    checkpoint = load_checkpoint(path)

    assert validate_public_checkpoint(checkpoint) == checkpoint


def test_validate_public_checkpoint_rejects_row_bounds_mismatch() -> None:
    checkpoint = _valid_checkpoint()
    checkpoint["row_bounds"] = {"start_row": 1, "end_row": 237984}

    with pytest.raises(PublicCorpusManifestError, match="row_bounds"):
        validate_public_checkpoint(checkpoint)


def test_validate_public_checkpoint_rejects_count_mismatch() -> None:
    checkpoint = _valid_checkpoint()
    checkpoint["scanned_rows"] = 230144

    with pytest.raises(PublicCorpusManifestError, match="count"):
        validate_public_checkpoint(checkpoint)


def test_validate_public_checkpoint_rejects_dirty_forbidden_scan() -> None:
    checkpoint = _valid_checkpoint()
    checkpoint["forbidden_marker_scan"] = {"status": "dirty", "hits": 1}

    with pytest.raises(PublicCorpusManifestError, match="forbidden_marker_scan"):
        validate_public_checkpoint(checkpoint)

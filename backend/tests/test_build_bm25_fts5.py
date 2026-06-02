"""Tests for the public Riksdagen BM25 FTS5 builder."""

from __future__ import annotations

import importlib.util
import json
import sqlite3
from pathlib import Path

import pytest

from app.shared.public_corpus_manifest import (
    PUBLIC_BM25_PATH,
    PUBLIC_CHROMA_COLLECTION,
    PUBLIC_EMBEDDING_MODEL,
    PUBLIC_PROFILE,
    SOURCE_ATTRIBUTION_TEXT,
)
from app.shared.public_source_guard import PUBLIC_SOURCE, PUBLIC_SOURCE_SCOPE


def _load_builder():
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "build_bm25_fts5.py"
    spec = importlib.util.spec_from_file_location("build_bm25_fts5", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _public_root(tmp_path: Path) -> Path:
    root = tmp_path / "local-data-public" / "riksdag"
    root.mkdir(parents=True)
    return root


def _public_row(doc_id: str, text: str = "Riksdagen behandlar offentlighetsprincipen") -> dict:
    return {
        "id": doc_id,
        "document_id": doc_id,
        "source": PUBLIC_SOURCE,
        "source_scope": PUBLIC_SOURCE_SCOPE,
        "title": f"Title {doc_id}",
        "date": "2021-09-13",
        "url": f"https://data.riksdagen.se/dokument/{doc_id}",
        "text": text,
        "metadata": {
            "document_id": doc_id,
            "source": PUBLIC_SOURCE,
            "source_scope": PUBLIC_SOURCE_SCOPE,
            "title": f"Title {doc_id}",
            "date": "2021-09-13",
            "url": f"https://data.riksdagen.se/dokument/{doc_id}",
        },
    }


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _write_manifest_and_checkpoint(public_root: Path, docs_path: Path, row_count: int) -> None:
    manifest = {
        "manifest_version": 1,
        "profile": PUBLIC_PROFILE,
        "corpus_scope": PUBLIC_SOURCE_SCOPE,
        "source_scope": PUBLIC_SOURCE_SCOPE,
        "source": PUBLIC_SOURCE,
        "allowed_sources": [PUBLIC_SOURCE],
        "forbidden_sources": [
            "diva",
            "private_pdf",
            "mixed_recovered_corpus",
            "government_non_riksdag",
        ],
        "requires_source_attribution": True,
        "source_attribution_text": SOURCE_ATTRIBUTION_TEXT,
        "input_path": str(docs_path),
        "output_path": str(docs_path),
        "output_rows": row_count,
        "document_count": row_count,
        "chunk_count": row_count,
        "bm25_path": str(public_root / "bm25_fts5" / "bm25.db"),
        "chroma_collection": PUBLIC_CHROMA_COLLECTION,
        "embedding_model": PUBLIC_EMBEDDING_MODEL,
        "created_at": "2026-05-29T00:00:00+00:00",
    }
    checkpoint = {
        "checkpoint_version": 1,
        "profile": PUBLIC_PROFILE,
        "corpus_scope": PUBLIC_SOURCE_SCOPE,
        "source_scope": PUBLIC_SOURCE_SCOPE,
        "input_path": "/tmp/recovered/docs.jsonl",
        "output_path": str(docs_path),
        "start_row": 1,
        "end_row": row_count,
        "row_bounds": {"start_row": 1, "end_row": row_count},
        "scanned_rows": row_count,
        "kept_rows": row_count,
        "skipped_non_riksdag_rows": 0,
        "forbidden_marker_scan": {"status": "clean", "hits": 0},
    }
    (public_root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    (public_root / "docs.checkpoint.json").write_text(
        json.dumps(checkpoint, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )


def test_valid_public_jsonl_builds_public_bm25_db(tmp_path: Path) -> None:
    builder = _load_builder()
    public_root = _public_root(tmp_path)
    docs_path = public_root / "docs.jsonl"
    output_path = public_root / "bm25_fts5" / "bm25.db"
    rows = [
        _public_row("H803222", "Offentlighetsprincipen behandlas i riksdagen"),
        _public_row("H803224", "Personuppgifter och Schengens informationssystem"),
    ]
    _write_jsonl(docs_path, rows)
    _write_manifest_and_checkpoint(public_root, docs_path, row_count=2)

    result = builder.build_public_bm25_fts5(
        input_path=docs_path,
        output_path=output_path,
        public_root=public_root,
        batch_size=1,
        optimize=False,
    )

    assert result["row_count"] == 2
    assert output_path.exists()
    with sqlite3.connect(output_path) as conn:
        assert conn.execute("select count(*) from documents").fetchone()[0] == 2
        sample = conn.execute(
            "select id, document_id, source, source_scope, title, date, url, metadata_json "
            "from documents order by id limit 1"
        ).fetchone()
    assert sample[2] == PUBLIC_SOURCE
    assert sample[3] == PUBLIC_SOURCE_SCOPE
    assert json.loads(sample[7])["source_scope"] == PUBLIC_SOURCE_SCOPE


def test_manifest_and_checkpoint_are_validated_before_indexing(tmp_path: Path) -> None:
    builder = _load_builder()
    public_root = _public_root(tmp_path)
    docs_path = public_root / "docs.jsonl"
    output_path = public_root / "bm25_fts5" / "bm25.db"
    _write_jsonl(docs_path, [_public_row("H803222")])
    _write_manifest_and_checkpoint(public_root, docs_path, row_count=1)
    manifest_path = public_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["profile"] = "private"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(builder.PublicBM25BuildError, match="profile must be"):
        builder.build_public_bm25_fts5(
            input_path=docs_path,
            output_path=output_path,
            public_root=public_root,
        )

    assert not output_path.exists()


def test_builder_fails_on_bad_source_scope(tmp_path: Path) -> None:
    builder = _load_builder()
    public_root = _public_root(tmp_path)
    docs_path = public_root / "docs.jsonl"
    output_path = public_root / "bm25_fts5" / "bm25.db"
    row = _public_row("H803222")
    row["source_scope"] = "mixed_private"
    _write_jsonl(docs_path, [row])
    _write_manifest_and_checkpoint(public_root, docs_path, row_count=1)

    with pytest.raises(builder.PublicSourceGuardError, match="INVALID_SCOPE"):
        builder.build_public_bm25_fts5(
            input_path=docs_path,
            output_path=output_path,
            public_root=public_root,
        )

    assert not output_path.exists()


def test_builder_fails_on_non_public_source(tmp_path: Path) -> None:
    builder = _load_builder()
    public_root = _public_root(tmp_path)
    docs_path = public_root / "docs.jsonl"
    output_path = public_root / "bm25_fts5" / "bm25.db"
    row = _public_row("H803222")
    row["source"] = "bm25"
    _write_jsonl(docs_path, [row])
    _write_manifest_and_checkpoint(public_root, docs_path, row_count=1)

    with pytest.raises(builder.PublicSourceGuardError, match="FORBIDDEN_SOURCE"):
        builder.build_public_bm25_fts5(
            input_path=docs_path,
            output_path=output_path,
            public_root=public_root,
        )

    assert not output_path.exists()


def test_builder_writes_only_under_public_root(tmp_path: Path) -> None:
    builder = _load_builder()
    public_root = _public_root(tmp_path)
    docs_path = public_root / "docs.jsonl"
    output_path = tmp_path / "local-data-private" / "bm25.db"
    _write_jsonl(docs_path, [_public_row("H803222")])
    _write_manifest_and_checkpoint(public_root, docs_path, row_count=1)

    with pytest.raises(builder.PublicBM25BuildError, match="public root"):
        builder.build_public_bm25_fts5(
            input_path=docs_path,
            output_path=output_path,
            public_root=public_root,
        )


def test_real_public_bm25_artifact_has_expected_row_count() -> None:
    db_path = Path(PUBLIC_BM25_PATH)
    if not db_path.exists():
        pytest.skip(f"public BM25 artifact not built: {db_path}")

    with sqlite3.connect(db_path) as conn:
        row_count = conn.execute("select count(*) from documents").fetchone()[0]

    assert row_count == 230_143

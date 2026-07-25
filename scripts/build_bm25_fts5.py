#!/usr/bin/env python3
"""Build the public Riksdagen BM25 SQLite/FTS5 index from validated JSONL."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.shared.public_corpus_manifest import (  # noqa: E402
    PUBLIC_BM25_PATH,
    PublicCorpusManifestError,
    load_checkpoint,
    load_manifest,
    validate_public_checkpoint,
    validate_public_manifest,
)
from app.shared.public_source_guard import (  # noqa: E402
    PUBLIC_SOURCE,
    PUBLIC_SOURCE_SCOPE,
    PublicSourceGuardError,
    validate_public_record,
)

DEFAULT_INPUT = Path("/home/ai-server2/rag/local-data-public/riksdag/docs.jsonl")
DEFAULT_OUTPUT = Path(PUBLIC_BM25_PATH)
DEFAULT_PUBLIC_ROOT = DEFAULT_INPUT.parent
BATCH_SIZE = 5_000

__all__ = [
    "PublicBM25BuildError",
    "PublicSourceGuardError",
    "build_public_bm25_fts5",
    "parse_args",
]


class PublicBM25BuildError(ValueError):
    """Raised when the public BM25 build contract is violated."""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default=str(DEFAULT_INPUT), help="Public Riksdagen docs.jsonl")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output SQLite BM25 DB")
    parser.add_argument(
        "--manifest-file",
        default="",
        help="Manifest JSON path. Default: manifest.json next to input.",
    )
    parser.add_argument(
        "--checkpoint-file",
        default="",
        help="Checkpoint JSON path. Default: docs.checkpoint.json next to input.",
    )
    parser.add_argument(
        "--public-root",
        default=str(DEFAULT_PUBLIC_ROOT),
        help="Required public corpus root for input/output path checks.",
    )
    parser.add_argument(
        "--batch-size", type=int, default=BATCH_SIZE, help="SQLite insert batch size."
    )
    parser.add_argument(
        "--no-optimize",
        action="store_true",
        help="Skip FTS5 optimize step, mainly for tests.",
    )
    return parser.parse_args(argv)


def _resolved(path: Path) -> Path:
    return path.expanduser().resolve()


def _require_under_public_root(path: Path, public_root: Path, *, label: str) -> None:
    resolved_path = _resolved(path)
    resolved_root = _resolved(public_root)
    try:
        resolved_path.relative_to(resolved_root)
    except ValueError as exc:
        raise PublicBM25BuildError(f"{label} must be under public root: {resolved_root}") from exc


def _load_validated_contract(
    *,
    input_path: Path,
    output_path: Path,
    manifest_file: Path,
    checkpoint_file: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        manifest = validate_public_manifest(load_manifest(manifest_file))
        checkpoint = validate_public_checkpoint(load_checkpoint(checkpoint_file))
    except PublicCorpusManifestError as exc:
        raise PublicBM25BuildError(str(exc)) from exc

    if _resolved(Path(manifest["output_path"])) != _resolved(input_path):
        raise PublicBM25BuildError("manifest output_path must match BM25 input path")
    if _resolved(Path(checkpoint["output_path"])) != _resolved(input_path):
        raise PublicBM25BuildError("checkpoint output_path must match BM25 input path")
    if _resolved(Path(manifest["bm25_path"])) != _resolved(output_path):
        raise PublicBM25BuildError("manifest bm25_path must match BM25 output path")
    if manifest["document_count"] != checkpoint["kept_rows"]:
        raise PublicBM25BuildError("manifest document_count must match checkpoint kept_rows")
    if manifest["chunk_count"] != checkpoint["kept_rows"]:
        raise PublicBM25BuildError("manifest chunk_count must match checkpoint kept_rows")

    return manifest, checkpoint


def _metadata_json(row: Mapping[str, Any]) -> str:
    metadata = row.get("metadata")
    if not isinstance(metadata, Mapping):
        metadata = {}
    normalized = dict(metadata)
    normalized.setdefault("source", PUBLIC_SOURCE)
    normalized.setdefault("source_scope", PUBLIC_SOURCE_SCOPE)
    normalized.setdefault("document_id", str(row.get("document_id") or row.get("id") or ""))
    return json.dumps(normalized, ensure_ascii=False, sort_keys=True)


def _row_values(row: Mapping[str, Any]) -> tuple[str, str, str, str, str, str, str, str, str]:
    doc_id = str(row.get("id") or "").strip()
    document_id = str(row.get("document_id") or doc_id).strip()
    text = str(row.get("text") or "")
    if not doc_id:
        raise PublicBM25BuildError("public JSONL row is missing id")
    if not document_id:
        raise PublicBM25BuildError(f"public JSONL row is missing document_id: {doc_id}")
    if not text:
        raise PublicBM25BuildError(f"public JSONL row is missing text: {doc_id}")
    return (
        doc_id,
        document_id,
        str(row.get("source") or ""),
        str(row.get("source_scope") or ""),
        str(row.get("title") or document_id),
        str(row.get("date") or ""),
        str(row.get("url") or ""),
        text,
        _metadata_json(row),
    )


def _iter_public_rows(path: Path) -> tuple[tuple[str, str, str, str, str, str, str, str, str], str]:
    with path.open(encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, 1):
            stripped = line.strip()
            if not stripped:
                continue
            payload = json.loads(stripped)
            if not isinstance(payload, Mapping):
                raise PublicBM25BuildError(f"line {line_no}: expected JSON object")
            validate_public_record(payload, stage="public_bm25_builder")
            values = _row_values(payload)
            yield values, values[7]


def _remove_sqlite_companions(path: Path) -> None:
    path.unlink(missing_ok=True)
    Path(f"{path}-wal").unlink(missing_ok=True)
    Path(f"{path}-shm").unlink(missing_ok=True)


def _create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
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
        );

        CREATE INDEX documents_source_scope_idx
            ON documents(source, source_scope);

        CREATE VIRTUAL TABLE docs_fts USING fts5(
            doc_id UNINDEXED,
            content,
            tokenize='unicode61 remove_diacritics 2',
            detail='column'
        );
    """)


def build_public_bm25_fts5(
    *,
    input_path: Path,
    output_path: Path,
    public_root: Path = DEFAULT_PUBLIC_ROOT,
    manifest_file: Path | None = None,
    checkpoint_file: Path | None = None,
    batch_size: int = BATCH_SIZE,
    optimize: bool = True,
) -> dict[str, Any]:
    if batch_size < 1:
        raise PublicBM25BuildError("batch_size must be positive")

    _require_under_public_root(input_path, public_root, label="input_path")
    _require_under_public_root(output_path, public_root, label="output_path")
    if not input_path.exists():
        raise FileNotFoundError(input_path)

    manifest_path = manifest_file or input_path.parent / "manifest.json"
    checkpoint_path = checkpoint_file or input_path.parent / "docs.checkpoint.json"
    manifest, checkpoint = _load_validated_contract(
        input_path=input_path,
        output_path=output_path,
        manifest_file=manifest_path,
        checkpoint_file=checkpoint_path,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = output_path.with_suffix(output_path.suffix + ".tmp")
    _remove_sqlite_companions(tmp_path)

    start = time.perf_counter()
    row_count = 0
    samples: list[dict[str, str]] = []
    documents_batch: list[tuple[str, str, str, str, str, str, str, str, str]] = []
    fts_batch: list[tuple[str, str]] = []
    conn: sqlite3.Connection | None = None

    try:
        conn = sqlite3.connect(tmp_path)
        conn.execute("PRAGMA journal_mode=OFF")
        conn.execute("PRAGMA synchronous=OFF")
        conn.execute("PRAGMA cache_size=-65536")
        _create_schema(conn)

        for values, text in _iter_public_rows(input_path):
            documents_batch.append(values)
            fts_batch.append((values[0], text))
            row_count += 1
            if len(samples) < 5:
                samples.append(
                    {
                        "id": values[0],
                        "source": values[2],
                        "source_scope": values[3],
                    }
                )
            if len(documents_batch) >= batch_size:
                _insert_batches(conn, documents_batch, fts_batch)
                documents_batch.clear()
                fts_batch.clear()

        if documents_batch:
            _insert_batches(conn, documents_batch, fts_batch)

        if row_count != manifest["document_count"]:
            raise PublicBM25BuildError(
                f"row count mismatch: indexed={row_count} manifest={manifest['document_count']}"
            )
        if row_count != checkpoint["kept_rows"]:
            raise PublicBM25BuildError(
                f"row count mismatch: indexed={row_count} checkpoint={checkpoint['kept_rows']}"
            )
        if row_count <= 0:
            raise PublicBM25BuildError("public BM25 index cannot be empty")

        if optimize:
            conn.execute("INSERT INTO docs_fts(docs_fts) VALUES('optimize')")
            conn.commit()
        conn.close()
        conn = None
        tmp_path.replace(output_path)
    except Exception:
        if conn is not None:
            conn.close()
        _remove_sqlite_companions(tmp_path)
        raise

    return {
        "input_path": str(input_path),
        "output_path": str(output_path),
        "row_count": row_count,
        "source": PUBLIC_SOURCE,
        "source_scope": PUBLIC_SOURCE_SCOPE,
        "elapsed_seconds": round(time.perf_counter() - start, 2),
        "sample_rows": samples,
    }


def _insert_batches(
    conn: sqlite3.Connection,
    documents_batch: list[tuple[str, str, str, str, str, str, str, str, str]],
    fts_batch: list[tuple[str, str]],
) -> None:
    conn.executemany(
        """
        INSERT INTO documents(
            id, document_id, source, source_scope, title, date, url, text, metadata_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        documents_batch,
    )
    conn.executemany("INSERT INTO docs_fts(doc_id, content) VALUES (?, ?)", fts_batch)
    conn.commit()


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    result = build_public_bm25_fts5(
        input_path=Path(args.input),
        output_path=Path(args.output),
        public_root=Path(args.public_root),
        manifest_file=Path(args.manifest_file) if args.manifest_file else None,
        checkpoint_file=Path(args.checkpoint_file) if args.checkpoint_file else None,
        batch_size=args.batch_size,
        optimize=not args.no_optimize,
    )
    print(f"Wrote {result['row_count']} public BM25 rows to {result['output_path']}")
    print(f"Sample rows: {json.dumps(result['sample_rows'], ensure_ascii=False)}")


if __name__ == "__main__":
    main()

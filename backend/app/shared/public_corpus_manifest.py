"""Manifest and checkpoint validation for the public Riksdagen corpus."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .public_source_guard import PUBLIC_SOURCE, PUBLIC_SOURCE_SCOPE

PUBLIC_PROFILE = "public-riksdag-demo"
EXPECTED_ALLOWED_SOURCES = (PUBLIC_SOURCE,)
EXPECTED_FORBIDDEN_SOURCES = (
    "diva",
    "private_pdf",
    "mixed_recovered_corpus",
    "government_non_riksdag",
)
SOURCE_ATTRIBUTION_TEXT = "Data source: Sveriges riksdag / Riksdagens öppna data"
PUBLIC_BM25_PATH = "/home/ai-server2/rag/local-data-public/riksdag/bm25_fts5/bm25.db"
PUBLIC_CHROMA_COLLECTION = "riksdag_documents_p1_jina_v3_1024"
PUBLIC_EMBEDDING_MODEL = "jinaai/jina-embeddings-v3"


class PublicCorpusManifestError(ValueError):
    """Raised when a public corpus manifest/checkpoint is invalid."""


def load_manifest(path: Path | str) -> dict[str, Any]:
    return _load_json_object(path, kind="manifest")


def load_checkpoint(path: Path | str) -> dict[str, Any]:
    return _load_json_object(path, kind="checkpoint")


def _load_json_object(path: Path | str, *, kind: str) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise PublicCorpusManifestError(f"{kind} must be a JSON object")
    return payload


def _fail(message: str) -> None:
    raise PublicCorpusManifestError(message)


def _require_non_empty_string(payload: dict[str, Any], key: str) -> None:
    if not isinstance(payload.get(key), str) or not payload[key].strip():
        _fail(f"{key} must be a non-empty string")


def _require_non_negative_int(payload: dict[str, Any], key: str) -> None:
    value = payload.get(key)
    if not isinstance(value, int) or value < 0:
        _fail(f"{key} must be a non-negative integer")


def validate_public_manifest(
    manifest: dict[str, Any],
    expected_profile: str = PUBLIC_PROFILE,
    expected_scope: str = PUBLIC_SOURCE_SCOPE,
) -> dict[str, Any]:
    """Validate the manifest contract consumed by public corpus builders."""
    if manifest.get("profile") != expected_profile:
        _fail(f"profile must be {expected_profile}")

    scope = manifest.get("source_scope")
    if scope != expected_scope:
        _fail(f"source_scope must be {expected_scope}")

    if manifest.get("allowed_sources") != list(EXPECTED_ALLOWED_SOURCES):
        _fail(f"allowed_sources must be {list(EXPECTED_ALLOWED_SOURCES)}")

    forbidden = set(manifest.get("forbidden_sources") or [])
    missing = sorted(set(EXPECTED_FORBIDDEN_SOURCES) - forbidden)
    if missing:
        _fail(f"forbidden_sources missing required entries: {missing}")

    if manifest.get("requires_source_attribution") is not True:
        _fail("requires_source_attribution must be true")

    if manifest.get("source_attribution_text") != SOURCE_ATTRIBUTION_TEXT:
        _fail("source_attribution_text is missing or incorrect")

    for key in (
        "created_at",
        "output_path",
        "bm25_path",
        "chroma_collection",
        "embedding_model",
    ):
        _require_non_empty_string(manifest, key)

    for key in ("document_count", "chunk_count"):
        _require_non_negative_int(manifest, key)

    return manifest


def validate_public_checkpoint(checkpoint: dict[str, Any]) -> dict[str, Any]:
    """Validate the splitter checkpoint before downstream indexing trusts it."""
    if checkpoint.get("profile") != PUBLIC_PROFILE:
        _fail(f"profile must be {PUBLIC_PROFILE}")
    if checkpoint.get("source_scope") != PUBLIC_SOURCE_SCOPE:
        _fail(f"source_scope must be {PUBLIC_SOURCE_SCOPE}")

    for key in ("input_path", "output_path"):
        _require_non_empty_string(checkpoint, key)

    for key in ("start_row", "end_row", "scanned_rows", "kept_rows", "skipped_non_riksdag_rows"):
        _require_non_negative_int(checkpoint, key)

    start_row = checkpoint["start_row"]
    end_row = checkpoint["end_row"]
    if start_row < 1 or end_row < start_row:
        _fail("row_bounds must satisfy 1 <= start_row <= end_row")

    row_bounds = checkpoint.get("row_bounds")
    if row_bounds != {"start_row": start_row, "end_row": end_row}:
        _fail("row_bounds must match top-level start_row/end_row")

    scanned = checkpoint["scanned_rows"]
    expected_scanned = checkpoint["kept_rows"] + checkpoint["skipped_non_riksdag_rows"]
    if scanned != expected_scanned:
        _fail(f"count mismatch: scanned_rows={scanned} expected={expected_scanned}")

    scan = checkpoint.get("forbidden_marker_scan")
    if not isinstance(scan, dict):
        _fail("forbidden_marker_scan must be present")
    if scan.get("status") != "clean" or scan.get("hits") != 0:
        _fail("forbidden_marker_scan must be clean with zero hits")

    return checkpoint

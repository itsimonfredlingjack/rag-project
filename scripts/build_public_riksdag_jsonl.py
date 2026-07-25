#!/usr/bin/env python3
"""Build a public Riksdagen-only JSONL corpus from a recovered JSONL source."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.shared.public_corpus_manifest import (  # noqa: E402
    EXPECTED_ALLOWED_SOURCES,
    EXPECTED_FORBIDDEN_SOURCES,
    PUBLIC_BM25_PATH,
    PUBLIC_CHROMA_COLLECTION,
    PUBLIC_EMBEDDING_MODEL,
    PUBLIC_PROFILE,
    SOURCE_ATTRIBUTION_TEXT,
)
from app.shared.public_source_guard import (  # noqa: E402
    PUBLIC_SOURCE,
    PUBLIC_SOURCE_SCOPE,
    PublicSourceGuardError,
    validate_public_record,
)

__all__ = ["PublicSourceGuardError", "build_public_riksdag_jsonl", "parse_args"]

REQUESTED_DEFAULT_INPUT = Path("/home/ai-server2/rag/local-data-private/docs.jsonl")
RECOVERED_FALLBACK_INPUT = (
    Path("/home/ai-server2/rag/RAG_TRANSFER")
    / "constitutional-ai-preservation-2026-04-10-selected"
    / "bm25_index"
    / "docs.jsonl"
)
DEFAULT_OUTPUT = Path("/home/ai-server2/rag/local-data-public/riksdag/docs.jsonl")
DEFAULT_START_ROW = 7_842
DEFAULT_END_ROW = 237_984

TAG_RE_TEMPLATE = r"<{tag}>\s*([^<]+?)\s*</{tag}>"
URL_RE = re.compile(r"https?://data\.riksdagen\.se/dokument/([A-Za-z0-9]+)(?:/text)?")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default=str(REQUESTED_DEFAULT_INPUT), help="Input docs.jsonl")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output public docs.jsonl")
    parser.add_argument("--start-row", type=int, default=DEFAULT_START_ROW, help="Inclusive row")
    parser.add_argument("--end-row", type=int, default=DEFAULT_END_ROW, help="Inclusive row")
    parser.add_argument(
        "--source-scope",
        default=PUBLIC_SOURCE_SCOPE,
        help="Required public source scope.",
    )
    parser.add_argument(
        "--checkpoint-file",
        default="",
        help="Checkpoint JSON path. Default: docs.checkpoint.json next to output.",
    )
    parser.add_argument(
        "--manifest-file",
        default="",
        help="Manifest JSON path. Default: manifest.json next to output.",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=5,
        help="Number of sample IDs printed and saved in checkpoint.",
    )
    return parser.parse_args(argv)


def resolve_input_path(path: Path) -> tuple[Path, Path | None]:
    """Resolve missing ideal private input to the recovered transfer JSONL when available."""
    if path.exists():
        return path, None
    if RECOVERED_FALLBACK_INPUT.exists():
        return RECOVERED_FALLBACK_INPUT, path
    raise FileNotFoundError(
        f"Input JSONL not found: {path}. Recovered fallback also missing: "
        f"{RECOVERED_FALLBACK_INPUT}"
    )


def _source_created_at(path: Path) -> str:
    timestamp = path.stat().st_mtime
    return datetime.fromtimestamp(timestamp, UTC).replace(microsecond=0).isoformat()


def _extract_tag(text: str, tag: str) -> str:
    match = re.search(TAG_RE_TEMPLATE.format(tag=re.escape(tag)), text, flags=re.IGNORECASE)
    return match.group(1).strip() if match else ""


def _extract_date(text: str) -> str:
    for tag in ("datum", "publicerad", "systemdatum"):
        value = _extract_tag(text, tag)
        if value:
            return value[:10]
    return ""


def _extract_url(text: str, document_id: str) -> str:
    match = URL_RE.search(text)
    if match:
        return f"https://data.riksdagen.se/dokument/{match.group(1)}"
    return f"https://data.riksdagen.se/dokument/{document_id}"


def _derive_title(text: str, document_id: str) -> str:
    tagged = _extract_tag(text, "titel")
    if tagged:
        return tagged[:500]
    first_line = (text or "").strip().splitlines()[0] if text else document_id
    if "<dokumentstatus>" in first_line:
        first_line = first_line.split("<dokumentstatus>", 1)[0]
    return (first_line.strip() or document_id)[:500]


def _document_id(obj: Mapping[str, Any], text: str) -> str:
    tagged = _extract_tag(text, "dok_id")
    return tagged or str(obj.get("id", "")).strip()


def _is_riksdag_row(obj: Mapping[str, Any]) -> bool:
    text = str(obj.get("text", ""))
    doc_id = str(obj.get("id", ""))
    return bool(doc_id and text and ("<dokumentstatus>" in text or "data.riksdagen.se" in text))


def _normalize_row(obj: Mapping[str, Any], *, line_no: int, source_scope: str) -> dict[str, Any]:
    text = str(obj.get("text", ""))
    document_id = _document_id(obj, text)
    title = _derive_title(text, document_id)
    date = _extract_date(text)
    url = _extract_url(text, document_id)
    row = {
        "id": document_id,
        "text": text,
        "source": PUBLIC_SOURCE,
        "source_scope": source_scope,
        "document_id": document_id,
        "title": title,
        "date": date,
        "url": url,
        "metadata": {
            "source": PUBLIC_SOURCE,
            "source_scope": source_scope,
            "document_id": document_id,
            "title": title,
            "date": date,
            "url": url,
            "source_line_no": line_no,
            "doc_type": _extract_tag(text, "typ") or "riksdag_document",
        },
    }
    validate_public_record(row, stage="public_jsonl_splitter")
    return row


def iter_bounded_jsonl(
    path: Path,
    *,
    start_row: int,
    end_row: int,
) -> Iterable[tuple[int, dict[str, Any], str]]:
    with path.open(encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, 1):
            if line_no < start_row:
                continue
            if line_no > end_row:
                break
            stripped = line.strip()
            if not stripped:
                continue
            yield line_no, json.loads(stripped), stripped


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )
    tmp.replace(path)


def build_public_riksdag_jsonl(
    *,
    input_path: Path,
    output_path: Path,
    start_row: int,
    end_row: int,
    source_scope: str,
    checkpoint_file: Path | None = None,
    manifest_file: Path | None = None,
    sample_size: int = 5,
) -> dict[str, Any]:
    if source_scope != PUBLIC_SOURCE_SCOPE:
        raise ValueError(f"Unsupported public source scope: {source_scope}")
    if start_row < 1 or end_row < start_row:
        raise ValueError("Expected 1 <= start_row <= end_row")

    resolved_input, fallback_for = resolve_input_path(input_path)
    checkpoint_path = checkpoint_file or output_path.parent / "docs.checkpoint.json"
    manifest_path = manifest_file or output_path.parent / "manifest.json"

    scanned_rows = 0
    kept_rows = 0
    skipped_non_riksdag = 0
    sample_ids: list[str] = []
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_output = output_path.with_suffix(output_path.suffix + ".tmp")

    try:
        with tmp_output.open("w", encoding="utf-8") as output:
            for line_no, obj, _raw_line in iter_bounded_jsonl(
                resolved_input,
                start_row=start_row,
                end_row=end_row,
            ):
                scanned_rows += 1
                if not _is_riksdag_row(obj):
                    skipped_non_riksdag += 1
                    continue
                row = _normalize_row(obj, line_no=line_no, source_scope=source_scope)
                output.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
                kept_rows += 1
                if len(sample_ids) < sample_size:
                    sample_ids.append(row["id"])
        tmp_output.replace(output_path)
    except Exception:
        tmp_output.unlink(missing_ok=True)
        raise

    result = {
        "profile": PUBLIC_PROFILE,
        "corpus_scope": source_scope,
        "source_scope": source_scope,
        "requested_input_path": str(input_path),
        "input_path": str(resolved_input),
        "fallback_for_missing_input": str(fallback_for) if fallback_for else None,
        "output_path": str(output_path),
        "start_row": start_row,
        "end_row": end_row,
        "row_bounds": {"start_row": start_row, "end_row": end_row},
        "scanned_rows": scanned_rows,
        "kept_rows": kept_rows,
        "skipped_non_riksdag_rows": skipped_non_riksdag,
        "forbidden_marker_scan": {"status": "clean", "hits": 0},
        "sample_ids": sample_ids,
    }

    checkpoint_payload = {
        **result,
        "checkpoint_version": 1,
    }
    manifest_payload = {
        "manifest_version": 1,
        "profile": result["profile"],
        "corpus_scope": source_scope,
        "source_scope": source_scope,
        "source": PUBLIC_SOURCE,
        "allowed_sources": list(EXPECTED_ALLOWED_SOURCES),
        "forbidden_sources": list(EXPECTED_FORBIDDEN_SOURCES),
        "requires_source_attribution": True,
        "source_attribution_text": SOURCE_ATTRIBUTION_TEXT,
        "input_path": str(resolved_input),
        "output_path": str(output_path),
        "output_rows": kept_rows,
        "document_count": kept_rows,
        "chunk_count": kept_rows,
        "row_bounds": {"start_row": start_row, "end_row": end_row},
        "bm25_path": PUBLIC_BM25_PATH,
        "chroma_collection": PUBLIC_CHROMA_COLLECTION,
        "embedding_model": PUBLIC_EMBEDDING_MODEL,
        "created_at": _source_created_at(resolved_input),
        "sample_ids": sample_ids,
    }
    write_json_atomic(checkpoint_path, checkpoint_payload)
    write_json_atomic(manifest_path, manifest_payload)
    return result


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    result = build_public_riksdag_jsonl(
        input_path=Path(args.input),
        output_path=Path(args.output),
        start_row=args.start_row,
        end_row=args.end_row,
        source_scope=args.source_scope,
        checkpoint_file=Path(args.checkpoint_file) if args.checkpoint_file else None,
        manifest_file=Path(args.manifest_file) if args.manifest_file else None,
        sample_size=args.sample_size,
    )
    print(f"Wrote {result['kept_rows']} public Riksdagen rows to {result['output_path']}")
    print("Sample IDs: " + ", ".join(result["sample_ids"]))


if __name__ == "__main__":
    main()

"""Tests for the public Riksdagen JSONL splitter."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from app.shared.public_corpus_manifest import (
    EXPECTED_FORBIDDEN_SOURCES,
    SOURCE_ATTRIBUTION_TEXT,
    validate_public_checkpoint,
    validate_public_manifest,
)


def _load_splitter():
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "build_public_riksdag_jsonl.py"
    spec = importlib.util.spec_from_file_location("build_public_riksdag_jsonl", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _riksdag_row(doc_id: str, title: str = "Testtitel") -> dict[str, str]:
    text = (
        f"{title} <dokumentstatus><dokument>\r\n"
        f" <dok_id>{doc_id}</dok_id>\r\n"
        " <rm>2020/21</rm>\r\n"
        " <typ>prop</typ>\r\n"
        " <datum>2021-09-13 00:00:00</datum>\r\n"
        " <publicerad>2021-09-14 00:00:00</publicerad>\r\n"
        f" <titel>{title}</titel>\r\n"
        f" <dokument_url_text>https://data.riksdagen.se/dokument/{doc_id}/text</dokument_url_text>\r\n"
        "</dokument></dokumentstatus>"
    )
    return {"id": doc_id, "text": text}


def _write_jsonl(path: Path, rows: list[dict[str, str]]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_splitter_writes_public_rows_manifest_and_checkpoint(tmp_path: Path) -> None:
    splitter = _load_splitter()
    input_path = tmp_path / "docs.jsonl"
    output_path = tmp_path / "public" / "docs.jsonl"
    rows = [
        {"id": "sfs_1", "text": "SFS row"},
        _riksdag_row("H803222", "Anpassningar av svensk lag"),
        _riksdag_row("H803224", "Behandling av personuppgifter"),
        {"id": "gov_1", "text": "Government row"},
    ]
    _write_jsonl(input_path, rows)

    result = splitter.build_public_riksdag_jsonl(
        input_path=input_path,
        output_path=output_path,
        start_row=2,
        end_row=3,
        source_scope="riksdagen_open_data_only",
    )

    written = _read_jsonl(output_path)
    assert [row["id"] for row in written] == ["H803222", "H803224"]
    assert result["kept_rows"] == 2
    assert result["scanned_rows"] == 2
    assert result["sample_ids"] == ["H803222", "H803224"]

    for row in written:
        assert row["source"] == "riksdagen"
        assert row["source_scope"] == "riksdagen_open_data_only"
        assert row["document_id"] == row["id"]
        assert row["url"] == f"https://data.riksdagen.se/dokument/{row['id']}"
        assert row["date"] == "2021-09-13"
        assert row["metadata"]["source"] == "riksdagen"
        assert row["metadata"]["source_scope"] == "riksdagen_open_data_only"

    checkpoint = json.loads((output_path.parent / "docs.checkpoint.json").read_text())
    manifest = json.loads((output_path.parent / "manifest.json").read_text())
    validate_public_checkpoint(checkpoint)
    validate_public_manifest(manifest)
    assert checkpoint["start_row"] == 2
    assert checkpoint["end_row"] == 3
    assert checkpoint["row_bounds"] == {"start_row": 2, "end_row": 3}
    assert checkpoint["kept_rows"] == 2
    assert checkpoint["forbidden_marker_scan"] == {"status": "clean", "hits": 0}
    assert manifest["corpus_scope"] == "riksdagen_open_data_only"
    assert manifest["source_scope"] == "riksdagen_open_data_only"
    assert manifest["output_rows"] == 2
    assert manifest["document_count"] == 2
    assert manifest["chunk_count"] == 2
    assert manifest["allowed_sources"] == ["riksdagen"]
    assert set(EXPECTED_FORBIDDEN_SOURCES).issubset(manifest["forbidden_sources"])
    assert manifest["requires_source_attribution"] is True
    assert manifest["source_attribution_text"] == SOURCE_ATTRIBUTION_TEXT


def test_splitter_rerun_is_deterministic(tmp_path: Path) -> None:
    splitter = _load_splitter()
    input_path = tmp_path / "docs.jsonl"
    output_path = tmp_path / "public" / "docs.jsonl"
    _write_jsonl(input_path, [_riksdag_row("H803222")])

    splitter.build_public_riksdag_jsonl(
        input_path=input_path,
        output_path=output_path,
        start_row=1,
        end_row=1,
        source_scope="riksdagen_open_data_only",
    )
    first = output_path.read_bytes()

    splitter.build_public_riksdag_jsonl(
        input_path=input_path,
        output_path=output_path,
        start_row=1,
        end_row=1,
        source_scope="riksdagen_open_data_only",
    )

    assert output_path.read_bytes() == first


def test_splitter_can_fallback_to_recovered_input_when_private_path_is_missing(
    tmp_path: Path,
) -> None:
    splitter = _load_splitter()
    missing_private_path = tmp_path / "local-data-private" / "docs.jsonl"
    recovered_path = tmp_path / "transfer" / "docs.jsonl"
    output_path = tmp_path / "public" / "docs.jsonl"
    recovered_path.parent.mkdir(parents=True)
    _write_jsonl(recovered_path, [_riksdag_row("H803222")])
    splitter.RECOVERED_FALLBACK_INPUT = recovered_path

    result = splitter.build_public_riksdag_jsonl(
        input_path=missing_private_path,
        output_path=output_path,
        start_row=1,
        end_row=1,
        source_scope="riksdagen_open_data_only",
    )

    assert result["input_path"] == str(recovered_path)
    assert result["fallback_for_missing_input"] == str(missing_private_path)
    assert _read_jsonl(output_path)[0]["source_scope"] == "riksdagen_open_data_only"


@pytest.mark.parametrize(
    "marker",
    [
        "diva",
        "DiVA",
        "FULLTEXT",
        "diva2:",
        "private_pdf",
        "mixed_recovered_corpus",
        "private source",
    ],
)
def test_splitter_fails_hard_on_forbidden_markers(tmp_path: Path, marker: str) -> None:
    splitter = _load_splitter()
    input_path = tmp_path / "docs.jsonl"
    output_path = tmp_path / "public" / "docs.jsonl"
    bad = _riksdag_row("H803222")
    bad["text"] += f" {marker}"
    _write_jsonl(input_path, [bad])

    with pytest.raises(splitter.PublicSourceGuardError, match="FORBIDDEN_MARKER"):
        splitter.build_public_riksdag_jsonl(
            input_path=input_path,
            output_path=output_path,
            start_row=1,
            end_row=1,
            source_scope="riksdagen_open_data_only",
        )

    assert not output_path.exists()

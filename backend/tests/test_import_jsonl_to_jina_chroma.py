"""Regression tests for the recovery JSONL -> Jina/Chroma importer."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_importer():
    script_path = Path(__file__).resolve().parents[2] / "scripts" / "import_jsonl_to_jina_chroma.py"
    spec = importlib.util.spec_from_file_location("import_jsonl_to_jina_chroma", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_bounded_passage_text_caps_text_and_marks_truncation() -> None:
    importer = _load_importer()

    bounded, truncated = importer.bounded_passage_text("abcdef" * 20, max_chars=40)

    assert truncated is True
    assert len(bounded) <= 40
    assert bounded.endswith(importer.TRUNCATION_MARKER)


def test_prepare_import_item_stores_bounded_text_and_original_size_metadata() -> None:
    importer = _load_importer()
    obj = {"id": "sfs_1915_218_1kap_1§", "text": "Lång lagtext. " * 100}

    item = importer.prepare_import_item(1, obj, max_text_chars=80)

    assert item["id"] == "sfs_1915_218_1kap_1§"
    assert len(item["text"]) <= 80
    assert item["metadata"]["original_text_chars"] == len(obj["text"])
    assert item["metadata"]["embedded_text_chars"] == len(item["text"])
    assert item["metadata"]["embedding_text_truncated"] is True


def test_configure_model_limits_sets_lower_sequence_limit() -> None:
    importer = _load_importer()

    class FakeModel:
        max_seq_length = 8192

    model = FakeModel()

    applied = importer.configure_model_limits(model, max_seq_length=1024)

    assert applied == 1024
    assert model.max_seq_length == 1024


def test_write_manifest_accepts_explicit_output_path(tmp_path: Path) -> None:
    importer = _load_importer()
    input_path = tmp_path / "docs.jsonl"
    procedural_path = tmp_path / "procedural.json"
    checkpoint_path = tmp_path / "checkpoint.json"
    manifest_path = tmp_path / "manifest.json"
    input_path.write_text('{"id":"x","text":"y"}\n', encoding="utf-8")
    procedural_path.write_text("[]", encoding="utf-8")
    checkpoint_path.write_text("{}", encoding="utf-8")

    class FakeCollection:
        def count(self) -> int:
            return 2

    importer.write_manifest(
        chroma_path=tmp_path / "chroma",
        input_path=input_path,
        procedural_path=procedural_path,
        checkpoint_path=checkpoint_path,
        model_name="jinaai/jina-embeddings-v3",
        collections={"sfs_lagtext_jina_v3_1024": FakeCollection()},
        total_jsonl_count=1,
        manifest_path=manifest_path,
    )

    assert manifest_path.exists()
    assert "sfs_lagtext_jina_v3_1024" in manifest_path.read_text(encoding="utf-8")

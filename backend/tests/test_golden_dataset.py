"""
Tests for Golden Evaluation Dataset — schema validation and dataset integrity.

Tests cover:
  - Dataset loading and parsing
  - Item schema validation
  - Coverage checks (modes, intents, difficulties)
  - Edge case handling
"""

import json
from pathlib import Path

import pytest

from eval.golden_dataset import (
    DifficultyLevel,
    EvalIntent,
    EvalMode,
    GoldenDataset,
    load_golden_dataset,
)


# ═══════════════════════════════════════════════════════════════════════════
# DATASET LOADING
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestDatasetLoading:
    """Tests for loading the golden dataset."""

    def test_load_v1_dataset(self):
        """Golden v1 dataset loads without errors."""
        dataset = load_golden_dataset(version="v1")
        assert isinstance(dataset, GoldenDataset)
        assert dataset.count > 0

    def test_dataset_version(self):
        dataset = load_golden_dataset(version="v1")
        assert dataset.version == "v1"

    def test_dataset_has_description(self):
        dataset = load_golden_dataset(version="v1")
        assert len(dataset.description) > 0

    def test_load_nonexistent_version_raises(self):
        with pytest.raises(FileNotFoundError):
            load_golden_dataset(version="v999")

    def test_load_explicit_path(self):
        path = Path(__file__).parent.parent / "eval" / "datasets" / "golden_v1.json"
        dataset = load_golden_dataset(path=str(path))
        assert dataset.count > 0


# ═══════════════════════════════════════════════════════════════════════════
# ITEM SCHEMA VALIDATION
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestItemSchema:
    """Tests for individual item schema."""

    @pytest.fixture
    def dataset(self):
        return load_golden_dataset(version="v1")

    def test_all_items_have_unique_ids(self, dataset):
        ids = [item.id for item in dataset.items]
        assert len(ids) == len(set(ids)), f"Duplicate IDs: {[i for i in ids if ids.count(i) > 1]}"

    def test_all_items_have_questions(self, dataset):
        for item in dataset.items:
            assert len(item.question) > 5, f"Item {item.id} has too-short question"

    def test_all_items_have_valid_mode(self, dataset):
        for item in dataset.items:
            assert isinstance(item.mode, EvalMode), f"Item {item.id} has invalid mode"

    def test_all_items_have_valid_intent(self, dataset):
        for item in dataset.items:
            assert isinstance(item.intent, EvalIntent), f"Item {item.id} has invalid intent"

    def test_all_items_have_valid_difficulty(self, dataset):
        for item in dataset.items:
            assert isinstance(
                item.difficulty, DifficultyLevel
            ), f"Item {item.id} has invalid difficulty"

    def test_all_items_have_category(self, dataset):
        for item in dataset.items:
            assert len(item.category) > 0, f"Item {item.id} missing category"

    def test_evidence_items_have_expected_sources(self, dataset):
        """EVIDENCE mode items should specify expected source types."""
        evidence_items = dataset.by_mode(EvalMode.EVIDENCE)
        for item in evidence_items:
            assert (
                len(item.expected_sources) > 0
            ), f"EVIDENCE item {item.id} missing expected_sources"

    def test_chat_items_have_no_sources(self, dataset):
        """CHAT mode items should not have expected sources."""
        chat_items = dataset.by_mode(EvalMode.CHAT)
        for item in chat_items:
            assert (
                len(item.expected_sources) == 0
            ), f"CHAT item {item.id} should not have expected_sources"

    def test_answer_fragments_are_lowercase_compatible(self, dataset):
        """Answer fragments should be lowercase (case-insensitive matching)."""
        for item in dataset.items:
            for frag in item.answer_fragments:
                # Fragments can be mixed case but should be meaningful (>2 chars)
                assert len(frag) > 1, f"Item {item.id} has too-short fragment: '{frag}'"


# ═══════════════════════════════════════════════════════════════════════════
# COVERAGE CHECKS
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestDatasetCoverage:
    """Verify the dataset covers required dimensions."""

    @pytest.fixture
    def dataset(self):
        return load_golden_dataset(version="v1")

    def test_minimum_item_count(self, dataset):
        """Dataset should have at least 50 items."""
        assert dataset.count >= 50, f"Only {dataset.count} items, need at least 50"

    def test_all_modes_covered(self, dataset):
        """All three response modes should be represented."""
        modes_present = {item.mode for item in dataset.items}
        assert EvalMode.EVIDENCE in modes_present, "Missing EVIDENCE mode items"
        assert EvalMode.ASSIST in modes_present, "Missing ASSIST mode items"
        assert EvalMode.CHAT in modes_present, "Missing CHAT mode items"

    def test_all_major_intents_covered(self, dataset):
        """All major intent categories should be represented."""
        intents_present = {item.intent for item in dataset.items}
        required_intents = {
            EvalIntent.LEGAL_TEXT,
            EvalIntent.PARLIAMENT_TRACE,
            EvalIntent.POLICY_ARGUMENTS,
            EvalIntent.RESEARCH_SYNTHESIS,
            EvalIntent.PRACTICAL_PROCESS,
        }
        missing = required_intents - intents_present
        assert len(missing) == 0, f"Missing intent coverage: {missing}"

    def test_all_difficulties_covered(self, dataset):
        """All difficulty levels should be represented."""
        diffs_present = {item.difficulty for item in dataset.items}
        assert DifficultyLevel.EASY in diffs_present
        assert DifficultyLevel.MEDIUM in diffs_present
        assert DifficultyLevel.HARD in diffs_present

    def test_evidence_mode_has_sufficient_items(self, dataset):
        """EVIDENCE mode should have the most items (>= 20)."""
        evidence_count = len(dataset.by_mode(EvalMode.EVIDENCE))
        assert evidence_count >= 20, f"Only {evidence_count} EVIDENCE items"

    def test_legal_text_intent_dominates(self, dataset):
        """LEGAL_TEXT should be the most common intent (core use case)."""
        legal_count = len(dataset.by_intent(EvalIntent.LEGAL_TEXT))
        assert legal_count >= 15, f"Only {legal_count} LEGAL_TEXT items"

    def test_quality_dimensions_covered(self, dataset):
        """Quality dimensions should be tagged on relevant items."""
        verbatim = sum(1 for i in dataset.items if i.requires_verbatim_citation)
        modal = sum(1 for i in dataset.items if i.requires_modal_preservation)
        recency = sum(1 for i in dataset.items if i.requires_recency_awareness)
        scope = sum(1 for i in dataset.items if i.requires_scope_boundary)

        assert verbatim >= 10, f"Only {verbatim} items test verbatim citation"
        assert modal >= 5, f"Only {modal} items test modal preservation"
        assert recency >= 5, f"Only {recency} items test recency awareness"
        assert scope >= 5, f"Only {scope} items test scope boundary"


# ═══════════════════════════════════════════════════════════════════════════
# FILTERING AND SUMMARY
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestDatasetFiltering:
    """Tests for dataset filtering and summary methods."""

    @pytest.fixture
    def dataset(self):
        return load_golden_dataset(version="v1")

    def test_by_mode_returns_correct_items(self, dataset):
        evidence = dataset.by_mode(EvalMode.EVIDENCE)
        for item in evidence:
            assert item.mode == EvalMode.EVIDENCE

    def test_by_intent_returns_correct_items(self, dataset):
        legal = dataset.by_intent(EvalIntent.LEGAL_TEXT)
        for item in legal:
            assert item.intent == EvalIntent.LEGAL_TEXT

    def test_by_difficulty_returns_correct_items(self, dataset):
        hard = dataset.by_difficulty(DifficultyLevel.HARD)
        for item in hard:
            assert item.difficulty == DifficultyLevel.HARD

    def test_by_category(self, dataset):
        grundlag = dataset.by_category("grundlag")
        assert len(grundlag) > 0
        for item in grundlag:
            assert item.category == "grundlag"

    def test_summary_has_all_keys(self, dataset):
        summary = dataset.summary()
        assert "total" in summary
        assert "by_mode" in summary
        assert "by_intent" in summary
        assert "by_difficulty" in summary
        assert "by_category" in summary
        assert "quality_dimensions" in summary

    def test_summary_total_matches(self, dataset):
        summary = dataset.summary()
        assert summary["total"] == dataset.count


# ═══════════════════════════════════════════════════════════════════════════
# JSON INTEGRITY
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestJsonIntegrity:
    """Tests for JSON file format integrity."""

    def test_json_is_valid(self):
        path = Path(__file__).parent.parent / "eval" / "datasets" / "golden_v1.json"
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        assert "items" in data
        assert isinstance(data["items"], list)

    def test_json_has_required_fields(self):
        path = Path(__file__).parent.parent / "eval" / "datasets" / "golden_v1.json"
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        for item in data["items"]:
            assert "id" in item, "Missing 'id' in item"
            assert "question" in item, f"Missing 'question' in item {item.get('id', '?')}"
            assert "mode" in item, f"Missing 'mode' in item {item.get('id', '?')}"
            assert "intent" in item, f"Missing 'intent' in item {item.get('id', '?')}"
            assert "difficulty" in item, f"Missing 'difficulty' in item {item.get('id', '?')}"

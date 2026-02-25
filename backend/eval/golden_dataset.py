"""
Golden Evaluation Dataset — Schema and Loader
==============================================

Defines the structure for golden Q&A pairs used to measure RAG quality.
Each item specifies: question, expected mode/intent, ground-truth answer fragments,
expected citation sources, and quality dimensions to evaluate.

Sprint 2 (P2-11): Initial scaffold with 60 diverse Swedish legal Q&A pairs.
"""

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional


# ═══════════════════════════════════════════════════════════════════════════
# ENUMS
# ═══════════════════════════════════════════════════════════════════════════


class EvalMode(str, Enum):
    """Expected response mode for a golden item."""

    EVIDENCE = "evidence"
    ASSIST = "assist"
    CHAT = "chat"


class EvalIntent(str, Enum):
    """Expected query intent classification."""

    LEGAL_TEXT = "legal_text"
    PARLIAMENT_TRACE = "parliament_trace"
    POLICY_ARGUMENTS = "policy_arguments"
    RESEARCH_SYNTHESIS = "research"
    PRACTICAL_PROCESS = "practical"
    EDGE_ABBREVIATION = "edge_abbr"
    EDGE_CLARIFICATION = "edge_clar"
    SMALLTALK = "smalltalk"
    UNKNOWN = "unknown"


class DifficultyLevel(str, Enum):
    """Question difficulty for stratified evaluation."""

    EASY = "easy"  # Single source, direct answer
    MEDIUM = "medium"  # Multiple sources, synthesis required
    HARD = "hard"  # Cross-reference, nuance, edge cases


# ═══════════════════════════════════════════════════════════════════════════
# DATA MODEL
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class GoldenItem:
    """
    A single golden evaluation item.

    Fields:
        id: Unique identifier (e.g., "G001")
        question: The user query in Swedish
        mode: Expected response mode (evidence/assist/chat)
        intent: Expected intent classification
        difficulty: Question difficulty level

        # Ground truth
        answer_fragments: Key phrases that MUST appear in a correct answer
        forbidden_fragments: Phrases that must NOT appear (hallucination traps)
        expected_sources: Source types/IDs expected in citations
        expected_law_refs: Specific law references expected (e.g., "RF 2 kap. 1 §")

        # Quality dimensions
        requires_verbatim_citation: Whether EVIDENCE mode verbatim citing is needed
        requires_modal_preservation: Whether modal verbs (far/ska/bör) matter
        requires_recency_awareness: Whether document age is relevant
        requires_scope_boundary: Whether answer should explicitly limit scope

        # Metadata
        category: Topical category for stratified reporting
        notes: Human notes about what makes this question interesting
    """

    id: str
    question: str
    mode: EvalMode
    intent: EvalIntent
    difficulty: DifficultyLevel

    # Ground truth
    answer_fragments: list[str] = field(default_factory=list)
    forbidden_fragments: list[str] = field(default_factory=list)
    expected_sources: list[str] = field(default_factory=list)
    expected_law_refs: list[str] = field(default_factory=list)

    # Quality dimensions
    requires_verbatim_citation: bool = False
    requires_modal_preservation: bool = False
    requires_recency_awareness: bool = False
    requires_scope_boundary: bool = False

    # Metadata
    category: str = ""
    notes: str = ""


@dataclass
class GoldenDataset:
    """
    Collection of golden evaluation items with metadata.

    Fields:
        version: Dataset version string
        description: Human-readable description
        items: List of golden items
        created: ISO date string
    """

    version: str
    description: str
    items: list[GoldenItem]
    created: str = ""

    @property
    def count(self) -> int:
        return len(self.items)

    def by_mode(self, mode: EvalMode) -> list[GoldenItem]:
        """Filter items by response mode."""
        return [i for i in self.items if i.mode == mode]

    def by_intent(self, intent: EvalIntent) -> list[GoldenItem]:
        """Filter items by intent."""
        return [i for i in self.items if i.intent == intent]

    def by_difficulty(self, difficulty: DifficultyLevel) -> list[GoldenItem]:
        """Filter items by difficulty."""
        return [i for i in self.items if i.difficulty == difficulty]

    def by_category(self, category: str) -> list[GoldenItem]:
        """Filter items by topical category."""
        return [i for i in self.items if i.category == category]

    def summary(self) -> dict:
        """Return distribution summary for reporting."""
        from collections import Counter

        return {
            "total": self.count,
            "by_mode": dict(Counter(i.mode.value for i in self.items)),
            "by_intent": dict(Counter(i.intent.value for i in self.items)),
            "by_difficulty": dict(Counter(i.difficulty.value for i in self.items)),
            "by_category": dict(Counter(i.category for i in self.items)),
            "quality_dimensions": {
                "requires_verbatim_citation": sum(
                    1 for i in self.items if i.requires_verbatim_citation
                ),
                "requires_modal_preservation": sum(
                    1 for i in self.items if i.requires_modal_preservation
                ),
                "requires_recency_awareness": sum(
                    1 for i in self.items if i.requires_recency_awareness
                ),
                "requires_scope_boundary": sum(1 for i in self.items if i.requires_scope_boundary),
            },
        }


# ═══════════════════════════════════════════════════════════════════════════
# LOADER
# ═══════════════════════════════════════════════════════════════════════════


def load_golden_dataset(
    path: Optional[str] = None,
    version: str = "v1",
) -> GoldenDataset:
    """
    Load golden evaluation dataset from JSON file.

    Args:
        path: Explicit path to JSON file (overrides version-based lookup)
        version: Dataset version to load (default: "v1")

    Returns:
        GoldenDataset with parsed items

    Raises:
        FileNotFoundError: If dataset file doesn't exist
        ValueError: If dataset format is invalid
    """
    if path is None:
        datasets_dir = Path(__file__).parent / "datasets"
        path = str(datasets_dir / f"golden_{version}.json")

    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Golden dataset not found: {path}")

    with open(file_path, encoding="utf-8") as f:
        raw = json.load(f)

    if "items" not in raw:
        raise ValueError(f"Invalid golden dataset format: missing 'items' key in {path}")

    items = []
    for item_data in raw["items"]:
        item = GoldenItem(
            id=item_data["id"],
            question=item_data["question"],
            mode=EvalMode(item_data["mode"]),
            intent=EvalIntent(item_data["intent"]),
            difficulty=DifficultyLevel(item_data["difficulty"]),
            answer_fragments=item_data.get("answer_fragments", []),
            forbidden_fragments=item_data.get("forbidden_fragments", []),
            expected_sources=item_data.get("expected_sources", []),
            expected_law_refs=item_data.get("expected_law_refs", []),
            requires_verbatim_citation=item_data.get("requires_verbatim_citation", False),
            requires_modal_preservation=item_data.get("requires_modal_preservation", False),
            requires_recency_awareness=item_data.get("requires_recency_awareness", False),
            requires_scope_boundary=item_data.get("requires_scope_boundary", False),
            category=item_data.get("category", ""),
            notes=item_data.get("notes", ""),
        )
        items.append(item)

    return GoldenDataset(
        version=raw.get("version", version),
        description=raw.get("description", ""),
        items=items,
        created=raw.get("created", ""),
    )

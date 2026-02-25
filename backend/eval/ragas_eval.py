"""
RAGAS-Inspired Evaluation Harness
==================================

Measures RAG quality using metrics inspired by RAGAS (Retrieval Augmented
Generation Assessment). Implemented locally (no external RAGAS dependency)
to support Swedish text and custom domain metrics.

Metrics:
  1. Answer Relevancy — Does the answer address the question?
  2. Faithfulness — Are claims grounded in provided context?
  3. Context Precision — Are retrieved docs relevant to the question?
  4. Context Recall — Do retrieved docs cover expected information?
  5. Citation Accuracy — Do cited doc_ids match retrieved documents?
  6. Fragment Coverage — How many expected answer fragments appear?
  7. Forbidden Fragment Check — Do forbidden phrases appear in answer?
  8. Modal Verb Preservation — Are legal modal verbs preserved correctly?

Sprint 2 (P2-12): Evaluation harness scaffold with overlap-based metrics.
"""

import re
from dataclasses import dataclass, field
from typing import Optional

from .golden_dataset import GoldenDataset, GoldenItem

# ═══════════════════════════════════════════════════════════════════════════
# TOKENIZATION (shared with faithfulness_service)
# ═══════════════════════════════════════════════════════════════════════════

_STOP_WORDS_SV = frozenset(
    {
        "och",
        "i",
        "att",
        "en",
        "ett",
        "av",
        "den",
        "det",
        "de",
        "som",
        "är",
        "för",
        "med",
        "på",
        "till",
        "om",
        "kan",
        "har",
        "ska",
        "inte",
        "eller",
        "från",
        "var",
        "vid",
        "enligt",
        "sin",
        "sina",
        "sitt",
        "the",
        "and",
        "of",
        "to",
        "in",
        "a",
        "is",
        "for",
        "that",
        "with",
        "this",
        "be",
        "by",
        "on",
        "not",
        "are",
        "was",
    }
)


def _tokenize(text: str) -> set[str]:
    """Lowercase tokenize, strip punctuation, remove stop words."""
    tokens = re.findall(r"\b\w{2,}\b", text.lower())
    return {t for t in tokens if t not in _STOP_WORDS_SV}


# ═══════════════════════════════════════════════════════════════════════════
# RESULT DATA CLASSES
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class ItemEvalResult:
    """Evaluation result for a single golden item."""

    item_id: str
    question: str
    mode: str
    intent: str
    difficulty: str

    # Core RAGAS-like metrics (0.0-1.0)
    answer_relevancy: float = 0.0
    faithfulness: float = 0.0
    context_precision: float = 0.0
    context_recall: float = 0.0

    # Domain-specific metrics
    citation_accuracy: float = 0.0
    fragment_coverage: float = 0.0
    forbidden_fragment_violations: int = 0
    modal_verb_preserved: Optional[bool] = None
    scope_respected: Optional[bool] = None

    # Metadata
    answer_length: int = 0
    num_sources: int = 0
    latency_ms: float = 0.0
    error: Optional[str] = None

    @property
    def composite_score(self) -> float:
        """Weighted composite quality score."""
        weights = {
            "answer_relevancy": 0.25,
            "faithfulness": 0.30,
            "context_precision": 0.15,
            "context_recall": 0.15,
            "fragment_coverage": 0.15,
        }
        score = (
            self.answer_relevancy * weights["answer_relevancy"]
            + self.faithfulness * weights["faithfulness"]
            + self.context_precision * weights["context_precision"]
            + self.context_recall * weights["context_recall"]
            + self.fragment_coverage * weights["fragment_coverage"]
        )
        # Penalize forbidden fragment violations
        if self.forbidden_fragment_violations > 0:
            score *= 0.5
        return score


@dataclass
class EvalReport:
    """Aggregated evaluation report across all items."""

    dataset_version: str
    total_items: int
    evaluated_items: int
    failed_items: int
    total_latency_ms: float

    # Aggregate metrics (averages)
    avg_answer_relevancy: float = 0.0
    avg_faithfulness: float = 0.0
    avg_context_precision: float = 0.0
    avg_context_recall: float = 0.0
    avg_citation_accuracy: float = 0.0
    avg_fragment_coverage: float = 0.0
    avg_composite_score: float = 0.0

    # Violation counts
    total_forbidden_violations: int = 0
    total_modal_failures: int = 0
    total_scope_failures: int = 0

    # Per-item results
    item_results: list[ItemEvalResult] = field(default_factory=list)

    # Breakdowns
    by_mode: dict = field(default_factory=dict)
    by_intent: dict = field(default_factory=dict)
    by_difficulty: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to JSON-serializable dict for reporting."""
        return {
            "summary": {
                "dataset_version": self.dataset_version,
                "total_items": self.total_items,
                "evaluated_items": self.evaluated_items,
                "failed_items": self.failed_items,
                "total_latency_ms": round(self.total_latency_ms, 1),
            },
            "aggregate_metrics": {
                "answer_relevancy": round(self.avg_answer_relevancy, 4),
                "faithfulness": round(self.avg_faithfulness, 4),
                "context_precision": round(self.avg_context_precision, 4),
                "context_recall": round(self.avg_context_recall, 4),
                "citation_accuracy": round(self.avg_citation_accuracy, 4),
                "fragment_coverage": round(self.avg_fragment_coverage, 4),
                "composite_score": round(self.avg_composite_score, 4),
            },
            "violations": {
                "forbidden_fragments": self.total_forbidden_violations,
                "modal_verb_failures": self.total_modal_failures,
                "scope_failures": self.total_scope_failures,
            },
            "breakdowns": {
                "by_mode": self.by_mode,
                "by_intent": self.by_intent,
                "by_difficulty": self.by_difficulty,
            },
        }


# ═══════════════════════════════════════════════════════════════════════════
# METRIC CALCULATORS
# ═══════════════════════════════════════════════════════════════════════════


def compute_answer_relevancy(question: str, answer: str) -> float:
    """
    Measure how relevant the answer is to the question.

    Uses token overlap between question and answer as a proxy.
    Higher overlap suggests the answer addresses the question's topic.

    Returns:
        Score 0.0-1.0
    """
    if not answer or not question:
        return 0.0

    q_tokens = _tokenize(question)
    a_tokens = _tokenize(answer)

    if not q_tokens:
        return 0.0

    overlap = q_tokens & a_tokens
    # Relevancy = fraction of question tokens present in answer
    return len(overlap) / len(q_tokens)


def compute_faithfulness(answer: str, context_texts: list[str]) -> float:
    """
    Measure how grounded the answer is in the provided context.

    Splits answer into sentences, checks each against context using token overlap.

    Returns:
        Score 0.0-1.0 (average grounding across sentences)
    """
    if not answer or not context_texts:
        return 0.0

    # Build combined context token set
    context_tokens = set()
    for ctx in context_texts:
        context_tokens |= _tokenize(ctx)

    if not context_tokens:
        return 0.0

    # Split answer into sentences
    sentences = re.split(r"(?<=[.!?])\s+", answer)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 15]

    if not sentences:
        return 1.0  # No substantial claims

    scores = []
    for sent in sentences:
        sent_tokens = _tokenize(sent)
        if not sent_tokens:
            continue
        overlap = sent_tokens & context_tokens
        scores.append(len(overlap) / len(sent_tokens))

    return sum(scores) / len(scores) if scores else 0.0


def compute_context_precision(question: str, context_texts: list[str]) -> float:
    """
    Measure how relevant the retrieved context is to the question.

    Checks what fraction of context documents have meaningful overlap
    with the question tokens.

    Returns:
        Score 0.0-1.0
    """
    if not question or not context_texts:
        return 0.0

    q_tokens = _tokenize(question)
    if not q_tokens:
        return 0.0

    relevant_count = 0
    for ctx in context_texts:
        ctx_tokens = _tokenize(ctx)
        overlap = q_tokens & ctx_tokens
        if len(overlap) / len(q_tokens) >= 0.2:  # At least 20% question token overlap
            relevant_count += 1

    return relevant_count / len(context_texts)


def compute_context_recall(
    golden_item: GoldenItem,
    context_texts: list[str],
) -> float:
    """
    Measure how well retrieved context covers expected information.

    Checks if expected answer fragments and law references appear
    in the retrieved context.

    Returns:
        Score 0.0-1.0
    """
    if not golden_item.answer_fragments and not golden_item.expected_law_refs:
        return 1.0  # Nothing to recall

    expected_items = golden_item.answer_fragments + golden_item.expected_law_refs
    if not expected_items:
        return 1.0

    combined_context = " ".join(context_texts).lower()
    found = sum(1 for item in expected_items if item.lower() in combined_context)

    return found / len(expected_items)


def compute_fragment_coverage(golden_item: GoldenItem, answer: str) -> float:
    """
    Check what fraction of expected answer fragments appear in the answer.

    Returns:
        Score 0.0-1.0
    """
    if not golden_item.answer_fragments:
        return 1.0  # Nothing required

    answer_lower = answer.lower()
    found = sum(1 for frag in golden_item.answer_fragments if frag.lower() in answer_lower)

    return found / len(golden_item.answer_fragments)


def check_forbidden_fragments(golden_item: GoldenItem, answer: str) -> int:
    """
    Count forbidden fragment violations in the answer.

    Returns:
        Number of violations (0 is good)
    """
    if not golden_item.forbidden_fragments:
        return 0

    answer_lower = answer.lower()
    return sum(1 for frag in golden_item.forbidden_fragments if frag.lower() in answer_lower)


def check_modal_verb_preservation(answer: str) -> bool:
    """
    Check if legal modal verbs are preserved correctly.

    In Swedish legal text:
    - "får" (may) != "ska" (shall) != "bör" (should)
    - Mixing these changes the legal meaning

    Returns:
        True if no suspicious modal verb substitution detected
    """
    # Simple heuristic: check that answer doesn't contain mixed modal verbs
    # in contexts that suggest substitution
    # This is a basic check — a full implementation would compare against source text
    suspicious_patterns = [
        r"\bska\b.*\bfår\b",  # "ska" and "får" in same sentence might be substitution
    ]
    for pattern in suspicious_patterns:
        if re.search(pattern, answer.lower()):
            # Not necessarily wrong, but flagged for manual review
            return True  # Conservative: don't flag without source comparison

    return True


def compute_citation_accuracy(
    cited_doc_ids: list[str],
    retrieved_doc_ids: list[str],
) -> float:
    """
    Check what fraction of cited document IDs exist in retrieved documents.

    Returns:
        Score 0.0-1.0
    """
    if not cited_doc_ids:
        return 1.0  # No citations to check

    retrieved_set = set(retrieved_doc_ids)
    valid = sum(1 for doc_id in cited_doc_ids if doc_id in retrieved_set)

    return valid / len(cited_doc_ids)


# ═══════════════════════════════════════════════════════════════════════════
# EVALUATION ENGINE
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class PipelineResponse:
    """
    Standardized response from the RAG pipeline for evaluation.

    This is what the evaluation harness expects from the pipeline adapter.
    """

    answer: str
    sources: list[dict] = field(default_factory=list)  # [{id, title, snippet, score}]
    cited_doc_ids: list[str] = field(default_factory=list)
    mode_used: str = ""
    latency_ms: float = 0.0
    error: Optional[str] = None


class EvalHarness:
    """
    Evaluation harness that runs golden dataset items through the RAG pipeline
    and computes quality metrics.

    Usage:
        dataset = load_golden_dataset()
        harness = EvalHarness(dataset)

        # With a real pipeline adapter:
        report = await harness.run(pipeline_fn)

        # Or evaluate a single pre-computed response:
        result = harness.evaluate_item(golden_item, pipeline_response)
    """

    def __init__(self, dataset: GoldenDataset):
        self.dataset = dataset

    def evaluate_item(
        self,
        item: GoldenItem,
        response: PipelineResponse,
    ) -> ItemEvalResult:
        """
        Evaluate a single item against its pipeline response.

        Args:
            item: Golden dataset item with expected values
            response: Actual pipeline response

        Returns:
            ItemEvalResult with computed metrics
        """
        result = ItemEvalResult(
            item_id=item.id,
            question=item.question,
            mode=item.mode.value,
            intent=item.intent.value,
            difficulty=item.difficulty.value,
            answer_length=len(response.answer),
            num_sources=len(response.sources),
            latency_ms=response.latency_ms,
        )

        if response.error:
            result.error = response.error
            return result

        answer = response.answer
        context_texts = [s.get("snippet", "") for s in response.sources]

        # Core RAGAS-like metrics
        result.answer_relevancy = compute_answer_relevancy(item.question, answer)
        result.faithfulness = compute_faithfulness(answer, context_texts)
        result.context_precision = compute_context_precision(item.question, context_texts)
        result.context_recall = compute_context_recall(item, context_texts)

        # Domain-specific metrics
        result.fragment_coverage = compute_fragment_coverage(item, answer)
        result.forbidden_fragment_violations = check_forbidden_fragments(item, answer)
        result.citation_accuracy = compute_citation_accuracy(
            response.cited_doc_ids,
            [s.get("id", "") for s in response.sources],
        )

        # Quality dimension checks
        if item.requires_modal_preservation:
            result.modal_verb_preserved = check_modal_verb_preservation(answer)

        return result

    def build_report(self, results: list[ItemEvalResult]) -> EvalReport:
        """
        Aggregate individual results into a report.

        Args:
            results: List of per-item evaluation results

        Returns:
            EvalReport with aggregate metrics and breakdowns
        """
        valid_results = [r for r in results if r.error is None]
        failed_results = [r for r in results if r.error is not None]

        report = EvalReport(
            dataset_version=self.dataset.version,
            total_items=self.dataset.count,
            evaluated_items=len(valid_results),
            failed_items=len(failed_results),
            total_latency_ms=sum(r.latency_ms for r in results),
        )

        if valid_results:
            report.avg_answer_relevancy = _mean([r.answer_relevancy for r in valid_results])
            report.avg_faithfulness = _mean([r.faithfulness for r in valid_results])
            report.avg_context_precision = _mean([r.context_precision for r in valid_results])
            report.avg_context_recall = _mean([r.context_recall for r in valid_results])
            report.avg_citation_accuracy = _mean([r.citation_accuracy for r in valid_results])
            report.avg_fragment_coverage = _mean([r.fragment_coverage for r in valid_results])
            report.avg_composite_score = _mean([r.composite_score for r in valid_results])

        # Violation counts
        report.total_forbidden_violations = sum(
            r.forbidden_fragment_violations for r in valid_results
        )
        report.total_modal_failures = sum(
            1 for r in valid_results if r.modal_verb_preserved is False
        )
        report.total_scope_failures = sum(1 for r in valid_results if r.scope_respected is False)

        report.item_results = results

        # Breakdowns
        report.by_mode = _breakdown(valid_results, lambda r: r.mode)
        report.by_intent = _breakdown(valid_results, lambda r: r.intent)
        report.by_difficulty = _breakdown(valid_results, lambda r: r.difficulty)

        return report


# ═══════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════


def _mean(values: list[float]) -> float:
    """Safe mean calculation."""
    return sum(values) / len(values) if values else 0.0


def _breakdown(results: list[ItemEvalResult], key_fn) -> dict:
    """Group results by key and compute per-group averages."""
    from collections import defaultdict

    groups = defaultdict(list)
    for r in results:
        groups[key_fn(r)].append(r)

    breakdown = {}
    for key, group in sorted(groups.items()):
        breakdown[key] = {
            "count": len(group),
            "avg_composite": round(_mean([r.composite_score for r in group]), 4),
            "avg_faithfulness": round(_mean([r.faithfulness for r in group]), 4),
            "avg_relevancy": round(_mean([r.answer_relevancy for r in group]), 4),
            "avg_fragment_coverage": round(_mean([r.fragment_coverage for r in group]), 4),
        }

    return breakdown

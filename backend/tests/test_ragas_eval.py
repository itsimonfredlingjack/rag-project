"""
Tests for RAGAS-inspired Evaluation Harness.

Tests cover:
  - Individual metric calculations
  - Item-level evaluation
  - Report aggregation
  - Edge cases (empty inputs, missing data)
"""

import pytest

from eval.golden_dataset import (
    DifficultyLevel,
    EvalIntent,
    EvalMode,
    GoldenItem,
    load_golden_dataset,
)
from eval.ragas_eval import (
    EvalHarness,
    PipelineResponse,
    check_forbidden_fragments,
    check_modal_verb_preservation,
    compute_answer_relevancy,
    compute_citation_accuracy,
    compute_context_precision,
    compute_context_recall,
    compute_faithfulness,
    compute_fragment_coverage,
)


# ═══════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════


def _item(
    id="G999",
    question="Vad säger RF om yttrandefrihet?",
    mode="evidence",
    intent="legal_text",
    answer_fragments=None,
    forbidden_fragments=None,
    expected_sources=None,
    expected_law_refs=None,
    requires_modal_preservation=False,
) -> GoldenItem:
    """Create a test golden item."""
    return GoldenItem(
        id=id,
        question=question,
        mode=EvalMode(mode),
        intent=EvalIntent(intent),
        difficulty=DifficultyLevel.MEDIUM,
        answer_fragments=answer_fragments or [],
        forbidden_fragments=forbidden_fragments or [],
        expected_sources=expected_sources or [],
        expected_law_refs=expected_law_refs or [],
        requires_modal_preservation=requires_modal_preservation,
        category="test",
    )


def _response(
    answer="",
    sources=None,
    cited_doc_ids=None,
    error=None,
) -> PipelineResponse:
    """Create a test pipeline response."""
    return PipelineResponse(
        answer=answer,
        sources=sources or [],
        cited_doc_ids=cited_doc_ids or [],
        error=error,
    )


# ═══════════════════════════════════════════════════════════════════════════
# ANSWER RELEVANCY
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestAnswerRelevancy:
    """Tests for answer relevancy scoring."""

    def test_high_relevancy(self):
        score = compute_answer_relevancy(
            question="Vad säger RF om yttrandefrihet?",
            answer="RF säger att yttrandefrihet skyddas i grundlagen.",
        )
        assert score > 0.3

    def test_low_relevancy(self):
        score = compute_answer_relevancy(
            question="Vad säger RF om yttrandefrihet?",
            answer="Bananer är gula frukter som växer i tropiska klimat.",
        )
        assert score < 0.2

    def test_empty_answer(self):
        assert compute_answer_relevancy("test?", "") == 0.0

    def test_empty_question(self):
        assert compute_answer_relevancy("", "test answer") == 0.0


# ═══════════════════════════════════════════════════════════════════════════
# FAITHFULNESS
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestFaithfulness:
    """Tests for faithfulness scoring."""

    def test_grounded_answer(self):
        score = compute_faithfulness(
            answer="Yttrandefrihet innebär rätten att fritt uttrycka tankar.",
            context_texts=["Yttrandefrihet innebär rätten att fritt uttrycka tankar och åsikter."],
        )
        assert score > 0.5

    def test_ungrounded_answer(self):
        score = compute_faithfulness(
            answer="AI revolutionerar demokratiska processer globalt och förändrar allt.",
            context_texts=["Personuppgiftslagen reglerar behandling av personuppgifter."],
        )
        assert score < 0.4

    def test_empty_answer(self):
        assert compute_faithfulness("", ["context"]) == 0.0

    def test_empty_context(self):
        assert compute_faithfulness("test answer", []) == 0.0

    def test_multiple_contexts(self):
        score = compute_faithfulness(
            answer="Yttrandefrihet skyddas av grundlagen. GDPR reglerar personuppgifter.",
            context_texts=[
                "Yttrandefrihet skyddas i grundlagen.",
                "GDPR reglerar behandling av personuppgifter i EU.",
            ],
        )
        assert score > 0.4


# ═══════════════════════════════════════════════════════════════════════════
# CONTEXT PRECISION
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestContextPrecision:
    """Tests for context precision scoring."""

    def test_all_relevant(self):
        score = compute_context_precision(
            question="Vad säger RF om yttrandefrihet?",
            context_texts=[
                "RF 2 kap. reglerar yttrandefrihet som grundläggande frihet.",
                "Grundlagen skyddar yttrandefrihet enligt RF.",
            ],
        )
        assert score > 0.5

    def test_no_relevant(self):
        score = compute_context_precision(
            question="Vad säger RF om yttrandefrihet?",
            context_texts=[
                "Bananer importeras från Sydamerika.",
                "Fotboll är en populär sport i Sverige.",
            ],
        )
        assert score == 0.0

    def test_empty_inputs(self):
        assert compute_context_precision("", []) == 0.0


# ═══════════════════════════════════════════════════════════════════════════
# CONTEXT RECALL
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestContextRecall:
    """Tests for context recall scoring."""

    def test_full_recall(self):
        item = _item(
            answer_fragments=["yttrandefrihet", "grundlagen"],
            expected_law_refs=["RF 2 kap."],
        )
        score = compute_context_recall(
            item,
            ["RF 2 kap. om yttrandefrihet i grundlagen"],
        )
        assert score == 1.0

    def test_partial_recall(self):
        item = _item(
            answer_fragments=["yttrandefrihet", "grundlagen", "skydd"],
            expected_law_refs=["RF 2 kap."],
        )
        score = compute_context_recall(
            item,
            ["Yttrandefrihet skyddas i grundlagen."],
        )
        # "RF 2 kap." is missing from context
        assert 0.0 < score < 1.0

    def test_no_expected_items(self):
        item = _item(answer_fragments=[], expected_law_refs=[])
        score = compute_context_recall(item, ["any context"])
        assert score == 1.0  # Nothing to recall


# ═══════════════════════════════════════════════════════════════════════════
# FRAGMENT COVERAGE
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestFragmentCoverage:
    """Tests for answer fragment coverage."""

    def test_full_coverage(self):
        item = _item(answer_fragments=["yttrandefrihet", "grundlagen"])
        score = compute_fragment_coverage(item, "Yttrandefrihet skyddas av grundlagen.")
        assert score == 1.0

    def test_partial_coverage(self):
        item = _item(answer_fragments=["yttrandefrihet", "grundlagen", "proportionalitet"])
        score = compute_fragment_coverage(item, "Yttrandefrihet skyddas av grundlagen.")
        assert abs(score - 2 / 3) < 0.01

    def test_no_coverage(self):
        item = _item(answer_fragments=["yttrandefrihet"])
        score = compute_fragment_coverage(item, "Bananer är gula.")
        assert score == 0.0

    def test_no_required_fragments(self):
        item = _item(answer_fragments=[])
        score = compute_fragment_coverage(item, "Any answer")
        assert score == 1.0


# ═══════════════════════════════════════════════════════════════════════════
# FORBIDDEN FRAGMENTS
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestForbiddenFragments:
    """Tests for forbidden fragment detection."""

    def test_no_violations(self):
        item = _item(forbidden_fragments=["First Amendment"])
        count = check_forbidden_fragments(item, "RF 2 kap. om yttrandefrihet.")
        assert count == 0

    def test_violation_detected(self):
        item = _item(forbidden_fragments=["First Amendment"])
        count = check_forbidden_fragments(item, "Yttrandefrihet liknar First Amendment i USA.")
        assert count == 1

    def test_case_insensitive(self):
        item = _item(forbidden_fragments=["grundlagen"])
        count = check_forbidden_fragments(item, "GRUNDLAGEN säger att...")
        assert count == 1

    def test_no_forbidden_defined(self):
        item = _item(forbidden_fragments=[])
        count = check_forbidden_fragments(item, "Any text")
        assert count == 0


# ═══════════════════════════════════════════════════════════════════════════
# CITATION ACCURACY
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestCitationAccuracy:
    """Tests for citation accuracy scoring."""

    def test_all_valid(self):
        score = compute_citation_accuracy(
            cited_doc_ids=["doc_1", "doc_2"],
            retrieved_doc_ids=["doc_1", "doc_2", "doc_3"],
        )
        assert score == 1.0

    def test_some_invalid(self):
        score = compute_citation_accuracy(
            cited_doc_ids=["doc_1", "doc_4"],
            retrieved_doc_ids=["doc_1", "doc_2", "doc_3"],
        )
        assert score == 0.5

    def test_all_invalid(self):
        score = compute_citation_accuracy(
            cited_doc_ids=["doc_X"],
            retrieved_doc_ids=["doc_1", "doc_2"],
        )
        assert score == 0.0

    def test_no_citations(self):
        score = compute_citation_accuracy([], ["doc_1"])
        assert score == 1.0  # Nothing to check


# ═══════════════════════════════════════════════════════════════════════════
# MODAL VERB PRESERVATION
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestModalVerbPreservation:
    """Tests for modal verb preservation check."""

    def test_clean_text_passes(self):
        assert check_modal_verb_preservation("Myndigheten ska följa lagen.") is True

    def test_simple_modal_passes(self):
        assert check_modal_verb_preservation("Kommunen får besluta om detta.") is True


# ═══════════════════════════════════════════════════════════════════════════
# EVAL HARNESS INTEGRATION
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestEvalHarness:
    """Tests for the evaluation harness."""

    @pytest.fixture
    def dataset(self):
        return load_golden_dataset(version="v1")

    @pytest.fixture
    def harness(self, dataset):
        return EvalHarness(dataset)

    def test_evaluate_single_item(self, harness, dataset):
        """Evaluate a single item with a mock response."""
        item = dataset.items[0]  # G001
        response = _response(
            answer="Yttrandefrihet innebär rätten att fritt uttrycka tankar enligt RF 2 kap. 1 §.",
            sources=[
                {
                    "id": "rf_2_1",
                    "title": "RF 2 kap. 1 §",
                    "snippet": "Var och en är gentemot det allmänna tillförsäkrad yttrandefrihet: frihet att i tal, skrift eller bild eller på annat sätt meddela upplysningar samt uttrycka tankar, åsikter och känslor.",
                    "score": 0.92,
                }
            ],
            cited_doc_ids=["rf_2_1"],
        )

        result = harness.evaluate_item(item, response)

        assert result.item_id == "G001"
        assert result.answer_relevancy > 0.0
        assert result.faithfulness > 0.0
        assert result.fragment_coverage > 0.0
        assert result.composite_score > 0.0
        assert result.error is None

    def test_evaluate_error_response(self, harness, dataset):
        """Error response should be flagged."""
        item = dataset.items[0]
        response = _response(error="LLM timeout")

        result = harness.evaluate_item(item, response)

        assert result.error == "LLM timeout"
        assert result.composite_score == 0.0

    def test_build_report(self, harness, dataset):
        """Report aggregation from multiple results."""
        results = []
        for item in dataset.items[:5]:
            response = _response(
                answer=f"Svar om {item.question}: yttrandefrihet grundlagen RF",
                sources=[{"id": "doc_1", "snippet": "yttrandefrihet grundlagen RF", "score": 0.8}],
            )
            results.append(harness.evaluate_item(item, response))

        report = harness.build_report(results)

        assert report.total_items == dataset.count
        assert report.evaluated_items == 5
        assert report.failed_items == 0
        assert report.avg_composite_score >= 0.0
        assert "evidence" in report.by_mode or "assist" in report.by_mode

    def test_report_to_dict(self, harness, dataset):
        """Report serializes to dict correctly."""
        item = dataset.items[0]
        response = _response(answer="Test", sources=[])
        result = harness.evaluate_item(item, response)
        report = harness.build_report([result])
        d = report.to_dict()

        assert "summary" in d
        assert "aggregate_metrics" in d
        assert "violations" in d
        assert "breakdowns" in d

    def test_composite_score_penalizes_forbidden(self, harness):
        """Forbidden fragment violations halve the composite score."""
        item = _item(
            forbidden_fragments=["First Amendment"],
            answer_fragments=["yttrandefrihet"],
        )

        # Good response
        good_response = _response(
            answer="Yttrandefrihet skyddas i grundlagen.",
            sources=[{"id": "d1", "snippet": "yttrandefrihet grundlagen", "score": 0.9}],
        )
        good_result = harness.evaluate_item(item, good_response)

        # Bad response (with forbidden fragment)
        bad_response = _response(
            answer="Yttrandefrihet liknar First Amendment.",
            sources=[{"id": "d1", "snippet": "yttrandefrihet grundlagen", "score": 0.9}],
        )
        bad_result = harness.evaluate_item(item, bad_response)

        # Bad should score lower due to forbidden violation penalty
        if good_result.composite_score > 0:
            assert bad_result.composite_score < good_result.composite_score

    def test_evaluate_chat_item(self, harness):
        """CHAT items (smalltalk) with forbidden fragments should be clean."""
        item = _item(
            mode="chat",
            intent="smalltalk",
            question="Hej! Hur mår du?",
            forbidden_fragments=["RF", "lag"],
        )
        response = _response(answer="Hej! Jag mår bra, tack!")

        result = harness.evaluate_item(item, response)
        assert result.forbidden_fragment_violations == 0

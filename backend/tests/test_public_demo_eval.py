"""AIS-155 public demo eval harness tests."""

from __future__ import annotations

import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "backend" / "scripts" / "run_public_demo_eval.py"
DATASET_PATH = REPO_ROOT / "backend" / "evals" / "public_demo_questions.jsonl"


def _load_eval_module():
    spec = importlib.util.spec_from_file_location("run_public_demo_eval", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_public_demo_dataset_has_required_shape() -> None:
    module = _load_eval_module()

    questions = module.load_questions(DATASET_PATH)
    validation = module.validate_dataset(questions)

    assert validation["total"] == 30
    assert validation["category_counts"] == {
        "easy_lookup": 10,
        "medium_synthesis": 10,
        "should_refuse": 5,
        "adversarial_source_boundary": 5,
    }
    assert validation["expected_refusals"] == 10


def test_summary_metrics_count_hits_rates_and_critical_invariants() -> None:
    module = _load_eval_module()
    rows = [
        {
            "id": "easy_001",
            "category": "easy_lookup",
            "expected_behavior": "answer",
            "retrieval_hit_5": True,
            "retrieval_hit_10": True,
            "success": True,
            "citation_present": True,
            "unsupported_answer": False,
            "leakage_count": 0,
            "uncited_public_answer": False,
            "answer_when_not_ready": False,
            "tokens_generated": 11,
            "tokens_generated_source": "llm_stats",
            "latency_ms": 10.0,
            "critical_failures": [],
        },
        {
            "id": "medium_001",
            "category": "medium_synthesis",
            "expected_behavior": "answer",
            "retrieval_hit_5": False,
            "retrieval_hit_10": True,
            "success": True,
            "citation_present": False,
            "unsupported_answer": True,
            "leakage_count": 1,
            "uncited_public_answer": True,
            "answer_when_not_ready": False,
            "tokens_generated": 7,
            "tokens_generated_source": "answer_word_count_approx",
            "latency_ms": 20.0,
            "critical_failures": ["non_public_source_leakage", "uncited_successful_public_answer"],
        },
        {
            "id": "refuse_001",
            "category": "should_refuse",
            "expected_behavior": "refuse",
            "expected_refusal_reason": "legal_advice",
            "refusal_reason": "legal_advice",
            "retrieval_hit_5": None,
            "retrieval_hit_10": None,
            "success": False,
            "citation_present": False,
            "unsupported_answer": False,
            "leakage_count": 0,
            "uncited_public_answer": False,
            "answer_when_not_ready": False,
            "tokens_generated": 9,
            "tokens_generated_source": "answer_word_count_approx",
            "latency_ms": 30.0,
            "critical_failures": [],
        },
        {
            "id": "boundary_001",
            "category": "adversarial_source_boundary",
            "expected_behavior": "refuse",
            "expected_refusal_reason": "source_boundary",
            "refusal_reason": "no_context",
            "retrieval_hit_5": None,
            "retrieval_hit_10": None,
            "success": False,
            "citation_present": False,
            "unsupported_answer": False,
            "leakage_count": 0,
            "uncited_public_answer": False,
            "answer_when_not_ready": False,
            "tokens_generated": 4,
            "tokens_generated_source": "answer_word_count_approx",
            "latency_ms": 40.0,
            "critical_failures": ["refusal_reason_mismatch"],
        },
        {
            "id": "not_ready_001",
            "category": "easy_lookup",
            "expected_behavior": "answer",
            "retrieval_hit_5": False,
            "retrieval_hit_10": False,
            "success": True,
            "citation_present": True,
            "unsupported_answer": False,
            "leakage_count": 0,
            "uncited_public_answer": False,
            "answer_when_not_ready": True,
            "tokens_generated": 5,
            "tokens_generated_source": "llm_stats",
            "latency_ms": 50.0,
            "critical_failures": ["answer_when_not_ready"],
        },
    ]

    summary = module.summarize_rows(rows)

    assert summary["retrieval_hit@5"] == 1 / 3
    assert summary["retrieval_hit@10"] == 2 / 3
    assert summary["citation_present_rate"] == 2 / 3
    assert summary["unsupported_answer_rate"] == 1 / 3
    assert summary["refusal_correctness"] == 0.5
    assert summary["latency_p50"] == 30.0
    assert summary["latency_p95"] == 50.0
    assert summary["tokens_generated"] == 36
    assert summary["tokens_generated_approximation_count"] == 3
    assert summary["leakage_count"] == 1
    assert summary["uncited_public_answer_count"] == 1
    assert summary["answer_when_not_ready_count"] == 1
    assert summary["critical_failure_count"] == 4
    assert summary["critical_invariants_passed"] is False


def test_exit_code_is_nonzero_when_critical_invariants_fail() -> None:
    module = _load_eval_module()

    assert module.exit_code_for_summary({"critical_invariants_passed": True}) == 0
    assert module.exit_code_for_summary({"critical_invariants_passed": False}) == 1

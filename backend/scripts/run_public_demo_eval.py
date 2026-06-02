#!/usr/bin/env python3
"""Run the AIS-155 public Riksdagen BM25 demo eval suite."""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import statistics
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

PUBLIC_RIKSDAG_PROFILE_NAME = "public-riksdag-demo"
os.environ["CONST_PROFILE"] = PUBLIC_RIKSDAG_PROFILE_NAME

from app.services.bm25_service import get_bm25_service  # noqa: E402
from app.services.config_service import ConfigService, PUBLIC_RIKSDAG_PROFILE  # noqa: E402
from app.services.orchestrator_service import (  # noqa: E402
    OrchestratorService,
    build_dependency_readiness,
)
from app.services.public_bm25_query_service import (  # noqa: E402
    PUBLIC_QUERY_MODE,
    normalize_swedish_query,
)
from app.shared.public_source_guard import validate_public_record  # noqa: E402


DEFAULT_DATASET_PATH = BACKEND_ROOT / "evals" / "public_demo_questions.jsonl"
DEFAULT_RESULTS_DIR = BACKEND_ROOT / "evals" / "results"
REQUIRED_CATEGORY_COUNTS = {
    "easy_lookup": 10,
    "medium_synthesis": 10,
    "should_refuse": 5,
    "adversarial_source_boundary": 5,
}
EXPECTED_BEHAVIORS = {"answer", "refuse"}


def load_questions(path: Path) -> list[dict[str, Any]]:
    """Load JSONL public demo eval questions."""
    questions: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                question = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSONL row: {exc}") from exc
            question["_line_number"] = line_number
            questions.append(question)
    return questions


def validate_dataset(questions: list[dict[str, Any]]) -> dict[str, Any]:
    """Validate the committed dataset shape for AIS-155."""
    errors: list[str] = []
    ids: list[str] = []
    category_counts = Counter()
    expected_refusals = 0

    for index, question in enumerate(questions, start=1):
        row_id = str(question.get("id", "")).strip()
        category = str(question.get("category", "")).strip()
        expected_behavior = str(question.get("expected_behavior", "")).strip()
        text = str(question.get("question", "")).strip()
        expected_ids = question.get("expected_document_ids", [])

        if not row_id:
            errors.append(f"row {index}: missing id")
        ids.append(row_id)

        if category not in REQUIRED_CATEGORY_COUNTS:
            errors.append(f"{row_id or index}: invalid category {category!r}")
        category_counts[category] += 1

        if not text:
            errors.append(f"{row_id or index}: missing question")

        if expected_behavior not in EXPECTED_BEHAVIORS:
            errors.append(f"{row_id or index}: invalid expected_behavior {expected_behavior!r}")

        if expected_behavior == "refuse":
            expected_refusals += 1
            if not question.get("expected_refusal_reason"):
                errors.append(f"{row_id or index}: refusal row missing expected_refusal_reason")
        elif expected_behavior == "answer" and not expected_ids:
            errors.append(f"{row_id or index}: answer row missing expected_document_ids")

        if expected_ids and not isinstance(expected_ids, list):
            errors.append(f"{row_id or index}: expected_document_ids must be a list")

    duplicate_ids = sorted(row_id for row_id, count in Counter(ids).items() if row_id and count > 1)
    for row_id in duplicate_ids:
        errors.append(f"duplicate id {row_id!r}")

    expected_total = sum(REQUIRED_CATEGORY_COUNTS.values())
    if len(questions) != expected_total:
        errors.append(f"expected {expected_total} rows, got {len(questions)}")

    normalized_counts = {
        category: category_counts.get(category, 0) for category in REQUIRED_CATEGORY_COUNTS
    }
    if normalized_counts != REQUIRED_CATEGORY_COUNTS:
        errors.append(f"category counts mismatch: {normalized_counts}")

    return {
        "total": len(questions),
        "expected_total": expected_total,
        "category_counts": normalized_counts,
        "expected_refusals": expected_refusals,
        "duplicate_ids": duplicate_ids,
        "valid": not errors,
        "errors": errors,
    }


def summarize_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Calculate AIS-155 metrics from per-question result rows."""
    successful_rows = [row for row in rows if row.get("success") is True]
    expected_refusal_rows = [row for row in rows if row.get("expected_behavior") == "refuse"]
    hit5_rows = [row for row in rows if row.get("retrieval_hit_5") is not None]
    hit10_rows = [row for row in rows if row.get("retrieval_hit_10") is not None]
    latencies = [float(row["latency_ms"]) for row in rows if row.get("latency_ms") is not None]
    critical_failures = [failure for row in rows for failure in row.get("critical_failures", [])]

    return {
        "question_count": len(rows),
        "category_counts": dict(Counter(row.get("category") for row in rows)),
        "retrieval_hit@5": _rate(hit5_rows, "retrieval_hit_5"),
        "retrieval_hit@10": _rate(hit10_rows, "retrieval_hit_10"),
        "citation_present_rate": _rate(successful_rows, "citation_present"),
        "unsupported_answer_rate": _rate(successful_rows, "unsupported_answer"),
        "refusal_correctness": _refusal_correctness(expected_refusal_rows),
        "latency_p50": _latency_p50(latencies),
        "latency_p95": _nearest_rank_percentile(latencies, 95),
        "tokens_generated": sum(int(row.get("tokens_generated") or 0) for row in rows),
        "tokens_generated_approximation_count": sum(
            1 for row in rows if row.get("tokens_generated_source") == "answer_word_count_approx"
        ),
        "leakage_count": sum(int(row.get("leakage_count") or 0) for row in rows),
        "uncited_public_answer_count": sum(
            1 for row in rows if row.get("uncited_public_answer") is True
        ),
        "answer_when_not_ready_count": sum(
            1 for row in rows if row.get("answer_when_not_ready") is True
        ),
        "runtime_error_count": sum(1 for row in rows if row.get("runtime_error")),
        "critical_failure_count": len(critical_failures),
        "critical_failures": dict(Counter(critical_failures)),
        "critical_invariants_passed": len(critical_failures) == 0,
    }


def exit_code_for_summary(summary: dict[str, Any]) -> int:
    """Return process exit code for a completed eval summary."""
    return 0 if summary.get("critical_invariants_passed") is True else 1


async def run_eval(
    *,
    dataset_path: Path,
    output_path: Path,
    limit: int | None = None,
) -> dict[str, Any]:
    """Run the public demo eval and write a machine-readable artifact."""
    questions = load_questions(dataset_path)
    dataset_validation = validate_dataset(questions)
    if not dataset_validation["valid"]:
        raise ValueError(
            "Invalid public demo eval dataset: " + "; ".join(dataset_validation["errors"])
        )

    selected_questions = questions[:limit] if limit is not None else questions
    started_at = datetime.now(timezone.utc).isoformat()
    orchestrator = _build_public_orchestrator()
    await orchestrator.initialize()

    rows: list[dict[str, Any]] = []
    try:
        for question in selected_questions:
            rows.append(await _run_question(orchestrator, question))
    finally:
        await orchestrator.close()

    summary = summarize_rows(rows)
    artifact = {
        "run": {
            "profile": PUBLIC_RIKSDAG_PROFILE,
            "retrieval_mode": PUBLIC_QUERY_MODE,
            "dataset_path": str(dataset_path),
            "output_path": str(output_path),
            "started_at": started_at,
            "question_count": len(rows),
            "limited_to": limit,
        },
        "dataset_validation": dataset_validation,
        "metric_notes": {
            "tokens_generated": (
                "Uses RAGPipelineMetrics.tokens_generated when the LLM wrapper returns it; "
                "otherwise uses answer whitespace token count as a documented approximation."
            ),
            "unsupported_answer_rate": (
                "Counts successful answers with no citations, no public sources, or any "
                "non-public source leakage."
            ),
            "retrieval_hit@k": (
                "Counts whether any expected_document_ids appear in the same public BM25 "
                "top-k query used by the public path."
            ),
        },
        "summary": summary,
        "rows": rows,
    }
    _write_json(output_path, artifact)
    return artifact


async def _run_question(
    orchestrator: OrchestratorService, question: dict[str, Any]
) -> dict[str, Any]:
    expected_ids = [str(value) for value in question.get("expected_document_ids", [])]
    expected_behavior = str(question["expected_behavior"])
    readiness = await build_dependency_readiness(orchestrator)
    readiness_can_answer = bool(readiness.get("can_answer"))
    retrieved_ids, retrieval_error = _public_bm25_top_document_ids(
        orchestrator,
        question=str(question["question"]),
        enabled=readiness_can_answer and bool(expected_ids),
    )

    started = time.perf_counter()
    runtime_error = None
    result = None
    try:
        result = await orchestrator.process_query(str(question["question"]), mode="evidence")
    except Exception as exc:  # noqa: BLE001 - eval rows should survive per-question failures.
        runtime_error = f"{exc.__class__.__name__}: {exc}"
    elapsed_ms = (time.perf_counter() - started) * 1000

    if result is None:
        row = _base_error_row(
            question=question,
            readiness=readiness,
            retrieved_ids=retrieved_ids,
            retrieval_error=retrieval_error,
            runtime_error=runtime_error or "unknown runtime error",
            elapsed_ms=elapsed_ms,
        )
    else:
        row = _row_from_result(
            question=question,
            result=result,
            readiness=readiness,
            retrieved_ids=retrieved_ids,
            retrieval_error=retrieval_error,
            elapsed_ms=elapsed_ms,
        )

    critical_failures = _critical_failures(row, expected_behavior=expected_behavior)
    row["critical_failures"] = critical_failures
    return row


def _row_from_result(
    *,
    question: dict[str, Any],
    result: Any,
    readiness: dict[str, Any],
    retrieved_ids: list[str],
    retrieval_error: str | None,
    elapsed_ms: float,
) -> dict[str, Any]:
    expected_ids = [str(value) for value in question.get("expected_document_ids", [])]
    sources = list(getattr(result, "sources", []) or [])
    leaked_sources = _leaked_sources(sources)
    citation_present = _citation_present(result)
    success = bool(getattr(result, "success", False))
    tokens_generated, token_source = _tokens_generated(result)
    latency_ms = _latency_ms(result, elapsed_ms)

    return {
        "id": question["id"],
        "category": question["category"],
        "question": question["question"],
        "expected_behavior": question["expected_behavior"],
        "expected_refusal_reason": question.get("expected_refusal_reason"),
        "expected_document_ids": expected_ids,
        "retrieved_document_ids_top10": retrieved_ids[:10],
        "retrieval_hit_5": _retrieval_hit(retrieved_ids, expected_ids, 5),
        "retrieval_hit_10": _retrieval_hit(retrieved_ids, expected_ids, 10),
        "retrieval_error": retrieval_error,
        "success": success,
        "refusal_reason": getattr(result, "refusal_reason", None),
        "answer_excerpt": _answer_excerpt(getattr(result, "answer", "")),
        "source_document_ids": [_source_id(source) for source in sources],
        "source_count": len(sources),
        "citation_count": len(getattr(result, "citations", []) or []),
        "citation_present": citation_present,
        "leakage_count": len(leaked_sources),
        "leaked_sources": leaked_sources,
        "unsupported_answer": bool(
            success and (not citation_present or not sources or bool(leaked_sources))
        ),
        "uncited_public_answer": bool(success and not citation_present),
        "readiness_status": readiness.get("status"),
        "readiness_can_answer": bool(readiness.get("can_answer")),
        "answer_when_not_ready": bool(success and not readiness.get("can_answer")),
        "latency_ms": latency_ms,
        "tokens_generated": tokens_generated,
        "tokens_generated_source": token_source,
        "runtime_error": None,
    }


def _base_error_row(
    *,
    question: dict[str, Any],
    readiness: dict[str, Any],
    retrieved_ids: list[str],
    retrieval_error: str | None,
    runtime_error: str,
    elapsed_ms: float,
) -> dict[str, Any]:
    expected_ids = [str(value) for value in question.get("expected_document_ids", [])]
    return {
        "id": question["id"],
        "category": question["category"],
        "question": question["question"],
        "expected_behavior": question["expected_behavior"],
        "expected_refusal_reason": question.get("expected_refusal_reason"),
        "expected_document_ids": expected_ids,
        "retrieved_document_ids_top10": retrieved_ids[:10],
        "retrieval_hit_5": _retrieval_hit(retrieved_ids, expected_ids, 5),
        "retrieval_hit_10": _retrieval_hit(retrieved_ids, expected_ids, 10),
        "retrieval_error": retrieval_error,
        "success": False,
        "refusal_reason": None,
        "answer_excerpt": "",
        "source_document_ids": [],
        "source_count": 0,
        "citation_count": 0,
        "citation_present": False,
        "leakage_count": 0,
        "leaked_sources": [],
        "unsupported_answer": False,
        "uncited_public_answer": False,
        "readiness_status": readiness.get("status"),
        "readiness_can_answer": bool(readiness.get("can_answer")),
        "answer_when_not_ready": False,
        "latency_ms": round(elapsed_ms, 2),
        "tokens_generated": 0,
        "tokens_generated_source": "unavailable",
        "runtime_error": runtime_error,
    }


def _critical_failures(row: dict[str, Any], *, expected_behavior: str) -> list[str]:
    failures: list[str] = []
    if row.get("leakage_count", 0) > 0:
        failures.append("non_public_source_leakage")
    if row.get("uncited_public_answer") is True:
        failures.append("uncited_successful_public_answer")
    if row.get("answer_when_not_ready") is True:
        failures.append("answer_when_not_ready")
    if expected_behavior == "refuse" and row.get("refusal_reason") != row.get(
        "expected_refusal_reason"
    ):
        failures.append("refusal_reason_mismatch")
    if row.get("runtime_error"):
        failures.append("runtime_error")
    return failures


def _public_bm25_top_document_ids(
    orchestrator: OrchestratorService,
    *,
    question: str,
    enabled: bool,
) -> tuple[list[str], str | None]:
    if not enabled:
        return [], None

    try:
        bm25 = get_bm25_service(
            index_path=str(getattr(orchestrator.config, "bm25_index_path", "")),
            public_guard_enabled=True,
        )
        rows = bm25.search(
            normalize_swedish_query(question),
            k=10,
            return_docs=True,
            use_compound_splitting=True,
        )
    except Exception as exc:  # noqa: BLE001 - keep eval row-level evidence.
        return [], f"{exc.__class__.__name__}: {exc}"

    return [_row_document_id(row) for row in rows if _row_document_id(row)], None


def _row_document_id(row: dict[str, Any]) -> str:
    metadata = row.get("metadata")
    metadata_id = metadata.get("document_id") if isinstance(metadata, dict) else None
    return str(row.get("document_id") or metadata_id or row.get("id") or "").strip()


def _retrieval_hit(retrieved_ids: list[str], expected_ids: list[str], k: int) -> bool | None:
    if not expected_ids:
        return None
    return bool(set(retrieved_ids[:k]) & set(expected_ids))


def _leaked_sources(sources: list[Any]) -> list[dict[str, Any]]:
    leaks: list[dict[str, Any]] = []
    for source in sources:
        try:
            validate_public_record(source, stage="public_demo_eval")
        except Exception as exc:  # noqa: BLE001 - include guard reason in artifact.
            leaks.append(
                {
                    "id": _source_id(source),
                    "source": _value(source, "source"),
                    "source_scope": _value(source, "source_scope"),
                    "error": str(exc),
                }
            )
    return leaks


def _citation_present(result: Any) -> bool:
    citations = getattr(result, "citations", []) or []
    answer = str(getattr(result, "answer", "") or "")
    return bool(citations) or "Källor:" in answer


def _tokens_generated(result: Any) -> tuple[int, str]:
    metrics = getattr(result, "metrics", None)
    reported = int(getattr(metrics, "tokens_generated", 0) or 0)
    if reported > 0:
        return reported, "llm_stats"
    answer = str(getattr(result, "answer", "") or "")
    return len(answer.split()), "answer_word_count_approx"


def _latency_ms(result: Any, elapsed_ms: float) -> float:
    metrics = getattr(result, "metrics", None)
    reported = float(getattr(metrics, "total_pipeline_ms", 0.0) or 0.0)
    return round(reported if reported > 0 else elapsed_ms, 2)


def _source_id(source: Any) -> str:
    return str(
        _value(source, "document_id") or _value(source, "id") or _value(source, "doc_id") or ""
    )


def _value(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _answer_excerpt(answer: str, limit: int = 240) -> str:
    compact = " ".join(str(answer or "").split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3].rstrip() + "..."


def _rate(rows: list[dict[str, Any]], key: str) -> float | None:
    if not rows:
        return None
    return sum(1 for row in rows if row.get(key) is True) / len(rows)


def _refusal_correctness(rows: list[dict[str, Any]]) -> float | None:
    if not rows:
        return None
    return sum(
        1 for row in rows if row.get("refusal_reason") == row.get("expected_refusal_reason")
    ) / len(rows)


def _latency_p50(values: list[float]) -> float | None:
    if not values:
        return None
    return float(statistics.median(values))


def _nearest_rank_percentile(values: list[float], percentile: int) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil((percentile / 100) * len(ordered)))
    return float(ordered[rank - 1])


def _build_public_orchestrator() -> OrchestratorService:
    os.environ["CONST_PROFILE"] = PUBLIC_RIKSDAG_PROFILE
    config = ConfigService()
    return OrchestratorService(config=config)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _default_output_path() -> Path:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return DEFAULT_RESULTS_DIR / f"public_demo_eval_{timestamp}.json"


def print_summary(artifact: dict[str, Any]) -> None:
    summary = artifact["summary"]
    print("AIS-155 public demo eval")
    print(f"dataset: {artifact['run']['dataset_path']}")
    print(f"artifact: {artifact['run']['output_path']}")
    print(f"questions: {summary['question_count']}")
    print(f"retrieval_hit@5: {_fmt_metric(summary['retrieval_hit@5'])}")
    print(f"retrieval_hit@10: {_fmt_metric(summary['retrieval_hit@10'])}")
    print(f"citation_present_rate: {_fmt_metric(summary['citation_present_rate'])}")
    print(f"unsupported_answer_rate: {_fmt_metric(summary['unsupported_answer_rate'])}")
    print(f"refusal_correctness: {_fmt_metric(summary['refusal_correctness'])}")
    print(f"latency_p50: {_fmt_ms(summary['latency_p50'])}")
    print(f"latency_p95: {_fmt_ms(summary['latency_p95'])}")
    print(f"tokens_generated: {summary['tokens_generated']}")
    print(
        f"tokens_generated_approximation_count: {summary['tokens_generated_approximation_count']}"
    )
    print(f"leakage_count: {summary['leakage_count']}")
    print(f"uncited_public_answer_count: {summary['uncited_public_answer_count']}")
    print(f"answer_when_not_ready_count: {summary['answer_when_not_ready_count']}")
    print(f"critical_failure_count: {summary['critical_failure_count']}")
    if summary["critical_failures"]:
        print(f"critical_failures: {summary['critical_failures']}")


def _fmt_metric(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3f}"


def _fmt_ms(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f} ms"


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--questions", type=Path, default=DEFAULT_DATASET_PATH)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--no-fail-on-critical",
        action="store_true",
        help="Print and write results but return zero even when critical invariants fail.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    output_path = args.output or _default_output_path()
    artifact = asyncio.run(
        run_eval(dataset_path=args.questions, output_path=output_path, limit=args.limit)
    )
    print_summary(artifact)
    if args.no_fail_on_critical:
        return 0
    return exit_code_for_summary(artifact["summary"])


if __name__ == "__main__":
    raise SystemExit(main())

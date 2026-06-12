#!/usr/bin/env python3
"""Compare public demo eval summaries against a verified baseline."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

INVARIANT_KEYS = (
    "citation_present_rate",
    "unsupported_answer_rate",
    "refusal_correctness",
    "critical_invariants_passed",
    "leakage_count",
)

INVARIANT_EXPECTED: dict[str, Any] = {
    "citation_present_rate": 1.0,
    "unsupported_answer_rate": 0.0,
    "refusal_correctness": 1.0,
    "critical_invariants_passed": True,
    "leakage_count": 0,
}


def _load_summary(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    summary = payload.get("summary")
    if not isinstance(summary, dict):
        raise ValueError(f"{path} missing 'summary' object")
    return summary


def _check_invariants(summary: dict[str, Any], *, quick_eval: bool) -> list[str]:
    failures: list[str] = []
    for key in INVARIANT_KEYS:
        expected = INVARIANT_EXPECTED[key]
        actual = summary.get(key)
        if quick_eval and actual is None:
            continue
        if actual != expected:
            failures.append(f"{key}: expected {expected!r}, got {actual!r}")
    return failures


def _pct_delta(baseline: float | None, candidate: float | None) -> float | None:
    if baseline is None or candidate is None or baseline == 0:
        return None
    return ((candidate - baseline) / baseline) * 100.0


def compare_summaries(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    *,
    quick_eval: bool,
    latency_warn_p50_pct: float,
    latency_fail_p50_pct: float,
) -> dict[str, Any]:
    baseline_failures = _check_invariants(baseline, quick_eval=quick_eval)
    candidate_failures = _check_invariants(candidate, quick_eval=quick_eval)

    baseline_p50 = baseline.get("latency_p50")
    candidate_p50 = candidate.get("latency_p50")
    baseline_p95 = baseline.get("latency_p95")
    candidate_p95 = candidate.get("latency_p95")

    p50_delta = _pct_delta(
        float(baseline_p50) if baseline_p50 is not None else None,
        float(candidate_p50) if candidate_p50 is not None else None,
    )
    p95_delta = _pct_delta(
        float(baseline_p95) if baseline_p95 is not None else None,
        float(candidate_p95) if candidate_p95 is not None else None,
    )

    status = "PASS"
    notes: list[str] = []

    if candidate_failures:
        status = "FAIL"
        notes.append("candidate invariants failed")

    if quick_eval:
        notes.append("quick eval sample — latency deltas are indicative only")
        if candidate.get("critical_invariants_passed") is True and not candidate_failures:
            notes.append("candidate critical_invariants_passed=true")
    elif p50_delta is not None and p50_delta > latency_fail_p50_pct:
        status = "FAIL"
        notes.append(f"p50 regression {p50_delta:+.1f}% exceeds fail threshold")
    elif p50_delta is not None and p50_delta > latency_warn_p50_pct:
        if status == "PASS":
            status = "WARN"
        notes.append(f"p50 regression {p50_delta:+.1f}% exceeds warn threshold")

    return {
        "status": status,
        "quick_eval": quick_eval,
        "baseline_invariants_ok": not baseline_failures,
        "candidate_invariants_ok": not candidate_failures,
        "baseline_invariant_failures": baseline_failures,
        "candidate_invariant_failures": candidate_failures,
        "latency": {
            "baseline_p50_ms": baseline_p50,
            "candidate_p50_ms": candidate_p50,
            "p50_delta_pct": p50_delta,
            "baseline_p95_ms": baseline_p95,
            "candidate_p95_ms": candidate_p95,
            "p95_delta_pct": p95_delta,
        },
        "candidate_question_count": candidate.get("question_count"),
        "baseline_question_count": candidate.get("question_count"),
        "notes": notes,
    }


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--quick-eval", action="store_true")
    parser.add_argument("--latency-warn-p50-pct", type=float, default=25.0)
    parser.add_argument("--latency-fail-p50-pct", type=float, default=50.0)
    parser.add_argument("--json-out", type=Path, default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    result = compare_summaries(
        _load_summary(args.baseline),
        _load_summary(args.candidate),
        quick_eval=args.quick_eval,
        latency_warn_p50_pct=args.latency_warn_p50_pct,
        latency_fail_p50_pct=args.latency_fail_p50_pct,
    )
    if args.json_out:
        args.json_out.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 1 if result["status"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
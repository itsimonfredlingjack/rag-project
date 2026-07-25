#!/usr/bin/env python3
"""Summarize token usage from a public demo eval JSON artifact."""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("eval_json", type=Path)
    parser.add_argument("--budget", type=int, default=1024)
    parser.add_argument("--threshold-pct", type=float, default=60.0)
    args = parser.parse_args()

    payload = json.loads(args.eval_json.read_text(encoding="utf-8"))
    rows = [r for r in payload.get("rows", []) if r.get("success")]
    tokens = [int(r.get("tokens_generated") or 0) for r in rows]
    latencies = [float(r["latency_ms"]) for r in rows if r.get("latency_ms") is not None]

    if not tokens:
        print("No successful rows to profile.")
        return 1

    median_tokens = statistics.median(tokens)
    median_latency = statistics.median(latencies) if latencies else None
    threshold = args.budget * (args.threshold_pct / 100.0)

    print("=== Token budget profile ===")
    print(f"rows: {len(rows)}")
    print(f"median tokens_generated: {median_tokens:.0f}")
    print(f"total tokens_generated: {sum(tokens)}")
    print(f"mode_evidence_num_predict budget: {args.budget}")
    print(f"threshold for num_predict cut: {threshold:.0f} ({args.threshold_pct}%)")
    if median_latency is not None:
        print(f"median latency_ms: {median_latency:.0f}")

    if median_tokens > threshold:
        print("Recommendation: num_predict reduction MAY help — run bouncer after change")
    elif median_latency and median_latency > 5000 and median_tokens < threshold * 0.5:
        print(
            "Recommendation: latency high with short output — tune ctx/source payload, not num_predict"
        )
    else:
        print("Recommendation: keep num_predict; bottleneck likely elsewhere")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

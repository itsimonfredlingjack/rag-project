"""
Evaluation Runner — sends golden dataset to live API and measures quality.

Usage:
    cd backend
    source venv/bin/activate

    # Run full eval (60 items):
    python -m eval.run_eval

    # Filter by mode:
    python -m eval.run_eval --mode evidence

    # Filter by difficulty:
    python -m eval.run_eval --difficulty easy

    # Limit items (for quick testing):
    python -m eval.run_eval --limit 5

    # Save results to file:
    python -m eval.run_eval --output eval/results/baseline_2026-03-11.json
"""

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

from .golden_dataset import DifficultyLevel, EvalMode, load_golden_dataset
from .ragas_eval import EvalHarness, PipelineResponse

API_BASE = "http://localhost:8900/api/svensk-ragg"
QUERY_ENDPOINT = f"{API_BASE}/agent/query"
HEALTH_ENDPOINT = f"{API_BASE}/health"

# Timeout per query — first query loads reranker on CPU (~100s), subsequent are faster
REQUEST_TIMEOUT = 300.0
# Delay between requests to let GPU/CPU cool down and avoid OOM
INTER_REQUEST_DELAY = 2.0


async def check_health() -> bool:
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(HEALTH_ENDPOINT)
            data = resp.json()
            return data.get("status") == "healthy"
        except Exception as e:
            print(f"Health check failed: {e}")
            return False


async def query_pipeline(
    client: httpx.AsyncClient,
    question: str,
    mode: str,
) -> PipelineResponse:
    """Send a question to the API and return a PipelineResponse."""
    start = time.perf_counter()
    try:
        resp = await client.post(
            QUERY_ENDPOINT,
            json={"question": question, "mode": mode},
        )
        latency_ms = (time.perf_counter() - start) * 1000
        data = resp.json()

        if resp.status_code != 200:
            return PipelineResponse(
                answer="",
                error=f"HTTP {resp.status_code}: {data.get('detail', 'Unknown error')}",
                latency_ms=latency_ms,
            )

        sources = data.get("sources", [])
        cited_ids = [s.get("id", "") for s in sources if s.get("id")]

        return PipelineResponse(
            answer=data.get("answer", ""),
            sources=sources,
            cited_doc_ids=cited_ids,
            mode_used=data.get("mode", mode),
            latency_ms=latency_ms,
        )

    except httpx.TimeoutException:
        latency_ms = (time.perf_counter() - start) * 1000
        return PipelineResponse(answer="", error="Timeout", latency_ms=latency_ms)
    except Exception as e:
        latency_ms = (time.perf_counter() - start) * 1000
        return PipelineResponse(answer="", error=str(e), latency_ms=latency_ms)


async def run_eval(
    mode_filter: str | None = None,
    difficulty_filter: str | None = None,
    limit: int | None = None,
    output_path: str | None = None,
    concurrency: int = 1,
) -> dict:
    """Run the evaluation and return report dict."""

    # Health check
    if not await check_health():
        print("ERROR: Backend is not healthy. Start it first.")
        sys.exit(1)

    # Load dataset
    dataset = load_golden_dataset()
    items = dataset.items

    # Apply filters
    if mode_filter:
        mode_enum = EvalMode(mode_filter)
        items = [i for i in items if i.mode == mode_enum]
    if difficulty_filter:
        diff_enum = DifficultyLevel(difficulty_filter)
        items = [i for i in items if i.difficulty == diff_enum]
    if limit:
        items = items[:limit]

    total = len(items)
    print(f"\n{'=' * 60}")
    print("  Svensk Ragg — RAG Evaluation")
    print(f"  Dataset: golden_{dataset.version} ({dataset.count} items)")
    print(f"  Running: {total} items", end="")
    if mode_filter:
        print(f" [mode={mode_filter}]", end="")
    if difficulty_filter:
        print(f" [difficulty={difficulty_filter}]", end="")
    print(f"\n{'=' * 60}\n")

    harness = EvalHarness(dataset)
    results = []

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        for idx, item in enumerate(items, 1):
            tag = f"[{idx}/{total}] {item.id}"
            print(f"{tag} {item.question[:60]}...", end=" ", flush=True)

            response = await query_pipeline(client, item.question, item.mode.value)

            if response.error:
                print(f"ERROR: {response.error}")
                result = harness.evaluate_item(item, response)
            else:
                result = harness.evaluate_item(item, response)
                status = "OK" if result.composite_score >= 0.5 else "LOW"
                print(
                    f"{status} "
                    f"(comp={result.composite_score:.2f} "
                    f"frag={result.fragment_coverage:.2f} "
                    f"faith={result.faithfulness:.2f} "
                    f"{result.latency_ms:.0f}ms)"
                )

            results.append(result)

            # Delay between requests to avoid memory pressure
            if idx < total:
                await asyncio.sleep(INTER_REQUEST_DELAY)

    # Build report
    report = harness.build_report(results)
    report_dict = report.to_dict()

    # Add metadata
    report_dict["metadata"] = {
        "timestamp": datetime.now().isoformat(),
        "api_base": API_BASE,
        "filters": {
            "mode": mode_filter,
            "difficulty": difficulty_filter,
            "limit": limit,
        },
    }

    # Print summary
    print(f"\n{'=' * 60}")
    print("  RESULTS")
    print(f"{'=' * 60}")
    metrics = report_dict["aggregate_metrics"]
    print(f"  Composite Score:    {metrics['composite_score']:.4f}")
    print(f"  Answer Relevancy:   {metrics['answer_relevancy']:.4f}")
    print(f"  Faithfulness:       {metrics['faithfulness']:.4f}")
    print(f"  Context Precision:  {metrics['context_precision']:.4f}")
    print(f"  Context Recall:     {metrics['context_recall']:.4f}")
    print(f"  Fragment Coverage:  {metrics['fragment_coverage']:.4f}")
    print(f"  Citation Accuracy:  {metrics['citation_accuracy']:.4f}")

    violations = report_dict["violations"]
    print("\n  Violations:")
    print(f"    Forbidden fragments: {violations['forbidden_fragments']}")
    print(f"    Modal verb failures: {violations['modal_verb_failures']}")
    print(f"    Scope failures:      {violations['scope_failures']}")

    summary = report_dict["summary"]
    print(f"\n  Items: {summary['evaluated_items']}/{summary['total_items']} evaluated")
    print(f"  Failed: {summary['failed_items']}")
    print(f"  Total latency: {summary['total_latency_ms']:.0f}ms")
    if summary["evaluated_items"] > 0:
        avg_lat = summary["total_latency_ms"] / summary["evaluated_items"]
        print(f"  Avg latency: {avg_lat:.0f}ms")

    # Breakdowns
    for label, breakdown in [
        ("Mode", report_dict["breakdowns"]["by_mode"]),
        ("Difficulty", report_dict["breakdowns"]["by_difficulty"]),
    ]:
        print(f"\n  By {label}:")
        for key, vals in breakdown.items():
            print(
                f"    {key:12s}: comp={vals['avg_composite']:.4f} "
                f"frag={vals['avg_fragment_coverage']:.4f} "
                f"faith={vals['avg_faithfulness']:.4f} "
                f"(n={vals['count']})"
            )

    print(f"{'=' * 60}\n")

    # Save results
    if output_path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            json.dump(report_dict, f, ensure_ascii=False, indent=2)
        print(f"Results saved to {output_path}")

    return report_dict


def main():
    parser = argparse.ArgumentParser(description="Run RAG evaluation against live API")
    parser.add_argument("--mode", choices=["evidence", "assist", "chat"], help="Filter by mode")
    parser.add_argument(
        "--difficulty", choices=["easy", "medium", "hard"], help="Filter by difficulty"
    )
    parser.add_argument("--limit", type=int, help="Limit number of items to evaluate")
    parser.add_argument("--output", "-o", help="Save results JSON to file")
    args = parser.parse_args()

    asyncio.run(
        run_eval(
            mode_filter=args.mode,
            difficulty_filter=args.difficulty,
            limit=args.limit,
            output_path=args.output,
        )
    )


if __name__ == "__main__":
    main()

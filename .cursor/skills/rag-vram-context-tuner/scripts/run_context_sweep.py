#!/usr/bin/env python3
"""Benchmark num_ctx values for the public profile model via benchmark_ollama_models.py."""

from __future__ import annotations

import argparse
import csv
import io
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

DEFAULT_CONTEXTS = [1024, 1536, 2048, 3072, 4096]


def _repo_root(explicit: Path | None) -> Path:
    if explicit:
        return explicit.resolve()
    return Path(__file__).resolve().parents[4]


def _venv_python(repo: Path, explicit: Path | None) -> Path:
    if explicit and explicit.is_file():
        return explicit
    return repo / "backend" / ".venv" / "bin" / "python"


def _load_config(repo: Path, python: Path) -> tuple[str, int]:
    code = """
import json, os
os.environ["CONST_PROFILE"] = "public-riksdag-demo"
from app.services.config_service import PUBLIC_RIKSDAG_MODEL, ConfigSettings
s = ConfigSettings(_env_file=None)
print(json.dumps({"model": PUBLIC_RIKSDAG_MODEL, "ctx": s.ollama_num_ctx}))
"""
    proc = subprocess.run(
        [str(python), "-c", code],
        cwd=repo / "backend",
        capture_output=True,
        text=True,
        check=True,
    )
    payload = json.loads(proc.stdout.strip())
    return payload["model"], int(payload["ctx"])


def _run_benchmark(repo: Path, model: str, num_ctx: int, python: Path) -> list[dict[str, str]]:
    script = repo / "scripts/benchmark_ollama_models.py"
    proc = subprocess.run(
        [str(python), str(script), model, "--num-ctx", str(num_ctx)],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return [{"context": str(num_ctx), "error": proc.stderr.strip() or "benchmark failed"}]

    lines = [line for line in proc.stdout.splitlines() if line.strip()]
    if not lines or not lines[0].startswith("model,prompt,"):
        return [{"context": str(num_ctx), "error": "unexpected benchmark output"}]

    reader = csv.DictReader(io.StringIO("\n".join(lines)))
    rows = list(reader)
    for row in rows:
        row["context"] = str(num_ctx)
    return rows


def _recommend(rows: list[dict[str, str]], current_ctx: int) -> dict[str, Any]:
    rag_rows = [r for r in rows if r.get("prompt") == "rag_sv" and r.get("ok") == "True"]
    if not rag_rows:
        return {
            "recommended_ctx": current_ctx,
            "reason": "no successful rag_sv benchmarks; keep current config",
            "do_not_use": [],
        }

    def score(row: dict[str, str]) -> float:
        try:
            return float(row.get("wall_s") or 9999)
        except ValueError:
            return 9999.0

    best = min(rag_rows, key=score)
    best_ctx = int(best["context"])
    reason = (
        f"lowest rag_sv wall_s={best.get('wall_s')}s, processor={best.get('processor')}, "
        f"gen_tok_s={best.get('gen_tok_s')}"
    )
    do_not = []
    for r in rag_rows:
        ctx = int(r["context"])
        proc = r.get("processor", "")
        if ctx >= 4096 and "CPU" in proc:
            do_not.append(f"{ctx} on RTX 2060 6GB — heavy CPU/GPU split ({proc})")

    return {
        "recommended_ctx": best_ctx,
        "reason": reason,
        "do_not_use": do_not or [f"context > {best_ctx} if latency/regression fails full eval"],
        "current_ctx": current_ctx,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=None)
    parser.add_argument("--contexts", default=",".join(map(str, DEFAULT_CONTEXTS)))
    parser.add_argument("--python", type=Path, default=None)
    parser.add_argument("--json-out", type=Path, default=Path("/tmp/rag-context-sweep.json"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    repo = _repo_root(args.repo)
    python = _venv_python(repo, args.python)
    contexts = [int(x.strip()) for x in args.contexts.split(",") if x.strip()]
    model, current_ctx = _load_config(repo, python)

    if args.dry_run:
        print(
            json.dumps({"model": model, "contexts": contexts, "current_ctx": current_ctx}, indent=2)
        )
        return 0

    all_rows: list[dict[str, str]] = []
    for ctx in contexts:
        print(f"Benchmarking {model} @ num_ctx={ctx}...", file=sys.stderr)
        all_rows.extend(_run_benchmark(repo, model, ctx, python))

    recommendation = _recommend(all_rows, current_ctx)
    report = {
        "model": model,
        "current_ctx": current_ctx,
        "contexts_tested": contexts,
        "rows": all_rows,
        "recommendation": recommendation,
        "required_followup": [
            "rag-eval-regression-bouncer Level 1 (--limit 5)",
            "rag-eval-regression-bouncer Level 2 (30Q) before commit",
        ],
        "rollback": {
            "files": [
                "backend/app/services/config_service.py (ollama_num_ctx, gguf_context_window)",
                "start_system.sh (warmup num_ctx)",
            ],
        },
    }
    args.json_out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("=== Context sweep recommendation ===")
    print(f"Recommended: ollama_num_ctx={recommendation['recommended_ctx']}")
    print(f"Reason: {recommendation['reason']}")
    for item in recommendation.get("do_not_use", []):
        print(f"Do not use: {item}")
    print("Required follow-up: quick eval 5Q, then full eval 30Q (rag-eval-regression-bouncer)")
    print(f"Full report: {args.json_out}")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

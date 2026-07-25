#!/usr/bin/env python3
"""Small Ollama benchmark harness for local model-fit checks."""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

PROMPTS = {
    "short_sv": (
        "Svara kort pa svenska. Vad ar skillnaden mellan BM25 och dense "
        "retrieval i ett RAG-system?"
    ),
    "rag_sv": (
        "Du ar en lokal RAG-assistent for svenska myndighetsdokument. "
        "Forklara pa svenska hur du skulle svara pa en fraga om en lagtext "
        "nar sokresultaten innehaller motstridiga kallor. Namn tre "
        "forsiktighetsprinciper."
    ),
}


@dataclass
class Result:
    model: str
    prompt_name: str
    ok: bool
    wall_s: float
    load_s: float | None
    prompt_eval_rate: float | None
    eval_rate: float | None
    processor: str
    context: str
    error: str = ""


def ollama_generate(base_url: str, model: str, prompt: str, num_ctx: int) -> dict:
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "keep_alive": "30s",
        "options": {
            "num_ctx": num_ctx,
            "num_predict": 180,
            "temperature": 0.2,
            "top_p": 0.9,
        },
    }
    request = Request(
        f"{base_url}/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=900) as response:
        return json.loads(response.read().decode("utf-8"))


def run_command(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, text=True, capture_output=True, check=False)


def ollama_ps_for(model: str) -> tuple[str, str]:
    completed = run_command(["ollama", "ps"])
    if completed.returncode != 0:
        return "", ""
    lines = completed.stdout.splitlines()
    if len(lines) < 2:
        return "", ""
    header = lines[0]
    columns = ["NAME", "ID", "SIZE", "PROCESSOR", "CONTEXT", "UNTIL"]
    try:
        starts = {column: header.index(column) for column in columns}
    except ValueError:
        return "", ""
    for line in lines[1:]:
        name = line[starts["NAME"] : starts["ID"]].strip()
        if name != model:
            continue
        processor = line[starts["PROCESSOR"] : starts["CONTEXT"]].strip()
        context = line[starts["CONTEXT"] : starts["UNTIL"]].strip()
        return processor, context
    return "", ""


def ns_to_s(value: int | float | None) -> float | None:
    if not value:
        return None
    return round(float(value) / 1_000_000_000, 3)


def rate(count: int | None, duration_ns: int | None) -> float | None:
    if not count or not duration_ns:
        return None
    seconds = duration_ns / 1_000_000_000
    if seconds <= 0:
        return None
    return round(count / seconds, 2)


def unload(model: str) -> None:
    run_command(["ollama", "stop", model])


def benchmark_model(base_url: str, model: str, num_ctx: int) -> list[Result]:
    results: list[Result] = []
    for prompt_name, prompt in PROMPTS.items():
        start = time.perf_counter()
        try:
            data = ollama_generate(base_url, model, prompt, num_ctx)
            wall_s = round(time.perf_counter() - start, 3)
            processor, context = ollama_ps_for(model)
            results.append(
                Result(
                    model=model,
                    prompt_name=prompt_name,
                    ok=True,
                    wall_s=wall_s,
                    load_s=ns_to_s(data.get("load_duration")),
                    prompt_eval_rate=rate(
                        data.get("prompt_eval_count"),
                        data.get("prompt_eval_duration"),
                    ),
                    eval_rate=rate(data.get("eval_count"), data.get("eval_duration")),
                    processor=processor,
                    context=context,
                )
            )
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            results.append(
                Result(
                    model=model,
                    prompt_name=prompt_name,
                    ok=False,
                    wall_s=round(time.perf_counter() - start, 3),
                    load_s=None,
                    prompt_eval_rate=None,
                    eval_rate=None,
                    processor="",
                    context="",
                    error=str(exc),
                )
            )
            break
    unload(model)
    return results


def print_table(results: list[Result]) -> None:
    print("model,prompt,ok,wall_s,load_s,prompt_tok_s,gen_tok_s,processor,context,error")
    for item in results:
        print(
            ",".join(
                [
                    item.model,
                    item.prompt_name,
                    str(item.ok),
                    str(item.wall_s),
                    str(item.load_s or ""),
                    str(item.prompt_eval_rate or ""),
                    str(item.eval_rate or ""),
                    item.processor,
                    item.context,
                    item.error.replace(",", ";").replace("\n", " "),
                ]
            )
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("models", nargs="+")
    parser.add_argument("--base-url", default="http://localhost:11434")
    parser.add_argument("--num-ctx", type=int, default=4096)
    args = parser.parse_args()

    all_results: list[Result] = []
    for model in args.models:
        all_results.extend(benchmark_model(args.base_url, model, args.num_ctx))
    print_table(all_results)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

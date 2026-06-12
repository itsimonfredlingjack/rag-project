#!/usr/bin/env python3
"""Detect drift between public profile config, startup scripts, docs, and /ready."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PUBLIC_PROFILE = "public-riksdag-demo"
PUBLIC_SCOPE = "riksdagen_open_data_only"
PUBLIC_ROOT = "/home/ai-server2/rag/local-data-public/riksdag"


@dataclass
class Finding:
    severity: str  # DRIFT | WARN | OK
    check: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)


def _repo_root(explicit: Path | None) -> Path:
    if explicit:
        return explicit.resolve()
    return Path(__file__).resolve().parents[4]


def _venv_python(repo: Path) -> Path:
    return repo / "backend" / ".venv" / "bin" / "python"


def _load_public_settings(repo: Path) -> dict[str, Any]:
    python = _venv_python(repo)
    if not python.is_file():
        raise FileNotFoundError(f"backend venv not found: {python}")

    code = """
import json, os
os.environ["CONST_PROFILE"] = "public-riksdag-demo"
from app.services.config_service import PUBLIC_RIKSDAG_MODEL, ConfigSettings
settings = ConfigSettings(_env_file=None)
print(json.dumps({
    "PUBLIC_RIKSDAG_MODEL": PUBLIC_RIKSDAG_MODEL,
    "profile": settings.profile,
    "corpus_scope": settings.corpus_scope,
    "constitutional_model": settings.constitutional_model,
    "chromadb_enabled": settings.chromadb_enabled,
    "bm25_enabled": settings.bm25_enabled,
    "bm25_index_path": settings.bm25_index_path,
    "chromadb_path": settings.chromadb_path,
    "ollama_num_ctx": settings.ollama_num_ctx,
    "gguf_context_window": settings.gguf_context_window,
    "reranking_enabled": settings.reranking_enabled,
    "crag_enabled": settings.crag_enabled,
    "critic_revise_enabled": settings.critic_revise_enabled,
}))
"""
    proc = subprocess.run(
        [str(python), "-c", code],
        cwd=repo / "backend",
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(proc.stdout.strip())


def _grep_literal(path: Path, needle: str) -> bool:
    if not path.is_file():
        return False
    return needle in path.read_text(encoding="utf-8")


def _extract_warmup_num_ctx(start_script: Path) -> int | None:
    if not start_script.is_file():
        return None
    text = start_script.read_text(encoding="utf-8")
    match = re.search(r"num_ctx\\?\":(\d+)", text)
    return int(match.group(1)) if match else None


def _extract_default_model(script: Path) -> str | None:
    if not script.is_file():
        return None
    match = re.search(
        r'OLLAMA_MODEL:-([a-zA-Z0-9:.]+)\}"',
        script.read_text(encoding="utf-8"),
    )
    return match.group(1) if match else None


def _fetch_ready(url: str) -> dict[str, Any] | None:
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None


def check_drift(repo: Path, ready_url: str) -> list[Finding]:
    findings: list[Finding] = []
    cfg = _load_public_settings(repo)
    model = cfg["constitutional_model"]
    ctx = cfg["ollama_num_ctx"]

    if cfg["profile"] != PUBLIC_PROFILE:
        findings.append(Finding("DRIFT", "profile", f"expected {PUBLIC_PROFILE}", {"actual": cfg["profile"]}))
    else:
        findings.append(Finding("OK", "profile", PUBLIC_PROFILE))

    if cfg["corpus_scope"] != PUBLIC_SCOPE:
        findings.append(Finding("DRIFT", "corpus_scope", f"expected {PUBLIC_SCOPE}", {"actual": cfg["corpus_scope"]}))
    else:
        findings.append(Finding("OK", "corpus_scope", PUBLIC_SCOPE))

    for flag, expected in (
        ("chromadb_enabled", False),
        ("bm25_enabled", True),
        ("reranking_enabled", False),
        ("crag_enabled", False),
        ("critic_revise_enabled", False),
    ):
        actual = cfg[flag]
        if actual != expected:
            findings.append(Finding("DRIFT", flag, f"expected {expected}", {"actual": actual}))
        else:
            findings.append(Finding("OK", flag, str(expected)))

    for path_key in ("bm25_index_path", "chromadb_path"):
        path_val = cfg[path_key]
        if PUBLIC_ROOT not in path_val:
            findings.append(Finding("DRIFT", path_key, "not under public root", {"path": path_val}))
        if "local-data-private" in path_val:
            findings.append(Finding("DRIFT", path_key, "private path leak", {"path": path_val}))
        if PUBLIC_ROOT in path_val:
            findings.append(Finding("OK", path_key, path_val))

    start = repo / "start_system.sh"
    status = repo / "status.sh"
    start_model = _extract_default_model(start)
    status_model = _extract_default_model(status)
    warmup_ctx = _extract_warmup_num_ctx(start)

    if start_model != model:
        findings.append(Finding("DRIFT", "start_system.sh model", f"expected {model}", {"actual": start_model}))
    else:
        findings.append(Finding("OK", "start_system.sh model", model))

    if status_model != model:
        findings.append(Finding("DRIFT", "status.sh model", f"expected {model}", {"actual": status_model}))
    else:
        findings.append(Finding("OK", "status.sh model", model))

    if warmup_ctx is None:
        findings.append(Finding("WARN", "warmup num_ctx", "not found in start_system.sh"))
    elif warmup_ctx != ctx:
        findings.append(
            Finding("DRIFT", "warmup num_ctx", f"expected {ctx}", {"actual": warmup_ctx})
        )
    else:
        findings.append(Finding("OK", "warmup num_ctx", str(ctx)))

    config_py = repo / "backend/app/services/config_service.py"
    if not _grep_literal(config_py, f'PUBLIC_RIKSDAG_MODEL = "{model}"'):
        findings.append(Finding("DRIFT", "PUBLIC_RIKSDAG_MODEL constant", f"expected {model}"))

    for doc in (repo / "docs/MODEL_POLICY.md", repo / "docs/PUBLIC_RIKSDAG_DEMO.md"):
        if not doc.is_file():
            findings.append(Finding("WARN", doc.name, "missing"))
            continue
        text = doc.read_text(encoding="utf-8")
        if model not in text:
            findings.append(Finding("WARN", doc.name, f"model {model} not mentioned"))
        if str(ctx) not in text and "4096" in text and ctx != 4096:
            findings.append(Finding("WARN", doc.name, f"docs may still say 4096; config has {ctx}"))

    ready = _fetch_ready(ready_url)
    if ready is None:
        findings.append(Finding("WARN", "ready endpoint", f"unreachable: {ready_url}"))
    else:
        llm = ready.get("checks", {}).get("llm_service", {}).get("details", {})
        ready_model = llm.get("model")
        if ready_model and ready_model != model:
            findings.append(Finding("DRIFT", "ready llm model", f"expected {model}", {"actual": ready_model}))
        elif ready_model:
            findings.append(Finding("OK", "ready llm model", ready_model))
        if ready.get("can_answer") not in (True, "True", "true"):
            findings.append(Finding("WARN", "can_answer", str(ready.get("can_answer"))))

    return findings


def _status(findings: list[Finding]) -> str:
    if any(f.severity == "DRIFT" for f in findings):
        return "DRIFT"
    if any(f.severity == "WARN" for f in findings):
        return "WARN"
    return "OK"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=None)
    parser.add_argument("--ready-url", default="http://localhost:8900/api/svensk-ragg/ready")
    parser.add_argument("--json-out", type=Path, default=None)
    args = parser.parse_args()

    repo = _repo_root(args.repo)
    findings = check_drift(repo, args.ready_url)
    report = {
        "status": _status(findings),
        "repo": str(repo),
        "findings": [
            {"severity": f.severity, "check": f.check, "message": f.message, "details": f.details}
            for f in findings
        ],
    }

    if args.json_out:
        args.json_out.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"Status: {report['status']}")
    for f in findings:
        if f.severity != "OK":
            print(f"  [{f.severity}] {f.check}: {f.message} {f.details or ''}".rstrip())
    ok_count = sum(1 for f in findings if f.severity == "OK")
    print(f"OK checks: {ok_count}/{len(findings)}")
    print(json.dumps(report, indent=2))

    return 1 if report["status"] == "DRIFT" else 0


if __name__ == "__main__":
    raise SystemExit(main())
"""Allowlisted command entrypoint for ChatGPT app jobs."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _run(command: list[str], *, cwd: Path | None = None) -> int:
    completed = subprocess.run(command, cwd=str(cwd) if cwd else None, check=False)
    return completed.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Run allowlisted ChatGPT app jobs.")
    parser.add_argument("operation")
    args = parser.parse_args()

    backend_root = _backend_root()
    repo_root = _repo_root()

    operations: dict[str, list[str]] = {
        "readiness_check": [sys.executable, "-m", "app.main"],
        "rag_benchmark_quick": [sys.executable, str(repo_root / "rag_benchmark.py"), "--help"],
        "sfs_update": [sys.executable, str(repo_root / "scrapers" / "sfs_updater.py"), "--help"],
        "harvest_source": [
            sys.executable,
            str(repo_root / "scrapers" / "sfs_scraper.py"),
            "--help",
        ],
    }

    command = operations.get(args.operation)
    if not command:
        print(json.dumps({"ok": False, "error": f"Unsupported operation: {args.operation}"}))
        return 2

    if args.operation == "readiness_check":
        print(json.dumps({"ok": True, "operation": args.operation, "command": command}))
        return 0

    return _run(command, cwd=backend_root)


if __name__ == "__main__":
    raise SystemExit(main())

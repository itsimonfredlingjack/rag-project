#!/usr/bin/env python3
"""Generate docs/SYSTEM_SNAPSHOT.md from local configuration and repository state."""

from __future__ import annotations

import ast
import os
import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
API_DIR = BACKEND_DIR / "app" / "api"
OUTPUT_PATH = ROOT / "docs" / "SYSTEM_SNAPSHOT.md"
FRONTEND_DIR = ROOT / "apps" / "konstitutionell-frontend"
DEFAULT_BM25_DB = ROOT / "data" / "bm25_fts5" / "bm25.db"
DEFAULT_CHROMADB_PATH = Path("/home/ai-server/AN-FOR-NO-ASSHOLES/09_CONSTITUTIONAL-AI/chromadb_data")


@dataclass
class Route:
    method: str
    path: str


def parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        values[key] = value
    return values


def bool_from_value(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def collect_constitutional_routes() -> list[Route]:
    path = API_DIR / "constitutional_routes.py"
    content = path.read_text(encoding="utf-8")
    pattern = re.compile(r'@router\.(get|post|put|patch|delete)\("([^"]+)"')
    routes = [Route(method=m.upper(), path=p) for m, p in pattern.findall(content)]
    return sorted(routes, key=lambda r: (r.path, r.method))


def collect_document_routes() -> list[Route]:
    path = API_DIR / "document_routes.py"
    content = path.read_text(encoding="utf-8")

    prefix_match = re.search(r'APIRouter\(prefix="([^"]+)"', content)
    prefix = prefix_match.group(1) if prefix_match else ""

    pattern = re.compile(r'@router\.(get|post|put|patch|delete)\(\s*"([^"]+)"', re.MULTILINE)
    routes = [Route(method=m.upper(), path=f"{prefix}{p}") for m, p in pattern.findall(content)]
    return sorted(routes, key=lambda r: (r.path, r.method))


def load_frontend_backend_url() -> str:
    for candidate in (FRONTEND_DIR / ".env", FRONTEND_DIR / ".env.local", FRONTEND_DIR / ".env.example"):
        env = parse_env_file(candidate)
        if env.get("VITE_BACKEND_URL"):
            return env["VITE_BACKEND_URL"]
    return "http://localhost:8900"


def detect_chromadb_collections(chromadb_path: Path) -> tuple[list[tuple[str, str]], str | None]:
    if not chromadb_path.exists():
        return [], f"ChromaDB path saknas: {chromadb_path}"

    try:
        import chromadb  # type: ignore

        client = chromadb.PersistentClient(path=str(chromadb_path))
        collections = []
        for c in client.list_collections():
            count = "n/a"
            try:
                count = str(c.count())
            except Exception:
                pass
            collections.append((c.name, count))
        collections.sort(key=lambda x: x[0])
        return collections, None
    except Exception as exc:  # pragma: no cover
        return [], f"Kunde inte läsa ChromaDB collections: {exc}"


def detect_bm25_count(bm25_path: Path) -> tuple[int | None, str | None]:
    if not bm25_path.exists():
        return None, f"BM25-index saknas: {bm25_path}"

    try:
        with sqlite3.connect(bm25_path) as conn:
            cur = conn.execute("SELECT count(*) FROM docs_fts")
            row = cur.fetchone()
            return int(row[0]) if row else 0, None
    except Exception as exc:  # pragma: no cover
        return None, f"Kunde inte läsa BM25-index: {exc}"


def summarize_constitutional_routes(routes: Iterable[Route]) -> list[str]:
    lines: list[str] = []
    prefixes = ["/api/svensk-rag", "/api/constitutional (legacy)"]
    for prefix in prefixes:
        lines.append(f"- **{prefix}**")
        for route in routes:
            lines.append(f"  - `{route.method} {route.path}`")
    return lines


def build_snapshot() -> str:
    backend_env = parse_env_file(BACKEND_DIR / ".env")
    backend_env_example = parse_env_file(BACKEND_DIR / ".env.example")

    def env_value(name: str, default: str | None = None) -> str | None:
        return os.environ.get(name) or backend_env.get(name) or backend_env_example.get(name) or default

    bm25_enabled = bool_from_value(env_value("CONST_BM25_ENABLED", "true"), default=True)
    reranking_enabled = bool_from_value(env_value("CONST_RERANKING_ENABLED", "true"), default=True)
    crag_enabled = bool_from_value(env_value("CONST_CRAG_ENABLED", "true"), default=True)
    critic_revise_enabled = bool_from_value(env_value("CONST_CRITIC_REVISE_ENABLED", "true"), default=True)
    structured_output_enabled = bool_from_value(
        env_value("CONST_STRUCTURED_OUTPUT_ENABLED", "true"), default=True
    )
    intent_fallback_enabled = bool_from_value(
        env_value("CONST_INTENT_LLM_FALLBACK_ENABLED", "false"), default=False
    )

    llm_base_url = env_value("CONST_LLM_BASE_URL", "http://localhost:11434")
    configured_model = env_value("CONST_CONSTITUTIONAL_MODEL", "gemma3:12b")

    chromadb_path = Path(env_value("CONST_CHROMADB_PATH", str(DEFAULT_CHROMADB_PATH)) or DEFAULT_CHROMADB_PATH)
    bm25_path = Path(env_value("CONST_BM25_INDEX_PATH", str(DEFAULT_BM25_DB)) or DEFAULT_BM25_DB)

    chroma_collections, chroma_warning = detect_chromadb_collections(chromadb_path)
    bm25_rows, bm25_warning = detect_bm25_count(bm25_path)

    constitutional_routes = collect_constitutional_routes()
    document_routes = collect_document_routes()

    warnings: list[str] = []
    if chroma_warning:
        warnings.append(chroma_warning)
    if bm25_warning:
        warnings.append(bm25_warning)

    timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")

    lines: list[str] = [
        "# SYSTEM SNAPSHOT — Svensk RAG",
        "",
        f"_Generated: {timestamp}_",
        "",
        "## 1) Runtime configuration (effective from env/.env/.env.example)",
        "",
        f"- `CONST_APP_NAME`: `{env_value('CONST_APP_NAME', 'Svensk RAG')}`",
        f"- `CONST_PORT`: `{env_value('CONST_PORT', '8900')}`",
        f"- `CONST_LLM_BASE_URL`: `{llm_base_url}`",
        f"- `CONST_CONSTITUTIONAL_MODEL` (legacy key): `{configured_model}`",
        f"- Frontend backend URL (`VITE_BACKEND_URL`): `{load_frontend_backend_url()}`",
        "",
        "## 2) Feature flags",
        "",
        f"- BM25 (`CONST_BM25_ENABLED`): **{'enabled' if bm25_enabled else 'disabled'}**",
        f"- Reranking (`CONST_RERANKING_ENABLED`): **{'enabled' if reranking_enabled else 'disabled'}**",
        f"- CRAG (`CONST_CRAG_ENABLED`): **{'enabled' if crag_enabled else 'disabled'}**",
        f"- Critic-Revise (`CONST_CRITIC_REVISE_ENABLED`): **{'enabled' if critic_revise_enabled else 'disabled'}**",
        f"- Structured output (`CONST_STRUCTURED_OUTPUT_ENABLED`): **{'enabled' if structured_output_enabled else 'disabled'}**",
        f"- Intent fallback (`CONST_INTENT_LLM_FALLBACK_ENABLED`): **{'enabled' if intent_fallback_enabled else 'disabled'}**",
        "",
        "## 3) API endpoint summary",
        "",
        "### Agent/health/readiness/statistics",
        *summarize_constitutional_routes(constitutional_routes),
        "",
        "### Documents",
    ]

    lines.extend([f"- `{route.method} {route.path}`" for route in document_routes])

    lines.extend(
        [
            "",
            "## 4) Data stores",
            "",
            f"- ChromaDB path: `{chromadb_path}`",
            f"- BM25 index path: `{bm25_path}`",
            "",
            "### ChromaDB collections",
        ]
    )

    if chroma_collections:
        lines.extend([f"- `{name}`: {count} docs" for name, count in chroma_collections])
    else:
        lines.append("- Ingen lokal ChromaDB-data hittades eller kunde läsas.")

    lines.extend(["", "### BM25 (FTS5)"])
    if bm25_rows is None:
        lines.append("- Ingen lokal BM25-data hittades eller kunde läsas.")
    else:
        lines.append(f"- `docs_fts` row count: **{bm25_rows:,}**")

    lines.extend(
        [
            "",
            "## 5) Legacy compatibility",
            "",
            "- Publikt namn är **Svensk RAG**.",
            "- Legacy API-prefix `/api/constitutional/*` finns kvar för bakåtkompatibilitet.",
            "- Legacy env-prefix `CONST_` och vissa interna `constitutional_*` identifierare är kvar tills vidare för säker migrering.",
            "",
            "## 6) Warnings",
            "",
        ]
    )

    if warnings:
        lines.extend([f"- ⚠️ {warning}" for warning in warnings])
    else:
        lines.append("- Inga varningar.")

    lines.append("")
    return "\n".join(lines)


def main() -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(build_snapshot(), encoding="utf-8")
    print(f"Updated {OUTPUT_PATH}")


if __name__ == "__main__":
    main()

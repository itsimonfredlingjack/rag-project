"""Public route-surface contract tests."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

PUBLIC_PROFILE = "public-riksdag-demo"
PRIVATE_PROFILE = "private-swedish-legal-lab"
BACKEND_ROOT = Path(__file__).resolve().parents[1]


def _routes_for_profile(profile: str, **extra_env: str) -> set[str]:
    env = os.environ.copy()
    env.update(
        {
            "CONST_PROFILE": profile,
            "CONST_LOG_LEVEL": "ERROR",
            **extra_env,
        }
    )
    code = """
import json
from app.main import app
print("ROUTES_JSON=" + json.dumps(sorted(getattr(route, "path", "") for route in app.routes)))
"""
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=BACKEND_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    for line in completed.stdout.splitlines():
        if line.startswith("ROUTES_JSON="):
            return set(json.loads(line.removeprefix("ROUTES_JSON=")))
    raise AssertionError(
        f"No route payload in subprocess output:\n{completed.stdout}\n{completed.stderr}"
    )


def test_public_profile_disables_operator_docs_and_legacy_routes() -> None:
    paths = _routes_for_profile(PUBLIC_PROFILE)

    assert "/api/svensk-ragg/health" in paths
    assert "/api/svensk-ragg/ready" in paths
    assert "/api/svensk-ragg/agent/query" in paths
    assert "/api/svensk-ragg/agent/query/stream" in paths

    assert "/openapi.json" not in paths
    assert "/docs" not in paths
    assert "/redoc" not in paths
    assert "/mcp" not in paths
    assert "/sse" not in paths
    assert "/sse/message" not in paths
    assert "/ws/harvest" not in paths


def test_public_docs_can_be_explicitly_enabled_for_local_review() -> None:
    paths = _routes_for_profile(PUBLIC_PROFILE, CONST_API_DOCS_ENABLED="true")

    assert "/openapi.json" in paths
    assert "/docs" in paths
    assert "/redoc" in paths


def test_private_profile_keeps_local_operator_routes() -> None:
    paths = _routes_for_profile(PRIVATE_PROFILE)

    assert "/openapi.json" in paths
    assert "/docs" in paths
    assert "/redoc" in paths
    assert "/mcp" in paths
    assert "/sse" in paths
    assert "/sse/message" in paths
    assert "/ws/harvest" in paths


@pytest.mark.asyncio
async def test_public_document_facets_are_riksdag_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONST_PROFILE", PUBLIC_PROFILE)

    from app.api.document_routes import get_document_facets

    facets = await get_document_facets()

    assert facets["agencies"] == [{"id": "riksdagen", "name": "Riksdagen"}]
    assert facets["doc_types"] == [{"id": "riksdag", "name": "Riksdagsdokument"}]
    assert "diva" not in json.dumps(facets).lower()


@pytest.mark.asyncio
async def test_public_profile_blocks_private_lab_document_reads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CONST_PROFILE", PUBLIC_PROFILE)

    from app.api.document_routes import get_document, get_parent_document, list_documents

    for call in (
        lambda: list_documents(),
        lambda: get_document("GP02K1"),
        lambda: get_parent_document("sfs_1974_152_2kap_1§"),
    ):
        with pytest.raises(HTTPException) as exc:
            await call()
        assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_public_profile_blocks_operator_read_routes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CONST_PROFILE", PUBLIC_PROFILE)

    from app.api.constitutional_routes import (
        get_collections,
        get_prometheus_metrics,
        get_rag_metrics_endpoint,
        get_stats_overview,
    )

    for call in (
        get_rag_metrics_endpoint,
        get_prometheus_metrics,
        get_stats_overview,
        get_collections,
    ):
        with pytest.raises(HTTPException) as exc:
            await call()
        assert exc.value.status_code == 404

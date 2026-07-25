"""Public branding contract for the Svensk Ragg demo."""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]

PUBLIC_BRANDING_FILES = [
    REPO_ROOT / "README.md",
    REPO_ROOT / "docs" / "PUBLIC_RIKSDAG_DEMO.md",
    REPO_ROOT / "docs" / "LINKEDIN_RIKSDAG_DEMO_SCRIPT.md",
    REPO_ROOT / "apps" / "svensk-ragg-frontend" / "README.md",
    REPO_ROOT / "apps" / "svensk-ragg-frontend" / "index.html",
    REPO_ROOT / "apps" / "svensk-ragg-frontend" / "package.json",
    REPO_ROOT / "apps" / "svensk-ragg-frontend" / "electron" / "main.ts",
    REPO_ROOT / "apps" / "svensk-ragg-frontend" / "src" / "App.tsx",
    REPO_ROOT / "apps" / "svensk-ragg-frontend" / "src" / "stores" / "useAppStore.ts",
    REPO_ROOT / "apps" / "svensk-ragg-frontend" / "scripts" / "check-public-ui-contract.mjs",
    REPO_ROOT / "start_system.sh",
    REPO_ROOT / "status.sh",
    REPO_ROOT / "stop_system.sh",
]

FORBIDDEN_PUBLIC_BRAND_STRINGS = [
    "Svensk " + "RAG",
    "Konstitu" + "tionell AI",
    "Constitu" + "tional AI",
    "konstitu" + "tionell-frontend",
    "apps/" + "konstitu" + "tionell-frontend",
    "/api/" + "constitu" + "tional",
]
FORBIDDEN_PUBLIC_BRAND_TERMS = [
    "constitu" + "tional",
    "konstitu" + "tionell",
    "konstitu" + "tionen",
]


def test_public_branding_uses_svensk_ragg_only() -> None:
    missing = [path for path in PUBLIC_BRANDING_FILES if not path.exists()]
    assert missing == []

    for path in PUBLIC_BRANDING_FILES:
        text = path.read_text(encoding="utf-8")
        assert "Svensk Ragg" in text, f"{path} must include the public brand"
        for forbidden in FORBIDDEN_PUBLIC_BRAND_STRINGS:
            assert forbidden not in text, f"{path} still contains {forbidden!r}"
        lower_text = text.lower()
        for forbidden in FORBIDDEN_PUBLIC_BRAND_TERMS:
            assert forbidden not in lower_text, f"{path} still contains {forbidden!r}"


def test_svensk_ragg_api_aliases_are_registered() -> None:
    from app.main import app

    def _extract_paths(route):
        paths = []
        if getattr(route, "path", None):
            paths.append(route.path)
        if hasattr(route, "original_router") and hasattr(route.original_router, "routes"):
            for sub in route.original_router.routes:
                paths.extend(_extract_paths(sub))
        return paths

    paths = {p for r in app.routes for p in _extract_paths(r)}

    assert "/api/svensk-ragg/health" in paths
    assert "/api/svensk-ragg/ready" in paths
    assert "/api/svensk-ragg/agent/query" in paths
    assert "/api/svensk-ragg/agent/query/stream" in paths

from fastapi import FastAPI
import pytest


def test_build_tool_catalog_declares_read_and_write_tools():
    from app.chatgpt_app.server import build_tool_catalog

    catalog = build_tool_catalog()

    assert catalog["query_constitutional_ai"]["annotations"]["readOnlyHint"] is True
    assert catalog["inspect_runtime"]["annotations"]["readOnlyHint"] is True
    assert catalog["inspect_project"]["annotations"]["readOnlyHint"] is True
    assert catalog["run_diagnostic_job"]["annotations"]["readOnlyHint"] is False
    assert catalog["run_corpus_operation"]["annotations"]["readOnlyHint"] is False
    assert catalog["render_query_report"]["meta"]["ui_resource"] == "ui://widget/operator.html"


def test_build_widget_resource_descriptor_contains_chatgpt_metadata():
    from app.chatgpt_app.server import build_widget_resource_descriptor

    resource = build_widget_resource_descriptor()

    assert resource["uri"] == "ui://widget/operator.html"
    assert resource["mime_type"] == "text/html;profile=mcp-app"
    assert resource["meta"]["openai/widgetDescription"]
    assert resource["meta"]["ui"]["csp"]["connectDomains"] == []
    assert resource["meta"]["ui"]["prefersBorder"] is True


def test_mount_chatgpt_app_adds_mcp_route():
    from app.chatgpt_app.server import mount_chatgpt_app

    app = FastAPI()
    mount_chatgpt_app(app)

    mount_paths = {route.path for route in app.routes}
    assert "/mcp" in mount_paths


@pytest.mark.asyncio
async def test_public_profile_rejects_mcp_job_launches(monkeypatch):
    from unittest.mock import AsyncMock

    from app.chatgpt_app import server

    start_job = AsyncMock()
    monkeypatch.setattr(server._job_registry, "start", start_job)

    diagnostic = await server._launch_job(
        "run_diagnostic_job",
        "readiness_check",
        confirm=False,
        profile="public-riksdag-demo",
    )
    corpus = await server._launch_job(
        "run_corpus_operation",
        "sfs_update",
        confirm=True,
        profile="public-riksdag-demo",
    )

    assert diagnostic.isError is True
    assert diagnostic.structuredContent["status"] == "rejected"
    assert corpus.isError is True
    assert corpus.structuredContent["status"] == "rejected"
    start_job.assert_not_called()


@pytest.mark.asyncio
async def test_private_profile_can_launch_allowlisted_diagnostic_job(monkeypatch):
    from unittest.mock import AsyncMock

    from app.chatgpt_app import server
    from app.chatgpt_app.server import JobStatus

    start_job = AsyncMock(
        return_value=JobStatus(
            id="job-1",
            tool_name="run_diagnostic_job",
            operation="readiness_check",
            status="queued",
            command=["python", "-m", "app.chatgpt_app.job_runner", "readiness_check"],
            read_only=True,
            created_at="2026-05-31T00:00:00+00:00",
        )
    )
    monkeypatch.setattr(server._job_registry, "start", start_job)

    result = await server._launch_job(
        "run_diagnostic_job",
        "readiness_check",
        confirm=False,
        profile="private-swedish-legal-lab",
    )

    assert result.isError is not True
    assert result.structuredContent["status"] == "queued"
    start_job.assert_awaited_once()

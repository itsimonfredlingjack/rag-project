"""MCP server integration for the internal ChatGPT operator app."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Literal

from fastapi import FastAPI
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import CallToolResult, TextContent, ToolAnnotations

from ..services.orchestrator_service import OrchestratorService, get_orchestrator_service
from ..services.readiness_service import build_dependency_readiness
from ..services.retrieval_service import RetrievalStrategy
from ..utils.metrics import get_rag_metrics
from .adapters import build_query_tool_payload
from .jobs import JobValidationError, JobRequest, resolve_job_request
from .widget import build_widget_html

WIDGET_URI = "ui://widget/operator.html"
REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = Path(__file__).resolve().parents[2]
ALLOWED_MCP_HOSTS = [
    "127.0.0.1:*",
    "localhost:*",
    "[::1]:*",
]
ALLOWED_MCP_ORIGINS = [
    "http://127.0.0.1:*",
    "http://localhost:*",
    "http://[::1]:*",
    "https://chatgpt.com",
    "https://chat.openai.com",
    "https://web-sandbox.oaiusercontent.com",
]


def build_tool_catalog() -> dict[str, dict[str, Any]]:
    """Return a documentation-friendly view of the tool surface."""
    return {
        "query_constitutional_ai": {
            "title": "Query Constitutional AI",
            "description": (
                "Use this when you need a real RAG answer from the Constitutional AI "
                "backend with evidence, retrieval strategy, and sources."
            ),
            "annotations": {
                "readOnlyHint": True,
                "destructiveHint": False,
                "openWorldHint": False,
                "idempotentHint": True,
            },
            "meta": {
                "openai/toolInvocation/invoking": "Querying corpus…",
                "openai/toolInvocation/invoked": "Query ready",
            },
        },
        "inspect_runtime": {
            "title": "Inspect Runtime",
            "description": (
                "Use this when you want runtime health, readiness, model config, "
                "collection status, and observability signals."
            ),
            "annotations": {
                "readOnlyHint": True,
                "destructiveHint": False,
                "openWorldHint": False,
                "idempotentHint": True,
            },
            "meta": {
                "openai/toolInvocation/invoking": "Inspecting runtime…",
                "openai/toolInvocation/invoked": "Runtime snapshot ready",
            },
        },
        "inspect_project": {
            "title": "Inspect Project",
            "description": (
                "Use this when you need project structure, canonical docs, risks, and "
                "recommended next steps for planning."
            ),
            "annotations": {
                "readOnlyHint": True,
                "destructiveHint": False,
                "openWorldHint": False,
                "idempotentHint": True,
            },
            "meta": {
                "openai/toolInvocation/invoking": "Reading project…",
                "openai/toolInvocation/invoked": "Project snapshot ready",
            },
        },
        "render_query_report": {
            "title": "Render Query Report",
            "description": (
                "Use this when you want the ChatGPT widget to render a Constitutional AI "
                "query report. Prefer calling query_constitutional_ai first when the "
                "model wants to reason over the data before rendering."
            ),
            "annotations": {
                "readOnlyHint": True,
                "destructiveHint": False,
                "openWorldHint": False,
                "idempotentHint": True,
            },
            "meta": {
                "ui": {"resourceUri": WIDGET_URI},
                "ui_resource": WIDGET_URI,
                "openai/outputTemplate": WIDGET_URI,
                "openai/toolInvocation/invoking": "Rendering query report…",
                "openai/toolInvocation/invoked": "Query report rendered",
            },
        },
        "render_operator_dashboard": {
            "title": "Render Operator Dashboard",
            "description": (
                "Use this when you want the widget to render runtime health, project "
                "insights, and next-step planning in one operator view."
            ),
            "annotations": {
                "readOnlyHint": True,
                "destructiveHint": False,
                "openWorldHint": False,
                "idempotentHint": True,
            },
            "meta": {
                "ui": {"resourceUri": WIDGET_URI},
                "ui_resource": WIDGET_URI,
                "openai/outputTemplate": WIDGET_URI,
                "openai/toolInvocation/invoking": "Rendering operator dashboard…",
                "openai/toolInvocation/invoked": "Operator dashboard rendered",
            },
        },
        "run_diagnostic_job": {
            "title": "Run Diagnostic Job",
            "description": (
                "Use this when you need a non-destructive diagnostic job such as "
                "readiness checks or quick retrieval benchmarks."
            ),
            "annotations": {
                "readOnlyHint": False,
                "destructiveHint": False,
                "openWorldHint": False,
                "idempotentHint": False,
            },
            "meta": {
                "openai/toolInvocation/invoking": "Starting diagnostic job…",
                "openai/toolInvocation/invoked": "Diagnostic job started",
            },
        },
        "run_corpus_operation": {
            "title": "Run Corpus Operation",
            "description": (
                "Use this when an operator explicitly wants an allowlisted corpus action "
                "such as reindexing or a source update. Requires confirm=true."
            ),
            "annotations": {
                "readOnlyHint": False,
                "destructiveHint": False,
                "openWorldHint": False,
                "idempotentHint": False,
            },
            "meta": {
                "openai/toolInvocation/invoking": "Starting corpus operation…",
                "openai/toolInvocation/invoked": "Corpus operation started",
            },
        },
        "get_job_status": {
            "title": "Get Job Status",
            "description": (
                "Use this when you need the latest status and logs for a previously "
                "started diagnostic or corpus job."
            ),
            "annotations": {
                "readOnlyHint": True,
                "destructiveHint": False,
                "openWorldHint": False,
                "idempotentHint": True,
            },
            "meta": {
                "openai/toolInvocation/invoking": "Checking job status…",
                "openai/toolInvocation/invoked": "Job status ready",
            },
        },
    }


def build_widget_resource_descriptor() -> dict[str, Any]:
    """Return metadata for the ChatGPT widget resource."""
    csp = {"connectDomains": [], "resourceDomains": []}
    return {
        "uri": WIDGET_URI,
        "mime_type": "text/html;profile=mcp-app",
        "meta": {
            "ui": {
                "prefersBorder": True,
                "csp": csp,
            },
            "openai/widgetDescription": (
                "Internal Constitutional AI operator dashboard for query reports, "
                "runtime health, project insights, and job status."
            ),
            "openai/widgetPrefersBorder": True,
            "openai/widgetCSP": {
                "connect_domains": [],
                "resource_domains": [],
            },
        },
    }


@dataclass
class JobStatus:
    id: str
    tool_name: str
    operation: str
    status: str
    command: list[str]
    read_only: bool
    created_at: str
    started_at: str | None = None
    completed_at: str | None = None
    returncode: int | None = None
    stdout: str = ""
    stderr: str = ""

    def to_public_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["command_display"] = " ".join(self.command)
        return payload


class JobRegistry:
    """Track allowlisted background jobs launched from MCP tools."""

    def __init__(self) -> None:
        self._jobs: dict[str, JobStatus] = {}
        self._lock = asyncio.Lock()

    async def start(self, job_request: JobRequest) -> JobStatus:
        now = _now_iso()
        job_id = uuid.uuid4().hex
        status = JobStatus(
            id=job_id,
            tool_name=job_request.tool_name,
            operation=job_request.operation,
            status="queued",
            command=job_request.command,
            read_only=job_request.read_only,
            created_at=now,
        )
        async with self._lock:
            self._jobs[job_id] = status
        asyncio.create_task(self._run_job(job_id, job_request))
        return status

    async def get(self, job_id: str) -> JobStatus | None:
        async with self._lock:
            return self._jobs.get(job_id)

    async def _run_job(self, job_id: str, job_request: JobRequest) -> None:
        await self._update(job_id, status="running", started_at=_now_iso())
        try:
            process = await asyncio.create_subprocess_exec(
                *job_request.command,
                cwd=str(BACKEND_ROOT),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_bytes, stderr_bytes = await process.communicate()
            stdout = _trim_output(stdout_bytes.decode("utf-8", errors="replace"))
            stderr = _trim_output(stderr_bytes.decode("utf-8", errors="replace"))
            await self._update(
                job_id,
                status="succeeded" if process.returncode == 0 else "failed",
                completed_at=_now_iso(),
                returncode=process.returncode,
                stdout=stdout,
                stderr=stderr,
            )
        except Exception as exc:  # pragma: no cover - defensive path
            await self._update(
                job_id,
                status="failed",
                completed_at=_now_iso(),
                returncode=-1,
                stderr=str(exc),
            )

    async def _update(self, job_id: str, **changes: Any) -> None:
        async with self._lock:
            job = self._jobs[job_id]
            for key, value in changes.items():
                setattr(job, key, value)


_job_registry = JobRegistry()


def create_chatgpt_mcp_server(
    *,
    orchestrator_provider: Callable[[], OrchestratorService] | None = None,
) -> FastMCP:
    """Create the FastMCP server used by ChatGPT Developer Mode."""
    catalog = build_tool_catalog()
    widget_descriptor = build_widget_resource_descriptor()
    provider = orchestrator_provider or get_orchestrator_service

    server = FastMCP(
        "Constitutional AI Operator",
        instructions=(
            "Internal operator app for Constitutional AI. Prefer read-only inspection "
            "tools for understanding the project and runtime before launching jobs."
        ),
        host="0.0.0.0",
        stateless_http=True,
        json_response=True,
        streamable_http_path="/",
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=ALLOWED_MCP_HOSTS,
            allowed_origins=ALLOWED_MCP_ORIGINS,
        ),
    )

    @server.resource(
        widget_descriptor["uri"],
        name="constitutional-operator-widget",
        title="Constitutional AI Operator",
        description=(
            "Widget UI for query reports, runtime snapshots, project insights, and "
            "operational job tracking."
        ),
        mime_type=widget_descriptor["mime_type"],
        meta=widget_descriptor["meta"],
    )
    def operator_widget() -> str:
        return build_widget_html(default_view="operator")

    @server.tool(
        name="query_constitutional_ai",
        title=catalog["query_constitutional_ai"]["title"],
        description=catalog["query_constitutional_ai"]["description"],
        annotations=ToolAnnotations(**catalog["query_constitutional_ai"]["annotations"]),
        meta=catalog["query_constitutional_ai"]["meta"],
    )
    async def query_constitutional_ai(
        question: str,
        mode: Literal["auto", "chat", "assist", "evidence"] = "auto",
        retrieval_strategy: Literal[
            "parallel_v1", "rewrite_v1", "rag_fusion", "adaptive"
        ] = "adaptive",
        use_agent: bool = False,
    ) -> CallToolResult:
        result = await _run_query(
            orchestrator=provider(),
            question=question,
            mode=mode,
            retrieval_strategy=retrieval_strategy,
            use_agent=use_agent,
        )
        payload = build_query_tool_payload(result)
        structured = {
            **payload["structured_content"],
            "mode": getattr(result.mode, "value", str(result.mode)),
        }
        return CallToolResult(
            content=[
                TextContent(type="text", text=payload["summary_text"] or "No answer returned.")
            ],
            structuredContent=structured,
            _meta=payload["meta"],
        )

    @server.tool(
        name="inspect_runtime",
        title=catalog["inspect_runtime"]["title"],
        description=catalog["inspect_runtime"]["description"],
        annotations=ToolAnnotations(**catalog["inspect_runtime"]["annotations"]),
        meta=catalog["inspect_runtime"]["meta"],
    )
    async def inspect_runtime() -> CallToolResult:
        snapshot = await _build_runtime_snapshot(provider())
        summary = (
            f"Runtime is {snapshot['readiness']['status']} with model "
            f"{snapshot['config']['constitutional_model']}."
        )
        structured = {
            "status": snapshot["readiness"]["status"],
            "service_count": len(snapshot["services"]),
            "collection_count": len(snapshot["collections"]),
            "constitutional_model": snapshot["config"]["constitutional_model"],
            "default_collections": snapshot["config"]["default_collections"],
        }
        return CallToolResult(
            content=[TextContent(type="text", text=summary)],
            structuredContent=structured,
            _meta=snapshot,
        )

    @server.tool(
        name="inspect_project",
        title=catalog["inspect_project"]["title"],
        description=catalog["inspect_project"]["description"],
        annotations=ToolAnnotations(**catalog["inspect_project"]["annotations"]),
        meta=catalog["inspect_project"]["meta"],
    )
    async def inspect_project() -> CallToolResult:
        snapshot = _build_project_snapshot()
        content_text = (
            "Project snapshot prepared with canonical docs, architecture hotspots, "
            "and recommended next steps."
        )
        structured = {
            "repo_root": str(REPO_ROOT),
            "canonical_doc_count": len(snapshot["canonical_docs"]),
            "architecture_summary": snapshot["architecture_summary"],
            "risk_count": len(snapshot["risks"]),
            "next_steps": snapshot["next_steps"],
        }
        return CallToolResult(
            content=[TextContent(type="text", text=content_text)],
            structuredContent=structured,
            _meta=snapshot,
        )

    @server.tool(
        name="render_query_report",
        title=catalog["render_query_report"]["title"],
        description=catalog["render_query_report"]["description"],
        annotations=ToolAnnotations(**catalog["render_query_report"]["annotations"]),
        meta=catalog["render_query_report"]["meta"],
    )
    async def render_query_report(
        question: str,
        mode: Literal["auto", "chat", "assist", "evidence"] = "auto",
        retrieval_strategy: Literal[
            "parallel_v1", "rewrite_v1", "rag_fusion", "adaptive"
        ] = "adaptive",
        use_agent: bool = False,
    ) -> CallToolResult:
        result = await _run_query(
            orchestrator=provider(),
            question=question,
            mode=mode,
            retrieval_strategy=retrieval_strategy,
            use_agent=use_agent,
        )
        payload = build_query_tool_payload(result)
        structured = {
            "view": "query",
            "question": question,
            "mode": getattr(result.mode, "value", str(result.mode)),
            **payload["structured_content"],
        }
        return CallToolResult(
            content=[TextContent(type="text", text="Rendering Constitutional AI query report.")],
            structuredContent=structured,
            _meta={
                **payload["meta"],
                "ui": {"resourceUri": WIDGET_URI, "defaultView": "query"},
                "openai/outputTemplate": WIDGET_URI,
            },
        )

    @server.tool(
        name="render_operator_dashboard",
        title=catalog["render_operator_dashboard"]["title"],
        description=catalog["render_operator_dashboard"]["description"],
        annotations=ToolAnnotations(**catalog["render_operator_dashboard"]["annotations"]),
        meta=catalog["render_operator_dashboard"]["meta"],
    )
    async def render_operator_dashboard() -> CallToolResult:
        runtime = await _build_runtime_snapshot(provider())
        project = _build_project_snapshot()
        structured = {
            "view": "operator",
            "runtime_status": runtime["readiness"]["status"],
            "constitutional_model": runtime["config"]["constitutional_model"],
            "architecture_summary": project["architecture_summary"],
            "next_steps": project["next_steps"],
        }
        return CallToolResult(
            content=[TextContent(type="text", text="Rendering operator dashboard.")],
            structuredContent=structured,
            _meta={
                "runtime": runtime,
                "project": project,
                "ui": {"resourceUri": WIDGET_URI, "defaultView": "operator"},
                "openai/outputTemplate": WIDGET_URI,
            },
        )

    @server.tool(
        name="run_diagnostic_job",
        title=catalog["run_diagnostic_job"]["title"],
        description=catalog["run_diagnostic_job"]["description"],
        annotations=ToolAnnotations(**catalog["run_diagnostic_job"]["annotations"]),
        meta=catalog["run_diagnostic_job"]["meta"],
    )
    async def run_diagnostic_job(
        operation: Literal[
            "readiness_check",
            "smoke_test_pipeline",
            "compare_retrieval_quality",
            "rag_benchmark_quick",
        ],
    ) -> CallToolResult:
        return await _launch_job("run_diagnostic_job", operation, confirm=False)

    @server.tool(
        name="run_corpus_operation",
        title=catalog["run_corpus_operation"]["title"],
        description=catalog["run_corpus_operation"]["description"],
        annotations=ToolAnnotations(**catalog["run_corpus_operation"]["annotations"]),
        meta=catalog["run_corpus_operation"]["meta"],
    )
    async def run_corpus_operation(
        operation: Literal["reindex_corpus", "sfs_update", "harvest_source"],
        confirm: bool = False,
    ) -> CallToolResult:
        return await _launch_job("run_corpus_operation", operation, confirm=confirm)

    @server.tool(
        name="get_job_status",
        title=catalog["get_job_status"]["title"],
        description=catalog["get_job_status"]["description"],
        annotations=ToolAnnotations(**catalog["get_job_status"]["annotations"]),
        meta=catalog["get_job_status"]["meta"],
    )
    async def get_job_status(job_id: str) -> CallToolResult:
        status = await _job_registry.get(job_id)
        if not status:
            return CallToolResult(
                content=[TextContent(type="text", text=f"Unknown job id: {job_id}")],
                structuredContent={"job_id": job_id, "status": "missing"},
                _meta={"job_id": job_id},
                isError=True,
            )

        return CallToolResult(
            content=[
                TextContent(
                    type="text",
                    text=f"Job {job_id} is {status.status}.",
                )
            ],
            structuredContent={
                "job_id": job_id,
                "status": status.status,
                "operation": status.operation,
                "returncode": status.returncode,
            },
            _meta=status.to_public_dict(),
        )

    return server


def mount_chatgpt_app(
    app: FastAPI,
    *,
    orchestrator_provider: Callable[[], OrchestratorService] | None = None,
) -> FastMCP:
    """Mount the ChatGPT MCP server into an existing FastAPI app."""
    existing = getattr(app.state, "chatgpt_mcp_server", None)
    if existing is not None:
        return existing

    server = create_chatgpt_mcp_server(orchestrator_provider=orchestrator_provider)
    mcp_app = server.streamable_http_app()
    app.state.chatgpt_mcp_server = server
    app.state.chatgpt_mcp_app = mcp_app
    app.mount("/mcp", mcp_app)
    return server


async def _launch_job(tool_name: str, operation: str, *, confirm: bool) -> CallToolResult:
    try:
        job_request = resolve_job_request(
            tool_name=tool_name,
            operation=operation,
            confirm=confirm,
        )
    except JobValidationError as exc:
        return CallToolResult(
            content=[TextContent(type="text", text=str(exc))],
            structuredContent={"operation": operation, "status": "rejected"},
            _meta={"tool_name": tool_name, "operation": operation},
            isError=True,
        )

    status = await _job_registry.start(job_request)
    return CallToolResult(
        content=[
            TextContent(
                type="text",
                text=f"Started {operation}. Track progress with get_job_status.",
            )
        ],
        structuredContent={
            "job_id": status.id,
            "status": status.status,
            "operation": operation,
        },
        _meta=status.to_public_dict(),
    )


async def _run_query(
    *,
    orchestrator: OrchestratorService,
    question: str,
    mode: str,
    retrieval_strategy: str,
    use_agent: bool,
):
    strategy_map = {
        "parallel_v1": RetrievalStrategy.PARALLEL_V1,
        "rewrite_v1": RetrievalStrategy.REWRITE_V1,
        "rag_fusion": RetrievalStrategy.RAG_FUSION,
        "adaptive": RetrievalStrategy.ADAPTIVE,
    }
    strategy = strategy_map.get(retrieval_strategy, RetrievalStrategy.ADAPTIVE)
    return await orchestrator.process_query(
        question=question,
        mode=mode,
        k=10,
        retrieval_strategy=strategy,
        use_agent=use_agent,
    )


async def _build_runtime_snapshot(orchestrator: OrchestratorService) -> dict[str, Any]:
    healthy = await orchestrator.health_check()
    services = orchestrator.get_status()
    readiness = await build_dependency_readiness(orchestrator)
    readiness_checks = readiness["checks"]
    collections = readiness["collections"]
    metrics = get_rag_metrics().get_full_metrics()
    config = {
        "constitutional_model": getattr(orchestrator.config, "constitutional_model", "unknown"),
        "default_collections": getattr(orchestrator.config, "effective_default_collections", []),
        "chromadb_path": getattr(orchestrator.config, "chromadb_path", None),
        "critic_revise_enabled": getattr(
            orchestrator.config,
            "critic_revise_effective_enabled",
            False,
        ),
        "crag_enabled": getattr(orchestrator.config.settings, "crag_enabled", False),
    }
    return {
        "timestamp": _now_iso(),
        "health": {"status": "healthy" if healthy else "degraded", "services": services},
        "readiness": {
            "status": readiness["status"],
            "checks": readiness_checks,
        },
        "services": services,
        "collections": collections,
        "config": config,
        "metrics": {
            "lifetime": metrics.get("lifetime", {}),
            "last_5min": metrics.get("last_5min", {}),
            "by_mode": metrics.get("by_mode", {}),
        },
    }


async def _build_readiness_checks(
    orchestrator: OrchestratorService,
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    readiness = await build_dependency_readiness(orchestrator)
    return readiness["checks"], readiness["collections"]


def _build_project_snapshot() -> dict[str, Any]:
    canonical_docs = [
        _document_snapshot(REPO_ROOT / "README.md"),
        _document_snapshot(REPO_ROOT / "docs" / "ARCHITECTURE.md"),
        _document_snapshot(REPO_ROOT / "docs" / "IMPLEMENTATION_ROADMAP.md"),
        _document_snapshot(REPO_ROOT / "docs" / "README_DOCS_AND_RAG_INSTRUCTIONS.md"),
        _document_snapshot(REPO_ROOT / "docs" / "TECHNICAL_DEBT_ANALYSIS.md"),
    ]
    canonical_docs = [doc for doc in canonical_docs if doc is not None]

    return {
        "repo_root": str(REPO_ROOT),
        "timestamp": _now_iso(),
        "architecture_summary": [
            "FastAPI backend centered on OrchestratorService drives query routing, retrieval, guardrails, and generation.",
            "React frontend streams pipeline states and sources through a dedicated agent query SSE flow.",
            "Scrapers, indexers, evaluations, and docs live in the same mono-repo, which makes operator context rich but broad.",
        ],
        "key_paths": {
            "backend_entrypoint": "backend/app/main.py",
            "rag_routes": "backend/app/api/constitutional_routes.py",
            "frontend_state": "apps/konstitutionell-frontend/src/stores/useAppStore.ts",
            "docs_architecture": "docs/ARCHITECTURE.md",
        },
        "canonical_docs": canonical_docs,
        "risks": [
            "The orchestrator service remains large and is explicitly identified in repo docs as an architectural hotspot.",
            "The legacy /sse MCP placeholder still exists beside the new /mcp path and can confuse future integrations.",
            "Operational scripts are numerous and heterogeneous, so only narrow allowlists should ever be surfaced to tools.",
        ],
        "next_steps": [
            "Exercise the new /mcp operator layer with real queries and tune tool outputs for planning and debugging workflows.",
            "Continue decomposing OrchestratorService into smaller services to reduce coupling and simplify diagnostics.",
            "Add focused regression tests around MCP tool contracts, widget rendering metadata, and allowlisted job wrappers.",
        ],
        "frontend_signals": [
            "searchStage",
            "pipelineStage",
            "sources",
            "evidenceLevel",
            "thoughtChain",
        ],
    }


def _document_snapshot(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None

    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    headings = [line.lstrip("# ").strip() for line in lines if line.startswith("#")][:6]
    preview_lines = [line.strip() for line in lines if line.strip()][:4]
    return {
        "path": str(path.relative_to(REPO_ROOT)),
        "headings": headings,
        "preview": preview_lines,
    }


def _trim_output(value: str, limit: int = 6000) -> str:
    value = value.strip()
    if len(value) <= limit:
        return value
    return value[: limit - 15] + "\n…output truncated"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()

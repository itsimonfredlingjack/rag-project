"""Public Riksdagen demo runtime profile tests."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.config_service import ConfigSettings


PUBLIC_PROFILE = "public-riksdag-demo"
PUBLIC_SCOPE = "riksdagen_open_data_only"
PUBLIC_ROOT = "/home/ai-server2/rag/local-data-public/riksdag"
REPO_ROOT = __import__("pathlib").Path(__file__).resolve().parents[2]


def test_public_riksdag_profile_applies_hard_public_defaults():
    settings = ConfigSettings(
        profile=PUBLIC_PROFILE,
        chromadb_path="/home/ai-server2/rag/local-data-private/chromadb",
        bm25_index_path="/home/ai-server2/rag/local-data-private/bm25_fts5/bm25.db",
        _env_file=None,
    )

    assert settings.profile == PUBLIC_PROFILE
    assert settings.corpus_scope == PUBLIC_SCOPE
    assert settings.bm25_enabled is True
    assert settings.chromadb_enabled is False
    assert settings.reranking_enabled is False
    assert settings.crag_enabled is False
    assert settings.critic_revise_enabled is False
    assert settings.structured_output_enabled is True
    assert settings.intent_llm_fallback_enabled is False
    assert settings.constitutional_model == "gemma4:e2b"
    assert settings.constitutional_fallback == "gemma4:e2b"
    assert settings.gguf_primary_model == "gemma4:e2b"
    assert settings.crag_grader_model == "gemma4:e2b"
    assert settings.gguf_context_window == 2048
    assert settings.ollama_num_ctx == 2048
    assert settings.mode_evidence_temperature <= 0.1
    assert settings.chromadb_path == f"{PUBLIC_ROOT}/chromadb"
    assert settings.pdf_cache_path == f"{PUBLIC_ROOT}/pdf_cache"
    assert settings.bm25_index_path == f"{PUBLIC_ROOT}/bm25_fts5/bm25.db"

    public_paths = (settings.chromadb_path, settings.pdf_cache_path, settings.bm25_index_path)
    assert all(path.startswith(PUBLIC_ROOT) for path in public_paths)
    assert all("local-data-private" not in path for path in public_paths)


def test_public_riksdag_profile_overrides_model_env_aliases(monkeypatch):
    monkeypatch.setenv("CONST_PROFILE", PUBLIC_PROFILE)
    monkeypatch.setenv("CONST_SVENSK_RAGG_MODEL", "gemma4:e2b")
    monkeypatch.setenv("CONST_SVENSK_RAGG_FALLBACK", "gemma4:e2b")
    monkeypatch.setenv("CONST_GGUF_PRIMARY_MODEL", "gemma4:e2b")
    monkeypatch.setenv("CONST_CRAG_GRADER_MODEL", "gemma4:e2b")

    settings = ConfigSettings(_env_file=None)

    assert settings.profile == PUBLIC_PROFILE
    assert settings.constitutional_model == "gemma4:e2b"
    assert settings.constitutional_fallback == "gemma4:e2b"
    assert settings.gguf_primary_model == "gemma4:e2b"
    assert settings.crag_grader_model == "gemma4:e2b"


def test_private_lab_defaults_remain_unchanged():
    settings = ConfigSettings(profile="private-swedish-legal-lab", _env_file=None)

    assert settings.profile == "private-swedish-legal-lab"
    assert settings.corpus_scope == "mixed_recovered_corpus"
    assert settings.chromadb_enabled is True
    assert settings.bm25_enabled is True
    assert settings.reranking_enabled is True
    assert settings.crag_enabled is True
    assert settings.critic_revise_enabled is True
    assert settings.constitutional_model == "gemma4:e2b"


def test_start_system_defaults_to_public_riksdag_demo_profile():
    script = (REPO_ROOT / "start_system.sh").read_text(encoding="utf-8")

    assert 'RUNTIME_PROFILE="${CONST_PROFILE:-public-riksdag-demo}"' in script
    assert 'MODEL="${OLLAMA_MODEL:-gemma4:e2b}"' in script
    assert "CONST_PROFILE='$RUNTIME_PROFILE'" in script


def test_default_orchestrator_dependency_reuses_lifespan_singleton():
    from app.services import orchestrator_service

    orchestrator_service._get_default_orchestrator_service.cache_clear()
    try:
        from_lifespan = orchestrator_service.get_orchestrator_service()
        from_fastapi_dependency = orchestrator_service.get_orchestrator_service(
            config=None,
            llm_service=None,
            query_processor=None,
            guardrail=None,
            retrieval=None,
            reranker=None,
            structured_output=None,
        )

        assert from_fastapi_dependency is from_lifespan
    finally:
        orchestrator_service._get_default_orchestrator_service.cache_clear()


@pytest.mark.asyncio
async def test_public_runtime_snapshot_exposes_status_without_absolute_paths(monkeypatch):
    from app.chatgpt_app import server

    async def fake_readiness(_orchestrator):
        return {
            "status": "ready",
            "checks": {},
            "collections": [],
            "timestamp": "2026-05-29T00:00:00",
        }

    monkeypatch.setattr(server, "build_dependency_readiness", fake_readiness)
    monkeypatch.setattr(
        server,
        "get_rag_metrics",
        lambda: SimpleNamespace(get_full_metrics=lambda: {}),
    )

    config = SimpleNamespace(
        profile=PUBLIC_PROFILE,
        corpus_scope=PUBLIC_SCOPE,
        constitutional_model="gemma4:e2b",
        effective_default_collections=["riksdag_documents_p1_jina_v3_1024"],
        chromadb_path=f"{PUBLIC_ROOT}/chromadb",
        bm25_enabled=True,
        bm25_index_path=f"{PUBLIC_ROOT}/bm25_fts5/bm25.db",
        structured_output_effective_enabled=True,
        critic_revise_effective_enabled=False,
        settings=SimpleNamespace(
            chromadb_enabled=False,
            crag_enabled=False,
            reranking_enabled=False,
            intent_llm_fallback_enabled=False,
            gguf_context_window=2048,
            ollama_num_ctx=2048,
        ),
    )
    orchestrator = SimpleNamespace(
        config=config,
        health_check=AsyncMock(return_value=True),
        get_status=MagicMock(return_value={}),
    )

    snapshot = await server._build_runtime_snapshot(orchestrator)

    assert snapshot["config"]["profile"] == PUBLIC_PROFILE
    assert snapshot["config"]["corpus_scope"] == PUBLIC_SCOPE
    assert snapshot["config"]["chromadb_enabled"] is False
    assert snapshot["config"]["bm25_index_path"] == "public_bm25_index"
    assert snapshot["config"]["chromadb_path"] == "public_chroma_disabled"
    assert "/home/" not in __import__("json").dumps(snapshot)


@pytest.mark.asyncio
async def test_public_orchestrator_health_skips_chroma_retrieval(monkeypatch):
    from app.services.orchestrator_service import OrchestratorService

    config = SimpleNamespace(
        profile=PUBLIC_PROFILE,
        critic_revise_effective_enabled=False,
        settings=SimpleNamespace(crag_enabled=False),
    )
    llm_service = SimpleNamespace(health_check=AsyncMock(return_value=True), close=AsyncMock())
    query_processor = SimpleNamespace(health_check=AsyncMock(return_value=True))
    guardrail = SimpleNamespace(health_check=AsyncMock(return_value=True))
    retrieval = SimpleNamespace(health_check=AsyncMock(return_value=False), close=AsyncMock())
    reranker = SimpleNamespace(health_check=AsyncMock(return_value=True), close=AsyncMock())
    structured_output = SimpleNamespace(
        health_check=AsyncMock(return_value=True), close=AsyncMock()
    )
    critic = SimpleNamespace(health_check=AsyncMock(return_value=True), close=AsyncMock())
    grader = SimpleNamespace(health_check=AsyncMock(return_value=True), close=AsyncMock())

    orchestrator = OrchestratorService(
        config=config,
        llm_service=llm_service,
        query_processor=query_processor,
        guardrail=guardrail,
        retrieval=retrieval,
        reranker=reranker,
        structured_output=structured_output,
        critic=critic,
        grader=grader,
    )

    assert await orchestrator.health_check() is True
    retrieval.health_check.assert_not_called()

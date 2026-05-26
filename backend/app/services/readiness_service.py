"""Shared deep-readiness checks for the Constitutional AI runtime."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .orchestrator_service import OrchestratorService


async def build_dependency_readiness(orchestrator: OrchestratorService) -> dict[str, Any]:
    """
    Build the single source of truth for runtime readiness.

    Health is process-level. Readiness is data/runtime-level: expected Chroma
    collections must be present and non-empty, BM25 must be usable, embeddings
    must be loaded, and the configured LLM must be reachable.
    """
    checks: dict[str, dict[str, Any]] = {}
    collections_payload: list[dict[str, Any]] = []
    all_ready = True

    try:
        if hasattr(orchestrator, "retrieval") and orchestrator.retrieval:
            chromadb_healthy = await orchestrator.retrieval.health_check()
            client = getattr(orchestrator.retrieval, "_chromadb_client", None)
            expected_collections = list(
                getattr(orchestrator.config, "effective_default_collections", [])
            )
            if chromadb_healthy and client:
                raw_collections = (
                    client.list_collections() if hasattr(client, "list_collections") else []
                )
                collection_names = sorted(
                    getattr(collection, "name", str(collection)) for collection in raw_collections
                )
                counts: dict[str, int | None] = {}
                for name in collection_names:
                    count = None
                    try:
                        collection = client.get_collection(name=name)
                        count = int(collection.count())
                    except Exception:
                        count = None
                    counts[name] = count
                    collections_payload.append({"name": name, "document_count": count})

                missing = sorted(set(expected_collections) - set(collection_names))
                empty = sorted(
                    name
                    for name in expected_collections
                    if name in counts and (counts[name] is None or counts[name] <= 0)
                )
                status_value = "ok" if not missing and not empty else "degraded"
                if missing or empty:
                    all_ready = False
                checks["chromadb"] = {
                    "status": status_value,
                    "details": {
                        "collections": len(collection_names),
                        "collection_names": collection_names,
                        "collection_counts": counts,
                        "expected_collections": expected_collections,
                        "missing_expected_collections": missing,
                        "empty_expected_collections": empty,
                    },
                }
            elif client is None:
                checks["chromadb"] = {
                    "status": "error",
                    "details": {"error": "Client not initialized"},
                }
                all_ready = False
            else:
                checks["chromadb"] = {
                    "status": "degraded",
                    "details": {"healthy": chromadb_healthy},
                }
                all_ready = False
        else:
            checks["chromadb"] = {
                "status": "error",
                "details": {"error": "Retrieval service not available"},
            }
            all_ready = False
    except Exception as exc:
        checks["chromadb"] = {"status": "error", "details": {"error": str(exc)}}
        all_ready = False

    try:
        if hasattr(orchestrator, "llm_service") and orchestrator.llm_service:
            llm_healthy = await orchestrator.llm_service.health_check()
            model_name = getattr(orchestrator.config.settings, "constitutional_model", "unknown")
            fallback_model = getattr(orchestrator.config.settings, "constitutional_fallback", None)
            available_models = []
            if llm_healthy and hasattr(orchestrator.llm_service, "list_models"):
                available_models = await orchestrator.llm_service.list_models()
            primary_available = (
                model_name == "unknown"
                or not available_models
                or any(model_name == model or model_name in model for model in available_models)
            )
            fallback_available = (
                not fallback_model
                or not available_models
                or any(
                    fallback_model == model or fallback_model in model
                    for model in available_models
                )
            )
            status_value = "ok" if llm_healthy and primary_available else "degraded"
            if not llm_healthy or not primary_available:
                all_ready = False
            checks["llm_service"] = {
                "status": status_value,
                "details": {
                    "model": model_name,
                    "fallback_model": fallback_model,
                    "available_models": available_models,
                    "primary_available": primary_available,
                    "fallback_available": fallback_available,
                },
            }
        else:
            checks["llm_service"] = {
                "status": "error",
                "details": {"error": "LLM service not available"},
            }
            all_ready = False
    except Exception as exc:
        checks["llm_service"] = {"status": "error", "details": {"error": str(exc)}}
        all_ready = False

    try:
        if hasattr(orchestrator, "retrieval") and orchestrator.retrieval:
            embedding_svc = getattr(orchestrator.retrieval, "_embedding_service", None)
            if embedding_svc:
                is_loaded_attr = getattr(embedding_svc, "is_loaded", None)
                if callable(is_loaded_attr):
                    loaded = bool(is_loaded_attr())
                else:
                    loaded = bool(getattr(embedding_svc, "is_initialized", False))
                checks["embedding_service"] = {
                    "status": "ok" if loaded else "degraded",
                    "details": {
                        "loaded": loaded,
                        "model": getattr(orchestrator.config, "embedding_model", None),
                        "expected_dim": getattr(orchestrator.config, "expected_embedding_dim", None),
                    },
                }
                if not loaded:
                    all_ready = False
            else:
                checks["embedding_service"] = {
                    "status": "degraded",
                    "details": {"error": "Embedding service not initialized"},
                }
                all_ready = False
        else:
            checks["embedding_service"] = {
                "status": "error",
                "details": {"error": "Retrieval service not available"},
            }
            all_ready = False
    except Exception as exc:
        checks["embedding_service"] = {"status": "error", "details": {"error": str(exc)}}
        all_ready = False

    try:
        bm25_enabled = bool(getattr(orchestrator.config, "bm25_enabled", False))
        bm25_service = None
        retrieval = getattr(orchestrator, "retrieval", None)
        retrieval_orchestrator = getattr(retrieval, "_orchestrator", None)
        if retrieval_orchestrator:
            bm25_service = getattr(retrieval_orchestrator, "_bm25_service", None)

        if bm25_service:
            validation = (
                bm25_service.validate()
                if hasattr(bm25_service, "validate")
                else {"usable": bool(getattr(bm25_service, "is_available", lambda: False)())}
            )
            details = (
                bm25_service.get_stats()
                if hasattr(bm25_service, "get_stats")
                else {"available": bool(getattr(bm25_service, "is_available", lambda: False)())}
            )
            usable = bool(validation.get("usable"))
            checks["bm25"] = {
                "status": "ok" if usable else "degraded",
                "details": {**details, "enabled": bm25_enabled, "validation": validation},
            }
            if bm25_enabled and not usable:
                all_ready = False
        else:
            status_value = "degraded" if bm25_enabled else "ok"
            checks["bm25"] = {
                "status": status_value,
                "details": {"enabled": bm25_enabled, "available": False, "usable": False},
            }
            if bm25_enabled:
                all_ready = False
    except Exception as exc:
        checks["bm25"] = {"status": "error", "details": {"error": str(exc)}}
        all_ready = False

    return {
        "status": "ready" if all_ready else "not_ready",
        "checks": checks,
        "collections": collections_payload,
        "timestamp": datetime.now().isoformat(),
    }

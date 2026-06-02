"""Shared deep-readiness checks for the Svensk Ragg runtime."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from .orchestrator_service import OrchestratorService
from ..shared.public_corpus_manifest import (
    PUBLIC_BM25_PATH,
    PublicCorpusManifestError,
    load_checkpoint,
    load_manifest,
    validate_public_checkpoint,
    validate_public_manifest,
)
from ..shared.public_source_guard import (
    PUBLIC_PROFILE,
    PUBLIC_SOURCE,
    PUBLIC_SOURCE_SCOPE,
    is_public_profile,
)


async def build_dependency_readiness(orchestrator: OrchestratorService) -> dict[str, Any]:
    if is_public_profile(getattr(orchestrator, "config", None)):
        return await _build_public_dependency_readiness(orchestrator)

    readiness = await _build_generic_dependency_readiness(orchestrator)
    readiness["profile"] = _config_value(orchestrator, "profile", "unknown")
    readiness["corpus_scope"] = _config_value(orchestrator, "corpus_scope", "unknown")
    readiness["can_answer"] = readiness["status"] == "ready"
    return readiness


async def _build_generic_dependency_readiness(orchestrator: OrchestratorService) -> dict[str, Any]:
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
                    fallback_model == model or fallback_model in model for model in available_models
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
                        "expected_dim": getattr(
                            orchestrator.config, "expected_embedding_dim", None
                        ),
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


async def _build_public_dependency_readiness(orchestrator: OrchestratorService) -> dict[str, Any]:
    """Build readiness for the public Riksdagen demo profile."""
    config = getattr(orchestrator, "config", None)
    profile = _config_value(orchestrator, "profile", "unknown")
    corpus_scope = _config_value(orchestrator, "corpus_scope", "unknown")
    bm25_path = _public_bm25_path(config)
    public_root = bm25_path.parent.parent
    manifest_path = public_root / "manifest.json"
    checkpoint_path = public_root / "docs.checkpoint.json"

    manifest = _read_public_manifest(manifest_path, profile=profile, corpus_scope=corpus_scope)
    checkpoint = _read_public_checkpoint(checkpoint_path, corpus_scope=corpus_scope)
    bm25 = _inspect_public_bm25(bm25_path, expected_document_count=manifest.get("document_count"))
    chroma = await _inspect_public_chroma(orchestrator)
    llm = await _inspect_public_llm(orchestrator)

    profile_ready = profile == PUBLIC_PROFILE and corpus_scope == PUBLIC_SOURCE_SCOPE
    manifest_ready = manifest["status"] == "ready"
    checkpoint_ready = checkpoint["status"] == "ready"
    bm25_ready = bm25["status"] == "ready"
    chroma_ready = chroma["status"] in {"ready", "disabled"}
    llm_ready = llm["status"] == "ready"
    can_answer = profile_ready and manifest_ready and checkpoint_ready and bm25_ready and llm_ready

    if can_answer and chroma["status"] == "disabled":
        status = "degraded_but_usable"
    elif can_answer and chroma_ready:
        status = "ready"
    else:
        status = "not_ready"

    checks = {
        "profile": {
            "status": "ok" if profile_ready else "error",
            "details": {
                "profile": profile,
                "expected_profile": PUBLIC_PROFILE,
                "corpus_scope": corpus_scope,
                "expected_corpus_scope": PUBLIC_SOURCE_SCOPE,
            },
        },
        "manifest": {
            "status": "ok" if manifest_ready else "error",
            "details": manifest,
        },
        "checkpoint": {
            "status": "ok" if checkpoint_ready else "error",
            "details": checkpoint,
        },
        "bm25": {
            "status": "ok" if bm25_ready else "error",
            "details": bm25,
        },
        "chromadb": {
            "status": "ok" if chroma_ready else "error",
            "details": chroma,
        },
        "llm_service": {
            "status": "ok" if llm_ready else "error",
            "details": llm,
        },
    }

    return {
        "status": status,
        "can_answer": can_answer,
        "profile": profile,
        "corpus_scope": corpus_scope,
        "manifest": manifest,
        "checkpoint": checkpoint,
        "bm25": bm25,
        "chroma": chroma,
        "llm": llm,
        "checks": checks,
        "collections": chroma.get("collections", []),
        "timestamp": datetime.now().isoformat(),
    }


def _config_value(orchestrator: Any, name: str, default: Any = None) -> Any:
    config = getattr(orchestrator, "config", None)
    value = getattr(config, name, None)
    if value is None and hasattr(config, "settings"):
        value = getattr(config.settings, name, None)
    return default if value is None else value


def _public_bm25_path(config: Any) -> Path:
    raw_path = getattr(config, "bm25_index_path", None)
    if not raw_path and hasattr(config, "settings"):
        raw_path = getattr(config.settings, "bm25_index_path", None)
    return Path(str(raw_path or PUBLIC_BM25_PATH))


def _read_public_manifest(path: Path, *, profile: str, corpus_scope: str) -> dict[str, Any]:
    if not path.exists():
        return {"status": "missing", "path": str(path)}

    try:
        manifest = validate_public_manifest(
            load_manifest(path),
            expected_profile=profile,
            expected_scope=PUBLIC_SOURCE_SCOPE,
        )
        manifest_scope = manifest.get("corpus_scope", manifest.get("source_scope"))
        if manifest_scope != corpus_scope:
            raise PublicCorpusManifestError(f"corpus_scope must be {corpus_scope}")
    except (OSError, ValueError, PublicCorpusManifestError) as exc:
        return {"status": "invalid", "path": str(path), "error": str(exc)}

    return {
        "status": "ready",
        "path": str(path),
        "document_count": manifest["document_count"],
        "chunk_count": manifest["chunk_count"],
        "source_scope": manifest["source_scope"],
        "corpus_scope": manifest.get("corpus_scope", manifest["source_scope"]),
        "bm25_path": manifest["bm25_path"],
        "chroma_collection": manifest["chroma_collection"],
        "embedding_model": manifest["embedding_model"],
    }


def _read_public_checkpoint(path: Path, *, corpus_scope: str) -> dict[str, Any]:
    if not path.exists():
        return {"status": "missing", "path": str(path)}

    try:
        checkpoint = validate_public_checkpoint(load_checkpoint(path))
        checkpoint_scope = checkpoint.get("corpus_scope", checkpoint.get("source_scope"))
        if checkpoint_scope != corpus_scope:
            raise PublicCorpusManifestError(f"corpus_scope must be {corpus_scope}")
    except (OSError, ValueError, PublicCorpusManifestError) as exc:
        return {"status": "invalid", "path": str(path), "error": str(exc)}

    return {
        "status": "ready",
        "path": str(path),
        "source_scope": checkpoint["source_scope"],
        "corpus_scope": checkpoint.get("corpus_scope", checkpoint["source_scope"]),
        "start_row": checkpoint["start_row"],
        "end_row": checkpoint["end_row"],
        "scanned_rows": checkpoint["scanned_rows"],
        "kept_rows": checkpoint["kept_rows"],
        "skipped_non_riksdag_rows": checkpoint["skipped_non_riksdag_rows"],
        "forbidden_marker_scan": checkpoint["forbidden_marker_scan"],
    }


def _inspect_public_bm25(path: Path, *, expected_document_count: int | None) -> dict[str, Any]:
    if not path.exists():
        return {"status": "missing", "path": str(path)}

    try:
        with sqlite3.connect(path) as conn:
            documents_count = int(conn.execute("select count(*) from documents").fetchone()[0])
            fts_count = int(conn.execute("select count(*) from docs_fts").fetchone()[0])
            provenance_rows = conn.execute(
                """
                select source, source_scope, count(*)
                from documents
                group by source, source_scope
                order by source, source_scope
                """
            ).fetchall()
    except sqlite3.Error as exc:
        return {"status": "error", "path": str(path), "error": str(exc)}

    provenance = [
        {"source": source, "source_scope": source_scope, "count": count}
        for source, source_scope, count in provenance_rows
    ]
    clean_provenance = provenance == [
        {
            "source": PUBLIC_SOURCE,
            "source_scope": PUBLIC_SOURCE_SCOPE,
            "count": documents_count,
        }
    ]
    counts_match = documents_count == fts_count
    manifest_count_matches = (
        expected_document_count is None or expected_document_count == documents_count
    )

    if documents_count <= 0 or fts_count <= 0:
        status = "empty"
    elif not clean_provenance or not counts_match or not manifest_count_matches:
        status = "invalid"
    else:
        status = "ready"

    return {
        "status": status,
        "path": str(path),
        "documents_count": documents_count,
        "fts_count": fts_count,
        "expected_document_count": expected_document_count,
        "counts_match": counts_match,
        "manifest_count_matches": manifest_count_matches,
        "provenance_status": "clean" if clean_provenance else "dirty",
        "provenance": provenance,
    }


async def _inspect_public_chroma(orchestrator: OrchestratorService) -> dict[str, Any]:
    enabled = bool(_config_value(orchestrator, "chromadb_enabled", True))
    if not enabled:
        return {"enabled": False, "status": "disabled"}

    retrieval = getattr(orchestrator, "retrieval", None)
    if not retrieval:
        return {"enabled": True, "status": "missing", "error": "Retrieval service not available"}

    try:
        healthy = await retrieval.health_check()
        client = getattr(retrieval, "_chromadb_client", None)
        if not healthy or client is None:
            return {"enabled": True, "status": "not_ready", "healthy": healthy}

        raw_collections = client.list_collections() if hasattr(client, "list_collections") else []
        collections = [
            {"name": getattr(collection, "name", str(collection))} for collection in raw_collections
        ]
    except Exception as exc:
        return {"enabled": True, "status": "error", "error": str(exc)}

    return {
        "enabled": True,
        "status": "ready",
        "collections": collections,
    }


async def _inspect_public_llm(orchestrator: OrchestratorService) -> dict[str, Any]:
    llm_service = getattr(orchestrator, "llm_service", None)
    model_name = _config_value(orchestrator, "constitutional_model", "unknown")
    fallback_model = _config_value(orchestrator, "constitutional_fallback", None)
    if not llm_service:
        return {
            "status": "missing",
            "healthy": False,
            "model": model_name,
            "fallback_model": fallback_model,
            "available_models": [],
            "primary_available": False,
        }

    try:
        healthy = bool(await llm_service.health_check())
        available_models = (
            list(await llm_service.list_models())
            if healthy and hasattr(llm_service, "list_models")
            else []
        )
    except Exception as exc:
        return {
            "status": "error",
            "healthy": False,
            "model": model_name,
            "fallback_model": fallback_model,
            "available_models": [],
            "primary_available": False,
            "error": str(exc),
        }

    primary_available = bool(
        model_name
        and model_name != "unknown"
        and any(model_name == model or model_name in model for model in available_models)
    )
    fallback_available = bool(
        not fallback_model
        or any(fallback_model == model or fallback_model in model for model in available_models)
    )

    return {
        "status": "ready" if healthy and primary_available else "unavailable",
        "healthy": healthy,
        "model": model_name,
        "fallback_model": fallback_model,
        "available_models": available_models,
        "primary_available": primary_available,
        "fallback_available": fallback_available,
    }

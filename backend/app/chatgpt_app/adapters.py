"""Adapters that shape backend results for ChatGPT app tools."""

from __future__ import annotations

from typing import Any

from ..shared.public_source_guard import validate_public_record_if_enabled


def _serialize_source(source: Any, *, public_guard_enabled: bool = False) -> dict[str, Any]:
    payload = {
        "id": getattr(source, "id", ""),
        "title": getattr(source, "title", ""),
        "snippet": getattr(source, "snippet", ""),
        "score": getattr(source, "score", 0.0),
        "source": getattr(source, "source", ""),
        "source_scope": getattr(source, "source_scope", None),
        "doc_type": getattr(source, "doc_type", None),
        "date": getattr(source, "date", None),
        "retriever": getattr(source, "retriever", None),
        "tier": getattr(source, "tier", None),
    }
    validate_public_record_if_enabled(
        payload,
        stage="api_response_serialization",
        enabled=public_guard_enabled,
    )
    return payload


def build_query_tool_payload(
    result: Any,
    *,
    public_guard_enabled: bool = False,
) -> dict[str, Any]:
    """Convert a RAGResult-like object into model and widget payloads."""
    metrics = getattr(result, "metrics", None)
    sources = [
        _serialize_source(source, public_guard_enabled=public_guard_enabled)
        for source in getattr(result, "sources", [])
    ]
    answer = getattr(result, "answer", "") or ""
    evidence_level = getattr(result, "evidence_level", "NONE") or "NONE"
    retrieval_strategy = getattr(metrics, "retrieval_strategy", None)
    refusal = evidence_level == "NONE" or not sources

    structured_content = {
        "answer": answer,
        "evidence_level": evidence_level,
        "source_count": len(sources),
        "retrieval_strategy": retrieval_strategy,
        "intent": getattr(result, "intent", None),
        "refusal": refusal,
    }

    meta = {
        "sources": sources,
        "reasoning_steps": list(getattr(result, "reasoning_steps", []) or []),
        "thought_chain": getattr(result, "thought_chain", None),
        "metrics": {
            "retrieval_ms": getattr(metrics, "retrieval_ms", None),
            "total_pipeline_ms": getattr(metrics, "total_pipeline_ms", None),
        },
    }

    return {
        "summary_text": answer,
        "structured_content": structured_content,
        "meta": meta,
    }

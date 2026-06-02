"""BM25-only query path for the public Riksdagen demo profile."""

from __future__ import annotations

import time
from typing import Any

from ..core.exceptions import SecurityViolationError
from ..shared.public_source_guard import (
    PUBLIC_SOURCE,
    PUBLIC_SOURCE_SCOPE,
    validate_public_record,
    validate_public_records,
)
from .bm25_service import get_bm25_service
from .guardrail_service import WardenStatus
from .prompt_service import build_llm_context, estimate_tokens
from .query_processor_service import ResponseMode
from .rag_models import Citation, RAGPipelineMetrics, RAGResult
from .retrieval_service import SearchResult
from ..shared.public_corpus_manifest import SOURCE_ATTRIBUTION_TEXT

PUBLIC_QUERY_MODE = "public_bm25_only"
MAX_CONTEXT_TOKENS = 2_800
MAX_CHUNKS = 8
MAX_CHUNK_TOKENS = 450
MAX_ANSWER_TOKENS = 700
MIN_CONTEXT_TOKENS = 8
PUBLIC_REFUSAL_ANSWER = (
    "Jag hittar inte tillräckligt stöd i de hämtade Riksdagen-källorna för att svara "
    "säkert på frågan."
)
LEGAL_ADVICE_PHRASES = (
    "vad ska jag göra juridiskt",
    "kan jag stämma",
    "har jag rätt att",
    "hur överklagar jag",
    "skriv en stämningsansökan",
    "är detta lagligt för mig",
)
SOURCE_BOUNDARY_PHRASES = (
    "diva",
    "privat pdf",
    "privata pdf",
    "private pdf",
    "fulltext",
    "forskningsartikel",
    "forskningsartiklar",
    "blanda med privata",
)


def normalize_swedish_query(query: str) -> str:
    """Normalize whitespace/case while leaving Swedish text and punctuation intact."""
    return " ".join((query or "").strip().casefold().split())


async def process_public_bm25_query(
    *,
    orchestrator: Any,
    question: str,
    mode: str | ResponseMode | None,
    readiness: dict[str, Any],
) -> RAGResult:
    """Execute the public Riksdagen BM25-only query path."""
    start_time = time.perf_counter()
    resolved_mode = _resolve_public_mode(mode)
    reasoning_steps: list[str] = [f"Public readiness status: {readiness.get('status')}"]

    if not bool(readiness.get("can_answer")):
        return _refusal_result(
            start_time=start_time,
            mode=resolved_mode,
            reasoning_steps=reasoning_steps,
            refusal_reason="readiness_not_answerable",
            retrieval_metadata={
                "mode": PUBLIC_QUERY_MODE,
                "chunks_used": 0,
                "deduplicated_documents": 0,
            },
        )

    _check_query_safety(orchestrator, question)
    normalized_query = normalize_swedish_query(question)
    reasoning_steps.append(f"Normalized public query: {normalized_query}")

    preflight_refusal = _preflight_refusal_reason(normalized_query)
    if preflight_refusal:
        return _refusal_result(
            start_time=start_time,
            mode=resolved_mode,
            reasoning_steps=reasoning_steps,
            refusal_reason=preflight_refusal,
            retrieval_metadata={
                "mode": PUBLIC_QUERY_MODE,
                "chunks_used": 0,
                "deduplicated_documents": 0,
            },
        )

    retrieval_start = time.perf_counter()
    bm25 = get_bm25_service(
        index_path=_config_value(orchestrator.config, "bm25_index_path"),
        public_guard_enabled=True,
    )
    raw_results = bm25.search(
        normalized_query,
        k=max(MAX_CHUNKS * 4, MAX_CHUNKS),
        return_docs=True,
        use_compound_splitting=True,
    )
    retrieval_ms = (time.perf_counter() - retrieval_start) * 1000

    sources = _select_public_sources(raw_results)
    validate_public_records(sources, stage="public_bm25_query_selected_sources", enabled=True)
    retrieval_metadata = {
        "mode": PUBLIC_QUERY_MODE,
        "chunks_used": len(sources),
        "deduplicated_documents": len({source.document_id or source.id for source in sources}),
        "raw_results": len(raw_results),
        "max_chunks": MAX_CHUNKS,
        "max_context_tokens": MAX_CONTEXT_TOKENS,
        "max_chunk_tokens": MAX_CHUNK_TOKENS,
        "max_answer_tokens": MAX_ANSWER_TOKENS,
    }

    if not sources:
        return _refusal_result(
            start_time=start_time,
            mode=resolved_mode,
            reasoning_steps=reasoning_steps,
            refusal_reason="no_context",
            retrieval_ms=retrieval_ms,
            retrieval_metadata=retrieval_metadata,
        )

    if _is_weak_context(sources):
        return _refusal_result(
            start_time=start_time,
            mode=resolved_mode,
            reasoning_steps=reasoning_steps,
            refusal_reason="weak_context",
            retrieval_ms=retrieval_ms,
            retrieval_metadata={
                **retrieval_metadata,
                "chunks_used": 0,
                "deduplicated_documents": 0,
            },
        )

    context_text = build_llm_context(
        sources,
        max_context_tokens=MAX_CONTEXT_TOKENS,
        public_guard_enabled=True,
    )
    messages = [
        {"role": "system", "content": _build_public_system_prompt(context_text)},
        {"role": "user", "content": f"Fråga: {question}"},
    ]
    full_answer, final_stats = await orchestrator.llm_service.chat_complete(
        messages,
        config_override={
            "temperature": 0.05,
            "top_p": 0.9,
            "repeat_penalty": 1.1,
            "num_predict": MAX_ANSWER_TOKENS,
            "think": False,
        },
    )

    final_answer = _apply_response_guardrail(orchestrator, full_answer, question, resolved_mode)
    total_ms = (time.perf_counter() - start_time) * 1000
    reasoning_steps.append(
        f"Public BM25 selected {len(sources)} chunks from {len(raw_results)} raw results"
    )
    final_answer = _append_public_citations_and_attribution(final_answer, sources)
    citations = _build_public_citations(sources)

    metrics = RAGPipelineMetrics(
        retrieval_ms=retrieval_ms,
        llm_generation_ms=float(final_stats.total_duration_ms if final_stats else 0),
        total_pipeline_ms=total_ms,
        mode=resolved_mode.value,
        sources_count=len(sources),
        tokens_generated=final_stats.tokens_generated if final_stats else 0,
        retrieval_strategy=PUBLIC_QUERY_MODE,
        retrieval_results_count=len(raw_results),
        top_relevance_score=sources[0].score if sources else 0.0,
        guardrail_status=WardenStatus.UNCHANGED.value,
        evidence_level="HIGH" if sources else "NONE",
        model_used=final_stats.model_used if final_stats else "",
        llm_latency_ms=final_stats.total_duration_ms if final_stats else 0.0,
        tokens_per_second=final_stats.tokens_per_second if final_stats else 0.0,
        saknas_underlag=not bool(sources),
    )

    return RAGResult(
        answer=final_answer,
        sources=sources,
        reasoning_steps=reasoning_steps,
        metrics=metrics,
        mode=resolved_mode,
        guardrail_status=WardenStatus.UNCHANGED,
        evidence_level="HIGH" if sources else "NONE",
        success=True,
        citations=citations,
        retrieval_metadata=retrieval_metadata,
        refusal_reason=None,
        data_source_attribution=SOURCE_ATTRIBUTION_TEXT,
    )


def _refusal_result(
    *,
    start_time: float,
    mode: ResponseMode,
    reasoning_steps: list[str],
    refusal_reason: str,
    retrieval_ms: float = 0.0,
    retrieval_metadata: dict[str, Any] | None = None,
) -> RAGResult:
    total_ms = (time.perf_counter() - start_time) * 1000
    return RAGResult(
        answer=PUBLIC_REFUSAL_ANSWER,
        sources=[],
        reasoning_steps=reasoning_steps,
        metrics=RAGPipelineMetrics(
            retrieval_ms=retrieval_ms,
            total_pipeline_ms=total_ms,
            mode=mode.value,
            retrieval_strategy=PUBLIC_QUERY_MODE,
            saknas_underlag=True,
        ),
        mode=mode,
        guardrail_status=WardenStatus.UNCHANGED,
        evidence_level="NONE",
        success=False,
        error=refusal_reason,
        retrieval_metadata=retrieval_metadata
        or {"mode": PUBLIC_QUERY_MODE, "chunks_used": 0, "deduplicated_documents": 0},
        refusal_reason=refusal_reason,
        data_source_attribution=SOURCE_ATTRIBUTION_TEXT,
    )


def _select_public_sources(raw_results: list[dict[str, Any]]) -> list[SearchResult]:
    selected: list[SearchResult] = []
    seen_document_ids: set[str] = set()
    estimated_context_tokens = 0

    for row in raw_results:
        validate_public_record(row, stage="public_bm25_query_result")
        document_id = _document_id(row)
        if not document_id or document_id in seen_document_ids:
            continue
        seen_document_ids.add(document_id)

        source = SearchResult(
            id=str(row.get("id") or document_id),
            document_id=document_id,
            title=str(row.get("title") or document_id),
            snippet=_trim_chunk_text(str(row.get("text") or row.get("snippet") or "")),
            score=float(row.get("score") or 0.0),
            source=str(row.get("source") or PUBLIC_SOURCE),
            source_scope=str(row.get("source_scope") or PUBLIC_SOURCE_SCOPE),
            doc_type="riksdag",
            date=_optional_str(row.get("date")),
            retriever="bm25",
            retriever_source="bm25",
            url=_optional_str(row.get("url")),
        )
        validate_public_record(source, stage="public_bm25_query_source")

        source_context_tokens = _estimate_source_context_tokens(source, len(selected) + 1)
        if selected and estimated_context_tokens + source_context_tokens > MAX_CONTEXT_TOKENS:
            break

        selected.append(source)
        estimated_context_tokens += source_context_tokens
        if len(selected) >= MAX_CHUNKS:
            break

    return selected


def _document_id(row: dict[str, Any]) -> str:
    metadata = row.get("metadata")
    metadata_id = metadata.get("document_id") if isinstance(metadata, dict) else None
    return str(row.get("document_id") or metadata_id or row.get("id") or "").strip()


def _trim_chunk_text(text: str) -> str:
    text = " ".join((text or "").split())
    if estimate_tokens(text) <= MAX_CHUNK_TOKENS:
        return text
    max_chars = MAX_CHUNK_TOKENS * 3
    trimmed = text[:max_chars].rsplit(" ", 1)[0].strip()
    return trimmed or text[:max_chars].strip()


def _estimate_source_context_tokens(source: SearchResult, index: int) -> int:
    part = (
        f"[Källa {index}: {source.title}] (id={source.id})"
        f" Typ: RIKSDAG | Relevans: {source.score:.2f}\n"
        f"{source.snippet}"
    )
    return estimate_tokens(part)


def _preflight_refusal_reason(normalized_query: str) -> str | None:
    if any(phrase in normalized_query for phrase in LEGAL_ADVICE_PHRASES):
        return "legal_advice"
    if any(phrase in normalized_query for phrase in SOURCE_BOUNDARY_PHRASES):
        return "source_boundary"
    return None


def _is_weak_context(sources: list[SearchResult]) -> bool:
    total_tokens = sum(estimate_tokens(source.snippet or "") for source in sources)
    return total_tokens < MIN_CONTEXT_TOKENS


def _append_public_citations_and_attribution(answer: str, sources: list[SearchResult]) -> str:
    source_ids = []
    for source in sources:
        source_id = source.document_id or source.id
        if source_id and source_id not in source_ids:
            source_ids.append(source_id)
    suffix = f"Källor: {', '.join(source_ids)}\n{SOURCE_ATTRIBUTION_TEXT}"
    stripped = (answer or "").strip()
    return f"{stripped}\n\n{suffix}" if stripped else suffix


def _build_public_citations(sources: list[SearchResult]) -> list[Citation]:
    citations: list[Citation] = []
    for source in sources:
        source_id = source.document_id or source.id
        citations.append(
            Citation(
                claim=f"Källa: {source.title}",
                source_id=source_id,
                source_title=source.title,
                source_collection=PUBLIC_SOURCE_SCOPE,
                tier="public_bm25",
            )
        )
    return citations


def _build_public_system_prompt(context_text: str) -> str:
    return (
        "Du svarar på svenska för en offentlig Riksdagsdemo.\n"
        "Använd endast källorna från Riksdagens öppna data i kontexten.\n"
        "Ange källhänvisningar med dokument-id eller titel när du gör sakpåståenden.\n"
        "Om källorna inte räcker, säg att underlag saknas.\n\n"
        f"Källkontext:\n{context_text}"
    )


def _apply_response_guardrail(
    orchestrator: Any,
    answer: str,
    question: str,
    mode: ResponseMode,
) -> str:
    guardrail = getattr(orchestrator, "guardrail", None)
    if not guardrail or not hasattr(guardrail, "validate_response"):
        return answer
    result = guardrail.validate_response(text=answer, query=question, mode=mode.value)
    return getattr(result, "corrected_text", answer)


def _check_query_safety(orchestrator: Any, question: str) -> None:
    guardrail = getattr(orchestrator, "guardrail", None)
    if not guardrail or not hasattr(guardrail, "check_query_safety"):
        return
    is_safe, reason = guardrail.check_query_safety(question)
    if not is_safe:
        raise SecurityViolationError(f"Frågan blockerades av säkerhetsskäl: {reason}")


def _resolve_public_mode(mode: str | ResponseMode | None) -> ResponseMode:
    if isinstance(mode, ResponseMode):
        return mode
    if isinstance(mode, str) and mode != "auto":
        try:
            return ResponseMode(mode)
        except ValueError:
            return ResponseMode.EVIDENCE
    return ResponseMode.EVIDENCE


def _config_value(config: Any, name: str, default: str = "") -> str:
    value = getattr(config, name, None)
    if value is None and hasattr(config, "settings"):
        value = getattr(config.settings, name, None)
    return str(value or default)


def _optional_str(value: Any) -> str | None:
    return str(value) if value is not None else None

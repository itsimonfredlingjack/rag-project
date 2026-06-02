"""
Orchestrator Service - High-Level RAG Orchestration
The "Brain" that binds together all services for the complete RAG pipeline
"""

import asyncio
import inspect
import json
import time
from functools import lru_cache
from typing import AsyncGenerator, List, Optional

from ..core.exceptions import SecurityViolationError
from ..shared.public_source_guard import is_public_profile, validate_public_records
from ..utils.logging import get_logger
from ..utils.metrics import get_rag_metrics, log_structured_metric
from .base_service import BaseService
from .config_service import ConfigService, get_config_service
from .critic_service import CriticService, get_critic_service
from .faithfulness_service import FaithfulnessService, get_faithfulness_service
from .grader_service import GraderService, get_grader_service
from .guardrail_service import GuardrailService, WardenStatus, get_guardrail_service
from .llm_service import LLMService, get_llm_service
from .query_processor_service import (
    QueryProcessorService,
    ResponseMode,
    get_query_processor_service,
)
from .reranking_service import RerankingService, get_reranking_service
from .retrieval_service import (
    RetrievalService,
    RetrievalStrategy,
    SearchResult,
    get_retrieval_service,
)
from .structured_output_service import (
    StructuredOutputService,
    get_structured_output_service,
)
from .intent_classifier import QueryIntent

logger = get_logger(__name__)


async def build_dependency_readiness(orchestrator) -> dict:
    """Late-bound readiness import to avoid an orchestrator/readiness import cycle."""
    from .readiness_service import build_dependency_readiness as _build_dependency_readiness

    return await _build_dependency_readiness(orchestrator)


def autocut_scores(scores: list[float], sensitivity: float = 0.15) -> int:
    """Find the optimal cutoff point in a sorted descending score list via gap detection."""
    if len(scores) <= 1:
        return len(scores)
    threshold = sensitivity * scores[0] if scores[0] > 0 else sensitivity
    for i in range(1, len(scores)):
        gap = scores[i - 1] - scores[i]
        if gap > threshold:
            return i
    return len(scores)


from .rag_models import (  # noqa: E402
    ANSWER_CONTRACTS,  # noqa: F401 - re-exported for backward compatibility
    RAGPipelineMetrics,
    RAGResult,
    ResponseTemplates,
    get_answer_contract,
)

from .prompt_service import (  # noqa: E402
    build_llm_context as _build_llm_context_fn,
    build_system_prompt as _build_system_prompt_fn,
    calculate_source_budget as _calculate_source_budget_fn,
    format_svensk_ragg_examples as _format_svensk_ragg_examples_fn,
    is_truncated_answer as _is_truncated_answer_fn,
    retrieve_svensk_ragg_examples as _retrieve_svensk_ragg_examples_fn,
)

from .crag_service import (  # noqa: E402
    CragResult,
    process_crag_grading as _process_crag_grading_fn,
)

from .generation_service import (  # noqa: E402
    process_structured_output as _process_structured_output_fn,
)

from .agentic_service import (  # noqa: E402
    run_agentic_flow as _run_agentic_flow_fn,
)

from .streaming_service import (  # noqa: E402
    stream_query as _stream_query_fn,
)


class OrchestratorService(BaseService):
    """
    Orchestrator Service - The "Brain" that binds together all RAG components.

    Orchestrates:
    1. Query classification (CHAT/ASSIST/EVIDENCE)
    2. Query decontextualization (from conversation history)
    3. Document retrieval (Phase 1-4 RetrievalOrchestrator)
    4. LLM generation (Gemma 3 12B)
    5. Guardrail validation (Jail Warden v2)
    6. Optional reranking (Jina cross-encoder)

    Thread Safety:
        - All services are singletons
        - No shared mutable state between coroutines
    """

    def _is_truncated_answer(self, llm_output: str) -> bool:
        """Detect if an answer is truncated. Delegates to prompt_service."""
        return _is_truncated_answer_fn(llm_output)

    def __init__(
        self,
        config: ConfigService,
        llm_service: Optional[LLMService] = None,
        query_processor: Optional[QueryProcessorService] = None,
        guardrail: Optional[GuardrailService] = None,
        retrieval: Optional[RetrievalService] = None,
        reranker: Optional[RerankingService] = None,
        structured_output: Optional[StructuredOutputService] = None,
        critic: Optional[CriticService] = None,
        grader: Optional[GraderService] = None,
        faithfulness: Optional[FaithfulnessService] = None,
    ):
        """
        Initialize Orchestrator Service.

        Args:
            config: ConfigService for configuration
            llm_service: LLMService (optional, will create if not provided)
            query_processor: QueryProcessorService (optional, will create if not provided)
            guardrail: GuardrailService (optional, will create if not provided)
            retrieval: RetrievalService (optional, will create if not provided)
            reranker: RerankingService (optional, will create if not provided)
            structured_output: StructuredOutputService (optional, will create if not provided)
            critic: CriticService (optional, will create if not provided)
            grader: GraderService (optional, will create if not provided)
            faithfulness: FaithfulnessService (optional, will create if not provided)
        """
        super().__init__(config)

        # Get or create services
        self.llm_service = llm_service or get_llm_service(config)
        self.query_processor = query_processor or get_query_processor_service(config)
        self.guardrail = guardrail or get_guardrail_service(config)
        self.retrieval = retrieval or get_retrieval_service(config)
        self.reranker = reranker or get_reranking_service(config)
        self.structured_output = structured_output or get_structured_output_service(config)
        # Only create critic service if explicitly provided (for backwards compatibility)
        self.critic = critic or get_critic_service(config, llm_service)
        # Only create grader service if explicitly provided (for backwards compatibility)
        self.grader = grader or get_grader_service(config)
        self.faithfulness = faithfulness or get_faithfulness_service(config)

        # Initialize LangGraph agentic flow (lazy initialization)
        self.agent_app = None

        critic_status = "ENABLED" if config.critic_revise_effective_enabled else "DISABLED"
        grader_status = "ENABLED" if config.settings.crag_enabled else "DISABLED"
        self.logger.info(
            f"Orchestrator Service initialized (RAG pipeline ready with structured output, critic→revise: {critic_status}, CRAG grading: {grader_status})"
        )

    async def initialize(self) -> None:
        """
        Initialize all child services.
        """
        # Initialize all services
        await self.llm_service.initialize()
        await self.query_processor.initialize()
        await self.guardrail.initialize()
        public_profile = is_public_profile(self.config)
        if public_profile:
            logger.info("Public Riksdagen profile: skipping Chroma retrieval initialization")
        else:
            await self.retrieval.initialize()
        if self.reranker and not public_profile:
            await self.reranker.initialize()
        await self.structured_output.initialize()  # NEW
        if self.critic and not public_profile:
            await self.critic.initialize()  # NEW
        if self.grader and not public_profile:
            await self.grader.initialize()  # NEW

        self._mark_initialized()
        logger.info("Orchestrator Service initialized (all child services ready)")

    async def run_agentic_flow(self, question: str, mode: Optional[str] = "auto") -> RAGResult:
        """Run query through LangGraph agentic flow. Delegates to agentic_service."""
        result, self.agent_app = await _run_agentic_flow_fn(
            config=self.config,
            query_processor=self.query_processor,
            llm_service=self.llm_service,
            guardrail=self.guardrail,
            agent_app=self.agent_app,
            question=question,
            mode=mode,
            resolve_mode_fn=self._resolve_query_mode,
        )
        return result

    async def health_check(self) -> bool:
        """
        Check if orchestrator and all child services are healthy.

        Returns:
            True if all services healthy, False otherwise
        """

        async def check_service_health(service) -> bool:
            health_check = getattr(service, "health_check", None)
            if not callable(health_check):
                return True
            result = health_check()
            if inspect.isawaitable(result):
                result = await result
            return result is True

        public_profile = is_public_profile(self.config)
        tasks = [
            check_service_health(self.llm_service),
            check_service_health(self.query_processor),
            check_service_health(self.guardrail),
        ]
        if hasattr(self, "structured_output") and self.structured_output:
            tasks.append(check_service_health(self.structured_output))

        if not public_profile:
            tasks.append(check_service_health(self.retrieval))

        if self.reranker and not public_profile:
            tasks.append(check_service_health(self.reranker))
        if self.critic and not public_profile:
            tasks.append(check_service_health(self.critic))
        if self.grader and not public_profile:
            tasks.append(check_service_health(self.grader))

        health_checks = await asyncio.gather(*tasks, return_exceptions=True)

        all_healthy = all(check is True for check in health_checks)

        logger.info(f"Orchestrator health check: {'OK' if all_healthy else 'DEGRADED'}")
        return all_healthy

    async def close(self) -> None:
        """
        Cleanup all child services.
        """
        # Close all services
        await self.llm_service.close()
        # Query processor and guardrail have no resources to close
        await self.retrieval.close()
        if self.reranker:
            await self.reranker.close()
        await self.structured_output.close()  # NEW
        if self.critic:
            await self.critic.close()  # NEW
        if self.grader:
            await self.grader.close()  # NEW

        self._mark_uninitialized()

    async def process_query(
        self,
        question: str,
        mode: Optional[str] = "auto",
        k: int = 10,
        retrieval_strategy: RetrievalStrategy = RetrievalStrategy.PARALLEL_V1,
        history: Optional[List[dict]] = None,
        enable_reranking: bool = True,
        enable_adaptive: bool = True,
        use_agent: bool = False,  # NEW: Flag to use agentic flow
        where_filter: Optional[dict] = None,
    ) -> RAGResult:
        """
        Execute full RAG pipeline.

        Pipeline:
        1. Classify query mode (CHAT/ASSIST/EVIDENCE)
        2. Decontextualize query if history provided
        3. Retrieve documents (parallel, rewrite, fusion, or adaptive)
        4. Generate LLM response
        5. Apply guardrail corrections
        6. Optional reranking of results

        Args:
            question: User's question
            mode: Response mode (auto/chat/assist/evidence)
            k: Number of documents to retrieve
            retrieval_strategy: Retrieval strategy (parallel_v1, rewrite_v1, rag_fusion, adaptive)
            history: Conversation history for decontextualization
            enable_reranking: Whether to use Jina reranking
            enable_adaptive: Whether to use adaptive retrieval
            use_agent: If True, use LangGraph agentic flow instead of linear pipeline

        Returns:
            RAGResult with answer, sources, metrics, etc.
        """
        if is_public_profile(self.config):
            from .public_bm25_query_service import process_public_bm25_query

            readiness = await build_dependency_readiness(self)
            return await process_public_bm25_query(
                orchestrator=self,
                question=question,
                mode=mode,
                readiness=readiness,
            )

        # NEW: Route to agentic flow if flag is set
        if use_agent:
            self.logger.info("Using agentic LangGraph flow")
            return await self.run_agentic_flow(question=question, mode=mode)

        # Original linear pipeline
        start_time = time.perf_counter()
        reasoning_steps = []

        # CRAG variables (initialized for metrics)
        grade_count = 0
        relevant_count = 0
        grade_ms = 0.0
        self_reflection_ms = 0.0
        thought_chain = None
        rewrite_count = 0

        try:
            # SECURITY: Check query for prompt injection attacks
            is_safe, safety_reason = self.guardrail.check_query_safety(question)
            if not is_safe:
                self.logger.warning(f"Query blocked by safety check: {safety_reason}")
                if safety_reason and safety_reason.startswith("SELF_HARM_DETECTED:"):
                    raise SecurityViolationError(safety_reason)
                raise SecurityViolationError(
                    f"Frågan blockerades av säkerhetsskäl: {safety_reason}"
                )

            # STEP 1: Query classification
            class_start = time.perf_counter()
            classification = self.query_processor.classify_query(question)
            resolved_mode = self._resolve_query_mode(mode, classification.mode)
            mode = resolved_mode

            query_classification_ms = (time.perf_counter() - class_start) * 1000
            reasoning_steps.append(
                f"Query classified as {resolved_mode.value} ({classification.reason})"
            )

            # CHAT mode: Skip RAG, just chat
            if resolved_mode == ResponseMode.CHAT:
                return await self._process_chat_mode(question, start_time, reasoning_steps)

            # STEP 2: Decontextualization (if history provided)
            decont_start = time.perf_counter()
            if history:
                decont_result = self.query_processor.decontextualize_query(question, history)
                search_query = decont_result.rewritten_query
                reasoning_steps.append(
                    f"Query decontextualized: '{decont_result.original_query}' → '{decont_result.rewritten_query}' (confidence: {decont_result.confidence:.2f})"
                )
            else:
                search_query = question
                reasoning_steps.append("No history provided, using original query")

            decontextualization_ms = (time.perf_counter() - decont_start) * 1000

            # Convert history to strings for retrieval service
            history_for_retrieval = None
            if history:
                history_for_retrieval = [
                    f"{h.get('role', 'user')}: {h.get('content', '')}" for h in history
                ]

            # STEP 3: Retrieval
            retrieval_start = time.perf_counter()

            # EPR: Always use intent-based routing
            retrieval_result = await self.retrieval.search_with_epr(
                query=search_query,
                k=k,
                where_filter=where_filter,
                history=history_for_retrieval,
            )
            self.logger.info(
                f"EPR used: intent={retrieval_result.intent}, "
                f"routing={retrieval_result.routing_used}"
            )

            retrieval_ms = (time.perf_counter() - retrieval_start) * 1000
            reasoning_steps.append(
                f"Retrieved {len(retrieval_result.results)} documents in {retrieval_ms:.1f}ms (strategy: {retrieval_result.metrics.strategy})"
            )

            if not retrieval_result.success:
                raise Exception(f"Retrieval failed: {retrieval_result.error}")

            # Initialize sources from retrieval result
            sources = retrieval_result.results
            self._guard_public_sources(sources, stage="orchestrator_retrieval_results")

            # STEP 3.5: Reranking BEFORE CRAG grading
            # Rerank first while GPU is free (before Ollama grading fills VRAM).
            # This also reduces the number of docs that need expensive LLM grading.
            reranking_ms = 0.0
            reranking_allowed = bool(enable_reranking and self.config.settings.reranking_enabled)
            if reranking_allowed and self.reranker and resolved_mode != ResponseMode.CHAT:
                rerank_start = time.perf_counter()

                try:
                    # Limit reranking input to top 10 by retrieval score.
                    # CPU reranking scales ~8s/doc; 10 docs ≈ 80s vs 19 docs ≈ 160s.
                    rerank_input = sources[:10]
                    rerank_result = await self.reranker.rerank(
                        query=search_query,
                        documents=[
                            {
                                "id": s.id,
                                "title": s.title,
                                "snippet": s.snippet,
                                "score": s.score,
                            }
                            for s in rerank_input
                        ],
                        top_k=len(rerank_input),
                    )

                    reranking_ms = (time.perf_counter() - rerank_start) * 1000

                    # Apply score threshold, autocut, and top-N filtering
                    score_threshold = self.config.settings.reranking_score_threshold
                    top_n = self.config.settings.reranking_top_n
                    autocut_n = autocut_scores(rerank_result.reranked_scores, sensitivity=0.15)
                    effective_n = max(2, min(autocut_n, top_n))

                    filtered_sources = []
                    for i, doc in enumerate(rerank_result.reranked_docs):
                        rerank_score = rerank_result.reranked_scores[i]
                        if rerank_score >= score_threshold and len(filtered_sources) < effective_n:
                            original = next((s for s in sources if s.id == doc["id"]), None)
                            if original:
                                filtered_sources.append(
                                    SearchResult(
                                        id=original.id,
                                        title=original.title,
                                        snippet=original.snippet,
                                        score=rerank_score,
                                        source=original.source,
                                        source_scope=getattr(original, "source_scope", None),
                                        doc_type=original.doc_type,
                                        date=original.date,
                                        retriever=original.retriever,
                                        tier=original.tier,
                                    )
                                )

                    # Minimum fallback: ensure at least N results survive reranking
                    min_results = self.config.settings.reranking_min_results
                    if len(filtered_sources) < min_results and rerank_result.reranked_docs:
                        for i, doc in enumerate(rerank_result.reranked_docs):
                            if len(filtered_sources) >= min_results:
                                break
                            if any(s.id == doc["id"] for s in filtered_sources):
                                continue
                            original = next((s for s in sources if s.id == doc["id"]), None)
                            if original:
                                filtered_sources.append(
                                    SearchResult(
                                        id=original.id,
                                        title=original.title,
                                        snippet=original.snippet,
                                        score=rerank_result.reranked_scores[i],
                                        source=original.source,
                                        source_scope=getattr(original, "source_scope", None),
                                        doc_type=original.doc_type,
                                        date=original.date,
                                        retriever=original.retriever,
                                        tier=original.tier,
                                    )
                                )
                        logger.warning(
                            f"Reranking fallback: padded to {len(filtered_sources)} "
                            f"results (min_results={min_results})"
                        )

                    reasoning_steps.append(
                        f"Reranked {len(sources)} → {len(filtered_sources)} sources "
                        f"(threshold={score_threshold}, top_n={top_n}, "
                        f"autocut={autocut_n}, effective_n={effective_n}, "
                        f"top_score={rerank_result.reranked_scores[0] if rerank_result.reranked_scores else 0:.4f}, "
                        f"latency={reranking_ms:.1f}ms)"
                    )
                    sources = filtered_sources

                except Exception as rerank_err:
                    reranking_ms = (time.perf_counter() - rerank_start) * 1000
                    logger.warning(
                        f"Reranking failed, skipping: {rerank_err}. "
                        f"Proceeding with {len(sources)} unranked sources."
                    )
                    reasoning_steps.append(
                        f"Reranking skipped (error: {str(rerank_err)[:80]}), "
                        f"using {len(sources)} sources without reranking"
                    )

            # EVIDENCE mode guard: refuse if no sources survived pipeline
            if resolved_mode == ResponseMode.EVIDENCE and not sources:
                refusal_text = getattr(
                    self.config.settings,
                    "evidence_refusal_template",
                    "Tyvärr kan jag inte besvara frågan utifrån de dokument som har "
                    "hämtats. Underlag saknas för att ge ett källbaserat svar.",
                )
                total_ms = (time.perf_counter() - start_time) * 1000
                reasoning_steps.append("EVIDENCE refusal: no sources after reranking")
                return RAGResult(
                    answer=refusal_text,
                    sources=[],
                    reasoning_steps=reasoning_steps,
                    metrics=RAGPipelineMetrics(
                        query_classification_ms=query_classification_ms,
                        decontextualization_ms=decontextualization_ms,
                        retrieval_ms=retrieval_ms,
                        reranking_ms=reranking_ms,
                        total_pipeline_ms=total_ms,
                        mode=resolved_mode.value,
                        saknas_underlag=True,
                    ),
                    mode=resolved_mode,
                    guardrail_status=WardenStatus.UNCHANGED,
                    evidence_level="NONE",
                    success=True,
                    thought_chain=thought_chain,
                )

            # EVIDENCE mode: refuse only if ALL sources have extremely low quality
            if (
                resolved_mode == ResponseMode.EVIDENCE
                and sources
                and all(s.score < 0.05 for s in sources)
            ):
                refusal_text = getattr(
                    self.config.settings,
                    "evidence_refusal_template",
                    "Tyvärr kan jag inte besvara frågan utifrån de dokument som har "
                    "hämtats. Underlag saknas för att ge ett källbaserat svar.",
                )
                total_ms = (time.perf_counter() - start_time) * 1000
                reasoning_steps.append(
                    f"EVIDENCE refusal: all {len(sources)} sources below 0.05 quality threshold"
                )
                return RAGResult(
                    answer=refusal_text,
                    sources=[],
                    reasoning_steps=reasoning_steps,
                    metrics=RAGPipelineMetrics(
                        query_classification_ms=query_classification_ms,
                        decontextualization_ms=decontextualization_ms,
                        retrieval_ms=retrieval_ms,
                        reranking_ms=reranking_ms,
                        total_pipeline_ms=total_ms,
                        mode=resolved_mode.value,
                        saknas_underlag=True,
                    ),
                    mode=resolved_mode,
                    guardrail_status=WardenStatus.UNCHANGED,
                    evidence_level="NONE",
                    success=True,
                    thought_chain=thought_chain,
                )

            # STEP 3.7: CRAG (Corrective RAG) - Grade reranked sources
            # Runs after reranking so: (a) fewer docs to grade, (b) GPU is free for Ollama
            grade_ms = 0.0
            grade_count = 0
            relevant_count = 0
            self_reflection_ms = 0.0
            thought_chain = None
            citation_plan = None
            rewrite_count = 0

            # Update retrieval_result.results to use reranked sources for CRAG
            retrieval_result.results = sources

            crag_result = await self._process_crag_grading(
                question=question,
                search_query=search_query,
                retrieval_result=retrieval_result,
                resolved_mode=resolved_mode,
                reasoning_steps=reasoning_steps,
                start_time=start_time,
                query_classification_ms=query_classification_ms,
                decontextualization_ms=decontextualization_ms,
                retrieval_ms=retrieval_ms,
            )

            # Early return if CRAG determined insufficient evidence
            if crag_result.early_return:
                return crag_result.result

            # Extract CRAG results
            sources = crag_result.sources
            self._guard_public_sources(sources, stage="orchestrator_crag_results")
            grade_ms = crag_result.grade_ms
            grade_count = crag_result.grade_count
            relevant_count = crag_result.relevant_count
            self_reflection_ms = crag_result.self_reflection_ms
            thought_chain = crag_result.thought_chain
            citation_plan = crag_result.citation_plan
            rewrite_count = crag_result.rewrite_count

            # STEP 4: Build LLM context from sources

            # Extract source text for context
            context_text = self._build_llm_context(sources)
            reasoning_steps.append(f"Built LLM context with {len(sources)} sources")

            # STEP 5: Generate LLM response
            llm_start = time.perf_counter()

            # Get mode-specific configuration
            llm_config = self.query_processor.get_mode_config(resolved_mode.value)

            # RetICL: Retrieve Svensk Ragg examples before building prompt
            svensk_ragg_examples = await self._retrieve_svensk_ragg_examples(
                query=question,
                mode=resolved_mode.value,
                k=2,
            )
            examples_text = self._format_svensk_ragg_examples(svensk_ragg_examples)

            # Build messages (inject thought_chain + citation_plan so LLM can use its reflection)
            system_prompt = self._build_system_prompt(
                resolved_mode.value,
                sources,
                context_text,
                structured_output_enabled=self.config.structured_output_effective_enabled,
                user_query=question,
                thought_chain=thought_chain,
                citation_plan=citation_plan,
            )
            # Replace placeholder with actual examples
            system_prompt = system_prompt.replace("{{SVENSK_RAGG_EXAMPLES}}", examples_text)

            # Inject intent-specific answer contract for better answer relevancy
            if retrieval_result.intent:
                try:
                    intent_enum = QueryIntent(retrieval_result.intent)
                    answer_contract = get_answer_contract(intent_enum)
                    if answer_contract:
                        system_prompt += f"\n\n{answer_contract}"
                except (ValueError, KeyError):
                    pass  # Unknown intent, skip contract
            messages = [
                {"role": "system", "content": system_prompt},
            ]

            messages.append({"role": "user", "content": f"Fråga: {question}"})

            if history:
                # Add conversation history
                for i, msg in enumerate(history):  # Insert after system, before current query
                    messages.insert(1 + i, msg)

            # Stream LLM response
            full_answer = ""
            final_stats = None

            async for token, stats in self.llm_service.chat_stream(
                messages=messages,
                config_override=llm_config,
            ):
                if token:
                    full_answer += token
                else:
                    final_stats = stats

            llm_generation_ms = (time.perf_counter() - llm_start) * 1000
            reasoning_steps.append(
                f"LLM generated {final_stats.tokens_generated if final_stats else 0} tokens in {llm_generation_ms:.1f}ms (model: {final_stats.model_used if final_stats else 'unknown'})"
            )

            # STEP 5.5 + 5A + 5B: Structured output, anti-truncation, critic→revise
            # Build set of retrieved doc IDs for citation cross-validation
            _retrieved_doc_ids = {s.id for s in sources if s.id}
            gen_result = await _process_structured_output_fn(
                config=self.config,
                structured_output_service=self.structured_output,
                llm_service=self.llm_service,
                critic_service=self.critic,
                faithfulness_service=self.faithfulness,
                full_answer=full_answer,
                mode=mode,
                question=question,
                system_prompt=system_prompt,
                llm_config=llm_config,
                sources=sources,
                reasoning_steps=reasoning_steps,
                create_fallback_fn=self._create_fallback_response,
                retrieved_doc_ids=_retrieved_doc_ids,
            )
            full_answer = gen_result.answer
            structured_output_data = gen_result.structured_data
            parse_errors = gen_result.parse_errors
            structured_output_ms = gen_result.structured_output_ms
            critic_revision_count = gen_result.critic_revision_count
            critic_ms = gen_result.critic_ms
            if gen_result.sources_cleared:
                sources = []

            # STEP 6: Apply guardrail corrections
            guardrail_start = time.perf_counter()
            guardrail_result = self.guardrail.validate_response(
                text=full_answer,
                query=question,
                mode=mode.value,
            )

            guardrail_ms = (time.perf_counter() - guardrail_start) * 1000
            reasoning_steps.append(
                f"Guardrail corrections: {len(guardrail_result.corrections)} applied (status: {guardrail_result.status})"
            )

            # Build final result
            final_answer = guardrail_result.corrected_text

            # Output leakage sanitization
            final_answer, leakage_items = self.guardrail.check_output_leakage(final_answer)
            if leakage_items:
                reasoning_steps.append(
                    f"Output sanitized: {len(leakage_items)} internal references removed"
                )

            # Determine evidence level
            evidence_level = self.query_processor.determine_evidence_level(
                sources=[{"score": s.score, "doc_type": s.doc_type} for s in sources],
                answer=final_answer,
            )

            # Build metrics
            total_pipeline_ms = (time.perf_counter() - start_time) * 1000

            metrics = RAGPipelineMetrics(
                query_classification_ms=query_classification_ms,
                decontextualization_ms=decontextualization_ms,
                retrieval_ms=retrieval_ms,
                llm_generation_ms=llm_generation_ms,
                guardrail_ms=guardrail_ms,
                reranking_ms=reranking_ms,
                structured_output_ms=structured_output_ms,  # NEW
                total_pipeline_ms=total_pipeline_ms,
                mode=mode.value,
                sources_count=len(sources),
                tokens_generated=final_stats.tokens_generated if final_stats else 0,
                corrections_count=len(guardrail_result.corrections),
                retrieval_strategy=retrieval_result.metrics.strategy,
                retrieval_results_count=len(retrieval_result.results),
                top_relevance_score=retrieval_result.metrics.top_score,
                guardrail_status=guardrail_result.status.value,
                evidence_level=evidence_level,
                model_used=final_stats.model_used if final_stats else "",
                llm_latency_ms=final_stats.total_duration_ms if final_stats else 0.0,
                parse_errors=parse_errors,  # NEW
                saknas_underlag=structured_output_data.get("saknas_underlag")
                if structured_output_data
                else None,  # NEW
                kallor_count=len(structured_output_data.get("kallor", []))
                if structured_output_data
                else 0,  # NEW
                structured_output_enabled=self.config.structured_output_effective_enabled,  # NEW
                tokens_per_second=final_stats.tokens_per_second if final_stats else 0.0,
                critic_revision_count=critic_revision_count,  # NEW
                critic_ms=0.0 if critic_revision_count == 0 else critic_ms,  # NEW
                critic_ok=gen_result.critic_ok,  # NEW
                crag_enabled=self.config.settings.crag_enabled,
                grade_count=grade_count,
                relevant_count=relevant_count,
                grade_ms=grade_ms,
                self_reflection_used=bool(thought_chain),
                self_reflection_ms=self_reflection_ms,
                rewrite_count=rewrite_count,
                faithfulness_score=gen_result.faithfulness_score,
                faithfulness_ms=gen_result.faithfulness_ms,
                faithfulness_claims_total=gen_result.faithfulness_claims_total,
                faithfulness_claims_supported=gen_result.faithfulness_claims_supported,
            )

            logger.info(
                f"RAG pipeline complete: {total_pipeline_ms:.1f}ms "
                f"(mode: {mode.value}, sources: {len(sources)}, "
                f"tokens: {final_stats.tokens_generated if final_stats else 0})"
            )

            # Record metrics for observability
            rag_metrics = get_rag_metrics()
            saknas_value = (
                structured_output_data.get("saknas_underlag") if structured_output_data else None
            )
            rag_metrics.record_event(
                question=question,
                mode=mode.value,
                saknas_underlag=saknas_value,
                parse_errors=parse_errors,
                latency_ms=total_pipeline_ms,
                model_used=final_stats.model_used if final_stats else "",
                retrieval_count=len(retrieval_result.results) if retrieval_result else 0,
            )

            # Structured log for log aggregation (Loki/Grafana/Splunk)
            log_structured_metric(
                logger=logger,
                event_type="rag_completion",
                question=question,
                mode=mode.value,
                saknas_underlag=saknas_value,
                parse_errors=parse_errors,
                latency_ms=total_pipeline_ms,
                sources_count=len(sources),
                evidence_level=evidence_level,
                model=final_stats.model_used if final_stats else "",
            )

            self._guard_public_sources(sources, stage="orchestrator_response_sources")

            return RAGResult(
                answer=final_answer,
                sources=sources,
                reasoning_steps=reasoning_steps,
                metrics=metrics,
                mode=mode,
                guardrail_status=guardrail_result.status,
                evidence_level=evidence_level,
                success=True,
                thought_chain=thought_chain,  # NEW
            )

        except SecurityViolationError as e:
            logger.error(f"Security violation in RAG pipeline: {e}")
            error_str = str(e)

            # Self-harm: compassionate response (not a security error)
            if error_str.startswith("SELF_HARM_DETECTED:"):
                compassionate_msg = error_str.split("SELF_HARM_DETECTED:", 1)[1].strip()
                return RAGResult(
                    answer=compassionate_msg,
                    sources=[],
                    reasoning_steps=["Self-harm concern detected — compassionate response"],
                    metrics=RAGPipelineMetrics(),
                    mode=mode if isinstance(mode, ResponseMode) else ResponseMode.ASSIST,
                    guardrail_status=WardenStatus.UNCHANGED,
                    evidence_level="NONE",
                    success=True,
                    thought_chain=None,
                )

            return RAGResult(
                answer="Din fråga kunde inte behandlas av säkerhetsskäl. "
                "Omformulera gärna din fråga.",
                sources=[],
                reasoning_steps=[f"Security violation: {error_str}"],
                metrics=RAGPipelineMetrics(saknas_underlag=True),
                mode=mode if isinstance(mode, ResponseMode) else ResponseMode.ASSIST,
                guardrail_status=WardenStatus.ERROR,
                evidence_level="NONE",
                success=False,
                error=error_str,
                thought_chain=None,
            )

        except Exception as e:
            logger.error(f"RAG pipeline failed: {e}")
            return RAGResult(
                answer="Tyvärr uppstod ett fel vid svarandet på din fråga.",
                sources=[],
                reasoning_steps=[f"Error: {str(e)}"],
                metrics=RAGPipelineMetrics(),
                mode=mode if isinstance(mode, ResponseMode) else ResponseMode.ASSIST,
                guardrail_status=WardenStatus.ERROR,
                evidence_level="NONE",
                success=False,
                error=str(e),
                thought_chain=None,  # NEW
            )

    async def _process_chat_mode(
        self,
        question: str,
        start_time: float,
        reasoning_steps: List[str],
    ) -> RAGResult:
        """
        Process query in CHAT mode (no RAG, just chat).

        Bypasses retrieval and guardrails, direct LLM chat.
        """
        # Build chat messages
        system_prompt = """Avslappnad AI-assistent. Svara kort på svenska.
MAX 2-3 meningar. INGEN MARKDOWN - skriv ren text utan *, **, #, -, eller listor.

Om frågan handlar om svensk lag eller myndighetsförvaltning, kan du hänvisa till att du har tillgång till en korpus med över 521 000 svenska myndighetsdokument, men svara kortfattat."""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": question},
        ]

        # Generate response
        full_answer = ""
        final_stats = None

        async for token, stats in self.llm_service.chat_stream(
            messages=messages,
            config_override={"temperature": 0.1, "num_predict": 512},
        ):
            if token:
                full_answer += token
            else:
                final_stats = stats

        reasoning_steps.append("CHAT mode: Direct LLM response (no RAG)")

        # Build metrics
        total_pipeline_ms = (time.perf_counter() - start_time) * 1000

        metrics = RAGPipelineMetrics(
            total_pipeline_ms=total_pipeline_ms,
            mode="chat",
            tokens_generated=final_stats.tokens_generated if final_stats else 0,
            llm_generation_ms=final_stats.total_duration_ms if final_stats else 0.0,
            model_used=final_stats.model_used if final_stats else "",
            llm_latency_ms=final_stats.total_duration_ms if final_stats else 0.0,
            tokens_per_second=final_stats.tokens_per_second if final_stats else 0.0,
        )

        return RAGResult(
            answer=full_answer,
            sources=[],
            reasoning_steps=reasoning_steps,
            metrics=metrics,
            mode=ResponseMode.CHAT,
            guardrail_status=WardenStatus.UNCHANGED,
            evidence_level="NONE",
            success=True,
            thought_chain=None,  # NEW
        )

    def _build_llm_context(self, sources) -> str:
        """Build LLM context from sources. Delegates to prompt_service."""
        try:
            context_window = int(getattr(self.config.settings, "gguf_context_window", 8192))
            num_predict = int(getattr(self.config.settings, "mode_evidence_num_predict", 1024))
        except (TypeError, ValueError):
            context_window = 8192
            num_predict = 1024
        budget = _calculate_source_budget_fn(
            context_window=context_window,
            system_prompt_overhead=2500,  # Role + rules + JSON instruction + reflection ~2500 tokens
            response_reserve=num_predict,
        )
        return _build_llm_context_fn(
            sources,
            max_context_tokens=budget,
            public_guard_enabled=is_public_profile(self.config),
        )

    def _guard_public_sources(self, sources, *, stage: str) -> None:
        validate_public_records(
            list(sources or []),
            stage=stage,
            enabled=is_public_profile(self.config),
        )

    async def _retrieve_svensk_ragg_examples(self, query: str, mode: str, k: int = 2):
        """Retrieve Svensk Ragg examples. Delegates to prompt_service."""
        return await _retrieve_svensk_ragg_examples_fn(self.config, query, mode, k)

    def _format_svensk_ragg_examples(self, examples):
        """Format Svensk Ragg examples. Delegates to prompt_service."""
        return _format_svensk_ragg_examples_fn(examples)

    def _build_system_prompt(
        self,
        mode: str,
        sources=None,
        context_text: str = "",
        structured_output_enabled: bool = True,
        user_query=None,
        thought_chain=None,
        citation_plan=None,
    ) -> str:
        """Build system prompt. Delegates to prompt_service."""
        return _build_system_prompt_fn(
            mode=mode,
            sources=sources or [],
            context_text=context_text,
            structured_output_enabled=structured_output_enabled,
            user_query=user_query,
            thought_chain=thought_chain,
            citation_plan=citation_plan,
        )

    async def stream_query(
        self,
        question: str,
        mode: Optional[str] = "auto",
        k: int = 10,
        retrieval_strategy: RetrievalStrategy = RetrievalStrategy.ADAPTIVE,
        history: Optional[List[dict]] = None,
        stream_session_id: Optional[str] = None,
        where_filter: Optional[dict] = None,
    ) -> AsyncGenerator[str, None]:
        """Stream RAG pipeline with SSE. Delegates to streaming_service."""
        if is_public_profile(self.config):
            try:
                result = await self.process_query(
                    question=question,
                    mode=mode,
                    k=k,
                    retrieval_strategy=retrieval_strategy,
                    history=history,
                    where_filter=where_filter,
                )
                if result.sources:
                    validate_public_records(
                        result.sources,
                        stage="public_stream_query_response",
                        enabled=True,
                    )

                retrieval_metadata = getattr(result, "retrieval_metadata", None) or {}
                total_ms = round(float(result.metrics.total_pipeline_ms or 0.0), 1)
                sources_metadata = []
                for source in result.sources or []:
                    source_payload = {
                        "id": source.id,
                        "document_id": getattr(source, "document_id", None) or source.id,
                        "title": source.title,
                        "snippet": source.snippet,
                        "score": float(source.score),
                        "doc_type": source.doc_type,
                        "source": source.source,
                        "source_scope": getattr(source, "source_scope", None),
                        "date": getattr(source, "date", None),
                        "url": getattr(source, "url", None),
                        "retriever": getattr(source, "retriever", None),
                        "retriever_source": getattr(source, "retriever_source", None),
                    }
                    sources_metadata.append(
                        {key: value for key, value in source_payload.items() if value is not None}
                    )

                metadata_event = {
                    "type": "metadata",
                    "mode": retrieval_metadata.get("mode", "public_bm25_only"),
                    "sources": sources_metadata,
                    "search_time_ms": round(float(result.metrics.retrieval_ms or 0.0), 1),
                    "latency_ms": total_ms,
                    "evidence_level": result.evidence_level,
                    "retrieval": retrieval_metadata,
                    "citations": [
                        {
                            "claim": citation.claim,
                            "source_id": citation.source_id,
                            "source_title": citation.source_title,
                            "source_collection": citation.source_collection,
                            "tier": citation.tier,
                        }
                        for citation in getattr(result, "citations", [])
                    ],
                }
                data_source_attribution = getattr(result, "data_source_attribution", None)
                if data_source_attribution is not None:
                    metadata_event["data_source_attribution"] = data_source_attribution
                refusal_reason = getattr(result, "refusal_reason", None)
                if refusal_reason is not None:
                    metadata_event["refusal"] = True
                    metadata_event["refusal_reason"] = refusal_reason
                if stream_session_id:
                    metadata_event["stream_session_id"] = stream_session_id

                yield f"data: {json.dumps(metadata_event)}\n\n"
                yield f"data: {json.dumps({'type': 'token', 'content': result.answer})}\n\n"
                yield f"data: {json.dumps({'type': 'done', 'total_time_ms': total_ms})}\n\n"
            except Exception as exc:
                yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"
            return

        async for event in _stream_query_fn(
            config=self.config,
            query_processor=self.query_processor,
            llm_service=self.llm_service,
            guardrail=self.guardrail,
            retrieval=self.retrieval,
            reranker=self.reranker,
            grader=self.grader,
            critic=self.critic,
            resolve_mode_fn=self._resolve_query_mode,
            build_llm_context_fn=self._build_llm_context,
            retrieve_examples_fn=self._retrieve_svensk_ragg_examples,
            format_examples_fn=self._format_svensk_ragg_examples,
            build_system_prompt_fn=self._build_system_prompt,
            question=question,
            mode=mode,
            k=k,
            retrieval_strategy=retrieval_strategy,
            history=history,
            stream_session_id=stream_session_id,
            where_filter=where_filter,
        ):
            yield event

    def _resolve_query_mode(self, mode: Optional[str], default_mode: ResponseMode) -> ResponseMode:
        """
        Resolve query mode from various input types.

        Args:
            mode: Mode as None, str, or ResponseMode enum
            default_mode: Default mode from classification

        Returns:
            Resolved ResponseMode enum
        """
        if mode is None:
            return default_mode
        elif isinstance(mode, ResponseMode):
            return mode
        elif isinstance(mode, str):
            if mode != "auto":
                try:
                    return ResponseMode(mode)
                except ValueError:
                    return default_mode
            return default_mode
        else:
            return default_mode

    def _create_fallback_response(
        self, mode: ResponseMode, reasoning_steps: List[str]
    ) -> tuple[str, dict]:
        """
        Create fallback response when structured output parsing fails.

        Args:
            mode: Response mode (EVIDENCE or ASSIST)
            reasoning_steps: List to append reasoning steps

        Returns:
            Tuple of (answer_text, structured_output_data)
        """
        if mode == ResponseMode.EVIDENCE:
            refusal_template = ResponseTemplates.EVIDENCE_REFUSAL
            reasoning_steps.append("EVIDENCE both attempts failed - using refusal template")
            return refusal_template, {
                "mode": "EVIDENCE",
                "saknas_underlag": True,
                "svar": refusal_template,
                "kallor": [],
                "fakta_utan_kalla": [],
            }
        else:
            safe_fallback = ResponseTemplates.SAFE_FALLBACK
            reasoning_steps.append("ASSIST both attempts failed - using safe fallback")
            return safe_fallback, {
                "mode": "ASSIST",
                "saknas_underlag": False,
                "svar": safe_fallback,
                "kallor": [],
                "fakta_utan_kalla": [],
            }

    async def _process_crag_grading(
        self,
        question: str,
        search_query: str,
        retrieval_result,
        resolved_mode,
        reasoning_steps,
        start_time: float,
        query_classification_ms: float,
        decontextualization_ms: float,
        retrieval_ms: float,
    ) -> CragResult:
        """Process CRAG grading. Delegates to crag_service."""
        return await _process_crag_grading_fn(
            config=self.config,
            grader=self.grader,
            critic=self.critic,
            question=question,
            search_query=search_query,
            retrieval_result=retrieval_result,
            resolved_mode=resolved_mode,
            reasoning_steps=reasoning_steps,
            start_time=start_time,
            query_classification_ms=query_classification_ms,
            decontextualization_ms=decontextualization_ms,
            retrieval_ms=retrieval_ms,
        )

    def _json(self, data: dict) -> str:
        """Helper to format SSE event data"""

        return json.dumps(data)

    def get_status(self) -> dict:
        """
        Get orchestrator status with child service status.

        Returns:
            Dictionary with orchestrator and child service health
        """
        return {
            "orchestrator": "initialized" if self.is_initialized else "uninitialized",
            "llm_service": "initialized" if self.llm_service.is_initialized else "uninitialized",
            "query_processor": "initialized"
            if self.query_processor.is_initialized
            else "uninitialized",
            "guardrail": "initialized" if self.guardrail.is_initialized else "uninitialized",
            "retrieval": "initialized" if self.retrieval.is_initialized else "uninitialized",
            "reranker": "initialized"
            if self.reranker and self.reranker.is_initialized
            else "not_available",
        }


@lru_cache()
def _get_default_orchestrator_service() -> OrchestratorService:
    return OrchestratorService(config=get_config_service())


# Dependency injection function for FastAPI
def get_orchestrator_service(
    config=None,
    llm_service=None,
    query_processor=None,
    guardrail=None,
    retrieval=None,
    reranker=None,
    structured_output=None,  # NEW
) -> OrchestratorService:
    """
    Get singleton OrchestratorService instance.

    Args:
        config: Optional ConfigService (uses default if not provided)
        llm_service: Optional LLMService (optional, will create if not provided)
        query_processor: Optional QueryProcessorService (optional, will create if not provided)
        guardrail: Optional GuardrailService (optional, will create if not provided)
        retrieval: Optional RetrievalService (typical, will create if not provided)
        reranker: Optional RerankingService (optional, will create if not provided)

    Returns:
        Cached OrchestratorService instance
    """
    if all(
        service is None
        for service in (
            config,
            llm_service,
            query_processor,
            guardrail,
            retrieval,
            reranker,
            structured_output,
        )
    ):
        return _get_default_orchestrator_service()

    if config is None:
        config = get_config_service()

    return OrchestratorService(
        config=config,
        llm_service=llm_service,
        query_processor=query_processor,
        guardrail=guardrail,
        retrieval=retrieval,
        reranker=reranker,
        structured_output=structured_output,  # NEW
    )

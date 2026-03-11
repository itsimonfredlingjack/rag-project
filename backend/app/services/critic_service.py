"""
Critic Service - Provides critique and revision of structured JSON responses

This service evaluates structured output quality and can revise responses
based on critic feedback. Used in the critic→revise loop for improved accuracy.

Feature-flagged: CONSTITUTIONAL_CRITIC_ENABLED
"""

import json
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

from ..utils.logging import get_logger
from .base_service import BaseService
from .config_service import ConfigService, get_config_service
from .llm_service import LLMService, get_llm_service
from .retrieval_service import SearchResult

logger = get_logger(__name__)


@dataclass
class CriticResult:
    """Result from critic evaluation"""

    ok: bool
    fel: List[str]
    atgard: str
    latency_ms: float


@dataclass
class CriticReflection:
    """
    Result from self-reflection (Chain of Thought).

    Generated BEFORE answering to ensure constitutional compliance.

    Attributes:
        thought_process: The generated chain of thought
        has_sufficient_evidence: Whether enough evidence exists to answer
        missing_evidence: List of what's missing for a good answer
        citation_plan: Which documents should be cited
        constitutional_compliance: Whether response will follow constitutional rules
        confidence: Confidence in the reflection (0.0-1.0)
        latency_ms: Time taken for reflection
    """

    thought_process: str
    has_sufficient_evidence: bool
    missing_evidence: List[str]
    citation_plan: List[str]
    constitutional_compliance: bool
    confidence: float
    latency_ms: float


class CriticService(BaseService):
    """
    Critic Service - Evaluates and revises structured JSON responses.

    Features:
    - Critique structured JSON for validity and quality
    - Revise responses based on critic feedback
    - Max 2 revision attempts
    - Feature-flagged integration

    Thread Safety:
        - No shared mutable state between coroutines
        - Safe for concurrent requests
    """

    def __init__(self, config: ConfigService, llm_service: Optional[LLMService] = None):
        """
        Initialize Critic Service.

        Args:
            config: ConfigService for configuration access
            llm_service: LLMService for model interactions (for self-reflection)
        """
        super().__init__(config)

        # Get or create services
        self.llm_service = llm_service or get_llm_service(config)

        # Configuration for self-reflection
        self.reflection_enabled = getattr(config.settings, "crag_enable_self_reflection", False)
        self.reflection_model = getattr(config.settings, "crag_grader_model", "qwen3.5:9b")
        self.reflection_timeout = getattr(config.settings, "crag_reflection_timeout", 15.0)

        # Semantic critic configuration (LLM-based)
        self.semantic_enabled = getattr(config.settings, "critic_semantic_enabled", False)

        self.logger.info(
            f"Critic Service initialized "
            f"(self-reflection: {self.reflection_enabled}, semantic: {self.semantic_enabled})"
        )

    async def initialize(self) -> None:
        """Initialize critic service (no-op for now)"""
        self._mark_initialized()
        self.logger.info("Critic Service initialized")

    async def health_check(self) -> bool:
        """Check if critic service is healthy"""
        return True

    async def close(self) -> None:
        """Cleanup critic service (no resources to close)"""
        self._mark_uninitialized()
        self.logger.info("Critic Service closed")

    async def self_reflection(
        self,
        query: str,
        mode: str,
        sources: List[SearchResult],
    ) -> CriticReflection:
        """
        Generate self-reflection (Chain of Thought) BEFORE answering.

        This is the CRAG Self-Reflection Node that ensures constitutional compliance
        by reflecting on the query and available evidence before generation.

        Args:
            query: User's question
            mode: Response mode (evidence/assist)
            sources: Retrieved and graded sources

        Returns:
            CriticReflection with chain of thought and evidence assessment
        """
        start_time = time.perf_counter()

        try:
            if not self.reflection_enabled:
                # Return empty reflection if not enabled
                return CriticReflection(
                    thought_process="Self-reflection disabled",
                    has_sufficient_evidence=len(sources) > 0,
                    missing_evidence=[],
                    citation_plan=[],
                    constitutional_compliance=True,
                    confidence=1.0,
                    latency_ms=0.0,
                )

            # Build reflection prompt
            prompt = self._build_reflection_prompt(query, mode, sources)

            # Create messages for LLM
            messages = [
                {
                    "role": "system",
                    "content": "Du är en reflekterande AI som följer svenska förvaltningslagens principer. Reflektera noggrant innan du svarar.",
                },
                {"role": "user", "content": prompt},
            ]

            # Generate reflection
            full_response = ""
            async for token, _ in self.llm_service.chat_stream(
                messages=messages,
                config_override={
                    "temperature": 0.1,  # Low temperature for consistent reflection
                    "top_p": 0.9,
                    "num_predict": 512,
                    "model": self.reflection_model,
                },
            ):
                if token:
                    full_response += token

            # Parse reflection response
            reflection = self._parse_reflection_response(full_response, sources)
            reflection.latency_ms = (time.perf_counter() - start_time) * 1000

            self.logger.info(
                f"Self-reflection complete: sufficient_evidence={reflection.has_sufficient_evidence}, "
                f"compliance={reflection.constitutional_compliance}, "
                f"confidence={reflection.confidence:.2f}"
            )

            return reflection

        except Exception as e:
            self.logger.error(f"Self-reflection failed: {e}")
            # Return safe fallback
            return CriticReflection(
                thought_process=f"Reflektion misslyckades: {str(e)[:100]}",
                has_sufficient_evidence=False,
                missing_evidence=["Reflektion kunde inte utföras"],
                citation_plan=[],
                constitutional_compliance=False,
                confidence=0.0,
                latency_ms=(time.perf_counter() - start_time) * 1000,
            )

    def _build_reflection_prompt(self, query: str, mode: str, sources: List[SearchResult]) -> str:
        """
        Build the self-reflection prompt for Chain of Thought.

        Args:
            query: User's question
            mode: Response mode
            sources: Available sources

        Returns:
            Formatted reflection prompt
        """
        sources_text = "\n".join(
            [
                f"[{i + 1}] {s.title} (score: {s.score:.2f})\n{s.snippet[:200]}..."
                for i, s in enumerate(sources[:5])  # Limit to top 5 sources
            ]
        )

        return f"""REFLEKTERA innan du svarar på följande fråga:

FRÅGA: {query}
SVARLÄGE: {mode.upper()}
TILLGÄNGLIGA KÄLLOR ({len(sources)}):
{sources_text if sources_text else "Inga källor hittades"}

KONSTITUTIONELLA REGLER (Svenska förvaltningslagen):
1. LEGALITET: Använd endast information som stöds av dokumenten
2. TRANSPARENS: Alla påståenden måste ha källhänvisning
3. OBJEKTIVITET: Var neutral, saklig och formell
4. SERVICEKYLDIGHET: Var hjälpsam inom ramen för lagen

REFLEKTIONSFRÅGOR:
1. Vilka dokument är relevanta för frågan? Varför?
2. Finns det tillräckligt stöd i dokumenten för att ge ett rättssäkert svar?
3. Hur ska jag strukturera svaret enligt konstitutionella regler?
4. Vilka källor måste jag citera och hur?
5. Måste jag avslå frågan om underlag saknas?

Returnera endast giltig JSON:
{{
  "thought_process": "Din tankekedja på svenska (max 200 ord)",
  "has_sufficient_evidence": true/false,
  "missing_evidence": ["lista på vad som saknas"],
  "citation_plan": ["vilka dokument som ska citera"],
  "constitutional_compliance": true/false,
  "confidence": 0.0-1.0
}}

EXEMPEL PÅ SVAR:
{{
  "thought_process": "Frågan handlar om GDPR artikel 6. Jag har 3 relevanta dokument som täcker detta. Tillräckligt stöd finns för att svara med källor.",
  "has_sufficient_evidence": true,
  "missing_evidence": [],
  "citation_plan": ["GDPR Article 6", "Dataskyddsförordningen"],
  "constitutional_compliance": true,
  "confidence": 0.9
}}"""

    @staticmethod
    def _parse_bool(value: object) -> bool:
        """Safely parse a boolean that might be a string like 'false'."""
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ("true", "yes", "ja", "1")
        if isinstance(value, (int, float)):
            return bool(value)
        return False

    def _regex_extract_reflection(self, text: str) -> Optional[dict]:
        """Extract reflection fields via regex when JSON parsing fails."""
        import re

        result: dict = {}

        match = re.search(r'"has_sufficient_evidence"\s*:\s*(true|false)', text, re.IGNORECASE)
        if match:
            result["has_sufficient_evidence"] = match.group(1).lower() == "true"

        match = re.search(r'"constitutional_compliance"\s*:\s*(true|false)', text, re.IGNORECASE)
        if match:
            result["constitutional_compliance"] = match.group(1).lower() == "true"

        match = re.search(r'"confidence"\s*:\s*([\d.]+)', text)
        if match:
            result["confidence"] = float(match.group(1))

        match = re.search(r'"thought_process"\s*:\s*"([^"]*)"', text)
        if match:
            result["thought_process"] = match.group(1)

        return result if result else None

    def _parse_reflection_response(
        self, response: str, sources: List[SearchResult]
    ) -> CriticReflection:
        """
        Parse self-reflection response and create CriticReflection.

        Uses three-tier parsing: JSON → regex fallback → plaintext detection.
        """
        try:
            response = response.strip()
            parsed = None

            # Attempt 1: Standard JSON extraction
            start_idx = response.find("{")
            end_idx = response.rfind("}") + 1
            if start_idx != -1 and end_idx > start_idx:
                json_str = response[start_idx:end_idx]
                try:
                    parsed = json.loads(json_str)
                except json.JSONDecodeError:
                    self.logger.debug(f"JSON parse failed, raw: {json_str[:200]!r}")

            # Attempt 2: Regex fallback for key fields
            if parsed is None:
                self.logger.debug(f"No valid JSON, trying regex. Raw: {response[:300]!r}")
                parsed = self._regex_extract_reflection(response)

            # Attempt 3: Plaintext yes/no detection
            if parsed is None:
                response_lower = response.lower().strip()
                if response_lower in ("no", "nej", "false", "ingen"):
                    parsed = {"has_sufficient_evidence": False, "confidence": 0.3}
                elif response_lower in ("yes", "ja", "true"):
                    parsed = {"has_sufficient_evidence": True, "confidence": 0.5}

            if parsed is None:
                raise ValueError(f"Could not parse reflection from: {response[:100]}")

            # Extract fields with safe boolean parsing
            thought_process = str(parsed.get("thought_process", "Ingen tankekedja genererad"))
            has_sufficient_evidence = self._parse_bool(parsed.get("has_sufficient_evidence", False))
            missing_evidence = parsed.get("missing_evidence", [])
            citation_plan = parsed.get("citation_plan", [])
            constitutional_compliance = self._parse_bool(
                parsed.get("constitutional_compliance", True)
            )
            confidence = float(parsed.get("confidence", 0.5))
            confidence = max(0.0, min(1.0, confidence))

            # Validate against actual sources
            if not sources and has_sufficient_evidence:
                has_sufficient_evidence = False
                missing_evidence.append("Inga källor tillgängliga")
                constitutional_compliance = False

            return CriticReflection(
                thought_process=thought_process,
                has_sufficient_evidence=has_sufficient_evidence,
                missing_evidence=missing_evidence,
                citation_plan=citation_plan,
                constitutional_compliance=constitutional_compliance,
                confidence=confidence,
                latency_ms=0.0,  # Will be set by caller
            )

        except (json.JSONDecodeError, ValueError, KeyError) as e:
            self.logger.warning(f"Failed to parse reflection response: {e}")
            self.logger.debug(f"Raw reflection response: {response[:500]!r}")

            # Return conservative fallback
            return CriticReflection(
                thought_process=f"Kunde inte tolka reflektion: {str(e)[:100]}",
                has_sufficient_evidence=len(sources) > 0,
                missing_evidence=["Reflektion misslyckades"],
                citation_plan=[],
                constitutional_compliance=False,
                confidence=0.0,
                latency_ms=0.0,
            )

    async def critique(
        self,
        candidate_json: str,
        mode: str,
        sources_context: Optional[List[Dict]] = None,
    ) -> CriticResult:
        """
        Critique structured JSON response for validity and quality.

        Args:
            candidate_json: JSON response to critique
            mode: Response mode (evidence/assist)
            sources_context: Optional context about retrieved sources

        Returns:
            CriticResult with evaluation
        """
        start_time = time.perf_counter()

        try:
            # Parse JSON for validation
            try:
                parsed = json.loads(candidate_json)
            except json.JSONDecodeError as e:
                return CriticResult(
                    ok=False,
                    fel=[f"Invalid JSON: {str(e)}"],
                    atgard="Return valid JSON following the exact schema",
                    latency_ms=(time.perf_counter() - start_time) * 1000,
                )

            # Validate required fields
            fel = []
            required_fields = ["mode", "saknas_underlag", "svar", "kallor", "fakta_utan_kalla"]

            for field in required_fields:
                if field not in parsed:
                    fel.append(f"Missing required field: {field}")

            if fel:
                return CriticResult(
                    ok=False,
                    fel=fel,
                    atgard=f"Add missing fields: {', '.join(fel)}",
                    latency_ms=(time.perf_counter() - start_time) * 1000,
                )

            # Mode-specific validation
            if mode == "evidence":
                # EVIDENCE mode validation
                saknas_underlag = parsed.get("saknas_underlag", False)
                kallor = parsed.get("kallor", [])

                if saknas_underlag:
                    # Refusal case - should have empty sources and proper refusal text
                    if kallor:
                        fel.append("EVIDENCE refusal should have empty 'kallor'")

                    refusal_keywords = ["kan inte besvara", "underlag saknas", "spekulera"]
                    svar = parsed.get("svar", "")
                    if not any(keyword.lower() in svar.lower() for keyword in refusal_keywords):
                        fel.append("EVIDENCE refusal should contain proper refusal language")
                else:
                    # Evidence case - should have sources
                    if not kallor:
                        fel.append("EVIDENCE with evidence should have non-empty 'kallor'")

                    # Validate source format
                    for source in kallor:
                        if not isinstance(source, dict):
                            fel.append("Each source in 'kallor' must be an object")
                            break

                        required_source_fields = ["doc_id", "chunk_id", "citat", "loc"]
                        for field in required_source_fields:
                            if field not in source:
                                fel.append(f"Source missing required field: {field}")

                    # Validate claims without sources
                    fakta_utan_kalla = parsed.get("fakta_utan_kalla", [])
                    if fakta_utan_kalla:
                        fel.append(
                            "EVIDENCE mode should not contain 'fakta_utan_kalla' (use ASSIST mode)"
                        )

            elif mode == "assist":
                # ASSIST mode validation - more permissive
                pass

            # Note: arbetsanteckning is NOT flagged here — it's a required schema
            # field that strip_internal_note() removes before reaching the user.

            # Semantic check: verify citation text appears in sources
            if sources_context and not parsed.get("saknas_underlag", False):
                citation_issues = self._verify_citation_text(parsed, sources_context)
                fel.extend(citation_issues)

            ok = len(fel) == 0
            atgard = (
                "Response is valid" if ok else "Fix identified issues and return corrected JSON"
            )

            return CriticResult(
                ok=ok, fel=fel, atgard=atgard, latency_ms=(time.perf_counter() - start_time) * 1000
            )

        except Exception as e:
            self.logger.error(f"Critic evaluation failed: {e}")
            return CriticResult(
                ok=False,
                fel=[f"Critic evaluation error: {str(e)}"],
                atgard="Try again with valid JSON format",
                latency_ms=(time.perf_counter() - start_time) * 1000,
            )

    def _verify_citation_text(self, parsed: Dict, sources_context: List[Dict]) -> List[str]:
        """
        Verify that citation text (citat) actually appears in the source documents.

        This is a cheap text-matching check — no LLM needed.

        Args:
            parsed: Parsed JSON response
            sources_context: List of source dicts with "id", "title", "snippet"

        Returns:
            List of error messages for fabricated citations
        """
        issues = []
        kallor = parsed.get("kallor", [])

        if not kallor or not sources_context:
            return issues

        # Build combined source text lookup
        source_texts = {}
        for src in sources_context:
            src_id = src.get("id", "")
            combined = f"{src.get('title', '')} {src.get('snippet', '')}".lower()
            source_texts[src_id] = combined

        for i, citation in enumerate(kallor):
            if not isinstance(citation, dict):
                continue

            citat = citation.get("citat", "")
            doc_id = citation.get("doc_id", "")

            if not citat or len(citat) < 10:
                continue  # Skip very short citations

            # Check if citation text appears in any source
            citat_lower = citat.lower()
            # Extract significant words (>3 chars) from the citation
            citat_words = {w for w in citat_lower.split() if len(w) > 3}

            if not citat_words:
                continue

            # Check overlap with all sources (not just cited doc_id)
            best_overlap = 0.0
            for src_text in source_texts.values():
                src_words = set(src_text.split())
                overlap = len(citat_words & src_words) / len(citat_words)
                best_overlap = max(best_overlap, overlap)

            if best_overlap < 0.3:
                issue = (
                    f"Citation {i + 1} (doc_id={doc_id}): citat text has <30% overlap "
                    f"with source text — possible fabrication"
                )
                issues.append(issue)
                self.logger.warning(
                    f"Citation audit: fabrication suspect — doc_id={doc_id}, "
                    f"overlap={best_overlap:.2f}, citat_preview={citat[:80]!r}"
                )

        if issues:
            self.logger.info(
                f"Citation audit: {len(issues)} fabrication(s) flagged "
                f"out of {len(kallor)} citations checked"
            )

        return issues

    async def revise(
        self,
        candidate_json: str,
        critic_feedback: CriticResult,
    ) -> str:
        """
        Revise JSON response based on critic feedback.

        When semantic_enabled is True, uses LLM to generate a revised answer.
        Otherwise falls back to mechanical JSON fixes.

        Args:
            candidate_json: Original JSON response
            critic_feedback: CriticResult from critique() call

        Returns:
            Revised JSON string
        """
        try:
            parsed = json.loads(candidate_json)

            # Try LLM-based semantic revision if enabled and errors are semantic
            has_semantic_errors = any(
                "fabrication" in e or "overlap" in e for e in critic_feedback.fel
            )
            if self.semantic_enabled and has_semantic_errors and self.llm_service:
                try:
                    revised = await self._llm_revise(parsed, critic_feedback)
                    if revised:
                        return revised
                except Exception as e:
                    self.logger.warning(f"LLM revision failed, falling back: {e}")

            # Mechanical revision fallback
            if not critic_feedback.ok:
                # Try to fix common issues
                if "Missing required field" in str(critic_feedback.fel):
                    # Add missing fields with defaults
                    if "saknas_underlag" not in parsed:
                        parsed["saknas_underlag"] = False
                    if "fakta_utan_kalla" not in parsed:
                        parsed["fakta_utan_kalla"] = []
                    if "kallor" not in parsed:
                        parsed["kallor"] = []

                # Remove fabricated citations flagged by semantic check
                if any("fabrication" in e for e in critic_feedback.fel):
                    # Strip citations that were flagged
                    # Keep only citations NOT flagged
                    flagged_indices = set()
                    for error in critic_feedback.fel:
                        if "fabrication" in error:
                            # Extract "Citation N" index
                            try:
                                idx = int(error.split("Citation ")[1].split(" ")[0]) - 1
                                flagged_indices.add(idx)
                            except (IndexError, ValueError):
                                pass

                    if flagged_indices and "kallor" in parsed:
                        parsed["kallor"] = [
                            k for i, k in enumerate(parsed["kallor"]) if i not in flagged_indices
                        ]
                        self.logger.info(f"Removed {len(flagged_indices)} fabricated citations")

                # Remove internal notes if present
                if "arbetsanteckning" in parsed:
                    del parsed["arbetsanteckning"]

                # For EVIDENCE refusals, ensure proper format
                if parsed.get("mode") == "EVIDENCE" and parsed.get("saknas_underlag", False):
                    if not parsed.get("kallor"):
                        parsed["kallor"] = []
                    if not parsed.get("fakta_utan_kalla"):
                        parsed["fakta_utan_kalla"] = []

            return json.dumps(parsed, ensure_ascii=False)

        except json.JSONDecodeError:
            # If we can't parse JSON, return empty but valid response
            safe_response = {
                "mode": "ASSIST",
                "saknas_underlag": False,
                "svar": "Could not parse response. Please try again.",
                "kallor": [],
                "fakta_utan_kalla": [],
            }
            return json.dumps(safe_response, ensure_ascii=False)
        except Exception as e:
            self.logger.error(f"Revision failed: {e}")
            # Return safe fallback
            safe_response = {
                "mode": "ASSIST",
                "saknas_underlag": False,
                "svar": "Response revision failed. Please try again.",
                "kallor": [],
                "fakta_utan_kalla": [],
            }
            return json.dumps(safe_response, ensure_ascii=False)

    async def _llm_revise(self, parsed: Dict, feedback: CriticResult) -> Optional[str]:
        """
        Use LLM to semantically revise the response based on critic feedback.

        Args:
            parsed: Parsed JSON response
            feedback: CriticResult with identified issues

        Returns:
            Revised JSON string, or None if LLM revision fails
        """
        errors_text = "\n".join(f"- {e}" for e in feedback.fel)
        original_json = json.dumps(parsed, ensure_ascii=False, indent=2)

        messages = [
            {
                "role": "system",
                "content": (
                    "Du är en kvalitetsgranskare för juridiska svar. "
                    "Korrigera svaret baserat på identifierade fel. "
                    "Returnera ENDAST giltig JSON utan extra text."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Följande svar har kvalitetsproblem:\n\n"
                    f"IDENTIFIERADE FEL:\n{errors_text}\n\n"
                    f"ÅTGÄRD: {feedback.atgard}\n\n"
                    f"ORIGINAL JSON:\n{original_json[:2000]}\n\n"
                    f"Korrigera felen och returnera giltig JSON."
                ),
            },
        ]

        full_response = ""
        async for token, _ in self.llm_service.chat_stream(
            messages=messages,
            config_override={
                "temperature": 0.1,
                "num_predict": 1024,
            },
        ):
            if token:
                full_response += token

        # Parse the LLM response
        full_response = full_response.strip()
        start_idx = full_response.find("{")
        end_idx = full_response.rfind("}") + 1

        if start_idx == -1 or end_idx == 0:
            return None

        json_str = full_response[start_idx:end_idx]
        revised = json.loads(json_str)  # Validates JSON

        # Ensure required fields exist
        for field_name in ["mode", "saknas_underlag", "svar", "kallor", "fakta_utan_kalla"]:
            if field_name not in revised:
                revised[field_name] = parsed.get(field_name, "")

        return json.dumps(revised, ensure_ascii=False)


def get_critic_service(
    config: Optional[ConfigService] = None, llm_service: Optional[LLMService] = None
) -> CriticService:
    """
    Get singleton Critic Service instance.

    Args:
        config: Optional ConfigService (uses default if not provided)
        llm_service: Optional LLMService (uses default if not provided)

    Returns:
        Singleton CriticService instance
    """
    if config is None:
        config = get_config_service()
    if llm_service is None:
        llm_service = get_llm_service(config)

    return CriticService(config, llm_service)

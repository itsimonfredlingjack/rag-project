"""
Structured Output Service - JSON Schema Validation for Anti-Hallucination
Validates LLM responses against strict schema before showing to user
"""

import json
import re
from functools import lru_cache
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, ValidationError

from ..utils.logging import get_logger
from .base_service import BaseService
from .config_service import ConfigService, get_config_service

logger = get_logger(__name__)


class StructuredOutputSchema(BaseModel):
    """Schema for structured LLM output"""

    mode: str = Field(..., description="EVIDENCE or ASSIST")
    saknas_underlag: bool = Field(..., description="True if supporting documents missing")
    svar: str = Field(..., description="Answer text to show to user")
    kallor: List[Dict[str, str]] = Field(
        default_factory=list, description="Sources: [{doc_id, chunk_id, citat, loc}]"
    )
    fakta_utan_kalla: List[str] = Field(
        default_factory=list, description="Facts without sources (should be empty in EVIDENCE mode)"
    )
    arbetsanteckning: str = Field(
        default="", description="Internal control note (will be stripped from response)"
    )


class StructuredOutputService(BaseService):
    """
    Service for validating structured LLM output.

    Features:
    - JSON schema validation
    - Citation enforcement (check that all facts have sources in EVIDENCE mode)
    - Anti-hallucination checks (no facts without sources in EVIDENCE)
    - Strip internal notes before returning to user
    """

    def __init__(self, config: ConfigService):
        super().__init__(config)
        self.logger.info("Structured Output Service initialized")

    async def initialize(self) -> None:
        self._mark_initialized()

    async def health_check(self) -> bool:
        return True

    async def close(self) -> None:
        self._mark_uninitialized()

    def validate_output(
        self,
        json_output: Dict[str, Any],
        mode: str,
        retrieved_doc_ids: Optional[set[str]] = None,
        retrieved_sources: Optional[list] = None,
    ) -> tuple[bool, List[str], Optional[StructuredOutputSchema]]:
        """
        Validate structured output against schema and mode-specific rules.

        Args:
            json_output: LLM response as JSON
            mode: Response mode (EVIDENCE or ASSIST)
            retrieved_doc_ids: Set of doc IDs from retrieval. If provided, citations
                are cross-validated to detect fabricated references.
            retrieved_sources: Source objects from retrieval. If provided, used to
                resolve fabricated doc_ids by matching titles.

        Returns:
            Tuple of (is_valid, errors_list, validated_schema)
        """
        errors = []

        # Step 1: Pydantic schema validation
        try:
            validated = StructuredOutputSchema(**json_output)
        except ValidationError as e:
            errors.extend([f"Schema validation error: {err['msg']}" for err in e.errors()])
            self.logger.error(f"Schema validation failed: {errors}")
            return False, errors, None

        # Step 2: Mode-specific validation
        if mode.upper() == "EVIDENCE":
            # EVIDENCE: fakta_utan_kalla MUST be empty
            if validated.fakta_utan_kalla:
                errors.append(
                    f"EVIDENCE mode: {len(validated.fakta_utan_kalla)} facts without sources. "
                    "In EVIDENCE mode, all facts MUST have sources."
                )

            # EVIDENCE: If saknas_underlag=true, svar should be refusal
            if validated.saknas_underlag:
                # Check if svar matches refusal pattern
                refusal_pattern = r"Tyvärr kan jag inte besvara frågan"
                if not re.search(refusal_pattern, validated.svar):
                    errors.append("EVIDENCE mode: If saknas_underlag=true, svar must be refusal.")

        elif mode.upper() == "ASSIST":
            # ASSIST: Fakta från dokument ska ha källa; allmän kunskap i fakta_utan_källa
            # This is more lenient - we just log a warning if facts without sources exist
            if validated.fakta_utan_kalla:
                self.logger.info(
                    f"ASSIST mode: {len(validated.fakta_utan_kalla)} facts without sources "
                    "(allowed for general knowledge)"
                )

        # Step 3: Citation cross-validation and resolution
        if retrieved_doc_ids is not None and validated.kallor:
            # Build title→id map for resolving model-generated doc_ids
            title_to_id: dict[str, str] = {}
            if retrieved_sources:
                for s in retrieved_sources:
                    title = getattr(s, "title", None)
                    sid = getattr(s, "id", None)
                    if title and sid:
                        title_to_id[title.lower().strip()] = sid

            resolved_kallor = []
            resolved_count = 0
            fabricated = []
            for src in validated.kallor:
                doc_id = src.get("doc_id", "")
                if not doc_id or doc_id in retrieved_doc_ids:
                    resolved_kallor.append(src)
                    continue

                # Try to resolve by title matching
                resolved_id = None
                doc_id_lower = doc_id.lower().strip()
                for title, real_id in title_to_id.items():
                    if doc_id_lower in title or title in doc_id_lower:
                        resolved_id = real_id
                        break

                if resolved_id:
                    src["doc_id"] = resolved_id
                    src["chunk_id"] = resolved_id
                    resolved_kallor.append(src)
                    resolved_count += 1
                else:
                    fabricated.append(doc_id)

            if resolved_count:
                self.logger.info(
                    f"Citation resolution: resolved {resolved_count} doc_id(s) by title matching"
                )
            if fabricated:
                self.logger.warning(
                    f"Citation cross-validation: {len(fabricated)} unresolvable doc_id(s): "
                    f"{fabricated[:5]}"
                )
            validated.kallor = resolved_kallor

        is_valid = len(errors) == 0

        if not is_valid:
            self.logger.warning(f"Structured output validation failed: {errors}")
        else:
            self.logger.info("Structured output validation passed")

        return is_valid, errors, validated

    def strip_internal_note(self, schema: StructuredOutputSchema) -> Dict[str, Any]:
        """
        Strip internal notes before returning to user.

        Args:
            schema: Validated structured output schema

        Returns:
            Cleaned dict without internal notes
        """
        return {
            "mode": schema.mode,
            "saknas_underlag": schema.saknas_underlag,
            "svar": schema.svar,
            "kallor": schema.kallor,
            "fakta_utan_kalla": schema.fakta_utan_kalla,
            # arbetsanteckning is NOT included (security/privacy)
        }

    @staticmethod
    def _sanitize_json_control_chars(text: str) -> str:
        """
        Escape raw control characters inside JSON string values.

        Walks char-by-char tracking whether we're inside a JSON string.
        Only escapes \\r, \\n, \\t when inside a string value — JSON
        structural whitespace outside strings is preserved.
        Already-escaped sequences (\\\\n etc.) are NOT double-escaped.
        """
        out: list[str] = []
        in_string = False
        escape_next = False

        for ch in text:
            if escape_next:
                out.append(ch)
                escape_next = False
                continue

            if ch == "\\":
                if in_string:
                    escape_next = True
                out.append(ch)
                continue

            if ch == '"':
                in_string = not in_string
                out.append(ch)
                continue

            if in_string:
                if ch == "\r":
                    out.append("\\r")
                    continue
                if ch == "\n":
                    out.append("\\n")
                    continue
                if ch == "\t":
                    out.append("\\t")
                    continue

            out.append(ch)

        return "".join(out)

    def parse_llm_json(self, text: str) -> Dict[str, Any]:
        """
        Parse JSON from LLM response, handling various formats.

        Args:
            text: LLM response text

        Returns:
            Parsed JSON dict

        Raises:
            json.JSONDecodeError: If text cannot be parsed as JSON
        """
        import re

        # Strip markdown code fences if present
        json_text = text.strip()
        if json_text.startswith("```json"):
            json_text = json_text[7:]
        if json_text.startswith("```"):
            json_text = json_text[3:]
        if json_text.endswith("```"):
            json_text = json_text[:-3]
        json_text = json_text.strip()

        # Sanitize control characters inside JSON string values
        json_text = self._sanitize_json_control_chars(json_text)

        # Try direct parse first
        try:
            return json.loads(json_text)
        except json.JSONDecodeError:
            pass

        # Try to find JSON object in text (handles preamble text)
        # Look for { ... } pattern that spans multiple lines
        json_match = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", json_text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass

        # More aggressive: find first { and last }
        first_brace = json_text.find("{")
        last_brace = json_text.rfind("}")
        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
            candidate = json_text[first_brace : last_brace + 1]
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass

        # Nothing worked, raise the original error
        return json.loads(json_text)

    async def validate_with_retries(
        self, llm_call_fn, mode: str, max_retries: int = 2, retry_instruction: str = None
    ) -> tuple[bool, List[str], Optional[StructuredOutputSchema], bool]:
        """
        Validate structured output with retry logic (max 2 attempts).

        Args:
            llm_call_fn: Async function that returns LLM response text
            mode: Response mode (EVIDENCE or ASSIST)
            max_retries: Maximum retry attempts (default: 2)
            retry_instruction: Optional instruction for retry attempt

        Returns:
            Tuple of (is_valid, errors, validated_schema, is_retry_attempt)
        """

        # Attempt 1: Normal structured output
        try:
            first_attempt_text = await llm_call_fn()
            json_output = self.parse_llm_json(first_attempt_text)
            is_valid, errors, validated = self.validate_output(json_output, mode)

            if is_valid and validated:
                return True, [], validated, False  # Success on first attempt
            else:
                # Validation failed, will retry
                pass

        except json.JSONDecodeError as e:
            # JSON parsing failed on first attempt
            is_valid, errors, validated = False, [f"JSON parse error: {str(e)}"], None

        # Retry attempts
        for attempt in range(1, max_retries):
            try:
                if retry_instruction:
                    # Add retry instruction to the LLM call
                    retry_text = await llm_call_fn(retry_instruction=retry_instruction)
                else:
                    retry_text = await llm_call_fn()

                json_output = self.parse_llm_json(retry_text)
                is_valid, errors, validated = self.validate_output(json_output, mode)

                if is_valid and validated:
                    return True, [], validated, True  # Success on retry attempt

            except json.JSONDecodeError as e:
                # JSON parsing failed on retry
                is_valid, errors, validated = (
                    False,
                    [f"JSON parse error on retry {attempt}: {str(e)}"],
                    None,
                )
                # Continue to next retry
                continue

        # All attempts failed
        return False, errors or ["All retry attempts failed"], None, True


@lru_cache()
def get_structured_output_service(
    config: Optional[ConfigService] = None,
) -> StructuredOutputService:
    if config is None:
        config = get_config_service()

    return StructuredOutputService(config)

"""
Tests for Structured Output Service
"""

import json
from unittest.mock import Mock, patch

import pytest

from app.services.structured_output_service import StructuredOutputService


class TestStructuredOutputService:
    """Test cases for structured output validation and parsing"""

    def setup_method(self):
        """Setup for each test method"""
        self.config_mock = Mock()
        self.config_mock.settings.debug = False

        with patch("app.services.structured_output_service.get_config_service") as mock_config:
            mock_config.return_value = self.config_mock
            self.service = StructuredOutputService(self.config_mock)

    def test_parse_llm_json_valid(self):
        """TF5: Test valid JSON parsing"""
        valid_json = '{"mode": "ASSIST", "saknas_underlag": false, "svar": "Test response", "kallor": [], "fakta_utan_kalla": []}'

        result = self.service.parse_llm_json(valid_json)

        assert isinstance(result, dict)
        assert result["mode"] == "ASSIST"
        assert result["saknas_underlag"] is False
        assert result["svar"] == "Test response"

    def test_parse_llm_json_with_fences(self):
        """TF5: Test JSON with markdown fences"""
        fenced_json = '```json\n{"mode": "ASSIST", "saknas_underlag": false, "svar": "Test response", "kallor": [], "fakta_utan_kalla": []}\n```'

        result = self.service.parse_llm_json(fenced_json)

        assert isinstance(result, dict)
        assert result["mode"] == "ASSIST"
        assert result["saknas_underlag"] is False
        assert result["svar"] == "Test response"

    def test_parse_llm_json_invalid(self):
        """TF5: Test invalid JSON parsing"""
        invalid_json = '{"mode": "ASSIST", invalid json'

        with pytest.raises(json.JSONDecodeError):
            self.service.parse_llm_json(invalid_json)

    def test_validate_output_evidence_mode_with_sources(self):
        """TF1: Test EVIDENCE mode validation with sources"""
        valid_evidence = {
            "mode": "EVIDENCE",
            "saknas_underlag": False,
            "svar": "Based on GDPR Article 6...",
            "kallor": [
                {
                    "doc_id": "gdpr_doc_1",
                    "chunk_id": "chunk_1",
                    "citat": "Article 6 text",
                    "loc": "section 1",
                }
            ],
            "fakta_utan_kalla": [],
            "arbetsanteckning": "Internal note",
        }

        is_valid, errors, validated = self.service.validate_output(valid_evidence, "EVIDENCE")

        assert is_valid is True
        assert len(errors) == 0
        assert validated.fakta_utan_kalla == []

    def test_validate_output_evidence_mode_without_sources(self):
        """TF3: Test EVIDENCE mode validation without sources (should fail)"""
        invalid_evidence = {
            "mode": "EVIDENCE",
            "saknas_underlag": False,
            "svar": "Based on my knowledge...",
            "kallor": [],
            "fakta_utan_kalla": ["Some fact without source"],
            "arbetsanteckning": "Internal note",
        }

        is_valid, errors, validated = self.service.validate_output(invalid_evidence, "EVIDENCE")

        assert is_valid is False
        assert len(errors) > 0
        assert "facts without sources" in errors[0]

    def test_validate_output_evidence_mode_refusal(self):
        """TF2: Test EVIDENCE mode with proper refusal"""
        refusal_evidence = {
            "mode": "EVIDENCE",
            "saknas_underlag": True,
            "svar": "Tyvärr kan jag inte besvara frågan utifrån de dokument som har hämtats i den här sökningen...",
            "kallor": [],
            "fakta_utan_kalla": [],
            "arbetsanteckning": "Refusal due to lack of supporting documents",
        }

        is_valid, errors, validated = self.service.validate_output(refusal_evidence, "EVIDENCE")

        assert is_valid is True
        assert validated.saknas_underlag is True
        assert len(validated.kallor) == 0

    def test_validate_output_assist_mode_with_general_knowledge(self):
        """TF4: Test ASSIST mode with general knowledge"""
        assist_mixed = {
            "mode": "ASSIST",
            "saknas_underlag": False,
            "svar": "GDPR regulates personal data processing. In Sweden, this is implemented through...",
            "kallor": [
                {
                    "doc_id": "gdpr_doc_1",
                    "chunk_id": "chunk_1",
                    "citat": "Article 6 text",
                    "loc": "section 1",
                }
            ],
            "fakta_utan_kalla": [
                "GDPR stands for General Data Protection Regulation",
                "The regulation applies across EU member states",
            ],
            "arbetsanteckning": "Mixed response with sources and general knowledge",
        }

        is_valid, errors, validated = self.service.validate_output(assist_mixed, "ASSIST")

        assert is_valid is True
        assert len(validated.kallor) > 0
        assert len(validated.fakta_utan_kalla) > 0

    def test_strip_internal_note_security(self):
        """TF5: Test that arbetsanteckning is stripped"""

        # Create a mock schema object
        mock_schema = Mock()
        mock_schema.mode = "ASSIST"
        mock_schema.saknas_underlag = False
        mock_schema.svar = "Test response"
        mock_schema.kallor = []
        mock_schema.fakta_utan_kalla = []
        mock_schema.arbetsanteckning = "This should not appear in output"

        result = self.service.strip_internal_note(mock_schema)

        assert "arbetsanteckning" not in result
        assert "This should not appear in output" not in str(result)
        assert result["svar"] == "Test response"

    def test_validate_with_retries_max_attempts(self):
        """TF6: Test retry logic with max attempts"""
        # Mock LLM call that fails twice
        call_count = 0

        async def mock_llm_call(retry_instruction=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise json.JSONDecodeError("Invalid JSON", "attempt 1", 0)
            elif call_count == 2:
                raise json.JSONDecodeError("Still invalid", "attempt 2", 0)
            else:
                raise Exception("Too many attempts")

        import asyncio

        async def run_test():
            result = await self.service.validate_with_retries(
                mock_llm_call, "ASSIST", max_retries=2
            )
            return result

        # This should run max 2 attempts and fail
        is_valid, errors, validated, is_retry = asyncio.run(run_test())

        assert is_valid is False
        assert is_retry is True
        assert call_count == 2  # Should only attempt twice, not more

    def test_validate_with_retries_success_on_retry(self):
        """TF5: Test successful retry after first failure"""
        call_count = 0

        async def mock_llm_call(retry_instruction=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise json.JSONDecodeError("Invalid JSON", "attempt 1", 0)
            else:
                # Return valid JSON on retry
                return '{"mode": "ASSIST", "saknas_underlag": false, "svar": "Success on retry", "kallor": [], "fakta_utan_kalla": []}'

        import asyncio

        async def run_test():
            result = await self.service.validate_with_retries(
                mock_llm_call, "ASSIST", max_retries=2
            )
            return result

        is_valid, errors, validated, is_retry = asyncio.run(run_test())

        assert is_valid is True
        assert is_retry is True
        assert call_count == 2
        assert validated.svar == "Success on retry"


class TestCitationResolution:
    """Test citation cross-validation resolves model-generated doc_ids by title matching."""

    def setup_method(self):
        self.config_mock = Mock()
        self.config_mock.settings.debug = False

        with patch("app.services.structured_output_service.get_config_service") as mock_config:
            mock_config.return_value = self.config_mock
            self.service = StructuredOutputService(self.config_mock)

    def _make_source(self, id, title):
        s = Mock()
        s.id = id
        s.title = title
        return s

    def test_exact_match_passes_through(self):
        """Valid doc_ids pass through unchanged."""
        output = {
            "mode": "EVIDENCE",
            "saknas_underlag": False,
            "svar": "Svar",
            "kallor": [{"doc_id": "real_id_1", "chunk_id": "real_id_1", "citat": "text"}],
            "fakta_utan_kalla": [],
        }
        sources = [self._make_source("real_id_1", "RF 2 kap.")]
        ids = {"real_id_1"}

        _, _, validated = self.service.validate_output(
            output, "EVIDENCE", retrieved_doc_ids=ids, retrieved_sources=sources
        )
        assert len(validated.kallor) == 1
        assert validated.kallor[0]["doc_id"] == "real_id_1"

    def test_title_match_resolves_fabricated_id(self):
        """Model-generated doc_id matching source title gets resolved to real ID."""
        output = {
            "mode": "EVIDENCE",
            "saknas_underlag": False,
            "svar": "Svar",
            "kallor": [{"doc_id": "RF 2 kap.", "chunk_id": "RF 2 kap.", "citat": "text"}],
            "fakta_utan_kalla": [],
        }
        sources = [self._make_source("sfs_1974_152_2kap", "RF 2 kap.")]
        ids = {"sfs_1974_152_2kap"}

        _, _, validated = self.service.validate_output(
            output, "EVIDENCE", retrieved_doc_ids=ids, retrieved_sources=sources
        )
        assert len(validated.kallor) == 1
        assert validated.kallor[0]["doc_id"] == "sfs_1974_152_2kap"

    def test_partial_title_match_resolves(self):
        """Partial title match resolves (e.g., 'RF 2 kap' in 'RF 2 kap. Grundläggande fri')."""
        output = {
            "mode": "EVIDENCE",
            "saknas_underlag": False,
            "svar": "Svar",
            "kallor": [{"doc_id": "RF 2 kap", "chunk_id": "RF 2 kap", "citat": "text"}],
            "fakta_utan_kalla": [],
        }
        sources = [
            self._make_source("sfs_1974_152_2kap_1", "RF 2 kap. Grundläggande fri- och rättigheter")
        ]
        ids = {"sfs_1974_152_2kap_1"}

        _, _, validated = self.service.validate_output(
            output, "EVIDENCE", retrieved_doc_ids=ids, retrieved_sources=sources
        )
        assert len(validated.kallor) == 1
        assert validated.kallor[0]["doc_id"] == "sfs_1974_152_2kap_1"

    def test_truly_fabricated_stripped(self):
        """Citations that can't be resolved are stripped."""
        output = {
            "mode": "EVIDENCE",
            "saknas_underlag": False,
            "svar": "Svar",
            "kallor": [{"doc_id": "totally_made_up", "chunk_id": "x", "citat": "text"}],
            "fakta_utan_kalla": [],
        }
        sources = [self._make_source("real_id_1", "RF 2 kap.")]
        ids = {"real_id_1"}

        _, _, validated = self.service.validate_output(
            output, "EVIDENCE", retrieved_doc_ids=ids, retrieved_sources=sources
        )
        assert len(validated.kallor) == 0

    def test_no_sources_param_strips_like_before(self):
        """Without retrieved_sources, fabricated doc_ids are stripped (backwards compat)."""
        output = {
            "mode": "EVIDENCE",
            "saknas_underlag": False,
            "svar": "Svar",
            "kallor": [{"doc_id": "fake_id", "chunk_id": "x", "citat": "text"}],
            "fakta_utan_kalla": [],
        }
        ids = {"real_id_1"}

        _, _, validated = self.service.validate_output(output, "EVIDENCE", retrieved_doc_ids=ids)
        assert len(validated.kallor) == 0


class TestSanitizeJsonControlChars:
    """Tests for _sanitize_json_control_chars and control-char handling in parse_llm_json."""

    def setup_method(self):
        self.config_mock = Mock()
        self.config_mock.settings.debug = False

        with patch("app.services.structured_output_service.get_config_service") as mock_config:
            mock_config.return_value = self.config_mock
            self.service = StructuredOutputService(self.config_mock)

    def test_crlf_in_svar_field_parsed_correctly(self):
        """JSON with raw \\r\\n in 'svar' string value should parse without crashing."""
        raw = '{"mode": "EVIDENCE", "saknas_underlag": false, "svar": "Rad 1\r\nRad 2\r\nRad 3", "kallor": [], "fakta_utan_kalla": []}'

        result = self.service.parse_llm_json(raw)

        # Sanitizer escapes raw control chars → json.loads interprets them back
        # The key assertion: parsing succeeds and content is preserved
        assert "Rad 1" in result["svar"]
        assert "Rad 2" in result["svar"]
        assert "Rad 3" in result["svar"]
        assert result["mode"] == "EVIDENCE"

    def test_tab_in_string_value_parsed_correctly(self):
        """JSON with raw \\t in string value should parse without crashing."""
        raw = '{"mode": "ASSIST", "saknas_underlag": false, "svar": "Kolumn1\tKolumn2", "kallor": [], "fakta_utan_kalla": []}'

        result = self.service.parse_llm_json(raw)

        assert "Kolumn1" in result["svar"]
        assert "Kolumn2" in result["svar"]

    def test_already_escaped_not_double_escaped(self):
        """Already-escaped sequences (\\\\n) must NOT be double-escaped."""
        raw = '{"mode": "ASSIST", "saknas_underlag": false, "svar": "Rad 1\\nRad 2", "kallor": [], "fakta_utan_kalla": []}'

        result = self.service.parse_llm_json(raw)

        # \\n in JSON becomes \n in Python string — this should remain a single newline
        assert result["svar"] == "Rad 1\nRad 2"

    def test_control_chars_outside_strings_preserved(self):
        """Control characters used as JSON whitespace (outside strings) should be preserved."""
        # JSON with newlines as structural whitespace (normal formatting)
        raw = '{\n  "mode": "ASSIST",\n  "saknas_underlag": false,\n  "svar": "Test",\n  "kallor": [],\n  "fakta_utan_kalla": []\n}'

        result = self.service.parse_llm_json(raw)

        assert result["mode"] == "ASSIST"
        assert result["svar"] == "Test"

    def test_markdown_fences_with_control_chars(self):
        """Markdown fences + control characters in string values should both be handled."""
        raw = '```json\n{"mode": "EVIDENCE", "saknas_underlag": false, "svar": "Lag\r\ntext", "kallor": [], "fakta_utan_kalla": []}\n```'

        result = self.service.parse_llm_json(raw)

        assert result["mode"] == "EVIDENCE"
        assert "Lag" in result["svar"]
        assert "text" in result["svar"]

    def test_sanitize_static_method_directly(self):
        """Test _sanitize_json_control_chars as a standalone function."""
        # Raw \r\n inside a string value
        text = '"hello\r\nworld"'
        sanitized = StructuredOutputService._sanitize_json_control_chars(text)
        assert sanitized == '"hello\\r\\nworld"'

    def test_sanitize_preserves_escaped_backslash_n(self):
        """Test that \\n (already escaped) is preserved."""
        text = r'"hello\nworld"'
        sanitized = StructuredOutputService._sanitize_json_control_chars(text)
        # The backslash-n should stay as is (already properly escaped)
        assert sanitized == r'"hello\nworld"'

    def test_raw_control_chars_would_fail_without_sanitizer(self):
        """Verify that raw control chars in JSON strings cause JSONDecodeError without sanitization."""
        raw = '{"svar": "Rad 1\r\nRad 2"}'
        # Without sanitization, this should fail
        with pytest.raises(json.JSONDecodeError):
            json.loads(raw)

        # With sanitization, it should succeed
        sanitized = StructuredOutputService._sanitize_json_control_chars(raw)
        result = json.loads(sanitized)
        assert "Rad 1" in result["svar"]
        assert "Rad 2" in result["svar"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

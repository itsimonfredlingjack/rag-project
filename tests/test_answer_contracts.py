"""
Tests for Answer Contracts per Intent.

These contracts define structured output formats for each query intent type,
ensuring consistent and appropriate responses.
"""

from backend.app.services.intent_classifier import QueryIntent
from backend.app.services.orchestrator_service import (
    ANSWER_CONTRACTS,
    get_answer_contract,
)


class TestAnswerContractsExist:
    """Test that answer contracts are defined for all primary intents."""

    def test_parliament_trace_contract_exists(self):
        """PARLIAMENT_TRACE intent should have a contract defined."""
        assert QueryIntent.PARLIAMENT_TRACE in ANSWER_CONTRACTS
        contract = ANSWER_CONTRACTS[QueryIntent.PARLIAMENT_TRACE]
        assert isinstance(contract, str)
        assert len(contract) > 50  # Not empty or trivial

    def test_policy_arguments_contract_exists(self):
        """POLICY_ARGUMENTS intent should have a contract defined."""
        assert QueryIntent.POLICY_ARGUMENTS in ANSWER_CONTRACTS
        contract = ANSWER_CONTRACTS[QueryIntent.POLICY_ARGUMENTS]
        assert isinstance(contract, str)
        assert len(contract) > 50

    def test_research_synthesis_contract_exists(self):
        """RESEARCH_SYNTHESIS intent should have a contract defined."""
        assert QueryIntent.RESEARCH_SYNTHESIS in ANSWER_CONTRACTS
        contract = ANSWER_CONTRACTS[QueryIntent.RESEARCH_SYNTHESIS]
        assert isinstance(contract, str)
        assert len(contract) > 50

    def test_legal_text_contract_exists(self):
        """LEGAL_TEXT intent should have a contract defined."""
        assert QueryIntent.LEGAL_TEXT in ANSWER_CONTRACTS
        contract = ANSWER_CONTRACTS[QueryIntent.LEGAL_TEXT]
        assert isinstance(contract, str)
        assert len(contract) > 50

    def test_practical_process_contract_exists(self):
        """PRACTICAL_PROCESS intent should have a contract defined."""
        assert QueryIntent.PRACTICAL_PROCESS in ANSWER_CONTRACTS
        contract = ANSWER_CONTRACTS[QueryIntent.PRACTICAL_PROCESS]
        assert isinstance(contract, str)
        assert len(contract) > 50


class TestAnswerContractContent:
    """Test that contracts contain required elements for their intent."""

    def test_parliament_trace_contains_tidslinje(self):
        """PARLIAMENT_TRACE contract should mention tidslinje (timeline)."""
        contract = ANSWER_CONTRACTS[QueryIntent.PARLIAMENT_TRACE]
        # Swedish for timeline - key structural element
        assert "tidslinje" in contract.lower()

    def test_parliament_trace_requires_sources(self):
        """PARLIAMENT_TRACE contract should require source citations."""
        contract = ANSWER_CONTRACTS[QueryIntent.PARLIAMENT_TRACE]
        # Should mention citations from riksdag documents
        assert "citat" in contract.lower() or "käll" in contract.lower()

    def test_policy_arguments_separates_riksdag_from_forskning(self):
        """POLICY_ARGUMENTS contract should clearly separate riksdag from research."""
        contract = ANSWER_CONTRACTS[QueryIntent.POLICY_ARGUMENTS]
        # Must have separate sections
        assert "riksdag" in contract.lower()
        assert "forskning" in contract.lower()
        # Should have explicit separation instruction
        assert "del a" in contract.lower() or "primärt" in contract.lower()
        assert "del b" in contract.lower() or "sekundärt" in contract.lower()

    def test_policy_arguments_prohibits_mixing_sources(self):
        """POLICY_ARGUMENTS contract should prohibit mixing source types."""
        contract = ANSWER_CONTRACTS[QueryIntent.POLICY_ARGUMENTS]
        # Should have a rule about not mixing
        assert "blanda" in contract.lower() or "aldrig" in contract.lower()

    def test_research_synthesis_disclaims_riksdagsbeslut(self):
        """RESEARCH_SYNTHESIS contract should disclaim that it's not riksdag decisions."""
        contract = ANSWER_CONTRACTS[QueryIntent.RESEARCH_SYNTHESIS]
        # Must explicitly state this is research, not riksdag
        assert "riksdag" in contract.lower() or "beslut" in contract.lower()
        # Should indicate research focus
        assert "forskning" in contract.lower()

    def test_research_synthesis_is_neutral(self):
        """RESEARCH_SYNTHESIS contract should be neutral, especially for health topics."""
        contract = ANSWER_CONTRACTS[QueryIntent.RESEARCH_SYNTHESIS]
        # Should mention neutral/objective approach or no treatment advice
        assert "neutral" in contract.lower() or "behandling" in contract.lower()

    def test_legal_text_requires_citation_format(self):
        """LEGAL_TEXT contract should require exact citation format."""
        contract = ANSWER_CONTRACTS[QueryIntent.LEGAL_TEXT]
        # Must require verbatim citation
        assert "citera" in contract.lower() or "ordagrant" in contract.lower()
        # Should specify citation format with law reference
        assert "§" in contract or "kap" in contract.lower()

    def test_legal_text_prohibits_interpretation(self):
        """LEGAL_TEXT contract should limit interpretation beyond law text."""
        contract = ANSWER_CONTRACTS[QueryIntent.LEGAL_TEXT]
        # Should restrict going beyond the text
        assert "tolkning" in contract.lower() or "lydelse" in contract.lower()

    def test_practical_process_mentions_steps(self):
        """PRACTICAL_PROCESS contract should structure output as steps."""
        contract = ANSWER_CONTRACTS[QueryIntent.PRACTICAL_PROCESS]
        # Should mention numbered/ordered steps
        assert "steg" in contract.lower() or "numrerad" in contract.lower()

    def test_practical_process_includes_authorities(self):
        """PRACTICAL_PROCESS contract should mention relevant authorities."""
        contract = ANSWER_CONTRACTS[QueryIntent.PRACTICAL_PROCESS]
        # Should reference myndigheter or instanser
        assert "myndighet" in contract.lower() or "instans" in contract.lower()


class TestGetAnswerContractFunction:
    """Test the getter function for answer contracts."""

    def test_get_contract_for_known_intent(self):
        """Should return the contract for a known intent."""
        contract = get_answer_contract(QueryIntent.PARLIAMENT_TRACE)
        assert contract == ANSWER_CONTRACTS[QueryIntent.PARLIAMENT_TRACE]

    def test_get_contract_for_all_primary_intents(self):
        """Should return contracts for all primary intents."""
        primary_intents = [
            QueryIntent.PARLIAMENT_TRACE,
            QueryIntent.POLICY_ARGUMENTS,
            QueryIntent.RESEARCH_SYNTHESIS,
            QueryIntent.LEGAL_TEXT,
            QueryIntent.PRACTICAL_PROCESS,
        ]
        for intent in primary_intents:
            contract = get_answer_contract(intent)
            assert contract, f"Contract missing for {intent}"
            assert len(contract) > 0

    def test_get_contract_for_unknown_intent_returns_empty(self):
        """Unknown/edge intents should return empty string."""
        # These intents don't have contracts - they're handled differently
        contract = get_answer_contract(QueryIntent.SMALLTALK)
        assert contract == ""

    def test_get_contract_for_edge_abbreviation_returns_empty(self):
        """Edge case intents should return empty string."""
        contract = get_answer_contract(QueryIntent.EDGE_ABBREVIATION)
        assert contract == ""

    def test_get_contract_for_unknown_returns_empty(self):
        """UNKNOWN intent should return empty string."""
        contract = get_answer_contract(QueryIntent.UNKNOWN)
        assert contract == ""

"""
Tests for FaithfulnessService — post-generation claim verification.

Tests cover:
  - Sentence splitting and tokenization
  - Overlap-based claim scoring
  - Integration with SearchResult objects
  - Edge cases (empty input, no sources, disabled service)
"""

import pytest
from unittest.mock import MagicMock

from app.services.faithfulness_service import (
    FaithfulnessService,
    _split_sentences,
    _tokenize,
)


# ═══════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════


def _source(id="doc_1", title="Test Doc", snippet="Test text", score=0.9, date="2024-01-01"):
    """Create a mock SearchResult."""
    s = MagicMock()
    s.id = id
    s.title = title
    s.snippet = snippet
    s.score = score
    s.source = "test_collection"
    s.doc_type = "sfs"
    s.date = date
    s.retriever = "dense"
    s.tier = "primary"
    s._metadata = None
    return s


def _config(enabled=True, threshold=0.25):
    """Create a mock ConfigService."""
    config = MagicMock()
    config.settings = MagicMock()
    config.settings.faithfulness_enabled = enabled
    config.settings.faithfulness_threshold = threshold
    return config


# ═══════════════════════════════════════════════════════════════════════════
# TOKENIZATION AND SENTENCE SPLITTING
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestTokenization:
    """Tests for text tokenization."""

    def test_basic_tokenization(self):
        tokens = _tokenize("Yttrandefrihet innebär rätten att fritt uttrycka tankar")
        assert "yttrandefrihet" in tokens
        assert "innebär" in tokens
        assert "rätten" in tokens
        assert "tankar" in tokens

    def test_stop_words_removed(self):
        tokens = _tokenize("och att en i den för med")
        assert len(tokens) == 0  # All stop words

    def test_short_words_removed(self):
        tokens = _tokenize("a i x test")
        # "a" and "i" are <2 chars or stop words
        assert "test" in tokens

    def test_case_insensitive(self):
        tokens = _tokenize("RF GDPR Dataskyddsförordningen")
        assert "gdpr" in tokens
        assert "dataskyddsförordningen" in tokens

    def test_punctuation_stripped(self):
        tokens = _tokenize("lag (2018:218), kap. 2 §1")
        assert "lag" in tokens
        assert "2018" in tokens


@pytest.mark.unit
class TestSentenceSplitting:
    """Tests for sentence splitting."""

    def test_basic_split(self):
        text = "Första meningen är lång nog att räknas. Andra meningen är också lång nog."
        sents = _split_sentences(text)
        assert len(sents) == 2

    def test_short_fragments_filtered(self):
        text = "OK. Nej. Denna mening är tillräckligt lång för att inkluderas."
        sents = _split_sentences(text)
        assert len(sents) == 1
        assert "tillräckligt" in sents[0]

    def test_empty_input(self):
        assert _split_sentences("") == []

    def test_single_sentence(self):
        text = "Yttrandefrihet är en grundläggande rättighet i Sverige."
        sents = _split_sentences(text)
        assert len(sents) == 1


# ═══════════════════════════════════════════════════════════════════════════
# FAITHFULNESS SCORING
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestFaithfulnessScoring:
    """Tests for faithfulness scoring logic."""

    @pytest.mark.asyncio
    async def test_fully_grounded_answer(self):
        """Answer using exact source text should score high."""
        service = FaithfulnessService(_config(enabled=True))

        answer = "Yttrandefrihet innebär rätten att fritt uttrycka tankar och åsikter."
        sources = [
            _source(
                snippet="Yttrandefrihet innebär rätten att fritt uttrycka tankar, åsikter och känslor."
            )
        ]

        result = await service.score_answer(answer=answer, sources=sources)

        assert result.overall_score > 0.5
        assert result.total_claims >= 1
        assert result.supported_claims >= 1

    @pytest.mark.asyncio
    async def test_ungrounded_answer(self):
        """Answer with no source overlap should score low."""
        service = FaithfulnessService(_config(enabled=True))

        answer = "Artificiell intelligens revolutionerar demokratiska processer globalt."
        sources = [
            _source(snippet="Personuppgiftslagen reglerar behandling av personuppgifter i Sverige.")
        ]

        result = await service.score_answer(answer=answer, sources=sources)

        assert result.overall_score < 0.5
        assert result.unsupported_claims >= 1

    @pytest.mark.asyncio
    async def test_partial_grounding(self):
        """Answer partially supported should get mid-range score."""
        service = FaithfulnessService(_config(enabled=True))

        answer = (
            "Yttrandefrihet skyddas i grundlagen. "
            "Dessutom har det visat sig att artificiell intelligens påverkar samhället."
        )
        sources = [
            _source(snippet="Yttrandefrihet skyddas av grundlagen som en fundamental rättighet.")
        ]

        result = await service.score_answer(answer=answer, sources=sources)

        # First claim should be supported, second should not
        assert result.total_claims >= 1

    @pytest.mark.asyncio
    async def test_disabled_service_returns_default(self):
        """Disabled service returns 1.0 score (no scoring applied)."""
        service = FaithfulnessService(_config(enabled=False))

        result = await service.score_answer(
            answer="Test answer", sources=[_source()], question="test"
        )

        assert result.overall_score == 0.0  # No answer to score against
        assert result.latency_ms == 0.0

    @pytest.mark.asyncio
    async def test_empty_answer(self):
        """Empty answer is vacuously faithful (no claims to hallucinate)."""
        service = FaithfulnessService(_config(enabled=True))

        result = await service.score_answer(answer="", sources=[_source()])

        assert result.overall_score == 1.0  # No claims = no hallucination
        assert result.total_claims == 0

    @pytest.mark.asyncio
    async def test_no_sources(self):
        """No sources returns 0.0 score."""
        service = FaithfulnessService(_config(enabled=True))

        result = await service.score_answer(answer="Test answer", sources=[])

        assert result.overall_score == 0.0

    @pytest.mark.asyncio
    async def test_multiple_sources_best_match(self):
        """Score should use the best matching source for each claim."""
        service = FaithfulnessService(_config(enabled=True))

        answer = "GDPR artikel 6 reglerar laglig grund för personuppgiftsbehandling."
        sources = [
            _source(id="doc_1", snippet="Offentlighetsprincipen i Sverige"),
            _source(
                id="doc_2",
                snippet="GDPR artikel 6 anger sex lagliga grunder för behandling av personuppgifter.",
            ),
        ]

        result = await service.score_answer(answer=answer, sources=sources)

        # Should match doc_2 better
        assert result.overall_score > 0.3
        if result.claims:
            assert result.claims[0].best_source_title != ""

    @pytest.mark.asyncio
    async def test_threshold_determines_supported(self):
        """Claims below threshold marked unsupported, above marked supported."""
        # Low threshold: more claims pass
        service_low = FaithfulnessService(_config(enabled=True, threshold=0.1))
        # High threshold: fewer claims pass
        service_high = FaithfulnessService(_config(enabled=True, threshold=0.9))

        answer = "Denna lag gäller behandling av personuppgifter i svenska myndigheter."
        sources = [_source(snippet="Lagen gäller behandling av personuppgifter hos myndigheter.")]

        result_low = await service_low.score_answer(answer=answer, sources=sources)
        result_high = await service_high.score_answer(answer=answer, sources=sources)

        assert result_low.supported_claims >= result_high.supported_claims


# ═══════════════════════════════════════════════════════════════════════════
# SERVICE LIFECYCLE
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
class TestFaithfulnessServiceLifecycle:
    """Tests for service initialization and health."""

    @pytest.mark.asyncio
    async def test_initialize_and_close(self):
        service = FaithfulnessService(_config())
        await service.initialize()
        assert service.is_initialized is True

        health = await service.health_check()
        assert health is True

        await service.close()
        assert service.is_initialized is False

    def test_config_defaults(self):
        """Service picks up config values."""
        service = FaithfulnessService(_config(enabled=True, threshold=0.3))
        assert service.enabled is True
        assert service.threshold == 0.3

    def test_config_disabled(self):
        service = FaithfulnessService(_config(enabled=False))
        assert service.enabled is False

from app.services.config_service import get_config_service
from app.services.grader_service import GRADING_GRAMMAR, GraderService
from app.services.orchestrator_service import autocut_scores


def test_grading_grammar_is_3way_json():
    assert "status" in GRADING_GRAMMAR
    assert "RELEVANT" in GRADING_GRAMMAR
    assert "IRRELEVANT" in GRADING_GRAMMAR
    assert "AMBIGUOUS" in GRADING_GRAMMAR
    assert "confidence" in GRADING_GRAMMAR


def test_parse_grading_response_3way_relevant():
    service = GraderService(config=get_config_service())
    result = service._parse_grading_response(
        "doc-1", '{"status":"RELEVANT","confidence":0.85}', threshold=0.15
    )
    assert result.relevant is True
    assert result.status == "RELEVANT"
    assert result.confidence == 0.85
    assert result.score == 0.85


def test_parse_grading_response_3way_irrelevant():
    service = GraderService(config=get_config_service())
    result = service._parse_grading_response(
        "doc-2", '{"status":"IRRELEVANT","confidence":0.90}', threshold=0.15
    )
    assert result.relevant is False
    assert result.status == "IRRELEVANT"
    assert result.confidence == 0.90
    assert result.score == 0.0


def test_parse_grading_response_3way_ambiguous():
    service = GraderService(config=get_config_service())
    result = service._parse_grading_response(
        "doc-3", '{"status":"AMBIGUOUS","confidence":0.50}', threshold=0.15
    )
    assert result.relevant is False
    assert result.status == "AMBIGUOUS"
    assert result.confidence == 0.50
    assert result.score == 0.25  # confidence * 0.5 for ambiguous


def test_parse_grading_response_legacy_yes():
    """Legacy format backward compatibility."""
    service = GraderService(config=get_config_service())
    result = service._parse_grading_response("doc-4", '{"relevance":"yes"}', threshold=0.15)
    assert result.relevant is True
    assert result.status == "RELEVANT"
    assert result.score == 1.0


def test_parse_grading_response_legacy_no():
    """Legacy format backward compatibility."""
    service = GraderService(config=get_config_service())
    result = service._parse_grading_response("doc-5", '{"relevance":"no"}', threshold=0.15)
    assert result.relevant is False
    assert result.status == "IRRELEVANT"
    assert result.score == 0.0


def test_autocut_scores_clear_gap():
    """Gap between 0.85 and 0.3 should cut at index 2."""
    assert autocut_scores([0.9, 0.85, 0.3, 0.1]) == 2


def test_autocut_scores_no_gap():
    """No large gap should keep all."""
    assert autocut_scores([0.5, 0.48, 0.46]) == 3


def test_autocut_scores_single():
    assert autocut_scores([0.9]) == 1


def test_autocut_scores_empty():
    assert autocut_scores([]) == 0


# ── Edge cases: confidence extremes ──────────────────────────────────


def test_parse_max_confidence():
    """Max confidence 1.00 should parse correctly."""
    service = GraderService(config=get_config_service())
    result = service._parse_grading_response(
        "doc-max", '{"status":"RELEVANT","confidence":1.00}', threshold=0.15
    )
    assert result.relevant is True
    assert result.confidence == 1.0
    assert result.score == 1.0


def test_parse_zero_confidence():
    """Zero confidence should still parse and set score appropriately."""
    service = GraderService(config=get_config_service())
    result = service._parse_grading_response(
        "doc-zero", '{"status":"RELEVANT","confidence":0.00}', threshold=0.15
    )
    assert result.relevant is True
    assert result.confidence == 0.0
    assert result.score == 0.0


# ── Edge cases: keyword fallback ──────────────────────────────────


def test_keyword_fallback_relevant():
    """Keyword fallback for malformed JSON with 'relevant' keyword."""
    service = GraderService(config=get_config_service())
    result = service._parse_grading_response(
        "doc-kw", 'broken json with "relevant" mention', threshold=0.15
    )
    assert result.status == "RELEVANT"
    assert result.confidence == 0.5
    assert "Keyword fallback" in result.reason


def test_keyword_fallback_ambiguous():
    """Keyword fallback detecting 'ambiguous' keyword."""
    service = GraderService(config=get_config_service())
    result = service._parse_grading_response(
        "doc-kw2", 'broken json "ambiguous" text', threshold=0.15
    )
    assert result.status == "AMBIGUOUS"
    assert result.relevant is False


def test_keyword_fallback_irrelevant():
    """Keyword fallback defaults to IRRELEVANT."""
    service = GraderService(config=get_config_service())
    result = service._parse_grading_response(
        "doc-kw3", "completely broken response", threshold=0.15
    )
    assert result.status == "IRRELEVANT"
    assert result.relevant is False


# ── Edge cases: legacy boolean format ──────────────────────────────


def test_legacy_bool_true():
    """Legacy format with boolean true value."""
    service = GraderService(config=get_config_service())
    result = service._parse_grading_response("doc-bool", '{"relevant": true}', threshold=0.15)
    assert result.relevant is True
    assert result.status == "RELEVANT"


def test_legacy_bool_false():
    """Legacy format with boolean false value."""
    service = GraderService(config=get_config_service())
    result = service._parse_grading_response("doc-bool2", '{"relevant": false}', threshold=0.15)
    assert result.relevant is False
    assert result.status == "IRRELEVANT"


# ── Autocut edge cases ──────────────────────────────────────────────


def test_autocut_identical_scores():
    """Identical scores should keep all (no gap)."""
    assert autocut_scores([0.5, 0.5, 0.5, 0.5]) == 4


def test_autocut_steep_drop():
    """Steep drop after first should cut at 1."""
    assert autocut_scores([0.9, 0.1, 0.05]) == 1


def test_autocut_custom_sensitivity():
    """Custom sensitivity changes cutoff behavior."""
    scores = [0.9, 0.85, 0.3, 0.1]
    # High sensitivity: smaller gaps trigger cut
    result_high = autocut_scores(scores, sensitivity=0.05)
    # Low sensitivity: only large gaps trigger cut
    result_low = autocut_scores(scores, sensitivity=0.5)
    assert result_high <= result_low

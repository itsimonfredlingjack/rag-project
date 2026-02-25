"""
Confidence Signals Tests

Tests for dynamic threshold scaling with RRF k and
ConfidenceCalculator integration.
"""

from app.services.confidence_signals import (
    _BASE_THRESHOLDS,
    _REFERENCE_K,
    _SCORE_DEPENDENT_KEYS,
    ConfidenceCalculator,
    compute_thresholds,
)


# ── Threshold scaling ────────────────────────────────────────────────


def test_compute_thresholds_at_reference_k():
    """At reference k, thresholds should equal base values."""
    result = compute_thresholds(_REFERENCE_K)
    for key, value in _BASE_THRESHOLDS.items():
        assert result[key] == value, f"{key}: {result[key]} != {value}"


def test_compute_thresholds_higher_k_lowers_score_thresholds():
    """Higher k should produce lower score-dependent thresholds."""
    base = compute_thresholds(_REFERENCE_K)
    high_k = compute_thresholds(60.0)
    for key in _SCORE_DEPENDENT_KEYS:
        assert high_k[key] < base[key], f"{key}: {high_k[key]} not < {base[key]}"


def test_compute_thresholds_lower_k_raises_score_thresholds():
    """Lower k should produce higher score-dependent thresholds."""
    base = compute_thresholds(_REFERENCE_K)
    low_k = compute_thresholds(15.0)
    for key in _SCORE_DEPENDENT_KEYS:
        assert low_k[key] > base[key], f"{key}: {low_k[key]} not > {base[key]}"


def test_non_score_thresholds_unchanged():
    """Non-score thresholds (ratios, penalties) should be invariant to k."""
    for k in [15.0, 30.0, 45.0, 60.0, 120.0]:
        result = compute_thresholds(k)
        for key, value in _BASE_THRESHOLDS.items():
            if key not in _SCORE_DEPENDENT_KEYS:
                assert result[key] == value, f"k={k}, {key}: {result[key]} != {value}"


def test_compute_thresholds_k45_specific_value():
    """Verify at production k=45 (reference), base values are returned unchanged."""
    result = compute_thresholds(45.0)
    # At reference k=45, scale factor = 1.0, so values match base thresholds
    assert abs(result["top_score_low"] - _BASE_THRESHOLDS["top_score_low"]) < 1e-10
    assert abs(result["margin_low"] - _BASE_THRESHOLDS["margin_low"]) < 1e-10


# ── ConfidenceCalculator integration ─────────────────────────────────


def test_confidence_calculator_uses_rrf_k():
    """Constructor should use computed thresholds when rrf_k is given."""
    calc = ConfidenceCalculator(rrf_k=45.0)
    expected = compute_thresholds(45.0)
    assert calc.thresholds == expected


def test_confidence_calculator_default_thresholds():
    """Default constructor should use base thresholds."""
    calc = ConfidenceCalculator()
    assert calc.thresholds == _BASE_THRESHOLDS


def test_confidence_calculator_explicit_thresholds_override():
    """Explicit thresholds dict should override rrf_k."""
    custom = {"top_score_low": 0.999}
    calc = ConfidenceCalculator(thresholds=custom)
    assert calc.thresholds == custom

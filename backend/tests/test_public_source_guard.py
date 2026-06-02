"""Tests for the public Riksdagen source-scope guard."""

from __future__ import annotations

import pytest

from app.shared.public_source_guard import (
    PUBLIC_SOURCE,
    PUBLIC_SOURCE_SCOPE,
    PublicSourceGuardError,
    validate_public_record,
)


def test_validate_public_record_accepts_riksdagen_scope() -> None:
    validate_public_record(
        {
            "id": "H803222",
            "source": PUBLIC_SOURCE,
            "source_scope": PUBLIC_SOURCE_SCOPE,
            "title": "Proposition 2020/21:222",
            "metadata": {"source": PUBLIC_SOURCE, "source_scope": PUBLIC_SOURCE_SCOPE},
        },
        stage="splitter",
    )


def test_validate_public_record_allows_lowercase_fulltext_word() -> None:
    validate_public_record(
        {
            "id": "H501KU10",
            "source": PUBLIC_SOURCE,
            "source_scope": PUBLIC_SOURCE_SCOPE,
            "text": "För fulltexten, se pdf:en.",
        },
        stage="splitter",
    )


def test_validate_public_record_allows_diva_substring_inside_public_text() -> None:
    validate_public_record(
        {
            "id": "H811193",
            "source": PUBLIC_SOURCE,
            "source_scope": PUBLIC_SOURCE_SCOPE,
            "text": "Scandivanadium börjar bryta vanadin i Skåne.",
        },
        stage="splitter",
    )


@pytest.mark.parametrize(
    ("record", "expected"),
    [
        ({"id": "x", "source": "diva", "source_scope": PUBLIC_SOURCE_SCOPE}, "FORBIDDEN_SOURCE"),
        (
            {"id": "x", "source": PUBLIC_SOURCE, "source_scope": "mixed_recovered_corpus"},
            "INVALID_SCOPE",
        ),
        (
            {
                "id": "x",
                "source": PUBLIC_SOURCE,
                "source_scope": PUBLIC_SOURCE_SCOPE,
                "text": "Detta innehåller diva2:12345",
            },
            "FORBIDDEN_MARKER",
        ),
        (
            {
                "id": "x",
                "source": PUBLIC_SOURCE,
                "source_scope": PUBLIC_SOURCE_SCOPE,
                "metadata": {"path": "/tmp/private_pdf/source.pdf"},
            },
            "FORBIDDEN_MARKER",
        ),
    ],
)
def test_validate_public_record_rejects_non_public_records(record: dict, expected: str) -> None:
    with pytest.raises(PublicSourceGuardError, match=expected) as exc_info:
        validate_public_record(record, stage="splitter")

    message = str(exc_info.value)
    assert "stage=splitter" in message
    assert "id=x" in message

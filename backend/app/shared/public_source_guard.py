"""Shared source-scope guard for the public Riksdagen corpus."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

PUBLIC_PROFILE = "public-riksdag-demo"
PUBLIC_SOURCE = "riksdagen"
PUBLIC_SOURCE_SCOPE = "riksdagen_open_data_only"
FORBIDDEN_SUBSTRINGS = (
    ("FULLTEXT", True),
    ("private_pdf", False),
    ("mixed_recovered_corpus", False),
    ("private source", False),
    ("private_source", False),
    ("source=private", False),
)
FORBIDDEN_PATTERNS = (
    ("diva", re.compile(r"(?<![a-zåäö0-9])diva(?![a-zåäö0-9])", re.IGNORECASE)),
    ("diva2:", re.compile(r"diva2:", re.IGNORECASE)),
)


class PublicSourceGuardError(ValueError):
    """Raised when a public corpus record violates source-scope constraints."""


def _flatten_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        flattened: list[str] = []
        for key, nested in value.items():
            flattened.extend(_flatten_values(key))
            flattened.extend(_flatten_values(nested))
        return flattened
    if isinstance(value, (list, tuple, set)):
        flattened = []
        for item in value:
            flattened.extend(_flatten_values(item))
        return flattened
    return [str(value)]


def _record_id(record: Mapping[str, Any]) -> str:
    value = record.get("id") or record.get("document_id") or record.get("doc_id") or "unknown"
    return str(value)


def _fail(code: str, *, stage: str, record: Mapping[str, Any], detail: str) -> None:
    source = record.get("source", "unknown")
    scope = record.get("source_scope", "unknown")
    raise PublicSourceGuardError(
        f"PUBLIC_SOURCE_GUARD_{code} stage={stage} id={_record_id(record)} "
        f"source={source} source_scope={scope} {detail}"
    )


def is_public_profile(config_or_profile: Any) -> bool:
    """Return true when a config/profile object is the public Riksdagen runtime profile."""
    value = config_or_profile
    if not isinstance(value, str):
        value = getattr(config_or_profile, "profile", None)
    if value is None and hasattr(config_or_profile, "settings"):
        value = getattr(config_or_profile.settings, "profile", None)
    return str(value or "").strip() == PUBLIC_PROFILE


def public_guard_payload(record: Any) -> dict[str, Any]:
    """Convert mapping or dataclass-like retrieval records into guardable payloads."""
    if isinstance(record, Mapping):
        payload = dict(record)
    else:
        payload = {
            key: getattr(record, key)
            for key in (
                "id",
                "document_id",
                "source",
                "source_scope",
                "title",
                "date",
                "url",
                "text",
                "snippet",
                "metadata",
                "retriever",
                "retriever_source",
            )
            if hasattr(record, key)
        }

    metadata = payload.get("metadata")
    if isinstance(metadata, Mapping):
        payload.setdefault("source", metadata.get("source"))
        payload.setdefault("source_scope", metadata.get("source_scope"))
        payload.setdefault("document_id", metadata.get("document_id"))

    return payload


def validate_public_record(record: Any, *, stage: str) -> None:
    """Validate one public Riksdagen record and raise a clear error on leakage."""
    record = public_guard_payload(record)
    source = str(record.get("source", "")).strip()
    if source != PUBLIC_SOURCE:
        _fail("FORBIDDEN_SOURCE", stage=stage, record=record, detail=f"forbidden_source={source}")

    scope = str(record.get("source_scope", "")).strip()
    if scope != PUBLIC_SOURCE_SCOPE:
        _fail("INVALID_SCOPE", stage=stage, record=record, detail=f"invalid_scope={scope}")

    searchable = "\n".join(_flatten_values(record))
    searchable_casefolded = searchable.casefold()
    for marker, pattern in FORBIDDEN_PATTERNS:
        if pattern.search(searchable):
            _fail("FORBIDDEN_MARKER", stage=stage, record=record, detail=f"marker={marker}")

    for marker, case_sensitive in FORBIDDEN_SUBSTRINGS:
        haystack = searchable if case_sensitive else searchable_casefolded
        needle = marker if case_sensitive else marker.casefold()
        if needle in haystack:
            _fail("FORBIDDEN_MARKER", stage=stage, record=record, detail=f"marker={marker}")


def validate_public_record_if_enabled(record: Any, *, stage: str, enabled: bool) -> None:
    """Validate a record only when public mode is active."""
    if enabled:
        validate_public_record(record, stage=stage)


def validate_public_records(
    records: list[Any] | tuple[Any, ...],
    *,
    stage: str,
    enabled: bool,
) -> None:
    """Validate multiple records only when public mode is active."""
    if not enabled:
        return
    for record in records:
        validate_public_record(record, stage=stage)

"""Model policy tests for runtime LLM configuration."""

import pytest
from pydantic import ValidationError

from app.services.config_service import ConfigSettings


def test_runtime_model_policy_rejects_excluded_model_families():
    with pytest.raises(ValidationError, match="excluded by repo model policy"):
        ConfigSettings(
            constitutional_model="qwen3.5:4b-q4_K_M",
            constitutional_fallback="gemma4:e2b",
            crag_grader_model="gemma4:e2b",
            gguf_primary_model="gemma4:e2b",
        )


def test_runtime_model_policy_allows_gemma4_default_family():
    settings = ConfigSettings(
        constitutional_model="gemma4:e2b",
        constitutional_fallback="gemma4:e2b",
        crag_grader_model="gemma4:e2b",
        gguf_primary_model="gemma4:e2b",
    )

    assert settings.constitutional_model == "gemma4:e2b"


def test_svensk_ragg_model_env_aliases_are_supported(monkeypatch):
    monkeypatch.setenv("CONST_SVENSK_RAGG_MODEL", "gemma3:4b")
    monkeypatch.setenv("CONST_SVENSK_RAGG_FALLBACK", "gemma3:4b")

    settings = ConfigSettings(_env_file=None)

    assert settings.constitutional_model == "gemma3:4b"
    assert settings.constitutional_fallback == "gemma3:4b"

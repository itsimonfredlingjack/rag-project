"""
Application configuration for Svensk Ragg Backend
Environment variables and settings
"""

from functools import lru_cache
from typing import ClassVar, Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings with environment variable support"""

    PUBLIC_PROFILE: ClassVar[str] = "public-riksdag-demo"

    # Application
    app_name: str = "Svensk Ragg Backend"
    app_version: str = "2.0.0"
    debug: bool = False
    profile: str = "private-swedish-legal-lab"
    api_docs_enabled: Optional[bool] = None
    operator_routes_enabled: Optional[bool] = None
    legacy_sse_enabled: Optional[bool] = None
    harvest_ws_enabled: Optional[bool] = None

    # Server
    host: str = "0.0.0.0"
    port: int = 8900

    # LLM (Ollama)
    llm_base_url: str = "http://localhost:11434"

    # Ollama (local)
    ollama_base_url: str = "http://localhost:11434"
    ollama_timeout_seconds: int = 120

    # CRAG (Corrective RAG) Settings
    # Maps to CONST_CRAG_ENABLED and CONST_CRAG_ENABLE_SELF_REFLECTION
    crag_enabled: bool = False
    crag_enable_self_reflection: bool = False
    crag_grade_threshold: float = 0.15

    # CORS - explicit origins needed when allow_credentials=True
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://localhost:5175",
        "http://127.0.0.1:5175",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
        "http://localhost:3002",
        "http://127.0.0.1:3002",
        "http://localhost:3003",
        "http://127.0.0.1:3003",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ]
    cors_allow_credentials: bool = True

    # Logging
    log_level: str = "INFO"
    log_json: bool = False
    log_file: Optional[str] = None

    # WebSocket
    ws_heartbeat_interval: int = 30
    ws_max_message_size: int = 65536

    model_config = {
        "env_prefix": "CONST_",
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

    @property
    def is_public_profile(self) -> bool:
        return self.profile.strip() == self.PUBLIC_PROFILE

    @property
    def api_docs_exposed(self) -> bool:
        if self.api_docs_enabled is not None:
            return self.api_docs_enabled
        return not self.is_public_profile

    @property
    def local_operator_routes_exposed(self) -> bool:
        if self.operator_routes_enabled is not None:
            return self.operator_routes_enabled
        return not self.is_public_profile

    @property
    def legacy_sse_exposed(self) -> bool:
        if self.legacy_sse_enabled is not None:
            return self.legacy_sse_enabled
        return self.local_operator_routes_exposed

    @property
    def harvest_ws_exposed(self) -> bool:
        if self.harvest_ws_enabled is not None:
            return self.harvest_ws_enabled
        return self.local_operator_routes_exposed


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()


# Convenience exports
settings = get_settings()

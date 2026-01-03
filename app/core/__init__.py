"""
Core Module - Configuration, Exceptions, Error Handlers
"""

from ..config import Settings as ConfigSettings
from .exceptions import (
    ConstitutionalAIError,
    ResourceNotFoundError,
    ConfigurationError,
    LLMTimeoutError,
    LLMConnectionError,
    LLMModelNotFoundError,
    EmbeddingError,
    RetrievalError,
    QueryClassificationError,
    SecurityViolationError,
    ValidationError,
    RerankingError,
    ServiceNotInitializedError,
)
from .error_handlers import (
    constitutional_exception_handler,
    register_exception_handlers,
)

__all__ = [
    # Config
    "ConfigSettings",
    
    # Exceptions
    "ConstitutionalAIError",
    "ResourceNotFoundError",
    "ConfigurationError",
    "LLMTimeoutError",
    "LLMConnectionError",
    "LLMModelNotFoundError",
    "EmbeddingError",
    "RetrievalError",
    "QueryClassificationError",
    "SecurityViolationError",
    "ValidationError",
    "RerankingError",
    "ServiceNotInitializedError",
    
    # Error Handlers
    "constitutional_exception_handler",
    "register_exception_handlers",
]


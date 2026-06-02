"""API key authentication for write operations."""

import hmac
import os
from typing import Optional

from fastapi import Header, HTTPException, status

PUBLIC_PROFILE = "public-riksdag-demo"
PRIVATE_PROFILE = "private-swedish-legal-lab"
TRUE_VALUES = {"1", "true", "yes", "on"}


def _get_configured_api_key() -> Optional[str]:
    """Get the configured API key from environment."""
    api_key = os.environ.get("CONST_API_KEY", "").strip()
    return api_key or None


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in TRUE_VALUES


def _current_profile() -> str:
    return os.environ.get("CONST_PROFILE", PRIVATE_PROFILE).strip() or PRIVATE_PROFILE


async def require_write_access(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
) -> Optional[str]:
    """
    Dependency that requires a valid API key for write operations.

    Write access is fail-closed by default. Unauthenticated writes are only
    allowed for non-public local development when explicitly enabled with
    CONST_ALLOW_UNAUTHENTICATED_WRITES=true.
    """
    profile = _current_profile()
    if profile == PUBLIC_PROFILE:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Document writes are disabled in the public demo profile.",
        )

    configured_key = _get_configured_api_key()

    if configured_key is None:
        if _env_truthy("CONST_ALLOW_UNAUTHENTICATED_WRITES"):
            return None
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Document writes require CONST_API_KEY. Set "
                "CONST_ALLOW_UNAUTHENTICATED_WRITES=true only for local non-public development."
            ),
        )

    if not x_api_key or not hmac.compare_digest(x_api_key, configured_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key. Provide X-API-Key header.",
        )

    return x_api_key

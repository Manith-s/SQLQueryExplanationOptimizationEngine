"""
Authentication module for API key verification.

Provides Bearer token authentication using API keys configured via environment variables.
"""

from typing import Optional
from fastapi import HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.core.config import settings

# Create security scheme for Bearer tokens (auto_error=False makes it optional)
security = HTTPBearer(auto_error=False)


def verify_token(credentials: Optional[HTTPAuthorizationCredentials] = Security(security)) -> str:
    """
    Verify the Bearer token against the configured API key.

    Args:
        credentials: HTTPAuthorizationCredentials from the security dependency

    Returns:
        The verified token string

    Raises:
        HTTPException: 403 Forbidden if token is invalid or missing when auth is enabled
    """
    if not settings.AUTH_ENABLED:
        # If auth is disabled, allow all requests
        return "auth-disabled"

    # Auth is enabled, check credentials
    if credentials is None:
        raise HTTPException(
            status_code=403,
            detail="Authentication required. Please provide a Bearer token."
        )

    token = credentials.credentials

    if token != settings.API_KEY:
        raise HTTPException(
            status_code=403,
            detail="Invalid API key. Please provide a valid Bearer token."
        )

    return token


def get_optional_token(credentials: HTTPAuthorizationCredentials = Security(security)) -> str | None:
    """
    Get token if provided, but don't fail if missing (for optional auth).

    Args:
        credentials: HTTPAuthorizationCredentials from the security dependency

    Returns:
        The token string if valid, None otherwise
    """
    try:
        return verify_token(credentials)
    except HTTPException:
        return None

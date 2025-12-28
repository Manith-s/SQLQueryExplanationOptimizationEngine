"""
Security middleware and utilities for QEO.

Provides:
- Security headers
- Request logging with sanitization
- CORS configuration
"""

import logging
import time
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.core.validation import sanitize_error_message, sanitize_sql_for_logging

logger = logging.getLogger(__name__)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware to add security headers to all responses."""

    def __init__(self, app: ASGIApp, enable: bool = True):
        """
        Initialize security headers middleware.

        Args:
            app: ASGI application
            enable: Enable security headers (default: True)
        """
        super().__init__(app)
        self.enable = enable

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Add security headers to response."""
        response = await call_next(request)

        if self.enable:
            # Security headers from production.py
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["X-XSS-Protection"] = "1; mode=block"
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
            response.headers["Content-Security-Policy"] = "default-src 'self'"

            # Additional security headers
            response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
            response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"

        return response


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware to log requests with sanitization."""

    def __init__(self, app: ASGIApp, enable: bool = True):
        """
        Initialize request logging middleware.

        Args:
            app: ASGI application
            enable: Enable request logging (default: True)
        """
        super().__init__(app)
        self.enable = enable

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Log request and response with sanitization."""
        if not self.enable:
            return await call_next(request)

        start_time = time.time()

        # Extract request info
        method = request.method
        path = request.url.path
        client_ip = request.client.host if request.client else "unknown"

        # Get user agent
        user_agent = request.headers.get("user-agent", "unknown")

        # Process request
        try:
            response = await call_next(request)
            duration_ms = (time.time() - start_time) * 1000

            # Log successful request
            logger.info(
                f"{method} {path} - {response.status_code} - "
                f"{duration_ms:.2f}ms - IP: {client_ip} - UA: {user_agent[:50]}"
            )

            # Add response time header
            response.headers["X-Response-Time"] = f"{duration_ms:.2f}ms"

            return response

        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000

            # Sanitize error message
            error_msg = sanitize_error_message(str(e))

            # Log error
            logger.error(
                f"{method} {path} - ERROR - "
                f"{duration_ms:.2f}ms - IP: {client_ip} - Error: {error_msg}"
            )

            # Re-raise exception
            raise


def get_cors_config(allowed_origins: list = None) -> dict:
    """
    Get CORS configuration.

    Args:
        allowed_origins: List of allowed origins (None for default)

    Returns:
        CORS configuration dictionary
    """
    from app.core.production import ProductionSettings

    # Use production settings if no custom origins provided
    if allowed_origins is None:
        allowed_origins = ProductionSettings.CORS_ORIGINS

    # If empty or contains wildcard, allow all (development only)
    if not allowed_origins or "*" in allowed_origins:
        allow_all = True
        origins = ["*"]
    else:
        allow_all = False
        origins = allowed_origins

    return {
        "allow_origins": origins,
        "allow_credentials": not allow_all,  # Can't use credentials with wildcard
        "allow_methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["*"] if allow_all else [
            "Authorization",
            "Content-Type",
            "Accept",
            "Origin",
            "User-Agent",
            "DNT",
            "Cache-Control",
            "X-Requested-With"
        ],
        "expose_headers": [
            "X-RateLimit-Limit",
            "X-RateLimit-Remaining",
            "X-RateLimit-Reset",
            "X-Response-Time"
        ],
        "max_age": 600  # 10 minutes
    }


def log_api_request(method: str, path: str, sql: str = None, **kwargs) -> None:
    """
    Log API request with sanitization.

    Args:
        method: HTTP method
        path: Request path
        sql: SQL query (will be sanitized)
        **kwargs: Additional parameters to log
    """
    # Sanitize SQL if provided
    if sql:
        sql = sanitize_sql_for_logging(sql)

    # Build log message
    parts = [f"{method} {path}"]

    if sql:
        parts.append(f"SQL: {sql}")

    for key, value in kwargs.items():
        # Skip sensitive fields
        if key.lower() in ["password", "token", "key", "secret"]:
            value = "[REDACTED]"
        parts.append(f"{key}: {value}")

    logger.info(" | ".join(parts))


def validate_origin(origin: str, allowed_origins: list) -> bool:
    """
    Validate if origin is allowed.

    Args:
        origin: Request origin
        allowed_origins: List of allowed origins

    Returns:
        True if allowed, False otherwise
    """
    if not origin:
        return False

    # Wildcard allows all
    if "*" in allowed_origins:
        return True

    # Exact match
    if origin in allowed_origins:
        return True

    # Pattern matching (e.g., *.example.com)
    for allowed in allowed_origins:
        if allowed.startswith("*."):
            domain = allowed[2:]
            if origin.endswith(domain):
                return True

    return False

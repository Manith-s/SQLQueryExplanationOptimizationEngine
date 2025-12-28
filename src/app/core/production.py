"""
Production configuration and settings.

This module provides production-ready configurations for security,
performance, and logging.
"""

import logging
import os
from typing import Any, Dict, List


class ProductionSettings:
    """Production-specific settings and configurations."""

    # Security settings
    ALLOWED_HOSTS: List[str] = os.getenv("ALLOWED_HOSTS", "*").split(",")
    CORS_ORIGINS: List[str] = os.getenv("CORS_ORIGINS", "").split(",") if os.getenv("CORS_ORIGINS") else []
    SECURE_HEADERS: bool = os.getenv("SECURE_HEADERS", "true").lower() == "true"

    # Performance settings
    DB_POOL_SIZE: int = int(os.getenv("DB_POOL_SIZE", "10"))
    DB_MAX_OVERFLOW: int = int(os.getenv("DB_MAX_OVERFLOW", "20"))
    REQUEST_TIMEOUT_SECONDS: int = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "30"))
    WORKER_COUNT: int = int(os.getenv("WORKER_COUNT", "4"))

    # Rate limiting
    RATE_LIMIT_STORAGE: str = os.getenv("RATE_LIMIT_STORAGE", "memory://")
    RATE_LIMIT_STRATEGY: str = os.getenv("RATE_LIMIT_STRATEGY", "fixed-window")

    # Logging
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FORMAT: str = os.getenv(
        "LOG_FORMAT",
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    LOG_JSON: bool = os.getenv("LOG_JSON", "false").lower() == "true"

    # Monitoring
    SENTRY_DSN: str = os.getenv("SENTRY_DSN", "")
    ENABLE_PROFILING: bool = os.getenv("ENABLE_PROFILING", "false").lower() == "true"


def get_security_headers() -> Dict[str, str]:
    """
    Get security headers for production deployment.

    Returns:
        Dictionary of security headers
    """
    headers = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "X-XSS-Protection": "1; mode=block",
        "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
        "Content-Security-Policy": "default-src 'self'",
    }
    return headers


def configure_logging() -> None:
    """Configure production logging settings."""
    logging.basicConfig(
        level=getattr(logging, ProductionSettings.LOG_LEVEL),
        format=ProductionSettings.LOG_FORMAT,
    )

    # Configure specific loggers
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("fastapi").setLevel(logging.INFO)


def get_cors_config() -> Dict[str, Any]:
    """
    Get CORS configuration for production.

    Returns:
        Dictionary of CORS settings
    """
    if ProductionSettings.CORS_ORIGINS and ProductionSettings.CORS_ORIGINS[0]:
        origins = ProductionSettings.CORS_ORIGINS
    else:
        origins = ["*"]

    return {
        "allow_origins": origins,
        "allow_credentials": True,
        "allow_methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["*"],
        "expose_headers": ["X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset"],
    }


def get_database_config() -> Dict[str, Any]:
    """
    Get database configuration for production.

    Returns:
        Dictionary of database pool settings
    """
    return {
        "pool_size": ProductionSettings.DB_POOL_SIZE,
        "max_overflow": ProductionSettings.DB_MAX_OVERFLOW,
        "pool_pre_ping": True,
        "pool_recycle": 3600,  # Recycle connections after 1 hour
    }

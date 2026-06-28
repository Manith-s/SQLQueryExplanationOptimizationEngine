"""
Health check router.

Provides basic health and status endpoints.
"""

from fastapi import APIRouter

from app import __version__
from app.core import db

router = APIRouter()


@router.get("/health")
async def health_check():
    """Health endpoint reporting service status, version, and dependencies."""
    database = "unavailable"
    hypopg = "unavailable"
    try:
        rows = db.run_sql("SELECT 1", timeout_ms=500)
        if rows and rows[0][0] == 1:
            database = "connected"
        try:
            ext = db.run_sql(
                "SELECT 1 FROM pg_extension WHERE extname = 'hypopg'",
                timeout_ms=500,
            )
            hypopg = "available" if ext else "not_installed"
        except Exception:
            hypopg = "not_installed"
    except Exception:
        database = "unavailable"

    # The service itself is up and serving requests; dependency status is
    # reported separately so callers can decide readiness.
    return {
        "status": "healthy",
        "version": __version__,
        "database": database,
        "hypopg": hypopg,
    }


@router.get("/livez")
async def livez():
    """Liveness probe: process is up."""
    return {"status": "alive"}


@router.get("/healthz")
async def healthz():
    """Readiness probe: DB reachable with short timeout."""
    try:
        rows = db.run_sql("SELECT 1", timeout_ms=500)
        ok = bool(rows and rows[0][0] == 1)
        return {"status": "ok" if ok else "degraded"}
    except Exception:
        return {"status": "degraded"}

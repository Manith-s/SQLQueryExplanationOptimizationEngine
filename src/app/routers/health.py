"""
Health check router.

Provides basic health and status endpoints.
"""

from fastapi import APIRouter

from app.core import db

router = APIRouter()


@router.get("/health")
async def health_check():
    """Back-compat simple health endpoint."""
    return {"status": "ok"}


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

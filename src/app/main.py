"""
FastAPI application entry point.

Mounts routers and provides minimal health route.
"""

from fastapi import FastAPI, Request, Response, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import time
import os
from pathlib import Path
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.routers import health, lint, explain, optimize, schema
from app.routers import workload
from app.core.metrics import init_metrics, observe_request, metrics_exposition
from app.core.auth import verify_token

app = FastAPI(
    title="SQL Query Explanation & Optimization Engine",
    description="A local, offline-capable tool for SQL analysis, explanation, and optimization",
    version="0.7.0",
)

# CORS middleware for development
from app.core.config import settings

# Configure rate limiter
limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])
app.state.limiter = limiter

# Custom rate limit exceeded handler with headers
@app.exception_handler(RateLimitExceeded)
async def custom_rate_limit_handler(request: Request, exc: RateLimitExceeded):
    """Custom handler for rate limit exceeded errors that adds helpful headers."""
    return Response(
        content='{"detail": "Rate limit exceeded. Please try again later."}',
        status_code=429,
        headers={
            "Content-Type": "application/json",
            "X-RateLimit-Limit": str(exc.detail.split()[0]) if exc.detail else "Unknown",
            "X-RateLimit-Reset": "60",  # seconds
            "Retry-After": "60"
        }
    )

allow_origins = (settings.__dict__.get("CORS_ALLOW_ORIGINS") or "*").split(",") if hasattr(settings, "CORS_ALLOW_ORIGINS") else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add SlowAPI middleware for rate limit headers
app.add_middleware(SlowAPIMiddleware)


@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    start = time.time()
    rid = request.headers.get("x-request-id", str(int(start * 1000000)))
    try:
        response = await call_next(request)
        duration_ms = int((time.time() - start) * 1000)
        try:
            route_tmpl = request.scope.get("route").path  # type: ignore[attr-defined]
        except Exception:
            route_tmpl = request.url.path
        try:
            observe_request(route_tmpl, request.method, response.status_code, duration_ms / 1000.0)
        except Exception:
            pass
        print(
            {
                "lvl": "info",
                "rid": rid,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "dur_ms": duration_ms,
            }
        )
        return response
    except Exception as e:
        duration_ms = int((time.time() - start) * 1000)
        print(
            {
                "lvl": "error",
                "rid": rid,
                "method": request.method,
                "path": request.url.path,
                "error": str(e),
                "dur_ms": duration_ms,
            }
        )
        raise

# Initialize metrics once on startup
init_metrics()


@app.get("/metrics")
async def metrics():
    if not settings.METRICS_ENABLED:
        return Response(status_code=404)
    data, content_type = metrics_exposition()
    return Response(content=data, media_type=content_type)

# Mount routers
# Health endpoint is public (no auth required)
app.include_router(health.router, tags=["health"])

# Apply authentication to all API routes (verify_token checks AUTH_ENABLED dynamically)
app.include_router(lint.router, prefix="/api/v1", tags=["lint"], dependencies=[Depends(verify_token)])
app.include_router(explain.router, prefix="/api/v1", tags=["explain"], dependencies=[Depends(verify_token)])
app.include_router(optimize.router, prefix="/api/v1", tags=["optimize"], dependencies=[Depends(verify_token)])
app.include_router(schema.router, prefix="/api/v1", tags=["schema"], dependencies=[Depends(verify_token)])
app.include_router(workload.router, prefix="/api/v1", tags=["workload"], dependencies=[Depends(verify_token)])


@app.get("/")
async def root():
    """Serve the web UI."""
    static_dir = Path(__file__).parent / "static"
    index_file = static_dir / "index.html"

    # If web UI exists, serve it, otherwise return API info
    if index_file.exists():
        return FileResponse(index_file)
    else:
        return {
            "name": "SQL Query Explanation & Optimization Engine",
            "version": "0.7.0",
            "status": "running",
            "docs": "/docs",
            "ui": "Web UI not found. Access API docs at /docs"
        }


@app.get("/api")
async def api_info():
    """API information endpoint."""
    return {
        "name": "SQL Query Explanation & Optimization Engine",
        "version": "0.7.0",
        "status": "running",
        "docs": "/docs"
    }


# Mount static files for the web UI
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


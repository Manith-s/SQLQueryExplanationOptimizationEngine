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
from app.routers import workload, profile, catalog, index, cache, correct
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


# Startup and shutdown events for profiler background tasks
@app.on_event("startup")
async def startup_event():
    """Start background tasks on application startup."""
    if settings.PROFILER_ENABLED:
        from app.core.profiler_tasks import get_background_tasks
        tasks = get_background_tasks()
        await tasks.start()
        print({"lvl": "info", "msg": "Profiler background tasks started"})


@app.on_event("shutdown")
async def shutdown_event():
    """Stop background tasks on application shutdown."""
    if settings.PROFILER_ENABLED:
        from app.core.profiler_tasks import get_background_tasks
        tasks = get_background_tasks()
        await tasks.stop()
        print({"lvl": "info", "msg": "Profiler background tasks stopped"})


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
app.include_router(correct.router, prefix="/api/v1", tags=["correct"], dependencies=[Depends(verify_token)])
app.include_router(explain.router, prefix="/api/v1", tags=["explain"], dependencies=[Depends(verify_token)])
app.include_router(optimize.router, prefix="/api/v1", tags=["optimize"], dependencies=[Depends(verify_token)])
app.include_router(schema.router, prefix="/api/v1", tags=["schema"], dependencies=[Depends(verify_token)])
app.include_router(workload.router, prefix="/api/v1", tags=["workload"], dependencies=[Depends(verify_token)])

# Profiler router (conditionally enabled)
if settings.PROFILER_ENABLED:
    app.include_router(profile.router, tags=["profiler"], dependencies=[Depends(verify_token)])

# Catalog and query builder router
app.include_router(catalog.router, tags=["catalog"], dependencies=[Depends(verify_token)])

# Index management and self-healing router
app.include_router(index.router, tags=["index-management"], dependencies=[Depends(verify_token)])

# Cache management router
app.include_router(cache.router, tags=["cache"], dependencies=[Depends(verify_token)])


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


@app.get("/profiler")
async def profiler_ui():
    """Serve the profiler dashboard UI."""
    if not settings.PROFILER_ENABLED:
        return Response(
            content='{"detail": "Profiler is disabled"}',
            status_code=503,
            media_type="application/json"
        )

    static_dir = Path(__file__).parent / "static"
    profiler_file = static_dir / "profiler.html"

    if profiler_file.exists():
        return FileResponse(profiler_file)
    else:
        return Response(
            content='{"detail": "Profiler UI not found"}',
            status_code=404,
            media_type="application/json"
        )


@app.get("/query-builder")
async def query_builder_ui():
    """Serve the visual query builder UI."""
    static_dir = Path(__file__).parent / "static"
    builder_file = static_dir / "query-builder.html"

    if builder_file.exists():
        return FileResponse(builder_file)
    else:
        return Response(
            content='{"detail": "Query Builder UI not found"}',
            status_code=404,
            media_type="application/json"
        )


@app.get("/plan-visualizer")
async def plan_visualizer_ui():
    """Serve the execution plan visualizer UI."""
    static_dir = Path(__file__).parent / "static"
    viz_file = static_dir / "plan-visualizer.html"

    if viz_file.exists():
        return FileResponse(viz_file)
    else:
        return Response(
            content='{"detail": "Plan Visualizer UI not found"}',
            status_code=404,
            media_type="application/json"
        )


@app.get("/api")
async def api_info():
    """API information endpoint."""
    return {
        "name": "SQL Query Explanation & Optimization Engine",
        "version": "0.7.0",
        "status": "running",
        "docs": "/docs",
        "uis": {
            "main": "/",
            "query_builder": "/query-builder",
            "plan_visualizer": "/plan-visualizer",
            "profiler": "/profiler" if settings.PROFILER_ENABLED else None
        }
    }


# Mount static files for the web UI
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


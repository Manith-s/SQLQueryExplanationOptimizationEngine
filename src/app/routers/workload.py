import hashlib
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field, conint

from app.core.workload import analyze_workload

router = APIRouter()

# Simple in-memory cache with TTL
_workload_cache: Dict[str, Dict[str, Any]] = {}
_cache_timestamps: Dict[str, float] = {}
_CACHE_TTL_SECONDS = 300  # 5 minutes


def _get_cache_key(sqls: List[str], top_k: int, what_if: bool) -> str:
    """Generate a cache key from the request parameters."""
    content = f"{','.join(sorted(sqls))}:{top_k}:{what_if}"
    return hashlib.md5(content.encode()).hexdigest()


def _get_cached_result(cache_key: str) -> Optional[Dict[str, Any]]:
    """Retrieve cached result if still valid."""
    if cache_key in _workload_cache:
        timestamp = _cache_timestamps.get(cache_key, 0)
        if time.time() - timestamp < _CACHE_TTL_SECONDS:
            return _workload_cache[cache_key]
        else:
            # Expired, remove from cache
            _workload_cache.pop(cache_key, None)
            _cache_timestamps.pop(cache_key, None)
    return None


def _cache_result(cache_key: str, result: Dict[str, Any]) -> None:
    """Cache the analysis result."""
    _workload_cache[cache_key] = result
    _cache_timestamps[cache_key] = time.time()

    # Simple cache size limit (keep only last 50 entries)
    if len(_workload_cache) > 50:
        # Remove oldest entries
        oldest_keys = sorted(
            _cache_timestamps.keys(), key=lambda k: _cache_timestamps[k]
        )[:10]
        for key in oldest_keys:
            _workload_cache.pop(key, None)
            _cache_timestamps.pop(key, None)


class WorkloadRequest(BaseModel):
    sqls: List[str] = Field(..., description="List of SQL statements")
    top_k: conint(ge=1, le=50) = 10
    what_if: bool = False


class WorkloadResponse(BaseModel):
    ok: bool = True
    suggestions: List[Dict[str, Any]] = Field(default_factory=list)
    perQuery: List[Dict[str, Any]] = Field(default_factory=list)
    workloadStats: Optional[Dict[str, Any]] = None
    topPatterns: List[Dict[str, Any]] = Field(default_factory=list)
    groupedQueries: List[Dict[str, Any]] = Field(default_factory=list)
    workloadRecommendations: List[Dict[str, Any]] = Field(default_factory=list)
    cached: bool = False


@router.post("/workload", response_model=WorkloadResponse)
async def workload(req: WorkloadRequest) -> WorkloadResponse:
    """
    Analyze a workload of multiple SQL queries.

    Provides pattern detection, query grouping, and workload-level optimization recommendations.
    Results are cached for 5 minutes to improve performance for repeated analyses.
    """
    # Check cache
    cache_key = _get_cache_key(req.sqls, req.top_k, req.what_if)
    cached_result = _get_cached_result(cache_key)

    if cached_result:
        return WorkloadResponse(ok=True, cached=True, **cached_result)

    # Perform analysis
    res = analyze_workload(req.sqls, top_k=int(req.top_k), what_if=bool(req.what_if))

    # Cache the result
    _cache_result(cache_key, res)

    return WorkloadResponse(
        ok=True,
        cached=False,
        suggestions=res.get("suggestions", []),
        perQuery=res.get("perQuery", []),
        workloadStats=res.get("workloadStats"),
        topPatterns=res.get("topPatterns", []),
        groupedQueries=res.get("groupedQueries", []),
        workloadRecommendations=res.get("workloadRecommendations", []),
    )

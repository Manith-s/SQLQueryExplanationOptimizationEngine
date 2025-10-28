"""
SQL optimization router.

Provides deterministic rewrite and index suggestions for a given SQL query.
"""

from typing import List, Optional, Literal, Dict, Any
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, conint
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core import db, sql_analyzer, plan_heuristics
from app.core.config import settings
from app.core.optimizer import analyze as optimizer_analyze
from app.core import whatif
from app.core import plan_diff


router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


class OptimizeRequest(BaseModel):
    sql: str = Field(..., description="SQL to analyze")
    analyze: bool = Field(False, description="Use EXPLAIN ANALYZE if true")
    what_if: bool = Field(True, description="Enable HypoPG what-if evaluation")
    timeout_ms: conint(ge=1, le=600000) = Field(10000, description="Statement timeout (ms)")
    advisors: List[Literal["rewrite", "index"]] = Field(
        default_factory=lambda: ["rewrite", "index"], description="Which advisors to run"
    )
    top_k: conint(ge=1, le=50) = Field(10, description="Max suggestions to return")
    diff: bool = Field(False, description="Include plan diff for top index suggestion when what-if ran")


class OptimizeResponse(BaseModel):
    ok: bool = True
    message: str = "ok"
    suggestions: List[Dict[str, Any]] = Field(default_factory=list)
    summary: Dict[str, Any] = Field(default_factory=dict)
    ranking: Literal["cost_based", "heuristic"] = "heuristic"
    whatIf: Dict[str, Any] = Field(default_factory=dict)
    plan_warnings: List[Dict[str, Any]] = Field(default_factory=list)
    plan_metrics: Dict[str, Any] = Field(default_factory=dict)
    advisorsRan: List[str] = Field(default_factory=list)
    dataSources: Dict[str, Any] = Field(default_factory=dict)
    actualTopK: int = 0
    planDiff: Optional[Dict[str, Any]] = None


@router.post(
    "/optimize",
    response_model=OptimizeResponse,
    summary="Deterministic optimization suggestions (rewrites + index advisor)",
    description="Runs static analysis, optional EXPLAIN/ANALYZE, schema+stats fetch, plan heuristics, and returns deterministic suggestions.",
    responses={
        200: {
            "description": "Optimization suggestions",
            "content": {
                "application/json": {
                    "example": {
                        "ok": True,
                        "message": "ok",
                        "suggestions": [
                            {
                                "kind": "rewrite",
                                "title": "Align ORDER BY with index to support Top-N",
                                "rationale": "Matching order-by with an index enables early termination.",
                                "impact": "medium",
                                "confidence": 0.800,
                                "statements": [],
                                "alt_sql": "-- Ensure leading index columns match ORDER BY direction",
                                "safety_notes": None
                            }
                        ],
                        "summary": {"summary": "Top suggestion: Align ORDER BY with index to support Top-N", "score": 0.800},
                        "plan_warnings": [],
                        "plan_metrics": {"planning_time_ms": 0.0, "execution_time_ms": 0.0, "node_count": 1},
                        "advisorsRan": ["rewrite", "index"],
                        "dataSources": {"plan": "explain", "stats": True},
                        "actualTopK": 1
                    }
                }
            }
        }
    }
)
@limiter.limit("10/minute")
async def optimize_sql(request: Request, req: OptimizeRequest) -> OptimizeResponse:
    try:
        # Apply defaults
        if req.timeout_ms is None:
            req.timeout_ms = settings.OPT_TIMEOUT_MS_DEFAULT

        # Parse SQL statically
        ast_info = sql_analyzer.parse_sql(req.sql)
        if ast_info.get("type") != "SELECT":
            return OptimizeResponse(
                ok=False,
                message="Only SELECT statements are supported for optimization",
            )

        # Identify tables involved
        tables = [t.get("name") for t in (ast_info.get("tables") or []) if t.get("name")]

        # Optionally run EXPLAIN
        plan = None
        plan_warnings: List[Dict[str, Any]] = []
        plan_metrics: Dict[str, Any] = {}
        plan_source = "none"
        try:
            plan = db.run_explain(req.sql, analyze=req.analyze, timeout_ms=req.timeout_ms)
            plan_warnings, plan_metrics = plan_heuristics.analyze(plan)
            plan_source = "explain_analyze" if req.analyze else "explain"
        except Exception:
            # Soft-fail: still continue with rewrites
            plan = None
            plan_source = "none"

        # Fetch schema and lightweight stats
        schema_info = db.fetch_schema()
        stats = {}
        stats_used = False
        try:
            stats = db.fetch_table_stats(tables)
            stats_used = True
        except Exception:
            stats = {}
            stats_used = False

        # Optimizer options (could be extended from config)
        options = {
            "min_index_rows": settings.OPT_MIN_ROWS_FOR_INDEX,
            "max_index_cols": settings.OPT_MAX_INDEX_COLS,
        }

        result = optimizer_analyze(
            sql=req.sql,
            ast_info=ast_info,
            plan=plan,
            schema=schema_info,
            stats=stats,
            options=options,
        )

        server_top_k = min(int(req.top_k or settings.OPT_TOP_K), settings.OPT_TOP_K)
        suggestions = result.get("suggestions", [])[: server_top_k]
        summary = result.get("summary", {})

        # Optional what-if (HypoPG) ranking/evaluation
        ranking = "heuristic"
        whatif_info: Dict[str, Any] = {"enabled": False, "available": False, "trials": 0, "filteredByPct": 0}
        if req.what_if and settings.WHATIF_ENABLED:
            try:
                wi = whatif.evaluate(req.sql, suggestions, timeout_ms=req.timeout_ms)
                ranking = wi.get("ranking", ranking)
                whatif_info = wi.get("whatIf", whatif_info)
                suggestions = wi.get("suggestions", suggestions)
            except Exception:
                # Graceful fallback
                ranking = "heuristic"
                whatif_info = {"enabled": True, "available": False, "trials": 0, "filteredByPct": 0}

        # Optional Plan Diff for top index suggestion
        resp_plan_diff: Optional[Dict[str, Any]] = None
        if req.diff and (whatif_info.get("enabled") and whatif_info.get("available")):
            try:
                # Baseline costed plan
                baseline = db.run_explain_costs(req.sql, timeout_ms=req.timeout_ms)
                # Pick top index suggestion
                top_index = next((s for s in suggestions if s.get("kind") == "index"), None)
                if top_index:
                    # Parse table and cols from statements
                    from app.core.whatif import _parse_index_stmt  # type: ignore
                    stmt_list = top_index.get("statements") or []
                    if stmt_list:
                        table, cols = _parse_index_stmt(stmt_list[0])
                        if table and cols:
                            with db.get_conn() as conn:
                                with conn.cursor() as cur:
                                    cur.execute("SELECT hypopg_reset()")
                                    cur.execute("SELECT * FROM hypopg_create_index(%s)", (f"CREATE INDEX ON {table} ({', '.join(cols)})",))
                                    after = db.run_explain_costs(req.sql, timeout_ms=req.timeout_ms)
                                    cur.execute("SELECT hypopg_reset()")
                                    resp_plan_diff = plan_diff.diff_plans(baseline, after)
            except Exception:
                resp_plan_diff = None

        return OptimizeResponse(
            ok=True,
            message="stub: optimize ok",
            suggestions=suggestions,
            summary=summary,
            ranking=ranking,
            whatIf=whatif_info,
            plan_warnings=plan_warnings,
            plan_metrics=plan_metrics,
            advisorsRan=["rewrite", "index"],
            dataSources={"plan": plan_source, "stats": stats_used},
            actualTopK=len(suggestions),
            planDiff=resp_plan_diff,
        )

    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

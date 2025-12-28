"""
FastAPI router for the EXPLAIN endpoint.

Provides query execution plan analysis with optional ANALYZE support
and natural language explanations.
"""

import os
from functools import lru_cache
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, conint

from app.core import db, llm_adapter, plan_heuristics, prompts
from app.core.config import settings

router = APIRouter()

# Optional in-memory cache for explanations (disabled in production)
if settings.APP_ENV != "production":
    explanation_cache = lru_cache(maxsize=100)(lambda *args: args[-1])
else:

    def explanation_cache(*args):
        return args[-1]  # No-op cache


class ExplainRequest(BaseModel):
    """Request model for EXPLAIN endpoint."""

    sql: str = Field(..., description="SQL query to analyze")
    analyze: bool = Field(False, description="Use EXPLAIN ANALYZE for actual metrics")
    timeout_ms: conint(ge=1, le=600000) = Field(
        10000, description="Statement timeout in milliseconds (1ms to 10min)"
    )
    nl: bool = Field(False, description="Generate natural language explanation")
    audience: Literal["beginner", "practitioner", "dba"] = Field(
        "practitioner", description="Target audience for explanation"
    )
    style: Literal["concise", "detailed"] = Field(
        "concise", description="Explanation style"
    )
    length: Literal["short", "medium", "long"] = Field(
        "short", description="Explanation length"
    )
    plan: Optional[dict] = Field(
        None, description="Optional precomputed plan to use instead of running EXPLAIN"
    )


class ExplainResponse(BaseModel):
    """Response model for EXPLAIN endpoint."""

    ok: bool = True
    plan: dict = Field(..., description="Query execution plan")
    warnings: list = Field(default_factory=list, description="Plan analysis warnings")
    metrics: dict = Field(
        default_factory=dict, description="Plan metrics when available"
    )
    explanation: Optional[str] = Field(None, description="Natural language explanation")
    explain_provider: Optional[str] = Field(None, description="LLM provider used")
    message: str = "ok"


@router.post(
    "/explain",
    response_model=ExplainResponse,
    summary="Explain a SQL query plan and optionally generate NL explanation",
    description="Runs EXPLAIN/ANALYZE with bounded timeout and returns plan, heuristics, and optional NL explanation.",
    responses={
        200: {
            "description": "Plan and optional explanation",
            "content": {
                "application/json": {
                    "example": {
                        "ok": True,
                        "plan": {"Plan": {"Node Type": "Seq Scan"}},
                        "warnings": [],
                        "metrics": {
                            "planning_time_ms": 1.23,
                            "execution_time_ms": 0.45,
                            "node_count": 2,
                        },
                        "explanation": "The query selects a constant value...",
                        "explain_provider": "ollama",
                        "message": "ok",
                    }
                }
            },
        }
    },
)
async def explain_query(req: ExplainRequest) -> ExplainResponse:
    """
    Analyze a SQL query's execution plan and optionally explain it in natural language.

    Args:
        req: ExplainRequest with SQL query and options

    Returns:
        ExplainResponse with plan, warnings, metrics, and optional explanation

    Raises:
        HTTPException: If query analysis fails
    """
    try:
        # Use provided plan if present; otherwise attempt EXPLAIN
        plan_error = None
        if req.plan:
            plan = req.plan
        else:
            try:
                # Handle TEMP table creation within the same session
                sql_lc = (req.sql or "").strip().lower()
                if sql_lc.startswith("create temporary table") or sql_lc.startswith(
                    "create temp table"
                ):
                    # Execute DDL; no plan
                    db.run_sql(req.sql, timeout_ms=req.timeout_ms)
                    plan = {}
                else:
                    plan = db.run_explain(
                        sql=req.sql, analyze=req.analyze, timeout_ms=req.timeout_ms
                    )
            except Exception as ex:
                # If NL explanation requested, soft-fail plan but continue
                if req.nl:
                    plan = {}
                    plan_error = str(ex)
                else:
                    # For invalid SQL or timeouts, return HTTP 400 with normalized message
                    detail = str(ex)
                    if "timeout" in detail.lower():
                        detail = f"Timeout: {detail}"
                    raise HTTPException(status_code=400, detail=detail) from ex
        # Analyze plan for warnings and metrics (soft)
        try:
            warnings, metrics = plan_heuristics.analyze(plan)
        except Exception:
            warnings, metrics = [], {}
        # Base response without explanation
        base_message = "stub: explain ok"
        if plan_error:
            base_message = f"stub: explain ok (plan unavailable: {plan_error})"
        response = ExplainResponse(
            ok=True,
            plan=plan,
            warnings=warnings,
            metrics=metrics,
            message=base_message,
        )

        # Generate explanation if requested
        if req.nl:
            try:
                # Try to get cached explanation
                cache_key = (req.sql, req.analyze, req.audience, req.style, req.length)

                explanation = explanation_cache(
                    cache_key,
                    prompts.explain_template(
                        sql=req.sql,
                        plan=plan,
                        warnings=warnings,
                        metrics=metrics,
                        audience=req.audience,
                        style=req.style,
                        length=req.length,
                    ),
                )

                # Get LLM provider and generate explanation
                llm = llm_adapter.get_llm()
                response.explanation = llm.complete(
                    prompt=explanation, system=prompts.SYSTEM_PROMPT
                )
                # Report the actual provider used, not just the configured default
                try:
                    cls_name = type(llm).__name__.lower()
                    if "dummy" in cls_name:
                        response.explain_provider = "dummy"
                    elif "ollama" in cls_name:
                        response.explain_provider = "ollama"
                    else:
                        response.explain_provider = os.getenv(
                            "LLM_PROVIDER", getattr(settings, "LLM_PROVIDER", "dummy")
                        )
                except Exception:
                    response.explain_provider = os.getenv(
                        "LLM_PROVIDER", getattr(settings, "LLM_PROVIDER", "dummy")
                    )

            except Exception as e:
                # Don't fail the endpoint on LLM errors
                response.message = (
                    f"Plan analysis succeeded but explanation failed: {str(e)}"
                )
                response.explanation = None

        return response

    except Exception as e:
        # Unexpected errors
        raise HTTPException(status_code=400, detail=str(e)) from e

from typing import Any, Dict, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.sql_analyzer import lint_rules, parse_sql

router = APIRouter()

class LintRequest(BaseModel):
    sql: str = Field(..., description="SQL query to lint")

class LintIssue(BaseModel):
    code: str = Field(..., description="Issue code")
    message: str = Field(..., description="Issue description")
    severity: str = Field(..., description="Severity level: info, warn, or high")
    hint: str = Field(..., description="Suggestion to fix the issue")

class LintSummary(BaseModel):
    risk: str = Field(..., description="Overall risk level: low, medium, or high")

class LintResponse(BaseModel):
    ok: bool = Field(..., description="Whether the request was successful")
    message: Optional[str] = Field(None, description="Response message")
    error: Optional[str] = Field(None, description="Error message when ok=False")
    ast: Optional[Dict[str, Any]] = Field(None, description="Parsed AST information")
    issues: List[LintIssue] = Field(default_factory=list, description="List of linting issues")
    summary: LintSummary = Field(..., description="Summary of linting results")

@router.post("/lint", response_model=LintResponse)
async def lint_sql(request: LintRequest):
    sql = (request.sql or "").strip()
    if not sql:
        return LintResponse(
            ok=False,
            error="SQL is required",
            ast=None,
            issues=[],
            summary=LintSummary(risk="high")
        )

    try:
        ast_info = parse_sql(sql)
        lint_result = lint_rules(ast_info)
        issues = [LintIssue(**issue) for issue in lint_result.get("issues", [])]
        summary = LintSummary(**lint_result.get("summary", {"risk": "low"}))

        return LintResponse(
            ok=True,
            message="stub: lint ok",
            ast=ast_info,
            issues=issues,
            summary=summary
        )
    except Exception as e:
        return LintResponse(
            ok=True,  # Keep ok=True for parse errors
            message="stub: lint ok",
            ast={"type": "UNKNOWN", "error": str(e)},
            issues=[{
                "code": "PARSE_ERROR",
                "message": f"Error during SQL linting: {str(e)}",
                "severity": "high",
                "hint": "Check SQL syntax"
            }],
            summary=LintSummary(risk="high")
        )

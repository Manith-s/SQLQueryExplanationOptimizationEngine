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
    issues: List[LintIssue] = Field(
        default_factory=list, description="List of linting issues"
    )
    errors: List[LintIssue] = Field(
        default_factory=list, description="Syntax/parse errors (empty if SQL is valid)"
    )
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
            errors=[],
            summary=LintSummary(risk="high"),
        )

    try:
        ast_info = parse_sql(sql)
        lint_result = lint_rules(ast_info)
        issues = [LintIssue(**issue) for issue in lint_result.get("issues", [])]

        # Detect syntax/parse errors: a valid top-level statement parses to a
        # known statement type. Anything else (e.g. a stray Alias/Column) means
        # the SQL could not be parsed as a real statement.
        errors: List[LintIssue] = []
        stmt_type = (ast_info.get("type") or "").upper()
        valid_statements = {
            "SELECT", "INSERT", "UPDATE", "DELETE", "CREATE", "DROP",
            "ALTER", "TRUNCATE", "WITH", "UNION", "INTERSECT", "EXCEPT", "MERGE",
        }
        if stmt_type not in valid_statements:
            errors.append(
                LintIssue(
                    code="SYNTAX_ERROR",
                    message=(
                        "Unable to parse SQL as a valid statement "
                        f"(parsed as '{stmt_type or 'UNKNOWN'}')"
                    ),
                    severity="high",
                    hint="Check the SQL syntax (keywords, clause order, typos).",
                )
            )

        base_summary = lint_result.get("summary", {"risk": "low"})
        if errors:
            base_summary = {**base_summary, "risk": "high"}
        summary = LintSummary(**base_summary)

        return LintResponse(
            ok=True,
            message="ok",
            ast=ast_info,
            issues=issues,
            errors=errors,
            summary=summary,
        )
    except Exception as e:
        parse_error = LintIssue(
            code="PARSE_ERROR",
            message=f"Error during SQL linting: {str(e)}",
            severity="high",
            hint="Check SQL syntax",
        )
        return LintResponse(
            ok=True,  # Keep ok=True for parse errors (soft-fail contract)
            message="ok",
            ast={"type": "UNKNOWN", "error": str(e)},
            issues=[parse_error],
            errors=[parse_error],
            summary=LintSummary(risk="high"),
        )

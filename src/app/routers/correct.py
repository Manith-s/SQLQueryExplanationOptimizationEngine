"""
Query correction router for detecting and fixing SQL errors.
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.query_corrector import correct_query

router = APIRouter()


class CorrectRequest(BaseModel):
    sql: str = Field(..., description="SQL query to correct")


class CorrectionSuggestion(BaseModel):
    type: str = Field(..., description="Type: correction or suggestion")
    error: str = Field(..., description="Error type")
    message: str = Field(..., description="Error message")
    fix: Optional[str] = Field(None, description="Suggested fix")
    confidence: Optional[float] = Field(None, description="Confidence level (0-1)")
    explanation: Optional[str] = Field(None, description="Explanation of the issue")


class CorrectResponse(BaseModel):
    ok: bool = Field(True, description="Whether the request was successful")
    original: str = Field(..., description="Original SQL query")
    corrected: Optional[str] = Field(None, description="Corrected SQL query")
    is_valid: bool = Field(
        ..., description="Whether the original query is syntactically valid"
    )
    errors: List[Dict[str, Any]] = Field(
        default_factory=list, description="List of errors found"
    )
    suggestions: List[CorrectionSuggestion] = Field(
        default_factory=list, description="Correction suggestions"
    )
    can_auto_correct: bool = Field(
        False, description="Whether auto-correction is possible"
    )


@router.post("/correct", response_model=CorrectResponse)
async def correct_sql(request: CorrectRequest):
    """
    Correct SQL query syntax errors and common mistakes.

    Detects:
    - Syntax errors
    - Common typos (keywords, functions)
    - Missing clauses (FROM, WHERE, ON)
    - Logic errors (HAVING without GROUP BY)
    - Safety issues (UPDATE/DELETE without WHERE)
    """
    sql = (request.sql or "").strip()
    if not sql:
        raise HTTPException(status_code=400, detail="SQL is required")

    try:
        result = correct_query(sql)

        return CorrectResponse(
            ok=True,
            original=result["original"],
            corrected=result.get("corrected"),
            is_valid=result["is_valid"],
            errors=result.get("errors", []),
            suggestions=[
                CorrectionSuggestion(**s) for s in result.get("suggestions", [])
            ],
            can_auto_correct=result.get("can_auto_correct", False),
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error during correction: {str(e)}"
        ) from e

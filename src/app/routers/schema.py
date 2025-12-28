"""
FastAPI router for the schema inspection endpoint.

Provides database schema information including tables, columns, indexes, and constraints.
"""

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core import db

router = APIRouter()

class SchemaResponse(BaseModel):
    """Response model for schema endpoint."""
    ok: bool = True
    schema: dict = Field(..., description="Schema information")
    message: str = "ok"

@router.get("/schema", response_model=SchemaResponse)
async def get_schema(
    schema: str = "public",
    table: Optional[str] = None
) -> SchemaResponse:
    """
    Get database schema information.

    Args:
        schema: Schema name to inspect (default: public)
        table: Optional table name to filter results

    Returns:
        SchemaResponse with schema information

    Raises:
        HTTPException: If schema inspection fails
    """
    try:
        schema_info = db.fetch_schema(schema=schema, table=table)
        return SchemaResponse(ok=True, schema=schema_info)

    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=str(e)
        ) from e


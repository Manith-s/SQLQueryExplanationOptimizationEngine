"""
Database Catalog and Query Builder API

Provides endpoints for visual query building, validation, and intelligent suggestions.
"""

import re
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.db import fetch_schema_metadata, run_sql
from app.core.sql_analyzer import parse_sql

router = APIRouter(prefix="/api/v1", tags=["catalog"])


# Request/Response Models
class CatalogResponse(BaseModel):
    """Database catalog with tables, columns, and relationships."""
    tables: List[Dict[str, Any]]
    relationships: List[Dict[str, Any]]
    statistics: Dict[str, Any]


class ValidateRequest(BaseModel):
    """Request for query validation."""
    sql: str = Field(..., description="SQL query to validate")
    partial: bool = Field(default=False, description="Whether this is a partial query")


class ValidateResponse(BaseModel):
    """Query validation response."""
    valid: bool
    errors: List[str] = []
    warnings: List[str] = []
    suggestions: List[str] = []


class SuggestRequest(BaseModel):
    """Request for query suggestions."""
    partial_sql: Optional[str] = Field(None, description="Partial SQL query")
    context: Dict[str, Any] = Field(default_factory=dict, description="Query context")


class SuggestResponse(BaseModel):
    """Query suggestions response."""
    suggestions: List[Dict[str, Any]]
    context_hints: List[str] = []


class VisualPlanResponse(BaseModel):
    """Visual execution plan response."""
    plan_tree: Dict[str, Any]
    summary: Dict[str, Any]
    bottlenecks: List[Dict[str, Any]]


@router.get("/catalog", response_model=CatalogResponse)
async def get_catalog(
    schema: str = Query(default="public", description="Database schema name"),
    include_system: bool = Query(default=False, description="Include system tables")
):
    """
    Get database catalog with tables, columns, and relationships.

    Returns comprehensive metadata including:
    - Tables with columns and data types
    - Primary and foreign key relationships
    - Table statistics (row counts, sizes)
    - Index information
    """
    try:
        # Fetch schema metadata
        schema_data = fetch_schema_metadata(schema_name=schema)

        if not schema_data or "tables" not in schema_data:
            raise HTTPException(
                status_code=404,
                detail=f"Schema '{schema}' not found or inaccessible"
            )

        tables = schema_data["tables"]

        # Get table statistics
        statistics = {}
        try:
            stats_query = f"""
                SELECT
                    schemaname,
                    tablename,
                    n_live_tup as row_count,
                    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as total_size
                FROM pg_stat_user_tables
                WHERE schemaname = '{schema}'
                ORDER BY n_live_tup DESC
            """
            stats_result = run_sql(stats_query, timeout_ms=5000)

            if stats_result and "rows" in stats_result:
                for row in stats_result["rows"]:
                    table_name = row[1]  # tablename
                    statistics[table_name] = {
                        "row_count": row[2],  # n_live_tup
                        "total_size": row[3]  # total_size
                    }
        except Exception:
            # Stats are optional, continue without them
            pass

        # Detect relationships (foreign keys)
        relationships = []
        try:
            fk_query = f"""
                SELECT
                    tc.table_name as from_table,
                    kcu.column_name as from_column,
                    ccu.table_name as to_table,
                    ccu.column_name as to_column,
                    tc.constraint_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                    ON tc.constraint_name = kcu.constraint_name
                    AND tc.table_schema = kcu.table_schema
                JOIN information_schema.constraint_column_usage ccu
                    ON ccu.constraint_name = tc.constraint_name
                    AND ccu.table_schema = tc.table_schema
                WHERE tc.constraint_type = 'FOREIGN KEY'
                  AND tc.table_schema = '{schema}'
                ORDER BY tc.table_name, kcu.column_name
            """
            fk_result = run_sql(fk_query, timeout_ms=5000)

            if fk_result and "rows" in fk_result:
                for row in fk_result["rows"]:
                    relationships.append({
                        "from_table": row[0],
                        "from_column": row[1],
                        "to_table": row[2],
                        "to_column": row[3],
                        "constraint_name": row[4],
                        "type": "foreign_key"
                    })
        except Exception:
            # Relationships are optional
            pass

        # Enhance table data with statistics
        enhanced_tables = []
        for table in tables:
            table_name = table["name"]
            enhanced_table = {
                **table,
                "statistics": statistics.get(table_name, {
                    "row_count": None,
                    "total_size": "Unknown"
                })
            }
            enhanced_tables.append(enhanced_table)

        return CatalogResponse(
            tables=enhanced_tables,
            relationships=relationships,
            statistics={
                "total_tables": len(enhanced_tables),
                "total_relationships": len(relationships),
                "schema": schema
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch catalog: {str(e)}"
        ) from e


@router.post("/validate", response_model=ValidateResponse)
async def validate_query(request: ValidateRequest):
    """
    Validate SQL query and provide suggestions.

    Performs:
    - Syntax validation
    - Semantic analysis
    - Performance warnings
    - Best practice suggestions
    """
    try:
        errors = []
        warnings = []
        suggestions = []

        # Basic syntax check using sql_analyzer
        try:
            analysis = parse_sql(request.sql)

            if not analysis or "error" in analysis:
                errors.append(analysis.get("error", "Invalid SQL syntax"))
                return ValidateResponse(
                    valid=False,
                    errors=errors
                )

        except Exception as e:
            if not request.partial:
                errors.append(f"Syntax error: {str(e)}")
                return ValidateResponse(valid=False, errors=errors)

        # Check for common issues
        sql_upper = request.sql.upper()

        # Check for SELECT *
        if "SELECT *" in sql_upper:
            warnings.append("Using SELECT * may retrieve unnecessary columns")
            suggestions.append("Consider specifying exact columns needed")

        # Check for missing WHERE clause in DELETE/UPDATE
        if ("DELETE FROM" in sql_upper or "UPDATE" in sql_upper) and "WHERE" not in sql_upper:
            warnings.append("DELETE/UPDATE without WHERE clause affects all rows")
            suggestions.append("Add WHERE clause to limit affected rows")

        # Check for LIKE with leading wildcard
        if re.search(r"LIKE\s+['\"]%", sql_upper):
            warnings.append("LIKE patterns starting with % cannot use indexes")
            suggestions.append("Consider full-text search or restructuring the query")

        # Check for OR conditions (potentially slow)
        or_count = len(re.findall(r"\bOR\b", sql_upper))
        if or_count > 3:
            warnings.append(f"Query has {or_count} OR conditions which may be slow")
            suggestions.append("Consider using IN clause or UNION instead")

        # Check for subqueries in SELECT clause
        if re.search(r"SELECT.*\(.*SELECT.*\)", request.sql, re.IGNORECASE | re.DOTALL):
            warnings.append("Subqueries in SELECT clause execute for each row")
            suggestions.append("Consider using JOIN instead")

        # Validate table/column references if possible
        if analysis.get("tables"):
            try:
                # Check if referenced tables exist
                schema_data = fetch_schema_metadata()
                if schema_data and "tables" in schema_data:
                    existing_tables = {t["name"] for t in schema_data["tables"]}
                    for table in analysis["tables"]:
                        if table not in existing_tables:
                            warnings.append(f"Table '{table}' may not exist")
            except Exception:
                pass

        return ValidateResponse(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            suggestions=suggestions
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Validation failed: {str(e)}"
        ) from e


@router.post("/suggest", response_model=SuggestResponse)
async def suggest_query(request: SuggestRequest):
    """
    Provide intelligent query suggestions based on context.

    Suggests:
    - Table names
    - Column names
    - JOIN conditions
    - Common query patterns
    - Performance optimizations
    """
    try:
        suggestions = []
        context_hints = []

        # Get schema metadata for suggestions
        try:
            schema_data = fetch_schema_metadata()
            tables = schema_data.get("tables", []) if schema_data else []
        except Exception:
            tables = []

        # Analyze context
        context = request.context
        current_tables = context.get("tables", [])
        current_columns = context.get("columns", [])

        # Suggest tables if none selected
        if not current_tables:
            for table in tables[:10]:  # Top 10 tables
                suggestions.append({
                    "type": "table",
                    "value": table["name"],
                    "description": f"Table with {len(table.get('columns', []))} columns",
                    "priority": 1
                })
            context_hints.append("Start by selecting tables to query")

        # Suggest columns from selected tables
        elif current_tables and not current_columns:
            for table in tables:
                if table["name"] in current_tables:
                    for col in table.get("columns", [])[:5]:  # Top 5 columns
                        suggestions.append({
                            "type": "column",
                            "value": f"{table['name']}.{col['name']}",
                            "description": f"{col['data_type']} column",
                            "priority": 2
                        })
            context_hints.append("Select columns to include in your query")

        # Suggest JOIN conditions if multiple tables
        elif len(current_tables) > 1:
            # Try to detect possible join relationships
            for i, table1 in enumerate(current_tables):
                for table2 in current_tables[i+1:]:
                    # Look for common column patterns (id, *_id)
                    table1_data = next((t for t in tables if t["name"] == table1), None)
                    table2_data = next((t for t in tables if t["name"] == table2), None)

                    if table1_data and table2_data:
                        cols1 = {c["name"] for c in table1_data.get("columns", [])}
                        cols2 = {c["name"] for c in table2_data.get("columns", [])}

                        # Check for id column match
                        if f"{table2}_id" in cols1 or "id" in cols2:
                            suggestions.append({
                                "type": "join",
                                "value": f"JOIN {table2} ON {table1}.{table2}_id = {table2}.id",
                                "description": f"Suggested join between {table1} and {table2}",
                                "priority": 3
                            })

            context_hints.append("Consider adding JOIN conditions between tables")

        # Suggest common aggregate functions
        if current_columns:
            suggestions.append({
                "type": "function",
                "value": "COUNT(*)",
                "description": "Count all rows",
                "priority": 4
            })
            suggestions.append({
                "type": "function",
                "value": "AVG(column)",
                "description": "Calculate average",
                "priority": 4
            })
            suggestions.append({
                "type": "function",
                "value": "SUM(column)",
                "description": "Calculate sum",
                "priority": 4
            })

        # Suggest common patterns
        suggestions.append({
            "type": "pattern",
            "value": "WHERE column = value",
            "description": "Filter results",
            "priority": 5
        })

        suggestions.append({
            "type": "pattern",
            "value": "ORDER BY column DESC",
            "description": "Sort results",
            "priority": 5
        })

        suggestions.append({
            "type": "pattern",
            "value": "LIMIT 100",
            "description": "Limit result count",
            "priority": 5
        })

        # Sort by priority
        suggestions.sort(key=lambda x: x["priority"])

        return SuggestResponse(
            suggestions=suggestions[:20],  # Return top 20
            context_hints=context_hints
        )

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Suggestion failed: {str(e)}"
        ) from e


@router.get("/plan/visual", response_model=VisualPlanResponse)
async def get_visual_plan(
    sql: str = Query(..., description="SQL query to analyze"),
    analyze: bool = Query(default=False, description="Run EXPLAIN ANALYZE")
):
    """
    Get execution plan optimized for visualization.

    Returns:
    - Hierarchical tree structure
    - Cost and timing information
    - Identified bottlenecks
    - Node classifications
    """
    try:
        from app.core.db import run_explain

        # Get EXPLAIN plan
        plan_result = run_explain(sql, analyze=analyze)

        if not plan_result or "plan" not in plan_result:
            raise HTTPException(
                status_code=400,
                detail="Failed to generate execution plan"
            )

        plan_json = plan_result["plan"]

        # Transform plan for visualization
        plan_tree = _transform_plan_for_viz(plan_json)

        # Identify bottlenecks
        bottlenecks = _identify_bottlenecks(plan_json)

        # Create summary
        summary = {
            "total_cost": plan_json.get("Total Cost"),
            "planning_time": plan_result.get("Planning Time"),
            "execution_time": plan_result.get("Execution Time"),
            "node_count": _count_nodes(plan_json),
            "max_depth": _calculate_depth(plan_json)
        }

        return VisualPlanResponse(
            plan_tree=plan_tree,
            summary=summary,
            bottlenecks=bottlenecks
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate visual plan: {str(e)}"
        ) from e


def _transform_plan_for_viz(node: Dict[str, Any], depth: int = 0) -> Dict[str, Any]:
    """Transform EXPLAIN plan into visualization-friendly format."""
    # Determine node color based on cost
    cost = node.get("Total Cost", 0)
    if cost < 10:
        color = "#28a745"  # Green - fast
    elif cost < 100:
        color = "#ffc107"  # Yellow - moderate
    else:
        color = "#dc3545"  # Red - slow

    # Map node types to icons
    node_type = node.get("Node Type", "Unknown")
    icon = _get_node_icon(node_type)

    viz_node = {
        "id": f"node_{depth}_{hash(str(node)) % 10000}",
        "name": node_type,
        "node_type": node_type,
        "relation_name": node.get("Relation Name"),
        "alias": node.get("Alias"),
        "cost": {
            "startup": node.get("Startup Cost"),
            "total": node.get("Total Cost")
        },
        "rows": {
            "plan": node.get("Plan Rows"),
            "actual": node.get("Actual Rows")
        },
        "time": {
            "actual": node.get("Actual Total Time")
        },
        "color": color,
        "icon": icon,
        "depth": depth,
        "children": []
    }

    # Process children recursively
    if "Plans" in node:
        for child in node["Plans"]:
            viz_node["children"].append(
                _transform_plan_for_viz(child, depth + 1)
            )

    return viz_node


def _get_node_icon(node_type: str) -> str:
    """Get icon for node type."""
    icon_map = {
        "Seq Scan": "📋",
        "Index Scan": "📇",
        "Index Only Scan": "🔍",
        "Bitmap Heap Scan": "🗂️",
        "Nested Loop": "🔄",
        "Hash Join": "🔗",
        "Merge Join": "🔀",
        "Sort": "⬆️",
        "Aggregate": "∑",
        "Group": "📊",
        "Limit": "✂️"
    }
    return icon_map.get(node_type, "📦")


def _identify_bottlenecks(node: Dict[str, Any], bottlenecks: List = None) -> List[Dict[str, Any]]:
    """Identify performance bottlenecks in the plan."""
    if bottlenecks is None:
        bottlenecks = []

    node_type = node.get("Node Type")
    total_cost = node.get("Total Cost", 0)
    node.get("Startup Cost", 0)
    actual_rows = node.get("Actual Rows")
    plan_rows = node.get("Plan Rows")

    # Check for expensive operations
    if total_cost > 1000:
        bottlenecks.append({
            "type": "high_cost",
            "node_type": node_type,
            "cost": total_cost,
            "severity": "high",
            "description": f"{node_type} has very high cost ({total_cost:.2f})"
        })

    # Check for seq scans on large tables
    if node_type == "Seq Scan" and plan_rows and plan_rows > 10000:
        bottlenecks.append({
            "type": "seq_scan",
            "node_type": node_type,
            "relation": node.get("Relation Name"),
            "rows": plan_rows,
            "severity": "medium",
            "description": f"Sequential scan on {node.get('Relation Name')} ({plan_rows} rows)"
        })

    # Check for row estimation errors
    if actual_rows is not None and plan_rows is not None and plan_rows > 0:
        error_ratio = abs(actual_rows - plan_rows) / plan_rows
        if error_ratio > 10:  # More than 10x off
            bottlenecks.append({
                "type": "estimation_error",
                "node_type": node_type,
                "planned_rows": plan_rows,
                "actual_rows": actual_rows,
                "severity": "medium",
                "description": f"Large estimation error: planned {plan_rows}, actual {actual_rows}"
            })

    # Recurse through children
    if "Plans" in node:
        for child in node["Plans"]:
            _identify_bottlenecks(child, bottlenecks)

    return bottlenecks


def _count_nodes(node: Dict[str, Any]) -> int:
    """Count total nodes in plan tree."""
    count = 1
    if "Plans" in node:
        for child in node["Plans"]:
            count += _count_nodes(child)
    return count


def _calculate_depth(node: Dict[str, Any], current_depth: int = 0) -> int:
    """Calculate maximum depth of plan tree."""
    if "Plans" not in node or not node["Plans"]:
        return current_depth

    max_child_depth = current_depth
    for child in node["Plans"]:
        child_depth = _calculate_depth(child, current_depth + 1)
        max_child_depth = max(max_child_depth, child_depth)

    return max_child_depth

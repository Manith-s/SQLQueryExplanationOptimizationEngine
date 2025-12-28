"""
LLM prompting templates and helpers for SQL explanation.

This module provides templates and utilities for generating LLM prompts
that explain SQL queries and their execution plans.
"""

import json
from typing import Any, Dict, List, Optional

# System prompt that sets the context and constraints
SYSTEM_PROMPT = """You are an expert PostgreSQL database engineer explaining SQL queries and their execution plans.
Focus on:
1. What the query does in plain language
2. Key aspects of the execution plan
3. Performance implications and suggestions
4. Only facts visible in the provided SQL, AST, plan, and metrics

Be direct and technical. Don't apologize or use filler phrases.
Match the audience level and requested length."""


def _truncate_json(obj: Any, max_depth: int = 2, current_depth: int = 0) -> Any:
    """
    Recursively truncate JSON objects to a maximum depth.

    Args:
        obj: JSON-serializable object
        max_depth: Maximum nesting depth to keep
        current_depth: Current recursion depth

    Returns:
        Truncated object with "...(truncated)" for cut branches
    """
    if current_depth >= max_depth:
        return "...(truncated)"

    if isinstance(obj, dict):
        return {
            k: _truncate_json(v, max_depth, current_depth + 1) for k, v in obj.items()
        }
    elif isinstance(obj, list):
        return [_truncate_json(item, max_depth, current_depth + 1) for item in obj]
    return obj


def _format_warnings(warnings: List[Dict[str, Any]]) -> str:
    """Format warning list into readable text."""
    if not warnings:
        return "No warnings identified."

    return "\n".join(f"- {w['code']}: {w['detail']}" for w in warnings)


def _format_metrics(metrics: Dict[str, Any]) -> str:
    """Format metrics dict into readable text."""
    return (
        f"Planning time: {metrics.get('planning_time_ms', 0):.2f}ms, "
        f"Execution time: {metrics.get('execution_time_ms', 0):.2f}ms, "
        f"Node count: {metrics.get('node_count', 0)}"
    )


def explain_template(
    sql: str,
    ast: Optional[Dict] = None,
    plan: Optional[Dict] = None,
    warnings: Optional[List[Dict]] = None,
    metrics: Optional[Dict] = None,
    audience: str = "practitioner",
    style: str = "concise",
    length: str = "short",
    max_length: int = 2000,  # Limit total prompt length
) -> str:
    """
    Generate a prompt for explaining a SQL query.

    Args:
        sql: SQL query text
        ast: Optional parsed AST
        plan: Optional execution plan
        warnings: Optional list of heuristic warnings
        metrics: Optional plan metrics
        audience: Target audience (beginner/practitioner/dba)
        style: Explanation style (concise/detailed)
        length: Response length (short/medium/long)

    Returns:
        Formatted prompt string
    """
    # Clean and truncate inputs
    if ast:
        ast = _truncate_json(ast)
    if plan:
        plan = _truncate_json(plan)

    # Build prompt sections with length control
    sections = [f"Explain this SQL query concisely for a {audience}:\n\n{sql}\n"]

    if ast:
        sections.append(f"\nParsed structure:\n{json.dumps(ast, indent=2)}\n")

    if plan:
        sections.append(f"\nExecution plan:\n{json.dumps(plan, indent=2)}\n")

    if warnings:
        sections.append(f"\nPerformance warnings:\n{_format_warnings(warnings)}\n")

    if metrics:
        sections.append(f"\nPlan metrics:\n{_format_metrics(metrics)}\n")

    # Add specific instructions based on audience
    if audience == "beginner":
        sections.append(
            "\nUse simple terms and explain basic concepts. "
            "Focus on what the query does more than how it does it."
        )
    elif audience == "practitioner":
        sections.append(
            "\nAssume familiarity with SQL and basic optimization. "
            "Balance what/how with practical performance guidance."
        )
    elif audience == "dba":
        sections.append(
            "\nFocus on performance characteristics and optimization "
            "opportunities. Be specific about indexes and plan choices."
        )

    # Add length guidance
    if length == "short":
        sections.append("\nKeep the explanation brief and focused.")
    elif length == "medium":
        sections.append("\nProvide moderate detail while staying concise.")
    else:  # long
        sections.append("\nProvide comprehensive explanation and context.")

    return "\n".join(sections)

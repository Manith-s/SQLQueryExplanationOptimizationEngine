"""
PostgreSQL execution plan analysis and heuristics engine.

This module analyzes execution plans to identify potential performance issues
and calculate basic metrics.
"""

from typing import Any, Dict, List, Optional, Tuple


def _walk(node: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Walk a plan tree and return a flattened list of all nodes.

    Args:
        node: Plan node dictionary

    Returns:
        List of all nodes in the plan tree
    """
    nodes = [node]

    # Handle Plans array (parallel workers)
    if "Plans" in node:
        for child in node["Plans"]:
            nodes.extend(_walk(child))

    return nodes


def _get_node_type(node: Dict[str, Any]) -> str:
    """Extract node type, handling version differences."""
    return node.get("Node Type", node.get("node_type", "Unknown"))


def _get_rows(node: Dict[str, Any], actual: bool = False) -> Optional[float]:
    """Extract row count, handling version differences."""
    if actual:
        return node.get("Actual Rows", node.get("actual_rows"))
    return node.get("Plan Rows", node.get("plan_rows"))


def analyze(plan_root: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Analyze a plan tree and return warnings and metrics.

    Args:
        plan_root: Root of the plan tree (either {"Plan": {...}} or direct plan node)

    Returns:
        Tuple of (warnings, metrics) where warnings is a list of warning objects
        and metrics is a dictionary of numeric metrics
    """
    # Normalize plan structure
    plan = plan_root.get("Plan", plan_root)

    # Walk the tree to get all nodes
    nodes = _walk(plan)

    warnings = []
    metrics = {
        "planning_time_ms": plan_root.get("Planning Time", 0),
        "execution_time_ms": plan_root.get("Execution Time", 0),
        "node_count": len(nodes),
    }

    # Track tables seen for NO_INDEX_FILTER analysis
    tables_with_seqscan = set()
    tables_with_indexscan = set()

    for node in nodes:
        node_type = _get_node_type(node)

        # SEQ_SCAN_LARGE: Sequential scan with high row count
        if node_type == "Seq Scan":
            plan_rows = _get_rows(node, actual=False)
            actual_rows = _get_rows(node, actual=True)
            rows = actual_rows if actual_rows is not None else plan_rows

            if rows and rows >= 100000:
                warnings.append(
                    {
                        "code": "SEQ_SCAN_LARGE",
                        "level": "warn",
                        "detail": f"Sequential scan on {node.get('Relation Name', 'table')} "
                        f"with {rows:,.0f} rows",
                    }
                )

            # Track for NO_INDEX_FILTER analysis
            if "Filter" in node:
                tables_with_seqscan.add(node.get("Relation Name"))

        # Track tables with index scans
        elif "Index Scan" in node_type:
            tables_with_indexscan.add(node.get("Relation Name"))

        # NESTED_LOOP_SEQ_INNER: Nested Loop with sequential scan inner
        if node_type == "Nested Loop" and "Plans" in node:
            inner_plan = node["Plans"][1]  # Second plan is inner
            if _get_node_type(inner_plan) == "Seq Scan":
                warnings.append(
                    {
                        "code": "NESTED_LOOP_SEQ_INNER",
                        "level": "warn",
                        "detail": f"Nested loop joins with sequential scan inner side on "
                        f"{inner_plan.get('Relation Name', 'table')}",
                    }
                )

        # SORT_SPILL: Sort spilling to disk
        if "Sort" in node_type:
            sort_method = node.get("Sort Method", "")
            if "Disk" in sort_method or "External" in sort_method:
                warnings.append(
                    {
                        "code": "SORT_SPILL",
                        "level": "warn",
                        "detail": f"Sort spilled to disk using {sort_method}",
                    }
                )

        # ESTIMATE_MISMATCH: Actual vs planned rows mismatch
        plan_rows = _get_rows(node, actual=False)
        actual_rows = _get_rows(node, actual=True)
        if plan_rows is not None and actual_rows is not None:
            error = abs(actual_rows - plan_rows) / (plan_rows + 1)
            if error >= 0.5:  # 50% or more error
                warnings.append(
                    {
                        "code": "ESTIMATE_MISMATCH",
                        "level": "warn",
                        "detail": f"Row estimate error in {node_type}: "
                        f"Expected {plan_rows:,.0f}, got {actual_rows:,.0f} "
                        f"({error:.1%} error)",
                    }
                )

    # NO_INDEX_FILTER: Tables with seq scan + filter but no index scans
    for table in tables_with_seqscan - tables_with_indexscan:
        warnings.append(
            {
                "code": "NO_INDEX_FILTER",
                "level": "warn",
                "detail": f"Table {table} has Filter clause but no Index Scan alternatives",
            }
        )

    # PARALLEL_OFF: Large operation but no parallel nodes
    total_rows = sum(
        _get_rows(n, actual=True) or _get_rows(n, actual=False) or 0 for n in nodes
    )
    has_parallel = any("Parallel" in _get_node_type(n) for n in nodes)

    if total_rows >= 100000 and not has_parallel:
        warnings.append(
            {
                "code": "PARALLEL_OFF",
                "level": "warn",
                "detail": f"Query processes {total_rows:,.0f} rows but uses no parallel nodes",
            }
        )

    return warnings, metrics


# Compatibility shims for older tests
def analyze_plan(plan_root: Dict[str, Any]):
    return analyze(plan_root)


def suggest_from_plan(plan_root: Dict[str, Any]):
    return []

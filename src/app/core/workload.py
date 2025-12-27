from typing import List, Dict, Any, Tuple
import re
import hashlib
from collections import defaultdict
from app.core import sql_analyzer, db, plan_heuristics
from app.core.optimizer import analyze as analyze_one
from app.core.config import settings


def _normalize_sql_for_grouping(sql: str) -> str:
    """
    Normalize SQL to create a pattern signature for grouping similar queries.

    Replaces literals with placeholders to identify structural similarity.
    """
    # Normalize whitespace
    normalized = " ".join(sql.split())

    # Replace string literals
    normalized = re.sub(r"'[^']*'", "'?'", normalized)

    # Replace numbers
    normalized = re.sub(r"\b\d+\b", "?", normalized)

    # Normalize to lowercase for comparison
    normalized = normalized.lower()

    return normalized


def _detect_patterns(sql: str, ast_info: Dict[str, Any], plan: Dict[str, Any] = None) -> List[str]:
    """
    Detect common query patterns and anti-patterns.

    Returns:
        List of pattern names detected in the query
    """
    patterns = []

    # Pattern: SELECT *
    columns = ast_info.get("columns") or []
    if any(c.get("name") == "*" for c in columns):
        patterns.append("SELECT_STAR")

    # Pattern: Missing WHERE clause
    filters = ast_info.get("filters") or []
    if not filters and ast_info.get("type") == "SELECT":
        patterns.append("NO_WHERE_CLAUSE")

    # Pattern: Cartesian join (missing join conditions)
    joins = ast_info.get("joins") or []
    if len(joins) > 0:
        for join in joins:
            if not join.get("condition"):
                patterns.append("CARTESIAN_JOIN")
                break

    # Pattern: N+1 query indicator (queries in a loop - detected by frequency)
    # This will be detected at workload level

    # Pattern: ORDER BY without LIMIT
    order_by = ast_info.get("order_by") or []
    limit = ast_info.get("limit")
    if order_by and not limit:
        patterns.append("ORDER_WITHOUT_LIMIT")

    # Pattern: Subquery in SELECT
    sql_lower = sql.lower()
    if re.search(r"select.*\(\s*select", sql_lower):
        patterns.append("SUBQUERY_IN_SELECT")

    # Pattern: Sequential scan on large table (requires plan)
    if plan:
        def _check_seq_scan(node: Dict[str, Any]) -> bool:
            if node.get("Node Type") == "Seq Scan":
                rows = node.get("Plan Rows") or 0
                if rows > 10000:
                    return True
            for child in node.get("Plans") or []:
                if _check_seq_scan(child):
                    return True
            return False

        if _check_seq_scan(plan.get("Plan", {})):
            patterns.append("LARGE_SEQ_SCAN")

    # Pattern: Multiple JOINs
    if len(joins) >= 3:
        patterns.append("MULTIPLE_JOINS")

    return patterns


def _merge_candidates(all_suggs: List[Dict[str, Any]], top_k: int) -> List[Dict[str, Any]]:
    seen: Dict[str, Dict[str, Any]] = {}
    for s in all_suggs:
        if s.get("kind") != "index":
            continue
        key = s.get("title") or ""
        cur = seen.get(key)
        if not cur:
            cur = {**s, "frequency": 0}
            seen[key] = cur
        cur["frequency"] += 1
        # accumulate score if present
        cur["score"] = float(f"{(float(cur.get('score') or 0.0) + float(s.get('score') or 0.0)):.3f}")
    out = list(seen.values())
    out.sort(key=lambda x: (-float(x.get("score") or 0.0), -int(x.get("frequency") or 0), x.get("title") or ""))
    return out[: top_k]


def analyze_workload(sqls: List[str], top_k: int = 10, what_if: bool = False) -> Dict[str, Any]:
    """
    Analyze a workload of multiple queries with pattern detection and aggregation.

    Returns:
        Dictionary with merged suggestions, per-query analysis, patterns, and grouped queries
    """
    all_suggs: List[Dict[str, Any]] = []
    per_query: List[Dict[str, Any]] = []
    pattern_counts: Dict[str, int] = defaultdict(int)
    query_groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

    # Fetch schema once for all queries
    schema_info = db.fetch_schema()

    for sql in sqls:
        info = sql_analyzer.parse_sql(sql)
        if info.get("type") != "SELECT":
            per_query.append({"sql": sql, "skipped": True, "reason": "Non-SELECT statement"})
            continue

        # Get normalized pattern for grouping
        normalized = _normalize_sql_for_grouping(sql)
        pattern_hash = hashlib.md5(normalized.encode()).hexdigest()[:8]

        plan = None
        warnings: List[Dict[str, Any]] = []
        metrics: Dict[str, Any] = {}
        try:
            plan = db.run_explain(sql, analyze=False, timeout_ms=settings.OPT_TIMEOUT_MS_DEFAULT)
            warnings, metrics = plan_heuristics.analyze(plan)
        except Exception:
            plan = None

        # Detect patterns
        patterns = _detect_patterns(sql, info, plan)
        for pattern in patterns:
            pattern_counts[pattern] += 1

        try:
            tables = [t.get("name") for t in (info.get("tables") or []) if t.get("name")]
            stats = db.fetch_table_stats(tables, timeout_ms=settings.OPT_TIMEOUT_MS_DEFAULT)
        except Exception:
            stats = {}

        options = {
            "min_index_rows": settings.OPT_MIN_ROWS_FOR_INDEX,
            "max_index_cols": settings.OPT_MAX_INDEX_COLS,
        }

        res = analyze_one(sql, info, plan, schema_info, stats, options)
        suggs = res.get("suggestions", [])
        all_suggs.extend(suggs)

        query_info = {
            "sql": sql,
            "suggestions": suggs,
            "patterns": patterns,
            "warnings": warnings,
            "patternGroup": pattern_hash,
        }
        per_query.append(query_info)

        # Group similar queries
        query_groups[pattern_hash].append({
            "sql": sql,
            "patterns": patterns,
        })

    # Merge and rank suggestions
    merged = _merge_candidates(all_suggs, top_k)

    # Calculate workload-level metrics
    workload_stats = {
        "totalQueries": len(sqls),
        "analyzedQueries": len([q for q in per_query if not q.get("skipped")]),
        "skippedQueries": len([q for q in per_query if q.get("skipped")]),
        "uniquePatterns": len(query_groups),
    }

    # Identify top patterns
    top_patterns = sorted(
        [{"pattern": k, "count": v, "percentage": round(v / len(sqls) * 100, 1)}
         for k, v in pattern_counts.items()],
        key=lambda x: -x["count"]
    )[:10]

    # Generate workload-level recommendations
    workload_recommendations = _generate_workload_recommendations(
        pattern_counts, merged, query_groups
    )

    # Group queries by pattern with counts
    grouped_queries = [
        {
            "patternHash": pattern_hash,
            "count": len(queries),
            "exampleSql": queries[0]["sql"] if queries else "",
            "patterns": queries[0]["patterns"] if queries else [],
        }
        for pattern_hash, queries in sorted(
            query_groups.items(),
            key=lambda x: -len(x[1])
        )[:20]  # Top 20 groups
    ]

    return {
        "suggestions": merged,
        "perQuery": per_query,
        "workloadStats": workload_stats,
        "topPatterns": top_patterns,
        "groupedQueries": grouped_queries,
        "workloadRecommendations": workload_recommendations,
    }


def _generate_workload_recommendations(
    pattern_counts: Dict[str, int],
    merged_suggestions: List[Dict[str, Any]],
    query_groups: Dict[str, List[Dict[str, Any]]]
) -> List[Dict[str, Any]]:
    """
    Generate workload-level optimization recommendations based on detected patterns.
    """
    recommendations = []

    # Recommendation: SELECT * is common
    if pattern_counts.get("SELECT_STAR", 0) > 2:
        recommendations.append({
            "title": "Multiple queries use SELECT *",
            "description": f"{pattern_counts['SELECT_STAR']} queries use SELECT * which can fetch unnecessary data",
            "impact": "medium",
            "action": "Replace SELECT * with explicit column lists to reduce I/O",
            "affectedQueries": pattern_counts["SELECT_STAR"],
        })

    # Recommendation: Missing WHERE clauses
    if pattern_counts.get("NO_WHERE_CLAUSE", 0) > 1:
        recommendations.append({
            "title": "Queries without WHERE clauses detected",
            "description": f"{pattern_counts['NO_WHERE_CLAUSE']} queries scan entire tables",
            "impact": "high",
            "action": "Add WHERE clauses to filter rows and reduce data scanned",
            "affectedQueries": pattern_counts["NO_WHERE_CLAUSE"],
        })

    # Recommendation: Large sequential scans
    if pattern_counts.get("LARGE_SEQ_SCAN", 0) > 0:
        recommendations.append({
            "title": "Large sequential scans detected",
            "description": f"{pattern_counts['LARGE_SEQ_SCAN']} queries perform full table scans on large tables",
            "impact": "high",
            "action": "Add indexes on frequently filtered/joined columns",
            "affectedQueries": pattern_counts["LARGE_SEQ_SCAN"],
        })

    # Recommendation: N+1 pattern (many similar queries)
    for pattern_hash, queries in query_groups.items():
        if len(queries) > 10:  # Potential N+1 query pattern
            recommendations.append({
                "title": "Potential N+1 query pattern detected",
                "description": f"{len(queries)} similar queries detected, possibly executed in a loop",
                "impact": "high",
                "action": "Consider batching these queries or using JOINs to fetch data in fewer round trips",
                "affectedQueries": len(queries),
            })
            break  # Only report once

    # Recommendation: Top index suggestions from merged results
    top_indexes = [s for s in merged_suggestions if s.get("kind") == "index"][:3]
    if top_indexes:
        for idx, index_sugg in enumerate(top_indexes, 1):
            recommendations.append({
                "title": f"High-impact index #{idx}: {index_sugg.get('title', 'Unknown')}",
                "description": index_sugg.get("rationale", ""),
                "impact": index_sugg.get("impact", "medium"),
                "action": " ".join(index_sugg.get("statements", [])),
                "affectedQueries": index_sugg.get("frequency", 1),
                "score": index_sugg.get("score", 0.0),
            })

    # Sort by impact and affected queries
    impact_order = {"high": 3, "medium": 2, "low": 1}
    recommendations.sort(
        key=lambda x: (impact_order.get(x.get("impact", "low"), 0), x.get("affectedQueries", 0)),
        reverse=True
    )

    return recommendations[:10]  # Top 10 recommendations













"""
Core query optimizer module for deterministic SQL rewrite and index suggestions.

This module does not execute any DDL. It only produces suggestions as text and
structured metadata based on static SQL analysis, optional execution plans, and
schema/stats metadata fetched from the database catalogs.

Design goals:
- Deterministic output for identical inputs (no randomness, no time-based data)
- Pure functions with full typing for testability
- Clear, small heuristics that are easy to reason about
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from app.core import db as db_core
from app.core.config import settings

# ---------- Public types ----------

@dataclass(frozen=True)
class Suggestion:
    """Single optimization suggestion.

    Fields are deliberately simple to keep JSON responses stable and predictable.
    """

    kind: str  # "rewrite" | "index"
    title: str
    rationale: str
    impact: str  # "low" | "medium" | "high"
    confidence: float  # 0.0 .. 1.0 (will be rounded when serializing)
    statements: List[str]
    alt_sql: Optional[str] = None
    safety_notes: Optional[str] = None
    # Extended advisory fields (EPIC A)
    score: Optional[float] = None
    reason: Optional[str] = None
    estReductionPct: Optional[float] = None
    estIndexWidthBytes: Optional[int] = None


# ---------- Helpers ----------

def _normalize_table_name(name: str) -> str:
    s = (name or "").strip()
    if not s:
        return s
    # Strip quotes to normalize; keep schema qualification if present
    return s.replace('"', "")


def _extract_eq_and_range_filters(filters: List[str]) -> Tuple[List[Tuple[str, str]], List[Tuple[str, str]]]:
    """Extract equality and range predicates in a simple, deterministic way.

    Returns:
        (eq, rng) where each is a list of (table_or_alias_opt, column_name)
    """
    eq: List[Tuple[str, str]] = []
    rng: List[Tuple[str, str]] = []
    for f in filters or []:
        s = f or ""
        # table.column = literal
        for tbl, col, _q in re.findall(
            r"\b([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(['\"]?)[^\s)]+\3",
            s,
        ):
            eq.append((tbl, col))
        # column = literal (unqualified)
        for col, _q in re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(['\"]?)[^\s)]+\2", s):
            eq.append(("", col))

        # Range predicates: try to detect a left-hand column
        if re.search(r"(<=|>=|<|>|\bBETWEEN\b)", s, re.IGNORECASE):
            m = re.search(
                r"\b([A-Za-z_][A-Za-z0-9_]*)(?:\.([A-Za-z_][A-Za-z0-9_]*))?\s*(?:<=|>=|<|>|BETWEEN)",
                s,
                re.IGNORECASE,
            )
            if m:
                tbl = m.group(1) if m.group(2) else ""
                col = m.group(2) or m.group(1)
                rng.append((tbl, col))

    # Deduplicate preserving order
    def _dedupe(items: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
        seen: set[Tuple[str, str]] = set()
        out: List[Tuple[str, str]] = []
        for it in items:
            if it not in seen:
                seen.add(it)
                out.append(it)
        return out

    return _dedupe(eq), _dedupe(rng)


def _extract_join_keys(joins: List[Dict[str, Any]]) -> List[Tuple[str, str]]:
    keys: List[Tuple[str, str]] = []
    for j in joins or []:
        cond = (j.get("condition") or "")
        for m in re.findall(
            r"\b([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)\s*=\s*([A-Za-z_][A-Za-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)",
            cond,
        ):
            keys.append((f"{m[0]}.{m[1]}", f"{m[2]}.{m[3]}"))
    return keys


def _extract_order_group(ast_info: Dict[str, Any]) -> Tuple[List[str], List[str]]:
    order = [s or "" for s in (ast_info.get("order_by") or [])]
    group = [s or "" for s in (ast_info.get("group_by") or [])]
    return order, group


def _index_name(table: str, cols: List[str]) -> str:
    safe_table = re.sub(r"[^A-Za-z0-9_]+", "_", table or "tbl")
    safe_cols = [re.sub(r"[^A-Za-z0-9_]+", "_", c) for c in cols]
    name = f"idx_{safe_table}_" + "_".join(safe_cols)
    return name.lower()[:63]  # respect PG identifier length


def _existing_index_covers(existing: List[Dict[str, Any]], cols: List[str]) -> bool:
    target = [c.lower() for c in cols]
    for ix in existing or []:
        ix_cols = [str(c).lower() for c in (ix.get("columns") or [])]
        if ix_cols[: len(target)] == target:
            return True
    return False


def _table_rows(stats: Dict[str, Any], table: str) -> Optional[float]:
    t = (stats or {}).get(table) or {}
    return t.get("rows")


# ---------- Rewrites ----------

def suggest_rewrites(ast_info: Dict[str, Any], schema: Dict[str, Any]) -> List[Suggestion]:
    suggestions: List[Suggestion] = []

    # SELECT * -> explicit projection
    cols = ast_info.get("columns") or []
    if any(c.get("name") == "*" for c in cols):
        tables = ast_info.get("tables") or []
        first_table = (tables[0].get("name") if tables else None) or ""
        # If schema available, project first few columns deterministically
        explicit_cols: List[str] = []
        if schema and first_table:
            sch_tbls = {t.get("name"): t for t in (schema.get("tables") or [])}
            tinfo = sch_tbls.get(first_table)
            if tinfo:
                explicit_cols = [
                    (c.get("column_name") or c.get("name") or c.get("column"))
                    for c in (tinfo.get("columns") or [])
                    if (c.get("column_name") or c.get("name") or c.get("column"))
                ]
        proj = ", ".join(explicit_cols[:5]) if explicit_cols else "*"
        alt_sql = (
            "-- Replace SELECT * with explicit projection\n"
            f"/* projected */ SELECT {proj} FROM ..."
        )
        suggestions.append(
            Suggestion(
                kind="rewrite",
                title="Replace SELECT * with explicit columns",
                rationale="Explicit projections reduce I/O and improve index-only scan chances.",
                impact="low",
                confidence=0.9,
                statements=[],
                alt_sql=alt_sql,
            )
        )

    # IN (subquery) -> EXISTS
    for f in (ast_info.get("filters") or []):
        if re.search(r"\bIN\s*\(\s*SELECT\b", f or "", re.IGNORECASE):
            alt = re.sub(r"\bIN\s*\(\s*SELECT\b", "EXISTS (SELECT", f or "", flags=re.IGNORECASE)
            suggestions.append(
                Suggestion(
                    kind="rewrite",
                    title="Consider EXISTS instead of IN (subquery)",
                    rationale="EXISTS can short-circuit and avoid de-duplication work.",
                    impact="medium",
                    confidence=0.7,
                    statements=[],
                    alt_sql=f"-- Example rewrite\n... WHERE {alt} ...",
                )
            )

    # De-correlate simple subqueries (advice only)
    for f in (ast_info.get("filters") or []):
        if re.search(r"\bEXISTS\s*\(\s*SELECT\b", f or "", re.IGNORECASE):
            suggestions.append(
                Suggestion(
                    kind="rewrite",
                    title="Consider de-correlating subquery",
                    rationale="Unnest simple EXISTS subqueries to enable better join planning.",
                    impact="medium",
                    confidence=0.6,
                    statements=[],
                    alt_sql="-- Move correlated filters into JOIN conditions when equivalent",
                )
            )

    # ORDER BY ... LIMIT ... -> ensure index-compatible ordering (Top-N)
    order = ast_info.get("order_by") or []
    limit = ast_info.get("limit")
    if order and isinstance(limit, int):
        suggestions.append(
            Suggestion(
                kind="rewrite",
                title="Align ORDER BY with index to support Top-N",
                rationale="Matching order-by with an index enables early termination.",
                impact="medium",
                confidence=0.8,
                statements=[],
                alt_sql="-- Ensure leading index columns match ORDER BY direction",
            )
        )

    # Filter pushdown suggestion (advice only)
    if (ast_info.get("filters") or []) and (ast_info.get("group_by") or []):
        suggestions.append(
            Suggestion(
                kind="rewrite",
                title="Push filters below GROUP BY/CTEs when safe",
                rationale="Pushing predicates earlier reduces scanned rows before aggregation.",
                impact="medium",
                confidence=0.6,
                statements=[],
                alt_sql="-- Apply WHERE conditions inside subqueries to reduce input size",
            )
        )

    # Subquery to JOIN transformation
    filters = ast_info.get("filters") or []
    for f in filters:
        f_str = f or ""
        # Detect correlated subquery in WHERE clause
        if re.search(r'WHERE\s+[^=<>!]+\s*=\s*\(SELECT\s+\w+\s+FROM', f_str, re.IGNORECASE):
            suggestions.append(
                Suggestion(
                    kind="rewrite",
                    title="Consider converting correlated subquery to JOIN",
                    rationale="JOINs are often more efficient than correlated subqueries and enable better query planning.",
                    impact="high",
                    confidence=0.75,
                    statements=[],
                    alt_sql="-- Convert: WHERE col = (SELECT ... FROM t2 WHERE t2.id = t1.id)\n-- To: JOIN t2 ON t2.id = t1.id WHERE col = t2.col",
                )
            )

    # DISTINCT with GROUP BY
    columns = ast_info.get("columns") or []
    has_distinct = any(c.get("distinct") for c in columns if isinstance(c, dict))
    if has_distinct and ast_info.get("group_by"):
        suggestions.append(
            Suggestion(
                kind="rewrite",
                title="Remove redundant DISTINCT when using GROUP BY",
                rationale="GROUP BY already ensures uniqueness, DISTINCT is redundant.",
                impact="low",
                confidence=0.9,
                statements=[],
                alt_sql="-- Remove DISTINCT keyword when GROUP BY is present",
            )
        )

    # LIKE patterns optimization
    for f in filters:
        f_str = f or ""
        # Check for LIKE patterns that can use indexes
        if re.search(r"LIKE\s+['\"]%[^%']+['\"]", f_str, re.IGNORECASE):
            suggestions.append(
                Suggestion(
                    kind="rewrite",
                    title="Consider using prefix index for LIKE pattern",
                    rationale="LIKE 'prefix%' can use index scans, but LIKE '%suffix' cannot.",
                    impact="medium",
                    confidence=0.7,
                    statements=[],
                    alt_sql="-- For LIKE 'prefix%', ensure column has index. For '%suffix', consider reverse index or full-text search.",
                )
            )
        # Check for inefficient LIKE patterns
        if re.search(r"LIKE\s+['\"][^'\"]*%[^'\"]*%[^'\"]*['\"]", f_str, re.IGNORECASE):
            suggestions.append(
                Suggestion(
                    kind="rewrite",
                    title="Multiple wildcards in LIKE prevent index usage",
                    rationale="LIKE patterns with multiple % or _ wildcards cannot use indexes efficiently.",
                    impact="high",
                    confidence=0.9,
                    statements=[],
                    alt_sql="-- Consider full-text search (tsvector) or pattern matching functions for complex patterns",
                )
            )

    # UNION vs UNION ALL
    # Try to get original SQL from ast_info, fallback to empty string
    raw_sql = ast_info.get("raw_sql") or ""
    if not raw_sql:
        # Reconstruct SQL from AST if available
        raw_sql = str(ast_info.get("sql") or "")
    sql_upper = raw_sql.upper()
    if "UNION" in sql_upper and "UNION ALL" not in sql_upper:
        suggestions.append(
            Suggestion(
                kind="rewrite",
                title="Consider UNION ALL instead of UNION if duplicates are acceptable",
                rationale="UNION removes duplicates which requires sorting. UNION ALL is faster if duplicates don't matter.",
                impact="high",
                confidence=0.8,
                statements=[],
                alt_sql="-- Replace UNION with UNION ALL if duplicate elimination is not needed",
            )
        )

    # COUNT(*) vs COUNT(column)
    for col in columns:
        col_str = str(col.get("name") or col)
        if re.search(r'COUNT\s*\(\s*\w+\s*\)', col_str, re.IGNORECASE) and not re.search(r'COUNT\s*\(\s*\*\s*\)', col_str, re.IGNORECASE):
            suggestions.append(
                Suggestion(
                    kind="rewrite",
                    title="Consider COUNT(*) instead of COUNT(column)",
                    rationale="COUNT(*) is typically faster than COUNT(column) as it doesn't need to check for NULLs.",
                    impact="low",
                    confidence=0.7,
                    statements=[],
                    alt_sql="-- Use COUNT(*) unless you specifically need to exclude NULL values",
                )
            )

    # ORDER BY without LIMIT on large result sets
    if ast_info.get("order_by") and not ast_info.get("limit"):
        suggestions.append(
            Suggestion(
                kind="rewrite",
                title="Consider adding LIMIT when using ORDER BY",
                rationale="ORDER BY without LIMIT can be expensive on large result sets. Add LIMIT if you only need top N rows.",
                impact="medium",
                confidence=0.6,
                statements=[],
                alt_sql="-- Add LIMIT clause to restrict result set size",
            )
        )

    # Multiple OR conditions that could be IN
    for f in filters:
        f_str = f or ""
        # Detect pattern: col = val1 OR col = val2 OR col = val3
        or_pattern = r'(\w+)\s*=\s*([^\s]+)\s+OR\s+\1\s*=\s*([^\s]+)\s+OR\s+\1\s*=\s*([^\s]+)'
        if re.search(or_pattern, f_str, re.IGNORECASE):
            suggestions.append(
                Suggestion(
                    kind="rewrite",
                    title="Convert multiple OR conditions to IN clause",
                    rationale="IN clause is more readable and can be optimized better by the query planner.",
                    impact="low",
                    confidence=0.8,
                    statements=[],
                    alt_sql="-- Convert: col = val1 OR col = val2 OR col = val3\n-- To: col IN (val1, val2, val3)",
                )
            )

    # NOT IN vs NOT EXISTS
    for f in filters:
        f_str = f or ""
        if re.search(r'\bNOT\s+IN\s*\(', f_str, re.IGNORECASE):
            suggestions.append(
                Suggestion(
                    kind="rewrite",
                    title="Consider NOT EXISTS instead of NOT IN with subquery",
                    rationale="NOT EXISTS handles NULLs better than NOT IN and can be more efficient.",
                    impact="medium",
                    confidence=0.75,
                    statements=[],
                    alt_sql="-- Convert: WHERE col NOT IN (SELECT ...)\n-- To: WHERE NOT EXISTS (SELECT 1 FROM ... WHERE ... = col)",
                )
            )

    # Implicit joins (comma-separated) to explicit JOINs
    tables = ast_info.get("tables") or []
    joins = ast_info.get("joins") or []
    if len(tables) > 1 and len(joins) == 0:
        # Check if filters contain join conditions
        join_conditions = []
        for f in filters:
            f_str = f or ""
            # Pattern: table1.col = table2.col
            if re.search(r'\w+\.\w+\s*=\s*\w+\.\w+', f_str):
                join_conditions.append(f_str)

        if join_conditions:
            suggestions.append(
                Suggestion(
                    kind="rewrite",
                    title="Convert implicit joins to explicit JOIN syntax",
                    rationale="Explicit JOIN syntax is clearer and gives better control over join order.",
                    impact="low",
                    confidence=0.8,
                    statements=[],
                    alt_sql="-- Convert: FROM t1, t2 WHERE t1.id = t2.id\n-- To: FROM t1 JOIN t2 ON t1.id = t2.id",
                )
            )

    return suggestions


# ---------- Index Advisor ----------

def suggest_indexes(
    ast_info: Dict[str, Any],
    schema: Dict[str, Any],
    stats: Dict[str, Any],
    options: Dict[str, Any],
) -> List[Suggestion]:
    suggestions: List[Suggestion] = []

    min_rows = int(options.get("min_index_rows", 10000))
    max_cols = int(options.get("max_index_cols", 3))

    tables = ast_info.get("tables") or []
    table_names = [t.get("name") for t in tables if t.get("name")]

    # Build existing indexes map
    existing_by_table: Dict[str, List[Dict[str, Any]]] = {}
    for t in (schema.get("tables") or []):
        existing_by_table[t.get("name")] = t.get("indexes") or []

    eq_keys, range_keys = _extract_eq_and_range_filters(ast_info.get("filters") or [])
    join_pairs = _extract_join_keys(ast_info.get("joins") or [])
    order_by, group_by = _extract_order_group(ast_info)

    for tname in table_names:
        norm = _normalize_table_name(tname or "")
        if not norm or norm.startswith("("):
            continue

        rows = _table_rows(stats, norm) or 0
        if rows < min_rows:
            # Skip tiny tables
            continue

        # Collect candidate columns for this table
        eq_cols = [c for (tbl, c) in eq_keys if (not tbl) or tbl == norm]
        rng_cols = [c for (tbl, c) in range_keys if (not tbl) or tbl == norm]

        # Include join keys referencing this table
        for a, b in join_pairs:
            at, ac = a.split(".")
            bt, bc = b.split(".")
            if at == norm:
                eq_cols.append(ac)
            if bt == norm:
                eq_cols.append(bc)

        # Order/group columns (strip direction keywords) -> just collect identifiers
        def _norm_dir(expr: str) -> Optional[str]:
            m = re.search(r"\b([A-Za-z_][A-Za-z0-9_]*)\.?([A-Za-z_][A-Za-z0-9_]*)?\b", expr)
            if not m:
                return None
            return (m.group(2) or m.group(1))

        order_cols = [c for c in (_norm_dir(e) for e in order_by) if c]
        group_cols = [c for c in (_norm_dir(e) for e in group_by) if c]

        # Build index column order: equality -> range -> order/group
        ordered_cols: List[str] = []
        for col in eq_cols:
            if col not in ordered_cols:
                ordered_cols.append(col)
        for col in rng_cols:
            if col not in ordered_cols:
                ordered_cols.append(col)
        for col in order_cols + group_cols:
            if col not in ordered_cols:
                ordered_cols.append(col)

        if not ordered_cols:
            continue
        ordered_cols = ordered_cols[: max_cols]

        # Skip if an existing index already covers this prefix
        existing = existing_by_table.get(norm) or []
        if _existing_index_covers(existing, ordered_cols):
            continue
        # EPIC A: score, filter, width, reason
        try:
            col_stats = db_core.get_column_stats("public", norm)
        except Exception:
            col_stats = {}
        est_width = 0
        for c in ordered_cols:
            est_width += int((col_stats.get(c) or {}).get("avg_width") or 0)
        base_score = 0.0
        for c in eq_cols:
            if c in ordered_cols:
                base_score += 1.0
        for c in rng_cols:
            if c in ordered_cols:
                base_score += 0.5
        for c in order_cols + group_cols:
            if c in ordered_cols:
                base_score += 0.25
        # Join boost (if any join column touches this table)
        if any((c in (a.split(".")[-1], b.split(".")[-1]) for (a, b) in join_pairs)):
            base_score *= float(settings.OPT_JOIN_COL_PRIOR_BOOST)
        # Width penalty
        width_penalty = 1.0
        if est_width > 0:
            width_penalty = max(0.1, (settings.OPT_INDEX_MAX_WIDTH_BYTES / max(est_width, 1)) ** 0.5)
        score = base_score * width_penalty
        # Estimated reduction percent (heuristic & deterministic)
        est_pct = 0.0
        if rows > 0:
            est_pct = min(100.0, (len(eq_cols) * 10.0) + (5.0 if order_cols else 0.0))
        # Filtering
        if est_pct < float(settings.OPT_SUPPRESS_LOW_GAIN_PCT):
            continue
        if est_width > int(settings.OPT_INDEX_MAX_WIDTH_BYTES):
            continue

        ix_name = _index_name(norm, ordered_cols)
        stmt = (
            f"CREATE INDEX CONCURRENTLY {ix_name} ON {norm} (" + ", ".join(ordered_cols) + ")"
        )  # suggestion only; do not execute
        reason = (
            f"Boosts equality({len(eq_cols)}), range({len(rng_cols)}), order/group({len(order_cols)+len(group_cols)})"
        )

        suggestions.append(
            Suggestion(
                kind="index",
                title=f"Index on {norm}({', '.join(ordered_cols)})",
                rationale="Supports equality, range, and ordering for faster lookups and Top-N.",
                impact=("high" if (len(eq_cols) >= 1 and order_cols) else "medium"),
                confidence=(0.7 if order_cols else 0.6),
                statements=[stmt],
                score=float(f"{score:.3f}"),
                reason=reason,
                estReductionPct=float(f"{est_pct:.3f}"),
                estIndexWidthBytes=est_width,
            )
        )

    return suggestions


def _round3(x: float) -> float:
    return float(f"{x:.3f}")


def summarize(suggestions: List[Suggestion]) -> Dict[str, Any]:
    impact_weight = {"low": 0.2, "medium": 0.5, "high": 0.8}
    if not suggestions:
        return {"summary": "No optimizations identified.", "score": 0.0}
    total = 0.0
    cnt = 0
    for s in suggestions[:5]:
        total += impact_weight.get(str(s.impact), 0.3) * float(s.confidence)
        cnt += 1
    score = _round3(total / max(cnt, 1))
    top = suggestions[0]
    return {
        "summary": f"Top suggestion: {top.title}",
        "score": score,
    }


def analyze(
    sql: str,
    ast_info: Dict[str, Any],
    plan: Optional[Dict[str, Any]],
    schema: Dict[str, Any],
    stats: Dict[str, Any],
    options: Dict[str, Any],
) -> Dict[str, Any]:
    """Produce deterministic optimization suggestions for a query.

    Returns a dictionary with keys: suggestions (list[Suggestion-like dict]) and summary (dict).
    """
    rewrites = suggest_rewrites(ast_info, schema)
    idx = suggest_indexes(ast_info, schema, stats, options)

    # Merge and deterministically order by title for stable output
    suggestions = rewrites + idx
    # Stable ordering: sort alphabetically by title for deterministic output
    suggestions.sort(key=lambda s: s.title)

    # Convert dataclass to plain dicts for API serialization stability
    out_suggestions: List[Dict[str, Any]] = []
    for s in suggestions:
        out_suggestions.append(
            {
                "kind": s.kind,
                "title": s.title,
                "rationale": s.rationale,
                "impact": s.impact,
                "confidence": _round3(float(s.confidence)),
                "statements": list(s.statements),
                "alt_sql": s.alt_sql,
                "safety_notes": s.safety_notes,
                # Extended fields (optional to preserve backwards compatibility)
                "score": _round3(float(getattr(s, 'score', 0.0))) if getattr(s, 'score', None) is not None else None,
                "reason": getattr(s, 'reason', None),
                "estReductionPct": _round3(float(getattr(s, 'estReductionPct', 0.0))) if getattr(s, 'estReductionPct', None) is not None else None,
                "estIndexWidthBytes": int(getattr(s, 'estIndexWidthBytes', 0)) if getattr(s, 'estIndexWidthBytes', None) is not None else None,
            }
        )

    return {
        "suggestions": out_suggestions,
        "summary": summarize(suggestions),
    }



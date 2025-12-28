import re
from typing import Any, Dict, List, Optional

from sqlglot import exp, parse_one

DIALECT = "duckdb"


def _sql(node: exp.Expression) -> str:
    try:
        return node.sql(dialect=DIALECT)
    except Exception:
        return node.sql()


def _alias_name_from_raw(raw: str, base_name: str) -> Optional[str]:
    s = raw.strip()
    # Try "AS alias"
    m = re.search(r"\bAS\s+([A-Za-z_][A-Za-z0-9_]*)\s*$", s, re.IGNORECASE)
    if m:
        return m.group(1)
    # Try trailing token alias (e.g., "users u")
    parts = s.split()
    if len(parts) >= 2:
        last = parts[-1]
        if last.lower() != base_name.lower() and "(" not in last and "." not in last:
            return last
    return None


def _relation_name_alias(rel: exp.Expression):
    if isinstance(rel, exp.Alias):
        inner = rel.this
        raw = _sql(rel)
        # get base name
        if isinstance(inner, exp.Table):
            base = inner.name
        elif isinstance(inner, exp.Subquery):
            base = _sql(inner)
        else:
            base = _sql(inner)
        # prefer AST alias; fallback to raw parse
        alias_expr = getattr(rel, "alias", None)
        alias = getattr(getattr(alias_expr, "this", None), "name", None) or getattr(
            alias_expr, "name", None
        )
        if not alias:
            alias = _alias_name_from_raw(raw, base)
        return base, alias, raw

    raw = _sql(rel)
    if isinstance(rel, exp.Table):
        base = rel.name
        alias_expr = getattr(rel, "alias", None)
        alias = getattr(getattr(alias_expr, "this", None), "name", None) or getattr(
            alias_expr, "name", None
        )
        if not alias:
            alias = _alias_name_from_raw(raw, base)
        return base, alias, raw

    # Subquery without alias: expose raw as name
    if isinstance(rel, exp.Subquery):
        base = _sql(rel)
        alias = _alias_name_from_raw(raw, base)
        return base, alias, raw

    # Fallback
    return _sql(rel), None, raw


def extract_tables(ast: exp.Expression):
    out = []
    if isinstance(ast, exp.Select):
        # FROM clause
        from_expr = ast.args.get("from")
        if from_expr:
            # Handle FROM clause which contains the table expressions
            if hasattr(from_expr, "expressions") and from_expr.expressions:
                for rel in from_expr.expressions:
                    name, alias, raw = _relation_name_alias(rel)
                    out.append({"name": name, "alias": alias, "raw": raw})
            elif hasattr(from_expr, "this") and from_expr.this:
                # Single table in FROM (this is the case for "FROM users")
                name, alias, raw = _relation_name_alias(from_expr.this)
                out.append({"name": name, "alias": alias, "raw": raw})
            else:
                # Fallback: try to extract from the FROM expression itself
                name, alias, raw = _relation_name_alias(from_expr)
                out.append({"name": name, "alias": alias, "raw": raw})

        # JOIN clauses
        joins = ast.args.get("joins") or []
        for join in joins:
            if isinstance(join, exp.Join):
                rel = join.this
                if rel:
                    name, alias, raw = _relation_name_alias(rel)
                    out.append({"name": name, "alias": alias, "raw": raw})
    else:
        # For non-SELECT queries, find the first table
        for t in ast.find_all(exp.Table):
            out.append({"name": t.name, "alias": None, "raw": _sql(t)})
            break
    return out


def extract_columns(ast: exp.Expression):
    cols = []
    if isinstance(ast, exp.Select):
        # Select list
        for proj in ast.expressions:
            if isinstance(proj, exp.Alias):
                alias_id = getattr(proj, "alias", None)
                alias = getattr(
                    getattr(alias_id, "this", None), "name", None
                ) or getattr(alias_id, "name", None)
                cols.append(
                    {"table": None, "name": alias or _sql(proj.this), "raw": _sql(proj)}
                )
            elif isinstance(proj, exp.Column):
                cols.append(
                    {
                        "table": (proj.table or None),
                        "name": proj.name,
                        "raw": _sql(proj),
                    }
                )
            elif isinstance(proj, exp.Star):
                q = getattr(proj, "this", None)
                qual = getattr(getattr(q, "this", None), "name", None) or getattr(
                    q, "name", None
                )
                cols.append({"table": (qual or None), "name": "*", "raw": _sql(proj)})
            else:
                cols.append({"table": None, "name": _sql(proj), "raw": _sql(proj)})

    return cols


def _extract_joins(ast: exp.Expression):
    out = []
    if not isinstance(ast, exp.Select):
        return out

    joins = ast.args.get("joins") or []
    for join in joins:
        if isinstance(join, exp.Join):
            on = join.args.get("on")
            cond = _sql(on) if on else None
            raw = _sql(join)
            jkind = join.args.get("kind") or join.args.get("side") or "JOIN"
            is_cross = "CROSS JOIN" in raw.upper()
            out.append(
                {
                    "type": "CROSS JOIN" if is_cross else str(jkind).upper(),
                    "right": _sql(join.this) if join.this else None,
                    "condition": cond,
                    "raw": raw,
                }
            )
    return out


def _extract_filters(select: exp.Select) -> List[str]:
    w = select.args.get("where")
    if not w:
        return []
    node = getattr(w, "this", w)
    return [_sql(node)]


def _extract_group_by(select: exp.Select) -> List[str]:
    g = select.args.get("group")
    exprs = getattr(g, "expressions", []) if g else []
    return [_sql(e) for e in exprs]


def _extract_order_by(select: exp.Select) -> List[str]:
    o = select.args.get("order")
    exprs = getattr(o, "expressions", []) if o else []
    return [_sql(e) for e in exprs]


def _extract_limit(select: exp.Select):
    lim = select.args.get("limit")
    if not lim:
        return None
    expr = getattr(lim, "expression", lim)
    try:
        return int(expr.name)
    except Exception:
        return _sql(expr)


def _has_restrictive_filter(filters: List[str]) -> bool:
    for f in filters or []:
        s = f or ""
        if re.search(r"[<>]", s):
            return True
        if re.search(r"\b(BETWEEN|IN\s*\(|LIKE|DATE|TIMESTAMP)\b", s, re.I):
            return True
        if "'" in s:
            return True
        if re.search(r"=\s*\d", s):
            return True
    return False


def parse_sql(sql: str) -> Dict[str, Any]:
    try:
        ast = parse_one(sql)
    except Exception as e:
        return {
            "type": "UNKNOWN",
            "sql": sql,
            "error": f"Error parsing SQL: {e}",
            "tables": [],
            "columns": [],
            "joins": [],
            "filters": [],
            "group_by": [],
            "order_by": [],
            "limit": None,
        }

    stmt_type = (getattr(ast, "key", "") or "").upper() or "UNKNOWN"

    info: Dict[str, Any] = {
        "type": stmt_type,
        "sql": sql,
        "tables": extract_tables(ast),
        "columns": extract_columns(ast),
        "joins": _extract_joins(ast),
        "filters": _extract_filters(ast) if isinstance(ast, exp.Select) else [],
        "group_by": _extract_group_by(ast) if isinstance(ast, exp.Select) else [],
        "order_by": _extract_order_by(ast) if isinstance(ast, exp.Select) else [],
        "limit": _extract_limit(ast) if isinstance(ast, exp.Select) else None,
    }

    return info


def lint_rules(ast_info: Dict[str, Any]) -> Dict[str, Any]:
    issues = []

    # Handle parse errors first
    if "error" in ast_info:
        issues.append(
            {
                "code": "PARSE_ERROR",
                "message": ast_info["error"],
                "severity": "high",
                "hint": "Check SQL syntax",
            }
        )
        return {"issues": issues, "summary": {"risk": "high"}}

    # Only apply full rule set to SELECT queries
    if ast_info.get("type") == "SELECT":
        # SELECT * rule
        if any(c.get("name") == "*" for c in ast_info.get("columns", [])):
            issues.append(
                {
                    "code": "SELECT_STAR",
                    "message": "Using SELECT * is not recommended",
                    "severity": "warn",
                    "hint": "Explicitly list required columns",
                }
            )

        # Join rules
        for join in ast_info.get("joins", []):
            join_type = join.get("type", "").upper()
            is_cross = join_type == "CROSS JOIN"

            if not is_cross and not join.get("condition"):
                issues.append(
                    {
                        "code": "MISSING_JOIN_ON",
                        "message": f"Missing ON clause in {join_type}",
                        "severity": "high",
                        "hint": "Add an ON clause with join conditions",
                    }
                )

            if not join.get("condition"):
                issues.append(
                    {
                        "code": "CARTESIAN_JOIN",
                        "message": "Cartesian product detected",
                        "severity": "info" if is_cross else "high",
                        "hint": "Add join conditions or confirm if CROSS JOIN is intended",
                    }
                )

        # Ambiguous column check
        tables = ast_info.get("tables", [])
        if len(tables) >= 2:
            columns = ast_info.get("columns", [])
            for col in columns:
                if not col.get("table") and col.get("name") != "*":
                    issues.append(
                        {
                            "code": "AMBIGUOUS_COLUMN",
                            "message": f"Column {col.get('name')} is not table-qualified",
                            "severity": "warn",
                            "hint": "Qualify column with table name or alias",
                        }
                    )

        # Large table check
        large_patterns = ["events", "logs", "transactions", "fact_"]
        filters = ast_info.get("filters", [])
        limit = ast_info.get("limit")
        has_restrictive_filter = _has_restrictive_filter(filters)

        for table in tables:
            table_name = (table.get("name") or "").lower()
            if any(pattern in table_name for pattern in large_patterns):
                if not has_restrictive_filter and not limit:
                    issues.append(
                        {
                            "code": "UNFILTERED_LARGE_TABLE",
                            "message": f"Large table {table_name} queried without restrictive filters",
                            "severity": "warn",
                            "hint": "Add WHERE clause with restrictive predicates or LIMIT",
                        }
                    )

        # Implicit cast check
        id_patterns = ["_id", "_key", "_fk"]
        for filter_expr in filters:
            filter_expr = filter_expr or ""
            if (
                any(pattern in filter_expr.lower() for pattern in id_patterns)
                and "'" in filter_expr
            ):
                issues.append(
                    {
                        "code": "IMPLICIT_CAST_PREDICATE",
                        "message": "Possible implicit cast in predicate",
                        "severity": "info",
                        "hint": "Ensure column and literal types match",
                    }
                )

        # Unused join check
        if len(tables) > 1:  # Only check if we have joins
            joined = [(t.get("alias") or t.get("name") or "") for t in tables[1:]]
            used = set()

            # Check if we have SELECT * - if so, all tables are considered used
            has_select_star = any(
                c.get("name") == "*" for c in ast_info.get("columns", [])
            )
            if not has_select_star:  # Only check for unused tables if not SELECT *
                # Check columns
                for col in ast_info.get("columns", []):
                    if col.get("table"):
                        used.add(col.get("table"))

                # Check filters, group by, and order by
                for s in (
                    (filters or [])
                    + (ast_info.get("group_by") or [])
                    + (ast_info.get("order_by") or [])
                ):
                    s = s or ""
                    for j in joined:
                        if j and j in s:
                            used.add(j)

                # Report unused joined tables
                for j in joined:
                    if j and j not in used:
                        issues.append(
                            {
                                "code": "UNUSED_JOINED_TABLE",
                                "message": f"Table {j} is joined but not used",
                                "severity": "warn",
                                "hint": "Remove unused join or use columns from the table",
                            }
                        )

    # Calculate risk level
    if "error" in ast_info:
        risk = "high"
    else:
        high_count = sum(1 for issue in issues if issue["severity"] == "high")
        warn_count = sum(1 for issue in issues if issue["severity"] == "warn")
        info_count = sum(1 for issue in issues if issue["severity"] == "info")

        if high_count > 0:
            risk = "high"
        elif warn_count > 1:  # Changed from > 0 to > 1 for valid queries
            risk = "medium"
        elif warn_count == 1 and info_count == 0:  # Single warning = low risk
            risk = "low"
        else:
            risk = "low"

    return {"issues": issues, "summary": {"risk": risk}}

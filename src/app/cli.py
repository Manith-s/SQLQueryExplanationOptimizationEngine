"""Command-line interface for Query Explain & Optimize.

Supports lint, explain, and optimize without running the API server.
Deterministic outputs; no DDL execution.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, List

from app.core import db, plan_heuristics, sql_analyzer, whatif


def _print(data: Dict[str, Any], fmt: str) -> None:
    if fmt == "json":
        print(json.dumps(data, separators=(",", ":"), ensure_ascii=False))
    else:
        # Minimal text formatting
        for k, v in data.items():
            print(f"{k}: {v}")


def _print_table(suggestions: List[Dict[str, Any]]) -> None:
    headers = [
        "Kind",
        "Title",
        "Impact",
        "Conf",
        "estBefore",
        "estAfter",
        "Delta",
    ]
    rows: List[List[str]] = []
    for s in suggestions:
        rows.append([
            str(s.get("kind", "")),
            str(s.get("title", ""))[:60],
            str(s.get("impact", "")),
            f"{float(s.get('confidence', 0.0)):.3f}",
            (f"{float(s.get('estCostBefore')):.3f}" if s.get("estCostBefore") is not None else ""),
            (f"{float(s.get('estCostAfter')):.3f}" if s.get("estCostAfter") is not None else ""),
            (f"{float(s.get('estCostDelta')):.3f}" if s.get("estCostDelta") is not None else ""),
        ])

    # compute column widths
    widths = [len(h) for h in headers]
    for r in rows:
        for i, cell in enumerate(r):
            widths[i] = max(widths[i], len(cell))

    def fmt_row(cols: List[str]) -> str:
        return "  ".join(c.ljust(widths[i]) for i, c in enumerate(cols))

    print(fmt_row(headers))
    print("  ".join("-" * w for w in widths))
    for r in rows:
        print(fmt_row(r))


def _print_markdown(out: Dict[str, Any]) -> None:
    print("# QEO Optimize Report")
    summ = out.get("summary") or {}
    if summ:
        print(f"\n**Summary**: {summ.get('summary','')} (score={summ.get('score','')})\n")
    suggs = out.get("suggestions") or []
    if suggs:
        print("\n## Top Suggestions\n")
        for s in suggs[:10]:
            reason = s.get("reason") or s.get("rationale")
            print(f"- **{s.get('title')}** — {reason}")


def cmd_lint(args: argparse.Namespace) -> int:
    sql = _read_sql(args)
    info = sql_analyzer.parse_sql(sql)
    out = sql_analyzer.lint_rules(info)
    _print(out, args.format)
    return 0


def cmd_explain(args: argparse.Namespace) -> int:
    sql = _read_sql(args)
    try:
        plan = db.run_explain(sql, analyze=args.analyze, timeout_ms=args.timeout_ms)
        warnings, metrics = plan_heuristics.analyze(plan)
        out = {"plan": plan, "warnings": warnings, "metrics": metrics}
        _print(out, args.format)
        return 0
    except Exception as e:
        _print({"error": str(e)}, args.format)
        return 3


def cmd_optimize(args: argparse.Namespace) -> int:
    from app.core.optimizer import analyze as opt_analyze

    sql = _read_sql(args)
    info = sql_analyzer.parse_sql(sql)
    if info.get("type") != "SELECT":
        _print({"ok": False, "message": "Only SELECT supported"}, args.format)
        return 2

    plan = None
    warnings: list = []
    metrics: dict = {}
    try:
        plan = db.run_explain(sql, analyze=args.analyze, timeout_ms=args.timeout_ms)
        warnings, metrics = plan_heuristics.analyze(plan)
    except Exception:
        plan = None

    schema = db.fetch_schema()
    try:
        tables = [t.get("name") for t in (info.get("tables") or []) if t.get("name")]
        stats = db.fetch_table_stats(tables, timeout_ms=args.timeout_ms)
    except Exception:
        stats = {}

    options = {
        "min_index_rows": args.min_rows_for_index,
        "max_index_cols": args.max_index_cols,
    }
    result = opt_analyze(sql, info, plan, schema, stats, options)
    suggestions = result.get("suggestions", [])[: args.top_k]

    ranking = "heuristic"
    whatif_info = {"enabled": False, "available": False, "trials": 0, "filteredByPct": 0}
    if args.what_if:
        try:
            wi = whatif.evaluate(sql, suggestions, timeout_ms=args.timeout_ms, force_enabled=True)
            ranking = wi.get("ranking", ranking)
            whatif_info = wi.get("whatIf", whatif_info)
            suggestions = wi.get("suggestions", suggestions)
        except Exception:
            ranking = "heuristic"
            whatif_info = {"enabled": True, "available": False, "trials": 0, "filteredByPct": 0}

    out = {
        "ok": True,
        "message": "ok",
        "suggestions": suggestions,
        "summary": result.get("summary", {}),
        "plan_warnings": warnings,
        "plan_metrics": metrics,
        "ranking": ranking,
        "whatIf": whatif_info,
    }
    # Optional diff: compute for top index if what-if enabled
    if getattr(args, "diff", False) and (whatif_info.get("enabled") and whatif_info.get("available")):
        try:
            from app.core.plan_diff import diff_plans
            from app.core.whatif import _parse_index_stmt  # type: ignore
            baseline = db.run_explain_costs(sql, timeout_ms=args.timeout_ms)
            top_index = next((s for s in suggestions if s.get("kind") == "index"), None)
            if top_index:
                stmt_list = top_index.get("statements") or []
                if stmt_list:
                    table, cols = _parse_index_stmt(stmt_list[0])
                    if table and cols:
                        with db.get_conn() as conn:
                            with conn.cursor() as cur:
                                cur.execute("SELECT hypopg_reset()")
                                cur.execute("SELECT * FROM hypopg_create_index(%s)", (f"CREATE INDEX ON {table} ({', '.join(cols)})",))
                                after = db.run_explain_costs(sql, timeout_ms=args.timeout_ms)
                                cur.execute("SELECT hypopg_reset()")
                                out["planDiff"] = diff_plans(baseline, after)
        except Exception:
            pass
    if getattr(args, "markdown", False):
        _print_markdown(out)
    elif getattr(args, "table", False):
        _print_table(suggestions)
    else:
        _print(out, args.format)
    return 0


def cmd_workload(args: argparse.Namespace) -> int:
    from app.core.workload import analyze_workload
    # read SQLs from file (one per line or separated by ';')
    sqls: List[str] = []
    with open(args.file, "r", encoding="utf-8") as f:
        data = f.read()
    # split by newline; keep non-empty
    for line in data.splitlines():
        s = line.strip()
        if s:
            sqls.append(s)
    res = analyze_workload(sqls, top_k=int(args.top_k), what_if=bool(args.what_if))
    out = {"ok": True, "suggestions": res.get("suggestions", []), "perQuery": res.get("perQuery", [])}
    if getattr(args, "markdown", False):
        print("# QEO Workload Report\n\n## Top Suggestions\n")
        for s in out["suggestions"]:
            print(f"- {s.get('title')} (score={s.get('score')}, freq={s.get('frequency')})")
    elif getattr(args, "table", False):
        _print_table(out.get("suggestions", []))
    else:
        _print(out, "json")
    return 0


def _read_sql(args: argparse.Namespace) -> str:
    if args.sql:
        return args.sql
    if args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            return f.read()
    data = sys.stdin.read()
    if not data.strip():
        raise SystemExit(2)
    return data


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="qeo", description="Query Explain & Optimize CLI")
    p.add_argument("--format", choices=["json", "text"], default="json")
    p.add_argument("--timeout-ms", type=int, default=10000)

    sp = p.add_subparsers(dest="cmd", required=True)

    lint = sp.add_parser("lint", help="Lint SQL")
    lint.add_argument("--sql")
    lint.add_argument("--file")
    lint.set_defaults(func=cmd_lint)

    ex = sp.add_parser("explain", help="Explain SQL plan")
    ex.add_argument("--sql")
    ex.add_argument("--file")
    ex.add_argument("--analyze", action="store_true")
    ex.set_defaults(func=cmd_explain)

    opt = sp.add_parser("optimize", help="Optimize SQL")
    opt.add_argument("--sql")
    opt.add_argument("--file")
    opt.add_argument("--analyze", action="store_true")
    opt.add_argument("--top-k", type=int, default=10)
    opt.add_argument("--min-rows-for-index", type=int, default=10000)
    opt.add_argument("--max-index-cols", type=int, default=3)
    opt.add_argument("--what-if", dest="what_if", action="store_true", help="Enable HypoPG cost-based what-if evaluation")
    opt.add_argument("--no-what-if", dest="what_if", action="store_false")
    opt.add_argument("--table", action="store_true", help="Print compact table of suggestions with cost deltas when available")
    opt.add_argument("--markdown", action="store_true", help="Print human-readable markdown report")
    opt.add_argument("--diff", action="store_true", help="Include plan diff for top suggestion when what-if ran")
    opt.set_defaults(what_if=False)
    opt.set_defaults(func=cmd_optimize)

    wl = sp.add_parser("workload", help="Analyze a file with multiple SQL statements (one per line)")
    wl.add_argument("--file", required=True)
    wl.add_argument("--top-k", type=int, default=10)
    wl.add_argument("--what-if", dest="what_if", action="store_true")
    wl.add_argument("--table", action="store_true")
    wl.add_argument("--markdown", action="store_true")
    wl.set_defaults(func=cmd_workload)

    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        code = args.func(args)
        sys.exit(code)
    except SystemExit as e:
        raise e
    except Exception as e:
        _print({"error": str(e)}, getattr(args, "format", "json"))
        sys.exit(3)



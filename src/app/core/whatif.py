"""Cost-based what-if evaluator using HypoPG (optional, read-only).

This module never executes DDL for real. It creates hypothetical indexes via HypoPG
only to measure planner cost deltas, and resets state after trials.
"""

from __future__ import annotations

import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Tuple

from app.core import db
from app.core.config import settings
from app.core.metrics import count_whatif_filtered, observe_whatif_trial


def _parse_index_stmt(stmt: str) -> Tuple[str, List[str]]:
    """Extract table and columns from a CREATE INDEX suggestion statement.

    Expected format created by optimizer: CREATE INDEX ... ON table (col1, col2)
    """
    m = re.search(r"\bON\s+([A-Za-z0-9_\.]+)\s*\(([^\)]+)\)", stmt, re.IGNORECASE)
    if not m:
        return "", []
    table = m.group(1)
    cols = [c.strip().strip('"') for c in m.group(2).split(",")]
    return table, cols


def _plan_total_cost(plan: Dict[str, Any]) -> float:
    try:
        return float(plan.get("Plan", {}).get("Total Cost", 0.0))
    except Exception:
        return 0.0


def _hypopg_available() -> bool:
    try:
        rows = db.run_sql("SELECT extname FROM pg_extension WHERE extname='hypopg'")
        return any(r and r[0] == 'hypopg' for r in rows)
    except Exception:
        return False


def evaluate(sql: str, suggestions: List[Dict[str, Any]], timeout_ms: int, force_enabled: bool | None = None) -> Dict[str, Any]:
    """Evaluate top-N index suggestions via HypoPG and return cost deltas.

    Returns dict with:
      - ranking: "cost_based"|"heuristic"
      - whatIf: { enabled, available, trials, filteredByPct }
      - enriched suggestions (may include estCostBefore/After/Delta)
    """
    enabled = bool(settings.WHATIF_ENABLED) if force_enabled is None else bool(force_enabled)
    if not enabled:
        return {
            "ranking": "heuristic",
            "whatIf": {"enabled": False, "available": False, "trials": 0, "filteredByPct": 0},
            "suggestions": suggestions,
        }

    available = _hypopg_available()
    if not available:
        return {
            "ranking": "heuristic",
            "whatIf": {"enabled": True, "available": False, "trials": 0, "filteredByPct": 0},
            "suggestions": suggestions,
        }

    # Baseline cost
    baseline = db.run_explain_costs(sql, timeout_ms=timeout_ms)
    base_cost = _plan_total_cost(baseline)

    # Select top-N index suggestions to trial
    max_trials = int(settings.WHATIF_MAX_TRIALS)
    min_pct = float(settings.WHATIF_MIN_COST_REDUCTION_PCT)
    # Prioritize by candidate score if present, else by impact, then title
    cand_all = [s for s in suggestions if s.get("kind") == "index"]
    def _rank_cand(s: Dict[str, Any]):
        impact_rank = {"high": 3, "medium": 2, "low": 1}
        return (-float(s.get("score") or 0.0), -impact_rank.get(s.get("impact"), 0), s.get("title") or "")
    cand_all.sort(key=_rank_cand)
    candidates = cand_all[: max_trials]

    enriched: List[Dict[str, Any]] = []
    filtered = 0

    for s in suggestions:
        enriched.append(dict(s))

    if not candidates:
        return {
            "ranking": "heuristic",
            "whatIf": {"enabled": True, "available": True, "trials": 0, "filteredByPct": 0},
            "suggestions": enriched,
        }

    # Run each candidate (parallel with separate connections)
    trials = 0
    results: Dict[str, Dict[str, float]] = {}
    start_global = time.time()
    parallelism = max(1, int(settings.WHATIF_PARALLELISM))

    def _trial(cand: Dict[str, Any]) -> Tuple[str, float, float]:
        stmt_list = cand.get("statements") or []
        table, cols = ("", [])
        if stmt_list:
            table, cols = _parse_index_stmt(stmt_list[0])
        if not table or not cols:
            return (cand.get("title") or "", base_cost, 0.0)
        try:
            with db.get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(f"SET LOCAL statement_timeout = {int(settings.WHATIF_TRIAL_TIMEOUT_MS)}")
                    cur.execute("SELECT hypopg_reset()")
                    cur.execute("SELECT * FROM hypopg_create_index(%s)", (f"CREATE INDEX ON {table} ({', '.join(cols)})",))
                    t0 = time.time()
                    plan = db.run_explain_costs(sql, timeout_ms=int(settings.WHATIF_TRIAL_TIMEOUT_MS))
                    observe_whatif_trial(time.time() - t0)
                    cur.execute("SELECT hypopg_reset()")
                    cost_after = _plan_total_cost(plan)
                    return (cand.get("title") or "", cost_after, (time.time() - t0) * 1000.0)
        except Exception:
            return (cand.get("title") or "", base_cost, 0.0)

    with ThreadPoolExecutor(max_workers=parallelism) as ex:
        futs = {ex.submit(_trial, c): c for c in candidates}
        best_delta_pct = 0.0
        for fut in as_completed(futs):
            ttl_ms = (time.time() - start_global) * 1000.0
            if ttl_ms > float(settings.WHATIF_GLOBAL_TIMEOUT_MS):
                break
            title, cost_after, trial_ms = fut.result()
            trials += 1
            results[title] = {"after": cost_after, "trialMs": trial_ms}
            # Early stop if marginal improvements are below threshold
            if base_cost > 0:
                delta_pct = max(0.0, (base_cost - cost_after) / base_cost * 100.0)
                best_delta_pct = max(best_delta_pct, delta_pct)
                if best_delta_pct < float(settings.WHATIF_EARLY_STOP_PCT):
                    # If even best is below threshold, skip remaining
                    break

    # Attach deltas
    for cand in candidates:
        r = results.get(cand.get("title"))
        if not r:
            continue
        cost_after = r["after"]
        delta = base_cost - cost_after
        for e in enriched:
            if e.get("title") == cand.get("title") and e.get("kind") == "index":
                e["estCostBefore"] = float(f"{base_cost:.3f}")
                e["estCostAfter"] = float(f"{cost_after:.3f}")
                e["estCostDelta"] = float(f"{delta:.3f}")
                e["trialMs"] = float(f"{r['trialMs']:.3f}")
                break

    # Filter by min reduction pct
    out: List[Dict[str, Any]] = []
    for e in enriched:
        d = float(e.get("estCostDelta") or 0.0)
        if d > 0 and base_cost > 0:
            pct = (d / base_cost) * 100.0
            if pct + 1e-9 < min_pct:
                filtered += 1
                continue
        out.append(e)

    count_whatif_filtered(filtered)

    # Ranking: sort primarily by cost delta desc, then keep prior deterministic tie-breakers
    def _rank_key(x: Dict[str, Any]):
        impact_rank = {"high": 3, "medium": 2, "low": 1}
        return (
            -float(x.get("estCostDelta") or 0.0),
            -impact_rank.get(x.get("impact"), 0),
            -float(x.get("confidence") or 0.0),
            str(x.get("title") or ""),
        )

    out.sort(key=_rank_key)

    return {
        "ranking": "cost_based",
        "whatIf": {"enabled": True, "available": True, "trials": trials, "filteredByPct": filtered},
        "suggestions": out,
    }




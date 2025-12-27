#!/usr/bin/env python3
"""Benchmark micro-suite (opt-in; requires RUN_DB_TESTS=1).

Seeds ephemeral schema `bench_qeo`, runs representative queries through internal
APIs, captures EXPLAIN ANALYZE timings and plan metrics, writes JSON/CSV reports
under bench/report/. Drops schema afterwards.

This script is safe and read-only for product schemas; DDL is confined to
`bench_qeo` only.
"""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from typing import Any, Dict

from app.core import db, plan_heuristics


def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def seed(schema: str) -> None:
    # Create ephemeral schema and small tables
    stmts = [
        f"CREATE SCHEMA IF NOT EXISTS {schema}",
        f"DROP TABLE IF EXISTS {schema}.users",
        f"DROP TABLE IF EXISTS {schema}.orders",
        f"CREATE TABLE {schema}.users(id serial primary key, email text, status text, created_at timestamp default now())",
        f"CREATE TABLE {schema}.orders(id serial primary key, user_id int, amount numeric, created_at timestamp default now(), status text)",
    ]
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            for s in stmts:
                cur.execute(s)
            # Populate small synthetic data
            cur.execute(f"INSERT INTO {schema}.users(email,status) SELECT 'u'||g, 'active' FROM generate_series(1,1000) g")
            cur.execute(f"INSERT INTO {schema}.orders(user_id,amount,status) SELECT (random()*999)::int+1, random()*100, 'paid' FROM generate_series(1,5000)")
            conn.commit()


def teardown(schema: str) -> None:
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
            conn.commit()


def run_queries(schema: str) -> Dict[str, Any]:
    cases = {
        "orders_topn": f"SELECT * FROM {schema}.orders WHERE user_id = 123 ORDER BY created_at DESC LIMIT 50",
        "users_exists": f"SELECT * FROM {schema}.orders WHERE user_id IN (SELECT id FROM {schema}.users) LIMIT 100",
    }
    report = {"cases": {}}
    for name, sql in cases.items():
        try:
            plan = db.run_explain(sql, analyze=True, timeout_ms=15000)
            warnings, metrics = plan_heuristics.analyze(plan)
            report["cases"][name] = {
                "sql": sql,
                "planning_time_ms": metrics.get("planning_time_ms", 0),
                "execution_time_ms": metrics.get("execution_time_ms", 0),
                "node_count": metrics.get("node_count", 0),
                "warnings": warnings,
            }
        except Exception as e:
            report["cases"][name] = {"error": str(e)}
    return report


def write_reports(data: Dict[str, Any]) -> None:
    out_dir = Path("bench/report")
    ensure_dir(out_dir)
    (out_dir / "report.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    # Flatten to CSV (basic)
    rows = []
    for name, d in (data.get("cases") or {}).items():
        rows.append(
            {
                "case": name,
                "planning_time_ms": d.get("planning_time_ms", 0),
                "execution_time_ms": d.get("execution_time_ms", 0),
                "node_count": d.get("node_count", 0),
                "error": d.get("error", ""),
            }
        )
    with (out_dir / "report.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["case", "planning_time_ms", "execution_time_ms", "node_count", "error"])
        w.writeheader()
        w.writerows(rows)


def main() -> None:
    if os.getenv("RUN_DB_TESTS") != "1":
        print("bench: RUN_DB_TESTS=1 required")
        return
    schema = "bench_qeo"
    try:
        seed(schema)
        data = run_queries(schema)
        write_reports(data)
        print("bench: report written to bench/report/")
    finally:
        teardown(schema)


if __name__ == "__main__":
    main()




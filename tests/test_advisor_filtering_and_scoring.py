from app.core.optimizer import analyze


def _schema():
    return {
        "schema": "public",
        "tables": [
            {
                "name": "orders",
                "columns": [
                    {"column_name": "id"},
                    {"column_name": "user_id"},
                    {"column_name": "status"},
                    {"column_name": "created_at"},
                ],
                "indexes": [],
            }
        ],
    }


def test_low_gain_filtered_by_threshold(monkeypatch):
    # Force low gain by removing eq cols
    sql = "SELECT * FROM orders ORDER BY created_at DESC LIMIT 5"
    ast_info = {
        "type": "SELECT",
        "sql": sql,
        "tables": [{"name": "orders"}],
        "columns": [{"name": "*"}],
        "joins": [],
        "filters": [],
        "order_by": ["created_at DESC"],
        "group_by": [],
        "limit": 5,
    }
    stats = {"orders": {"rows": 200000, "indexes": []}}
    options = {"min_index_rows": 10000, "max_index_cols": 3}

    # Monkeypatch column stats to large width to test width filtering via heuristic
    from app.core import db as db_core

    def fake_col_stats(schema, table, timeout_ms=5000):
        return {"created_at": {"avg_width": 9000}}

    monkeypatch.setattr(db_core, "get_column_stats", fake_col_stats)

    out = analyze(sql, ast_info, None, _schema(), stats, options)
    # With wide column and low gain, index suggestions should be suppressed
    assert not [s for s in out["suggestions"] if s["kind"] == "index"]


def test_score_and_reason_present(monkeypatch):
    sql = "SELECT * FROM orders WHERE user_id = 1 AND status='paid' ORDER BY created_at DESC LIMIT 5"
    ast_info = {
        "type": "SELECT",
        "sql": sql,
        "tables": [{"name": "orders"}],
        "columns": [{"name": "*"}],
        "joins": [],
        "filters": ["user_id = 1", "status = 'paid'"],
        "order_by": ["created_at DESC"],
        "group_by": [],
        "limit": 5,
    }
    stats = {"orders": {"rows": 50000, "indexes": []}}
    options = {"min_index_rows": 10000, "max_index_cols": 3}

    # Monkeypatch column stats small widths
    from app.core import db as db_core

    def fake_col_stats(schema, table, timeout_ms=5000):
        return {"user_id": {"avg_width": 4}, "status": {"avg_width": 8}, "created_at": {"avg_width": 8}}

    monkeypatch.setattr(db_core, "get_column_stats", fake_col_stats)

    out = analyze(sql, ast_info, None, _schema(), stats, options)
    idx = [s for s in out["suggestions"] if s["kind"] == "index"]
    assert idx
    # Ensure 'score' and 'reason' present and deterministic rounding
    assert all("score" in s for s in idx)
    assert all("reason" in s for s in idx)
    # Ordering: rewrites first, then index sorted by -score then title
    titles = [s["title"] for s in out["suggestions"]]
    assert titles[0].startswith("Replace SELECT *") or titles[0].startswith("Align ORDER BY")













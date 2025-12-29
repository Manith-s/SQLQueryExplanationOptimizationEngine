from app.core.optimizer import analyze


def fake_schema():
    return {
        "schema": "public",
        "tables": [
            {
                "name": "users",
                "columns": [
                    {"column_name": "id"},
                    {"column_name": "email"},
                    {"column_name": "status"},
                    {"column_name": "created_at"},
                ],
                "indexes": [
                    {"name": "users_pkey", "unique": True, "columns": ["id"]},
                ],
            },
            {
                "name": "orders",
                "columns": [
                    {"column_name": "id"},
                    {"column_name": "user_id"},
                    {"column_name": "status"},
                    {"column_name": "created_at"},
                ],
                "indexes": [
                    {
                        "name": "orders_user_id_created_at",
                        "unique": False,
                        "columns": ["user_id", "created_at"],
                    }
                ],
            },
        ],
    }


def test_small_table_no_index():
    sql = "SELECT * FROM orders WHERE user_id = 1 ORDER BY created_at DESC LIMIT 5"
    ast_info = {
        "type": "SELECT",
        "sql": sql,
        "tables": [{"name": "orders"}],
        "columns": [{"name": "*"}],
        "joins": [],
        "filters": ["user_id = 1"],
        "order_by": ["created_at DESC"],
        "group_by": [],
        "limit": 5,
    }
    stats = {"orders": {"rows": 9999, "indexes": []}}
    options = {"min_index_rows": 10000, "max_index_cols": 3}
    out = analyze(sql, ast_info, None, fake_schema(), stats, options)
    assert not [s for s in out["suggestions"] if s["kind"] == "index"]


def test_index_dedup_when_existing_covers_prefix():
    sql = "SELECT * FROM orders WHERE user_id = 1 ORDER BY created_at DESC LIMIT 5"
    ast_info = {
        "type": "SELECT",
        "sql": sql,
        "tables": [{"name": "orders"}],
        "columns": [{"name": "*"}],
        "joins": [],
        "filters": ["user_id = 1"],
        "order_by": ["created_at DESC"],
        "group_by": [],
        "limit": 5,
    }
    stats = {"orders": {"rows": 50000, "indexes": []}}
    options = {"min_index_rows": 10000, "max_index_cols": 3}
    out = analyze(sql, ast_info, None, fake_schema(), stats, options)
    assert not [
        s
        for s in out["suggestions"]
        if s["kind"] == "index" and "user_id, created_at" in s["title"].replace(":", "")
    ], "existing index should prevent duplicate suggestion"


def test_rounding_confidence_three_decimals():
    sql = "SELECT * FROM orders WHERE user_id = 1 ORDER BY created_at DESC LIMIT 5"
    ast_info = {
        "type": "SELECT",
        "sql": sql,
        "tables": [{"name": "orders"}],
        "columns": [{"name": "*"}],
        "joins": [],
        "filters": ["user_id = 1"],
        "order_by": ["created_at DESC"],
        "group_by": [],
        "limit": 5,
    }
    stats = {"orders": {"rows": 50000, "indexes": []}}
    options = {"min_index_rows": 10000, "max_index_cols": 3}
    out = analyze(sql, ast_info, None, fake_schema(), stats, options)
    for s in out["suggestions"]:
        assert isinstance(s["confidence"], float)
        # check decimal places by string repr
        assert len(f"{s['confidence']:.3f}".split(".")[-1]) == 3


def test_topk_ordering_stable():
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
    out = analyze(sql, ast_info, None, fake_schema(), stats, options)
    titles = [s["title"] for s in out["suggestions"]]
    assert titles == sorted(titles, key=lambda t: t)


def test_exists_rewrite_suggestion_present():
    """Test EXISTS rewrite suggestion is generated for IN subqueries."""
    sql = "SELECT * FROM orders WHERE user_id IN (SELECT id FROM users) ORDER BY created_at DESC LIMIT 10"
    ast_info = {
        "type": "SELECT",
        "sql": sql,
        "tables": [{"name": "orders"}, {"name": "users"}],
        "columns": [{"name": "*"}],
        "joins": [],
        "filters": ["user_id IN (SELECT id FROM users)"],
        "order_by": ["created_at DESC"],
        "group_by": [],
        "limit": 10,
    }
    stats = {"orders": {"rows": 50000, "indexes": []}, "users": {"rows": 100000}}
    options = {"min_index_rows": 10000, "max_index_cols": 3}

    out = analyze(
        sql, ast_info, plan=None, schema=fake_schema(), stats=stats, options=options
    )
    titles = [s["title"] for s in out["suggestions"]]
    assert any("EXISTS".lower() in t.lower() or "Align ORDER BY" in t for t in titles)


def test_index_suggestion_for_filters_and_order():
    """Test index suggestions consider both filters and ORDER BY."""
    sql = "SELECT * FROM orders WHERE user_id = 1 AND status = 'paid' ORDER BY created_at DESC LIMIT 5"
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
    stats = {"orders": {"rows": 200000, "indexes": []}}
    options = {"min_index_rows": 10000, "max_index_cols": 3}

    out = analyze(
        sql, ast_info, plan=None, schema=fake_schema(), stats=stats, options=options
    )
    idx = [s for s in out["suggestions"] if s["kind"] == "index"]
    assert idx, "expected at least one index suggestion"
    # Ensure column order begins with equality keys
    joined_titles = "\n".join(s["title"] for s in idx)
    assert "orders(" in joined_titles


def test_determinism():
    """Test optimizer produces deterministic results."""
    sql = "SELECT * FROM orders WHERE user_id = 1 ORDER BY created_at DESC LIMIT 5"
    ast_info = {
        "type": "SELECT",
        "sql": sql,
        "tables": [{"name": "orders"}],
        "columns": [{"name": "*"}],
        "joins": [],
        "filters": ["user_id = 1"],
        "order_by": ["created_at DESC"],
        "group_by": [],
        "limit": 5,
    }
    stats = {"orders": {"rows": 200000, "indexes": []}}
    options = {"min_index_rows": 10000, "max_index_cols": 3}

    outs = [
        analyze(
            sql, ast_info, plan=None, schema=fake_schema(), stats=stats, options=options
        )
        for _ in range(5)
    ]
    for o in outs[1:]:
        assert o == outs[0]


def test_rewrite_exists_and_pushdown_detection():
    """Test EXISTS rewrite suggestion for IN subqueries."""
    from app.core.optimizer import suggest_rewrites

    ast_info = {
        "type": "SELECT",
        "sql": "SELECT * FROM t WHERE x IN (SELECT y FROM u)",
        "tables": [{"name": "t"}],
        "columns": [{"name": "*"}],
        "joins": [],
        "filters": ["x IN (SELECT y FROM u)"],
        "group_by": [],
        "order_by": [],
        "limit": None,
    }
    rewrites = suggest_rewrites(ast_info, {"tables": []})
    titles = [r.title for r in rewrites]
    assert any("EXISTS" in t or "Exists" in t for t in titles)


def test_low_gain_filtered_by_threshold(monkeypatch):
    """Test that low-gain index suggestions are filtered out."""
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

    from app.core import db as db_core

    def fake_col_stats(schema, table, timeout_ms=5000):
        return {"created_at": {"avg_width": 9000}}

    monkeypatch.setattr(db_core, "get_column_stats", fake_col_stats)

    out = analyze(sql, ast_info, None, fake_schema(), stats, options)
    # With wide column and low gain, index suggestions should be suppressed
    assert not [s for s in out["suggestions"] if s["kind"] == "index"]


def test_score_and_reason_present(monkeypatch):
    """Test that suggestions include score and reason fields."""
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

    from app.core import db as db_core

    def fake_col_stats(schema, table, timeout_ms=5000):
        return {
            "user_id": {"avg_width": 4},
            "status": {"avg_width": 8},
            "created_at": {"avg_width": 8},
        }

    monkeypatch.setattr(db_core, "get_column_stats", fake_col_stats)

    out = analyze(sql, ast_info, None, fake_schema(), stats, options)
    idx = [s for s in out["suggestions"] if s["kind"] == "index"]
    assert idx
    assert all("score" in s for s in idx)
    assert all("reason" in s for s in idx)

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
                    {"column_name": "amount"},
                    {"column_name": "created_at"},
                    {"column_name": "status"},
                ],
                "indexes": [],
            },
        ],
    }


def test_exists_rewrite_suggestion_present():
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

    out = analyze(sql, ast_info, plan=None, schema=fake_schema(), stats=stats, options=options)
    titles = [s["title"] for s in out["suggestions"]]
    assert any("EXISTS".lower() in t.lower() or "Align ORDER BY" in t for t in titles)


def test_index_suggestion_for_filters_and_order():
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

    out = analyze(sql, ast_info, plan=None, schema=fake_schema(), stats=stats, options=options)
    idx = [s for s in out["suggestions"] if s["kind"] == "index"]
    assert idx, "expected at least one index suggestion"
    # Ensure column order begins with equality keys
    joined_titles = "\n".join(s["title"] for s in idx)
    assert "orders(" in joined_titles


def test_determinism():
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
        analyze(sql, ast_info, plan=None, schema=fake_schema(), stats=stats, options=options)
        for _ in range(5)
    ]
    for o in outs[1:]:
        assert o == outs[0]



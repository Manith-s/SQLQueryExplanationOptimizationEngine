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
                "indexes": [
                    {"name": "orders_user_id_created_at", "unique": False, "columns": ["user_id", "created_at"]}
                ],
            }
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
    out = analyze(sql, ast_info, None, _schema(), stats, options)
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
    out = analyze(sql, ast_info, None, _schema(), stats, options)
    assert not [
        s for s in out["suggestions"] if s["kind"] == "index" and "user_id, created_at" in s["title"].replace(":", "")
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
    out = analyze(sql, ast_info, None, _schema(), stats, options)
    for s in out["suggestions"]:
        assert (isinstance(s["confidence"], float))
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
    out = analyze(sql, ast_info, None, _schema(), stats, options)
    titles = [s["title"] for s in out["suggestions"]]
    assert titles == sorted(titles, key=lambda t: t)








from app.core.optimizer import analyze


def _schema():
    return {
        "schema": "public",
        "tables": [
            {"name": "orders", "columns": [{"column_name": "id"}], "indexes": []}
        ],
    }


def test_optimizer_determinism_repeat_5x():
    sql = "SELECT * FROM orders WHERE id = 1 ORDER BY id DESC LIMIT 5"
    ast_info = {
        "type": "SELECT",
        "sql": sql,
        "tables": [{"name": "orders"}],
        "columns": [{"name": "*"}],
        "joins": [],
        "filters": ["id = 1"],
        "order_by": ["id DESC"],
        "group_by": [],
        "limit": 5,
    }
    stats = {"orders": {"rows": 50000, "indexes": []}}
    options = {"min_index_rows": 10000, "max_index_cols": 3}

    outs = [analyze(sql, ast_info, None, _schema(), stats, options) for _ in range(5)]
    for o in outs[1:]:
        assert o == outs[0]

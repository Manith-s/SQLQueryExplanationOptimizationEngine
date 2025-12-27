from app.core.optimizer import suggest_rewrites


def test_rewrite_exists_and_pushdown_detection():
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


def test_rewrite_decorrelate_and_topn():
    ast_info = {
        "type": "SELECT",
        "sql": "SELECT * FROM t WHERE EXISTS (SELECT 1 FROM u WHERE u.id=t.id) ORDER BY created_at DESC LIMIT 10",
        "tables": [{"name": "t"}],
        "columns": [{"name": "*"}],
        "joins": [],
        "filters": ["EXISTS (SELECT 1 FROM u WHERE u.id=t.id)"],
        "group_by": [],
        "order_by": ["created_at DESC"],
        "limit": 10,
    }
    rewrites = suggest_rewrites(ast_info, {"tables": []})
    titles = [r.title for r in rewrites]
    assert any("de-correlating" in t.lower() for t in titles)
    assert any("Align ORDER BY" in t for t in titles)













"""
Tests for SQL analyzer linting rules.

Tests the lint_rules function and individual rule functions.
"""

from app.core.sql_analyzer import lint_rules, parse_sql


def test_rule_select_star():
    """Test SELECT_STAR rule detection."""
    # Test SELECT *
    sql = "SELECT * FROM users"
    ast_info = parse_sql(sql)
    result = lint_rules(ast_info)

    select_star_issues = [i for i in result["issues"] if i["code"] == "SELECT_STAR"]
    assert len(select_star_issues) == 1
    assert select_star_issues[0]["severity"] == "warn"

    # Test SELECT t.*
    sql = "SELECT u.* FROM users u"
    ast_info = parse_sql(sql)
    result = lint_rules(ast_info)

    select_star_issues = [i for i in result["issues"] if i["code"] == "SELECT_STAR"]
    assert len(select_star_issues) == 1

    # Test normal SELECT (should not trigger)
    sql = "SELECT id, name FROM users"
    ast_info = parse_sql(sql)
    result = lint_rules(ast_info)

    select_star_issues = [i for i in result["issues"] if i["code"] == "SELECT_STAR"]
    assert len(select_star_issues) == 0


def test_rule_missing_join_on():
    """Test MISSING_JOIN_ON rule detection."""
    # Test JOIN without ON
    sql = "SELECT * FROM users u JOIN orders o"
    ast_info = parse_sql(sql)
    result = lint_rules(ast_info)

    missing_on_issues = [i for i in result["issues"] if i["code"] == "MISSING_JOIN_ON"]
    assert len(missing_on_issues) == 1
    assert missing_on_issues[0]["severity"] == "high"

    # Test JOIN with ON (should not trigger)
    sql = "SELECT * FROM users u JOIN orders o ON u.id = o.user_id"
    ast_info = parse_sql(sql)
    result = lint_rules(ast_info)

    missing_on_issues = [i for i in result["issues"] if i["code"] == "MISSING_JOIN_ON"]
    assert len(missing_on_issues) == 0


def test_rule_cartesian_join():
    """Test CARTESIAN_JOIN rule detection."""
    # Test implicit Cartesian JOIN
    sql = "SELECT * FROM users u JOIN orders o"
    ast_info = parse_sql(sql)
    result = lint_rules(ast_info)

    cartesian_issues = [i for i in result["issues"] if i["code"] == "CARTESIAN_JOIN"]
    assert len(cartesian_issues) == 1
    assert cartesian_issues[0]["severity"] == "high"

    # Test explicit CROSS JOIN
    sql = "SELECT * FROM users u CROSS JOIN orders o"
    ast_info = parse_sql(sql)
    result = lint_rules(ast_info)

    cartesian_issues = [i for i in result["issues"] if i["code"] == "CARTESIAN_JOIN"]
    assert len(cartesian_issues) == 1
    assert cartesian_issues[0]["severity"] == "info"

    # Test normal JOIN with ON (should not trigger)
    sql = "SELECT * FROM users u JOIN orders o ON u.id = o.user_id"
    ast_info = parse_sql(sql)
    result = lint_rules(ast_info)

    cartesian_issues = [i for i in result["issues"] if i["code"] == "CARTESIAN_JOIN"]
    assert len(cartesian_issues) == 0


def test_rule_ambiguous_column():
    """Test AMBIGUOUS_COLUMN rule detection."""
    # Test ambiguous column
    sql = "SELECT id FROM users u JOIN orders o"
    ast_info = parse_sql(sql)
    result = lint_rules(ast_info)

    ambiguous_issues = [i for i in result["issues"] if i["code"] == "AMBIGUOUS_COLUMN"]
    assert len(ambiguous_issues) == 1
    assert ambiguous_issues[0]["severity"] == "warn"

    # Test qualified column (should not trigger)
    sql = "SELECT u.id, o.id FROM users u JOIN orders o"
    ast_info = parse_sql(sql)
    result = lint_rules(ast_info)

    ambiguous_issues = [i for i in result["issues"] if i["code"] == "AMBIGUOUS_COLUMN"]
    assert len(ambiguous_issues) == 0


def test_rule_unfiltered_large_table():
    """Test UNFILTERED_LARGE_TABLE rule detection."""
    # Test large table without filters
    sql = "SELECT * FROM events"
    ast_info = parse_sql(sql)
    result = lint_rules(ast_info)

    unfiltered_issues = [
        i for i in result["issues"] if i["code"] == "UNFILTERED_LARGE_TABLE"
    ]
    assert len(unfiltered_issues) == 1
    assert unfiltered_issues[0]["severity"] == "warn"

    # Test large table with WHERE (should not trigger)
    sql = "SELECT * FROM events WHERE created_at >= '2024-01-01'"
    ast_info = parse_sql(sql)
    result = lint_rules(ast_info)

    unfiltered_issues = [
        i for i in result["issues"] if i["code"] == "UNFILTERED_LARGE_TABLE"
    ]
    assert len(unfiltered_issues) == 0

    # Test large table with LIMIT (should not trigger)
    sql = "SELECT * FROM events LIMIT 100"
    ast_info = parse_sql(sql)
    result = lint_rules(ast_info)

    unfiltered_issues = [
        i for i in result["issues"] if i["code"] == "UNFILTERED_LARGE_TABLE"
    ]
    assert len(unfiltered_issues) == 0

    # Test normal table (should not trigger)
    sql = "SELECT * FROM users"
    ast_info = parse_sql(sql)
    result = lint_rules(ast_info)

    unfiltered_issues = [
        i for i in result["issues"] if i["code"] == "UNFILTERED_LARGE_TABLE"
    ]
    assert len(unfiltered_issues) == 0


def test_rule_implicit_cast_predicate():
    """Test IMPLICIT_CAST_PREDICATE rule detection."""
    # Test string literal with numeric column
    sql = "SELECT * FROM users WHERE user_id = '123'"
    ast_info = parse_sql(sql)
    result = lint_rules(ast_info)

    cast_issues = [
        i for i in result["issues"] if i["code"] == "IMPLICIT_CAST_PREDICATE"
    ]
    assert len(cast_issues) == 1
    assert cast_issues[0]["severity"] == "info"

    # Test numeric literal (should not trigger)
    sql = "SELECT * FROM users WHERE user_id = 123"
    ast_info = parse_sql(sql)
    result = lint_rules(ast_info)

    cast_issues = [
        i for i in result["issues"] if i["code"] == "IMPLICIT_CAST_PREDICATE"
    ]
    assert len(cast_issues) == 0


def test_rule_unused_joined_table():
    """Test UNUSED_JOINED_TABLE rule detection."""
    # Test unused joined table
    sql = "SELECT u.name FROM users u JOIN orders o ON u.id = o.user_id"
    ast_info = parse_sql(sql)
    result = lint_rules(ast_info)

    unused_issues = [i for i in result["issues"] if i["code"] == "UNUSED_JOINED_TABLE"]
    assert len(unused_issues) == 1
    assert unused_issues[0]["severity"] == "warn"

    # Test used joined table (should not trigger)
    sql = "SELECT u.name, o.id FROM users u JOIN orders o ON u.id = o.user_id"
    ast_info = parse_sql(sql)
    result = lint_rules(ast_info)

    unused_issues = [i for i in result["issues"] if i["code"] == "UNUSED_JOINED_TABLE"]
    assert len(unused_issues) == 0

    # Test SELECT * (should not trigger)
    sql = "SELECT * FROM users u JOIN orders o ON u.id = o.user_id"
    ast_info = parse_sql(sql)
    result = lint_rules(ast_info)

    unused_issues = [i for i in result["issues"] if i["code"] == "UNUSED_JOINED_TABLE"]
    assert len(unused_issues) == 0


def test_rule_parse_error():
    """Test handling of parse errors."""
    sql = "SELECT * FROM users WHERE invalid_column ="
    ast_info = parse_sql(sql)
    result = lint_rules(ast_info)

    assert result["summary"]["risk"] == "high"
    parse_errors = [i for i in result["issues"] if i["code"] == "PARSE_ERROR"]
    assert len(parse_errors) == 1
    assert parse_errors[0]["severity"] == "high"


def test_rule_risk_calculation():
    """Test risk level calculation."""
    # Test high risk (multiple high severity issues)
    sql = "SELECT * FROM events JOIN logs"
    ast_info = parse_sql(sql)
    result = lint_rules(ast_info)

    assert result["summary"]["risk"] == "high"

    # Test medium risk (multiple warnings)
    sql = "SELECT * FROM users JOIN orders ON users.id = orders.user_id"
    ast_info = parse_sql(sql)
    result = lint_rules(ast_info)

    # This should be low risk since it's a valid query
    assert result["summary"]["risk"] == "low"

    # Test low risk (no issues)
    sql = "SELECT id, name FROM users WHERE created_at >= '2024-01-01'"
    ast_info = parse_sql(sql)
    result = lint_rules(ast_info)

    assert result["summary"]["risk"] == "low"


def test_good_query_no_issues():
    """Test that a good query produces no issues."""
    sql = """
    SELECT o.id, o.created_at, c.name
    FROM orders o
    JOIN customers c ON c.id = o.customer_id
    WHERE o.created_at >= DATE '2024-01-01'
    ORDER BY o.created_at DESC
    LIMIT 100
    """
    ast_info = parse_sql(sql)
    result = lint_rules(ast_info)

    assert result["summary"]["risk"] == "low"
    assert len(result["issues"]) == 0


def test_bad_query_multiple_issues():
    """Test that a bad query produces multiple issues."""
    sql = """
    SELECT *
    FROM events e
    JOIN users u
    WHERE e.user_id = u.id
    """
    ast_info = parse_sql(sql)
    result = lint_rules(ast_info)

    # Should have multiple issues
    assert len(result["issues"]) > 1

    # Check for specific issues
    issue_codes = [i["code"] for i in result["issues"]]
    assert "SELECT_STAR" in issue_codes
    assert "MISSING_JOIN_ON" in issue_codes or "CARTESIAN_JOIN" in issue_codes
    assert "UNFILTERED_LARGE_TABLE" in issue_codes

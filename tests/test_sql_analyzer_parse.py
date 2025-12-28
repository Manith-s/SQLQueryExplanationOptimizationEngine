"""
Tests for SQL analyzer parsing functionality.

Tests the parse_sql function with various SQL query types and structures.
"""

from app.core.sql_analyzer import parse_sql


def test_parse_basic_select():
    """Test parsing basic SELECT query."""
    sql = "SELECT id, name FROM users"
    result = parse_sql(sql)

    assert result["type"] == "SELECT"
    assert len(result["tables"]) == 1
    assert result["tables"][0]["name"] == "users"
    assert result["tables"][0]["alias"] is None
    assert result["tables"][0]["raw"] == "users"

    assert len(result["columns"]) == 2
    assert result["columns"][0]["name"] == "id"
    assert result["columns"][0]["table"] is None
    assert result["columns"][1]["name"] == "name"
    assert result["columns"][1]["table"] is None


def test_parse_qualified_tables_aliases():
    """Test parsing with qualified tables and aliases."""
    sql = "SELECT u.id, u.name, c.email FROM users u JOIN customers c ON c.id = u.customer_id"
    result = parse_sql(sql)

    assert result["type"] == "SELECT"

    # Check tables
    assert len(result["tables"]) == 2
    users = next(t for t in result["tables"] if t["name"] == "users")
    customers = next(t for t in result["tables"] if t["name"] == "customers")
    assert users["alias"] == "u"
    assert customers["alias"] == "c"

    # Check columns
    assert len(result["columns"]) == 3
    assert result["columns"][0]["table"] == "u"
    assert result["columns"][0]["name"] == "id"
    assert result["columns"][1]["table"] == "u"
    assert result["columns"][1]["name"] == "name"
    assert result["columns"][2]["table"] == "c"
    assert result["columns"][2]["name"] == "email"

    # Check joins
    assert len(result["joins"]) == 1
    assert result["joins"][0]["type"] == "JOIN"
    assert "c.id = u.customer_id" in result["joins"][0]["condition"]


def test_parse_where_multiple_predicates():
    """Test parsing WHERE clause with multiple predicates."""
    sql = "SELECT * FROM orders WHERE created_at >= '2024-01-01' AND status = 'active'"
    result = parse_sql(sql)

    assert result["type"] == "SELECT"
    assert len(result["filters"]) == 1
    assert "created_at >= '2024-01-01'" in result["filters"][0]
    assert "status = 'active'" in result["filters"][0]


def test_parse_group_by_order_by_limit():
    """Test parsing GROUP BY, ORDER BY, and LIMIT clauses."""
    sql = """
    SELECT category, COUNT(*) as count
    FROM products
    GROUP BY category
    ORDER BY count DESC
    LIMIT 10
    """
    result = parse_sql(sql)

    assert result["type"] == "SELECT"
    assert len(result["tables"]) == 1
    assert result["tables"][0]["name"] == "products"

    assert len(result["columns"]) == 2
    assert result["columns"][0]["name"] == "category"
    assert "COUNT(*)" in result["columns"][1]["raw"]

    assert len(result["group_by"]) == 1
    assert "category" in result["group_by"][0]

    assert len(result["order_by"]) == 1
    assert "count DESC" in result["order_by"][0]

    assert result["limit"] == 10


def test_parse_inner_left_joins_with_on():
    """Test parsing INNER and LEFT JOINs with ON conditions."""
    sql = """
    SELECT o.id, c.name
    FROM orders o
    INNER JOIN customers c ON c.id = o.customer_id
    LEFT JOIN products p ON p.id = o.product_id
    """
    result = parse_sql(sql)

    assert result["type"] == "SELECT"
    assert len(result["joins"]) == 2

    # Check INNER JOIN
    inner_join = next(j for j in result["joins"] if j["type"] == "INNER")
    assert "c.id = o.customer_id" in inner_join["condition"]

    # Check LEFT JOIN
    left_join = next(j for j in result["joins"] if j["type"] == "LEFT")
    assert "p.id = o.product_id" in left_join["condition"]


def test_parse_complex_query():
    """Test parsing a complex query with multiple clauses."""
    sql = """
    SELECT
        u.name,
        COUNT(o.id) as order_count,
        SUM(o.total) as total_spent
    FROM users u
    LEFT JOIN orders o ON u.id = o.user_id
    WHERE u.created_at >= DATE '2024-01-01'
    GROUP BY u.id, u.name
    HAVING COUNT(o.id) > 0
    ORDER BY total_spent DESC
    LIMIT 100
    """
    result = parse_sql(sql)

    assert result["type"] == "SELECT"
    assert len(result["tables"]) == 2
    assert len(result["joins"]) == 1
    assert len(result["filters"]) == 1
    assert len(result["group_by"]) == 2
    assert len(result["order_by"]) == 1
    assert result["limit"] == 100


def test_parse_non_select_query():
    """Test parsing non-SELECT queries."""
    # INSERT query
    sql = "INSERT INTO users (name, email) VALUES ('John', 'john@example.com')"
    result = parse_sql(sql)

    assert result["type"] == "INSERT"
    assert len(result["tables"]) == 1
    assert result["tables"][0]["name"] == "users"


def test_parse_invalid_sql():
    """Test parsing invalid SQL."""
    sql = "SELECT * FROM users WHERE invalid_column ="
    result = parse_sql(sql)

    assert result["type"] == "UNKNOWN"
    assert "error" in result


def test_parse_empty_sql():
    """Test parsing empty SQL."""
    sql = ""
    result = parse_sql(sql)

    assert result["type"] == "UNKNOWN"
    assert "error" in result


def test_parse_sql_with_subquery():
    """Test parsing SQL with subquery."""
    sql = """
    SELECT u.name,
           (SELECT COUNT(*) FROM orders o WHERE o.user_id = u.id) as order_count
    FROM users u
    """
    result = parse_sql(sql)

    assert result["type"] == "SELECT"
    assert len(result["tables"]) == 1
    assert len(result["columns"]) == 2
    assert "order_count" in result["columns"][1]["raw"]


def test_parse_sql_with_cte():
    """Test parsing SQL with Common Table Expression."""
    sql = """
    WITH user_orders AS (
        SELECT user_id, COUNT(*) as order_count
        FROM orders
        GROUP BY user_id
    )
    SELECT u.name, uo.order_count
    FROM users u
    JOIN user_orders uo ON u.id = uo.user_id
    """
    result = parse_sql(sql)

    assert result["type"] == "SELECT"
    assert len(result["tables"]) >= 2  # users and user_orders CTE
    assert len(result["joins"]) == 1
    assert len(result["columns"]) == 2

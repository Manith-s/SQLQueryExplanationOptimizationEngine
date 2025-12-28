"""
Tests for the lint endpoint.

Tests the /lint endpoint with various scenarios and validation.
"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_lint_happy_path():
    """Test POST /lint happy path with valid SQL."""
    sql = """
    SELECT o.id, o.created_at, c.name
    FROM orders o
    JOIN customers c ON c.id = o.customer_id
    WHERE o.created_at >= DATE '2024-01-01'
    ORDER BY o.created_at DESC
    LIMIT 100
    """

    response = client.post("/api/v1/lint", json={"sql": sql})

    assert response.status_code == 200
    data = response.json()

    # Check response structure
    assert data["ok"] is True
    assert data["ast"] is not None
    assert "issues" in data
    assert "summary" in data

    # Check AST structure
    ast = data["ast"]
    assert ast["type"] == "SELECT"
    assert "tables" in ast
    assert "columns" in ast
    assert "joins" in ast
    assert "filters" in ast
    assert "group_by" in ast
    assert "order_by" in ast
    assert "limit" in ast

    # Check summary structure
    summary = data["summary"]
    assert "risk" in summary
    assert summary["risk"] in ["low", "medium", "high"]


def test_lint_empty_sql():
    """Test POST /lint with empty SQL."""
    response = client.post("/api/v1/lint", json={"sql": ""})

    assert response.status_code == 200
    data = response.json()

    assert data["ok"] is False
    assert data["ast"] is None
    assert len(data["issues"]) == 0
    assert data["summary"]["risk"] == "high"


def test_lint_whitespace_only_sql():
    """Test POST /lint with whitespace-only SQL."""
    response = client.post("/api/v1/lint", json={"sql": "   \n\t  "})

    assert response.status_code == 200
    data = response.json()

    assert data["ok"] is False
    assert data["ast"] is None
    assert data["summary"]["risk"] == "high"


def test_lint_invalid_sql():
    """Test POST /lint with invalid SQL."""
    sql = "SELECT * FROM users WHERE invalid_column ="

    response = client.post("/api/v1/lint", json={"sql": sql})

    assert response.status_code == 200
    data = response.json()

    assert data["ok"] is True  # Should still return ok=True for parse errors
    assert data["ast"] is not None
    assert data["ast"]["type"] == "UNKNOWN"
    assert "error" in data["ast"]
    assert data["summary"]["risk"] == "high"

    # Should have parse error issues
    parse_errors = [i for i in data["issues"] if i["code"] == "PARSE_ERROR"]
    assert len(parse_errors) == 1
    assert parse_errors[0]["severity"] == "high"


def test_lint_sql_with_issues():
    """Test POST /lint with SQL that has linting issues."""
    sql = "SELECT * FROM events JOIN logs"

    response = client.post("/api/v1/lint", json={"sql": sql})

    assert response.status_code == 200
    data = response.json()

    assert data["ok"] is True
    assert data["ast"]["type"] == "SELECT"
    assert len(data["issues"]) > 0
    assert data["summary"]["risk"] == "high"

    # Check for specific issues
    issue_codes = [i["code"] for i in data["issues"]]
    assert "SELECT_STAR" in issue_codes
    assert "MISSING_JOIN_ON" in issue_codes or "CARTESIAN_JOIN" in issue_codes
    assert "UNFILTERED_LARGE_TABLE" in issue_codes


def test_lint_missing_sql_field():
    """Test POST /lint with missing sql field."""
    response = client.post("/api/v1/lint", json={})

    assert response.status_code == 422  # Validation error


def test_lint_invalid_json():
    """Test POST /lint with invalid JSON."""
    response = client.post("/api/v1/lint", data="invalid json", headers={"Content-Type": "application/json"})

    assert response.status_code == 422  # Validation error


def test_lint_issue_structure():
    """Test that lint issues have the correct structure."""
    sql = "SELECT * FROM users"

    response = client.post("/api/v1/lint", json={"sql": sql})

    assert response.status_code == 200
    data = response.json()

    # Check issue structure
    for issue in data["issues"]:
        assert "code" in issue
        assert "message" in issue
        assert "severity" in issue
        assert "hint" in issue

        # Check severity values
        assert issue["severity"] in ["info", "warn", "high"]

        # Check that all fields are strings
        assert isinstance(issue["code"], str)
        assert isinstance(issue["message"], str)
        assert isinstance(issue["severity"], str)
        assert isinstance(issue["hint"], str)


def test_lint_good_query_no_issues():
    """Test that a good query produces no issues."""
    sql = """
    SELECT o.id, o.created_at, c.name
    FROM orders o
    JOIN customers c ON c.id = o.customer_id
    WHERE o.created_at >= DATE '2024-01-01'
    ORDER BY o.created_at DESC
    LIMIT 100
    """

    response = client.post("/api/v1/lint", json={"sql": sql})

    assert response.status_code == 200
    data = response.json()

    assert data["ok"] is True
    assert data["summary"]["risk"] == "low"
    assert len(data["issues"]) == 0


def test_lint_bad_query_multiple_issues():
    """Test that a bad query produces multiple issues."""
    sql = """
    SELECT *
    FROM events e
    JOIN users u
    WHERE e.user_id = u.id
    """

    response = client.post("/api/v1/lint", json={"sql": sql})

    assert response.status_code == 200
    data = response.json()

    assert data["ok"] is True
    assert len(data["issues"]) > 1

    # Check for specific issues
    issue_codes = [i["code"] for i in data["issues"]]
    assert "SELECT_STAR" in issue_codes
    assert "MISSING_JOIN_ON" in issue_codes or "CARTESIAN_JOIN" in issue_codes
    assert "UNFILTERED_LARGE_TABLE" in issue_codes


def test_lint_non_select_query():
    """Test linting non-SELECT queries."""
    sql = "INSERT INTO users (name, email) VALUES ('John', 'john@example.com')"

    response = client.post("/api/v1/lint", json={"sql": sql})

    assert response.status_code == 200
    data = response.json()

    assert data["ok"] is True
    assert data["ast"]["type"] == "INSERT"
    assert len(data["ast"]["tables"]) == 1
    assert data["ast"]["tables"][0]["name"] == "users"
    # Non-SELECT queries should have fewer linting rules applied
    assert len(data["issues"]) == 0 or len(data["issues"]) < 3


def test_lint_complex_query():
    """Test linting a complex query."""
    sql = """
    WITH user_orders AS (
        SELECT user_id, COUNT(*) as order_count
        FROM orders
        GROUP BY user_id
    )
    SELECT u.name, uo.order_count
    FROM users u
    JOIN user_orders uo ON u.id = uo.user_id
    WHERE u.created_at >= '2024-01-01'
    ORDER BY uo.order_count DESC
    LIMIT 50
    """

    response = client.post("/api/v1/lint", json={"sql": sql})

    assert response.status_code == 200
    data = response.json()

    assert data["ok"] is True
    assert data["ast"]["type"] == "SELECT"
    assert data["summary"]["risk"] == "low"  # Should be a good query

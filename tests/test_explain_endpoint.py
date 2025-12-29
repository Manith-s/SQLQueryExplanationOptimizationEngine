"""
Integration tests for the EXPLAIN endpoint.

These tests require a running PostgreSQL database and RUN_DB_TESTS=1.
"""

import os

import pytest
from fastapi.testclient import TestClient

from app.main import app

# Skip all tests unless RUN_DB_TESTS=1
pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "1",
    reason="Database tests disabled. Set RUN_DB_TESTS=1 to enable.",
)


@pytest.fixture
def client():
    """Get FastAPI test client."""
    return TestClient(app)


def test_explain_simple_select(client):
    """Test EXPLAIN on a simple SELECT query."""
    response = client.post("/api/v1/explain", json={"sql": "SELECT 1", "analyze": True})
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert "Plan" in data["plan"]
    assert isinstance(data["warnings"], list)
    assert "planning_time_ms" in data["metrics"]
    assert "execution_time_ms" in data["metrics"]
    assert "node_count" in data["metrics"]


def test_explain_catalog_query(client):
    """Test EXPLAIN on a catalog query that should show plan details."""
    response = client.post(
        "/api/v1/explain",
        json={"sql": "SELECT * FROM pg_class LIMIT 5", "analyze": True},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert "Plan" in data["plan"]
    assert isinstance(data["warnings"], list)


def test_explain_invalid_sql(client):
    """Test EXPLAIN with invalid SQL returns 400."""
    response = client.post(
        "/api/v1/explain",
        json={"sql": "SELECT * FROM nonexistent_table", "analyze": False},
    )
    assert response.status_code == 400
    data = response.json()
    assert "detail" in data


def test_explain_timeout(client):
    """Test EXPLAIN respects timeout parameter."""
    response = client.post(
        "/api/v1/explain",
        json={
            "sql": "SELECT pg_sleep(2)",
            "analyze": True,
            "timeout_ms": 100,  # 100ms timeout
        },
    )
    assert response.status_code == 400
    assert "timeout" in response.json()["detail"].lower()


def test_explain_large_result(client):
    """Test EXPLAIN with a query that should trigger warnings."""
    # Create a test table
    client.post(
        "/api/v1/explain",
        json={
            "sql": """
        CREATE TEMPORARY TABLE test_large AS
        SELECT * FROM generate_series(1, 200000) AS id;
        """
        },
    )

    # Query it with a sequential scan
    response = client.post(
        "/api/v1/explain",
        json={"sql": "SELECT * FROM test_large WHERE id > 0", "analyze": True},
    )

    assert response.status_code == 200
    data = response.json()

    # Should have SEQ_SCAN_LARGE warning
    assert any(w["code"] == "SEQ_SCAN_LARGE" for w in data["warnings"])


def test_explain_nl_fallback_on_bad_provider(client):
    """Test NL explanation falls back gracefully on bad provider."""
    os.environ["LLM_PROVIDER"] = "nonexistent"
    response = client.post(
        "/api/v1/explain",
        json={"sql": "SELECT 1", "analyze": False, "timeout_ms": 2000, "nl": True},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data.get("explanation") is None
    assert "failed" in (data.get("message") or "").lower()
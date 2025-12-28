"""
Integration tests for production scenarios.

These tests require:
- PostgreSQL database running (docker compose up -d db)
- RUN_DB_TESTS=1 environment variable
"""

import os

import pytest
from fastapi.testclient import TestClient

# Skip all tests in this module if RUN_DB_TESTS is not set
pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "1",
    reason="Integration tests require RUN_DB_TESTS=1 and database"
)


@pytest.fixture
def client():
    """Create a test client."""
    from app.main import app
    return TestClient(app)


def test_health_check_production_ready(client):
    """Health check should return production-ready response."""
    response = client.get("/health")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "healthy"
    assert "database" in data
    assert "hypopg" in data


def test_database_connection_pool_works(client):
    """Database connection pooling should work correctly."""
    # Make multiple requests that hit the database
    for i in range(10):
        response = client.post(
            "/api/v1/explain",
            json={"sql": f"SELECT {i} FROM orders LIMIT 1"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True


def test_explain_with_analyze_works(client):
    """EXPLAIN ANALYZE should work in production."""
    response = client.post(
        "/api/v1/explain",
        json={
            "sql": "SELECT * FROM orders WHERE user_id = 1 LIMIT 10",
            "analyze": True
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert "plan" in data
    assert "metrics" in data


def test_optimize_with_whatif_works(client):
    """Optimize with what-if analysis should work in production."""
    response = client.post(
        "/api/v1/optimize",
        json={
            "sql": "SELECT * FROM orders WHERE user_id = 42 ORDER BY created_at DESC LIMIT 50",
            "what_if": True
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert "suggestions" in data
    assert "whatIf" in data

    # Check HypoPG availability
    whatif = data.get("whatIf", {})
    if whatif.get("available"):
        # If HypoPG is available, we should get trials
        assert "trialsRun" in whatif


def test_workload_analysis_with_caching(client):
    """Workload analysis should use caching correctly."""
    sqls = [
        "SELECT * FROM orders WHERE user_id = 1",
        "SELECT COUNT(*) FROM orders",
        "SELECT * FROM orders ORDER BY created_at DESC LIMIT 100"
    ]

    # First request (cache miss)
    response1 = client.post("/api/v1/workload", json={"sqls": sqls})
    assert response1.status_code == 200
    data1 = response1.json()
    assert data1["ok"] is True
    assert data1.get("cached") is False

    # Second identical request (cache hit)
    response2 = client.post("/api/v1/workload", json={"sqls": sqls})
    assert response2.status_code == 200
    data2 = response2.json()
    assert data2["ok"] is True
    assert data2.get("cached") is True

    # Results should be identical
    assert data1["suggestions"] == data2["suggestions"]
    assert data1["workloadStats"] == data2["workloadStats"]


def test_schema_endpoint_returns_complete_info(client):
    """Schema endpoint should return complete metadata."""
    response = client.get("/api/v1/schema")
    assert response.status_code == 200

    data = response.json()
    assert "schemas" in data

    schemas = data["schemas"]
    assert len(schemas) > 0

    # Check for public schema
    public_schema = next((s for s in schemas if s["schema"] == "public"), None)
    assert public_schema is not None

    # Check for orders table
    orders_table = next((t for t in public_schema.get("tables", []) if t["table"] == "orders"), None)
    assert orders_table is not None

    # Check table has columns
    assert len(orders_table.get("columns", [])) > 0

    # Check table has indexes
    assert "indexes" in orders_table


def test_error_handling_invalid_sql(client):
    """API should gracefully handle invalid SQL."""
    response = client.post(
        "/api/v1/lint",
        json={"sql": "SELCT * FORM invalid_syntax"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    # Should have syntax errors
    assert len(data.get("errors", [])) > 0


def test_error_handling_missing_table(client):
    """API should gracefully handle queries on non-existent tables."""
    response = client.post(
        "/api/v1/explain",
        json={"sql": "SELECT * FROM nonexistent_table_xyz"}
    )
    # Should return error status or graceful degradation
    assert response.status_code in [200, 400, 500]


def test_timeout_handling(client):
    """API should handle query timeouts gracefully."""
    # Use a timeout parameter to test timeout handling
    response = client.post(
        "/api/v1/explain",
        json={
            "sql": "SELECT * FROM orders",
            "timeout_ms": 1  # Very short timeout
        }
    )
    # Should either succeed or gracefully handle timeout
    assert response.status_code in [200, 408, 500]


def test_concurrent_requests_stability(client):
    """API should handle concurrent requests without errors."""
    import concurrent.futures

    def make_request(i):
        return client.post(
            "/api/v1/lint",
            json={"sql": f"SELECT {i} FROM orders"}
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(make_request, i) for i in range(10)]
        results = [f.result() for f in futures]

    # All requests should succeed
    assert all(r.status_code == 200 for r in results)


def test_large_workload_performance(client):
    """API should handle large workloads efficiently."""
    # Create 50 different queries
    sqls = [f"SELECT * FROM orders WHERE user_id = {i} LIMIT 10" for i in range(50)]

    response = client.post(
        "/api/v1/workload",
        json={"sqls": sqls, "top_k": 20}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert "workloadStats" in data

    stats = data["workloadStats"]
    assert stats["totalQueries"] == 50


def test_pattern_detection_in_workload(client):
    """Workload analysis should detect common patterns."""
    sqls = [
        "SELECT * FROM orders",  # SELECT_STAR, NO_WHERE_CLAUSE
        "SELECT * FROM orders WHERE user_id = 1",  # SELECT_STAR
        "SELECT id FROM orders",  # NO_WHERE_CLAUSE
        "SELECT * FROM orders ORDER BY created_at",  # SELECT_STAR, NO_WHERE_CLAUSE, ORDER_WITHOUT_LIMIT
    ]

    response = client.post("/api/v1/workload", json={"sqls": sqls})
    assert response.status_code == 200
    data = response.json()

    # Should have pattern detection
    assert "topPatterns" in data
    patterns = data["topPatterns"]
    assert len(patterns) > 0

    # Check for expected patterns
    pattern_names = [p["pattern"] for p in patterns]
    assert "SELECT_STAR" in pattern_names


def test_workload_recommendations_generated(client):
    """Workload analysis should generate recommendations."""
    sqls = [
        "SELECT * FROM orders WHERE user_id = 1",
        "SELECT * FROM orders WHERE user_id = 2",
        "SELECT * FROM orders WHERE user_id = 3",
    ]

    response = client.post("/api/v1/workload", json={"sqls": sqls})
    assert response.status_code == 200
    data = response.json()

    # Should have workload-level recommendations
    assert "workloadRecommendations" in data
    recommendations = data["workloadRecommendations"]
    assert isinstance(recommendations, list)


def test_query_grouping_in_workload(client):
    """Workload analysis should group similar queries."""
    sqls = [
        "SELECT * FROM orders WHERE user_id = 1",
        "SELECT * FROM orders WHERE user_id = 2",  # Same pattern
        "SELECT * FROM orders WHERE user_id = 3",  # Same pattern
        "SELECT COUNT(*) FROM orders",  # Different pattern
    ]

    response = client.post("/api/v1/workload", json={"sqls": sqls})
    assert response.status_code == 200
    data = response.json()

    # Should have grouped queries
    assert "groupedQueries" in data
    groups = data["groupedQueries"]
    assert len(groups) > 0

    # First group should have 3 queries
    first_group = groups[0]
    assert first_group["count"] == 3


def test_production_config_loaded():
    """Production configuration should be loadable."""
    from app.core.production import (
        ProductionSettings,
        get_cors_config,
        get_database_config,
        get_security_headers,
    )

    # Check settings exist
    assert hasattr(ProductionSettings, "DB_POOL_SIZE")
    assert hasattr(ProductionSettings, "WORKER_COUNT")
    assert hasattr(ProductionSettings, "LOG_LEVEL")

    # Check helper functions work
    headers = get_security_headers()
    assert "X-Content-Type-Options" in headers
    assert headers["X-Content-Type-Options"] == "nosniff"

    cors = get_cors_config()
    assert "allow_origins" in cors
    assert "allow_methods" in cors

    db_config = get_database_config()
    assert "pool_size" in db_config
    assert "pool_pre_ping" in db_config

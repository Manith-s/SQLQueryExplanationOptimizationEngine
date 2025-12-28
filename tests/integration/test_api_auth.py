"""
Integration tests for API authentication.

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
    reason="Integration tests require RUN_DB_TESTS=1 and database",
)


@pytest.fixture
def client_with_auth(monkeypatch):
    """Create a test client with authentication enabled."""
    monkeypatch.setenv("AUTH_ENABLED", "true")
    monkeypatch.setenv("API_KEY", "test-integration-key")

    # Import after setting env vars
    from app.main import app

    return TestClient(app)


@pytest.fixture
def client_without_auth(monkeypatch):
    """Create a test client with authentication disabled."""
    monkeypatch.setenv("AUTH_ENABLED", "false")

    from app.main import app

    return TestClient(app)


def test_health_endpoint_no_auth_required(client_with_auth):
    """Health endpoint should work without authentication even when auth is enabled."""
    response = client_with_auth.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"


def test_lint_endpoint_requires_auth(client_with_auth):
    """Lint endpoint should require authentication when enabled."""
    response = client_with_auth.post("/api/v1/lint", json={"sql": "SELECT 1"})
    assert response.status_code == 403
    assert "Authentication required" in response.json()["detail"]


def test_lint_endpoint_with_valid_token(client_with_auth):
    """Lint endpoint should accept valid tokens."""
    headers = {"Authorization": "Bearer test-integration-key"}
    response = client_with_auth.post(
        "/api/v1/lint", json={"sql": "SELECT 1"}, headers=headers
    )
    assert response.status_code == 200


def test_lint_endpoint_with_invalid_token(client_with_auth):
    """Lint endpoint should reject invalid tokens."""
    headers = {"Authorization": "Bearer wrong-key"}
    response = client_with_auth.post(
        "/api/v1/lint", json={"sql": "SELECT 1"}, headers=headers
    )
    assert response.status_code == 403
    assert "Invalid API key" in response.json()["detail"]


def test_explain_endpoint_requires_auth(client_with_auth):
    """Explain endpoint should require authentication when enabled."""
    response = client_with_auth.post(
        "/api/v1/explain", json={"sql": "SELECT * FROM orders LIMIT 1"}
    )
    assert response.status_code == 403


def test_explain_endpoint_with_auth(client_with_auth):
    """Explain endpoint should work with valid authentication."""
    headers = {"Authorization": "Bearer test-integration-key"}
    response = client_with_auth.post(
        "/api/v1/explain", json={"sql": "SELECT * FROM orders LIMIT 1"}, headers=headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert "plan" in data


def test_optimize_endpoint_requires_auth(client_with_auth):
    """Optimize endpoint should require authentication when enabled."""
    response = client_with_auth.post(
        "/api/v1/optimize", json={"sql": "SELECT * FROM orders WHERE user_id = 1"}
    )
    assert response.status_code == 403


def test_optimize_endpoint_with_auth(client_with_auth):
    """Optimize endpoint should work with valid authentication."""
    headers = {"Authorization": "Bearer test-integration-key"}
    response = client_with_auth.post(
        "/api/v1/optimize",
        json={"sql": "SELECT * FROM orders WHERE user_id = 1"},
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert "suggestions" in data


def test_schema_endpoint_requires_auth(client_with_auth):
    """Schema endpoint should require authentication when enabled."""
    response = client_with_auth.get("/api/v1/schema")
    assert response.status_code == 403


def test_schema_endpoint_with_auth(client_with_auth):
    """Schema endpoint should work with valid authentication."""
    headers = {"Authorization": "Bearer test-integration-key"}
    response = client_with_auth.get("/api/v1/schema", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert "schemas" in data


def test_workload_endpoint_requires_auth(client_with_auth):
    """Workload endpoint should require authentication when enabled."""
    response = client_with_auth.post(
        "/api/v1/workload", json={"sqls": ["SELECT 1", "SELECT 2"]}
    )
    assert response.status_code == 403


def test_workload_endpoint_with_auth(client_with_auth):
    """Workload endpoint should work with valid authentication."""
    headers = {"Authorization": "Bearer test-integration-key"}
    response = client_with_auth.post(
        "/api/v1/workload",
        json={"sqls": ["SELECT * FROM orders LIMIT 1", "SELECT COUNT(*) FROM orders"]},
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert "suggestions" in data


def test_all_endpoints_work_without_auth_when_disabled(client_without_auth):
    """All endpoints should work without tokens when auth is disabled."""
    # Lint
    response = client_without_auth.post("/api/v1/lint", json={"sql": "SELECT 1"})
    assert response.status_code == 200

    # Explain
    response = client_without_auth.post(
        "/api/v1/explain", json={"sql": "SELECT * FROM orders LIMIT 1"}
    )
    assert response.status_code == 200

    # Optimize
    response = client_without_auth.post(
        "/api/v1/optimize", json={"sql": "SELECT * FROM orders LIMIT 1"}
    )
    assert response.status_code == 200

    # Schema
    response = client_without_auth.get("/api/v1/schema")
    assert response.status_code == 200

    # Workload
    response = client_without_auth.post("/api/v1/workload", json={"sqls": ["SELECT 1"]})
    assert response.status_code == 200


def test_auth_token_case_sensitive(client_with_auth):
    """API keys should be case sensitive."""
    headers = {"Authorization": "Bearer TEST-INTEGRATION-KEY"}  # Wrong case
    response = client_with_auth.post(
        "/api/v1/lint", json={"sql": "SELECT 1"}, headers=headers
    )
    assert response.status_code == 403


def test_bearer_scheme_required(client_with_auth):
    """Token must use Bearer scheme."""
    headers = {"Authorization": "test-integration-key"}  # Missing "Bearer"
    response = client_with_auth.post(
        "/api/v1/lint", json={"sql": "SELECT 1"}, headers=headers
    )
    assert response.status_code == 403

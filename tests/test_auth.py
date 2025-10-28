"""
Tests for API key authentication.

Verifies that Bearer token authentication works correctly for protected routes
and that health endpoints remain public.
"""

import os
import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    """Create test client for FastAPI app."""
    return TestClient(app)


@pytest.fixture(autouse=True)
def enable_auth():
    """Enable authentication for all tests in this module."""
    original_auth = os.environ.get("AUTH_ENABLED")
    original_key = os.environ.get("API_KEY")

    os.environ["AUTH_ENABLED"] = "true"
    os.environ["API_KEY"] = "test-key-12345"

    # Force reload of settings
    from app.core import config
    config.settings.AUTH_ENABLED = True
    config.settings.API_KEY = "test-key-12345"

    yield

    # Restore original values
    if original_auth:
        os.environ["AUTH_ENABLED"] = original_auth
    else:
        os.environ.pop("AUTH_ENABLED", None)

    if original_key:
        os.environ["API_KEY"] = original_key
    else:
        os.environ.pop("API_KEY", None)

    # Restore settings
    config.settings.AUTH_ENABLED = False
    config.settings.API_KEY = "dev-key-12345"


def test_health_endpoint_no_auth_required(client):
    """Test that /health endpoint does not require authentication."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


def test_healthz_endpoint_no_auth_required(client):
    """Test that /healthz endpoint does not require authentication."""
    response = client.get("/healthz")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


def test_root_endpoint_no_auth_required(client):
    """Test that root / endpoint does not require authentication."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "running"


def test_api_endpoint_without_token(client):
    """Test that API endpoints require authentication when enabled."""
    response = client.post("/api/v1/lint", json={"sql": "SELECT 1"})
    assert response.status_code == 403


def test_api_endpoint_with_invalid_token(client):
    """Test that invalid tokens are rejected."""
    headers = {"Authorization": "Bearer invalid-token"}
    response = client.post("/api/v1/lint", json={"sql": "SELECT 1"}, headers=headers)
    assert response.status_code == 403
    data = response.json()
    assert "Invalid API key" in data["detail"]


def test_api_endpoint_with_valid_token(client):
    """Test that valid tokens are accepted."""
    headers = {"Authorization": "Bearer test-key-12345"}
    response = client.post("/api/v1/lint", json={"sql": "SELECT 1"}, headers=headers)
    assert response.status_code == 200


def test_explain_endpoint_with_valid_token(client):
    """Test that explain endpoint accepts valid tokens."""
    headers = {"Authorization": "Bearer test-key-12345"}
    response = client.post(
        "/api/v1/explain",
        json={"sql": "SELECT * FROM orders LIMIT 1"},
        headers=headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True


def test_optimize_endpoint_with_valid_token(client):
    """Test that optimize endpoint accepts valid tokens."""
    headers = {"Authorization": "Bearer test-key-12345"}
    response = client.post(
        "/api/v1/optimize",
        json={"sql": "SELECT * FROM orders LIMIT 1"},
        headers=headers
    )
    assert response.status_code == 200


def test_schema_endpoint_with_valid_token(client):
    """Test that schema endpoint accepts valid tokens."""
    headers = {"Authorization": "Bearer test-key-12345"}
    response = client.get("/api/v1/schema", headers=headers)
    assert response.status_code == 200


def test_workload_endpoint_with_valid_token(client):
    """Test that workload endpoint accepts valid tokens."""
    headers = {"Authorization": "Bearer test-key-12345"}
    response = client.post(
        "/api/v1/workload",
        json={"sqls": ["SELECT 1"]},
        headers=headers
    )
    assert response.status_code == 200


def test_missing_bearer_prefix(client):
    """Test that tokens without Bearer prefix are rejected."""
    headers = {"Authorization": "test-key-12345"}
    response = client.post("/api/v1/lint", json={"sql": "SELECT 1"}, headers=headers)
    assert response.status_code == 403


def test_case_sensitive_token(client):
    """Test that token comparison is case-sensitive."""
    headers = {"Authorization": "Bearer TEST-KEY-12345"}  # Wrong case
    response = client.post("/api/v1/lint", json={"sql": "SELECT 1"}, headers=headers)
    assert response.status_code == 403


def test_auth_disabled_allows_all_requests():
    """Test that when auth is disabled, all requests are allowed."""
    # Temporarily disable auth
    os.environ["AUTH_ENABLED"] = "false"
    from app.core import config
    config.settings.AUTH_ENABLED = False

    client = TestClient(app)

    # Should work without token
    response = client.post("/api/v1/lint", json={"sql": "SELECT 1"})
    assert response.status_code == 200

    # Re-enable auth
    os.environ["AUTH_ENABLED"] = "true"
    config.settings.AUTH_ENABLED = True

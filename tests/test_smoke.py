"""
Smoke tests for the application.

Verifies that the app starts correctly and all routes are accessible.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    """Create test client for FastAPI app."""
    return TestClient(app)


def test_app_starts():
    """Test that the app can be imported and instantiated."""
    assert app is not None
    assert app.title == "SQL Query Explanation & Optimization Engine"


def test_root_endpoint(client):
    """Test the root endpoint returns basic info."""
    response = client.get("/")
    assert response.status_code == 200

    data = response.json()
    assert "name" in data
    assert "version" in data
    assert "status" in data
    assert data["status"] == "running"


def test_health_endpoint(client):
    """Test the health endpoint returns OK status."""
    response = client.get("/health")
    assert response.status_code == 200

    data = response.json()
    assert "status" in data
    assert data["status"] == "ok"


def test_lint_endpoint_exists(client):
    """Test that the lint endpoint exists and returns stub response."""
    response = client.post("/api/v1/lint", json={"sql": "SELECT * FROM users"})
    assert response.status_code == 200

    data = response.json()
    assert "message" in data
    assert "stub" in data["message"]


def test_explain_endpoint_exists(client):
    """Test that the explain endpoint exists and returns a response."""
    response = client.post("/api/v1/explain", json={"sql": "SELECT * FROM orders LIMIT 1"})
    assert response.status_code == 200

    data = response.json()
    assert "ok" in data
    assert data["ok"] is True


def test_optimize_endpoint_exists(client):
    """Test that the optimize endpoint exists and returns stub response."""
    response = client.post("/api/v1/optimize", json={"sql": "SELECT * FROM users"})
    assert response.status_code == 200

    data = response.json()
    assert "message" in data
    assert "stub" in data["message"]


def test_docs_endpoint_exists(client):
    """Test that the API docs endpoint is accessible."""
    response = client.get("/docs")
    assert response.status_code == 200

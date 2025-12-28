"""
Tests for natural language explanation using the dummy LLM provider.
"""

import os

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    """Get FastAPI test client."""
    return TestClient(app)

@pytest.fixture(autouse=True)
def use_dummy_provider():
    """Force dummy provider for all tests."""
    original = os.environ.get("LLM_PROVIDER")
    os.environ["LLM_PROVIDER"] = "dummy"
    yield
    if original:
        os.environ["LLM_PROVIDER"] = original
    else:
        del os.environ["LLM_PROVIDER"]

def test_explain_nl_simple(client):
    """Test NL explanation for a simple query."""
    response = client.post("/api/v1/explain", json={
        "sql": "SELECT * FROM users",
        "nl": True,
        "analyze": False
    })

    assert response.status_code == 200
    data = response.json()

    assert data["ok"] is True
    assert data["explanation"] is not None
    assert len(data["explanation"]) > 0
    assert data["explain_provider"] == "dummy"

def test_explain_nl_complex(client):
    """Test NL explanation for a complex query."""
    response = client.post("/api/v1/explain", json={
        "sql": """
        WITH user_stats AS (
            SELECT user_id, COUNT(*) as order_count
            FROM orders
            WHERE created_at >= NOW() - INTERVAL '30 days'
            GROUP BY user_id
        )
        SELECT u.name, u.email, s.order_count
        FROM users u
        JOIN user_stats s ON s.user_id = u.id
        WHERE s.order_count > 5
        ORDER BY s.order_count DESC
        LIMIT 10
        """,
        "nl": True,
        "analyze": True,
        "audience": "dba",
        "style": "detailed",
        "length": "long"
    })

    assert response.status_code == 200
    data = response.json()

    assert data["ok"] is True
    assert data["explanation"] is not None
    assert len(data["explanation"]) > 200  # Should be detailed
    assert data["explain_provider"] == "dummy"

def test_explain_nl_huge_plan(client):
    """Test NL explanation handles large plans gracefully."""
    # Create a huge fake plan
    huge_plan = {
        "Plan": {
            "Node Type": "Nested Loop",
            "Plans": [{"Node Type": "Seq Scan"}] * 1000
        }
    }

    response = client.post("/api/v1/explain", json={
        "sql": "SELECT 1",
        "nl": True,
        "analyze": False,
        "plan": huge_plan
    })

    assert response.status_code == 200
    data = response.json()

    assert data["ok"] is True
    assert data["explanation"] is not None
    assert len(data["explanation"]) < 5000  # Should be reasonably truncated

def test_explain_nl_invalid_provider(client):
    """Test graceful handling of invalid LLM provider."""
    # Set invalid provider
    os.environ["LLM_PROVIDER"] = "nonexistent"

    response = client.post("/api/v1/explain", json={
        "sql": "SELECT 1",
        "nl": True
    })

    assert response.status_code == 200
    data = response.json()

    assert data["ok"] is True
    assert data["explanation"] is None
    assert "failed" in data["message"].lower()

@pytest.mark.skipif(
    os.getenv("RUN_OLLAMA_TESTS") != "1",
    reason="Ollama tests disabled. Set RUN_OLLAMA_TESTS=1 to enable."
)
def test_explain_nl_ollama(client):
    """Test NL explanation using Ollama (when available)."""
    # Use Ollama provider
    os.environ["LLM_PROVIDER"] = "ollama"

    response = client.post("/api/v1/explain", json={
        "sql": "SELECT * FROM users WHERE active = true",
        "nl": True,
        "analyze": False
    })

    assert response.status_code == 200
    data = response.json()

    if data["explanation"] is not None:
        assert data["explain_provider"] == "ollama"
        assert len(data["explanation"]) > 0
    else:
        assert "failed" in data["message"].lower()


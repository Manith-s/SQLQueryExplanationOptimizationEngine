import os
import pytest
from fastapi.testclient import TestClient
from app.main import app


pytestmark = pytest.mark.integration


def _db_enabled() -> bool:
    return os.getenv("RUN_DB_TESTS", "0") == "1"


@pytest.mark.skipif(not _db_enabled(), reason="RUN_DB_TESTS not set")
def test_explain_endpoint_happy_path():
    client = TestClient(app)
    resp = client.post(
        "/api/v1/explain",
        json={"sql": "SELECT 1", "analyze": False, "timeout_ms": 2000, "nl": False},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert "plan" in data


@pytest.mark.skipif(not _db_enabled(), reason="RUN_DB_TESTS not set")
def test_nl_fallback_on_bad_provider():
    client = TestClient(app)
    os.environ["LLM_PROVIDER"] = "nonexistent"
    resp = client.post(
        "/api/v1/explain",
        json={"sql": "SELECT 1", "analyze": False, "timeout_ms": 2000, "nl": True},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data.get("explanation") is None
    assert "failed" in (data.get("message") or "").lower()













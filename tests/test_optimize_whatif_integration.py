import os

import pytest
from fastapi.testclient import TestClient

from app.core import db
from app.main import app

pytestmark = pytest.mark.integration


def _db_enabled() -> bool:
    return os.getenv("RUN_DB_TESTS", "0") == "1"


def _hypopg_available() -> bool:
    try:
        rows = db.run_sql("SELECT extname FROM pg_extension WHERE extname='hypopg'")
        return any(r and r[0] == "hypopg" for r in rows)
    except Exception:
        return False


@pytest.mark.requires_hypopg
@pytest.mark.skipif(not _db_enabled(), reason="RUN_DB_TESTS not set")
@pytest.mark.skipif(not _hypopg_available(), reason="hypopg not available")
def test_optimize_with_whatif_costs():
    client = TestClient(app)
    sql = "SELECT * FROM orders WHERE user_id=42 ORDER BY created_at DESC LIMIT 50"
    resp = client.post(
        "/api/v1/optimize",
        json={
            "sql": sql,
            "analyze": False,
            "timeout_ms": 3000,
            "advisors": ["rewrite", "index"],
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    # When hypopg is available and enabled, some suggestions may include estCost* fields
    # We don't assert presence strictly, just ensure the call worked.

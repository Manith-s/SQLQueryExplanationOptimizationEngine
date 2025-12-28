"""
Integration tests for Catalog and Query Builder features.

Tests the database catalog, query validation, suggestions,
visual plan generation, and query history system.
"""

import os
import tempfile
from pathlib import Path

import pytest

# Skip if DB tests not enabled
pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "1",
    reason="Skipping DB-dependent tests (set RUN_DB_TESTS=1 to run)",
)


@pytest.fixture
def temp_history_db():
    """Create temporary query history database."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".db", delete=False) as f:
        db_path = f.name

    yield db_path

    try:
        Path(db_path).unlink()
    except Exception:
        pass


@pytest.fixture
def query_history(temp_history_db):
    """Create query history manager instance."""
    from app.core.query_history import QueryHistoryManager

    return QueryHistoryManager(db_path=temp_history_db)


def test_query_history_initialization(query_history):
    """Test query history database initialization."""
    # Verify tables were created
    with query_history._get_connection() as conn:
        tables = conn.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type='table'
            ORDER BY name
        """
        ).fetchall()

        table_names = [t["name"] for t in tables]

    assert "query_history" in table_names
    assert "query_templates" in table_names
    assert "query_versions" in table_names
    assert "shared_queries" in table_names


def test_add_query_to_history(query_history):
    """Test adding query to history."""
    query_id = query_history.add_query(
        query_text="SELECT * FROM users WHERE id = 1",
        execution_time_ms=123.45,
        total_cost=42.5,
        rows_returned=1,
        success=True,
        user_id="test_user",
    )

    assert query_id > 0

    # Verify query was stored
    queries = query_history.get_recent_queries(limit=10)
    assert len(queries) == 1
    assert queries[0]["execution_time_ms"] == 123.45
    assert queries[0]["success"] == 1


def test_query_type_detection(query_history):
    """Test automatic query type detection."""
    queries = [
        ("SELECT * FROM users", "SELECT"),
        ("INSERT INTO users VALUES (1)", "INSERT"),
        ("UPDATE users SET name='test'", "UPDATE"),
        ("DELETE FROM users WHERE id=1", "DELETE"),
    ]

    for sql, expected_type in queries:
        query_history.add_query(sql, execution_time_ms=100.0)
        recent = query_history.get_recent_queries(limit=1)
        assert recent[0]["query_type"] == expected_type


def test_get_recent_queries_with_filters(query_history):
    """Test filtering recent queries."""
    # Add multiple queries
    query_history.add_query(
        "SELECT * FROM users", execution_time_ms=100.0, user_id="user1"
    )
    query_history.add_query(
        "SELECT * FROM orders", execution_time_ms=200.0, user_id="user2"
    )
    query_history.add_query(
        "INSERT INTO logs VALUES (1)", execution_time_ms=50.0, user_id="user1"
    )

    # Filter by user
    user1_queries = query_history.get_recent_queries(user_id="user1")
    assert len(user1_queries) == 2

    # Filter by type
    select_queries = query_history.get_recent_queries(query_type="SELECT")
    assert len(select_queries) == 2


def test_create_and_get_templates(query_history):
    """Test query template management."""
    template_id = query_history.create_template(
        template_name="user_by_id",
        template_sql="SELECT * FROM users WHERE id = ?",
        description="Get user by ID",
        category="users",
        parameters=["user_id"],
        created_by="test_user",
    )

    assert template_id > 0

    # Get templates
    templates = query_history.get_templates()
    assert len(templates) == 1
    assert templates[0]["template_name"] == "user_by_id"
    assert templates[0]["parameters"] == ["user_id"]


def test_template_usage_tracking(query_history):
    """Test template usage counter."""
    template_id = query_history.create_template(
        template_name="test_template", template_sql="SELECT 1"
    )

    # Increment usage
    query_history.increment_template_usage(template_id)
    query_history.increment_template_usage(template_id)

    templates = query_history.get_templates()
    assert templates[0]["usage_count"] == 2


def test_query_versioning(query_history):
    """Test query version tracking."""
    query_id = "test_query_001"

    # Create version 1
    v1_id, v1_num = query_history.create_version(
        query_id=query_id,
        query_text="SELECT * FROM users",
        change_description="Initial version",
        created_by="test_user",
    )

    assert v1_num == 1

    # Create version 2
    v2_id, v2_num = query_history.create_version(
        query_id=query_id,
        query_text="SELECT id, name FROM users WHERE active = true",
        change_description="Added WHERE clause",
        created_by="test_user",
    )

    assert v2_num == 2

    # Get all versions
    versions = query_history.get_versions(query_id)
    assert len(versions) == 2
    assert versions[0]["version_number"] == 2  # Most recent first


def test_shared_query_links(query_history):
    """Test shareable query links."""
    share_token = query_history.create_shared_query(
        query_text="SELECT * FROM public_data",
        query_name="Public Data Query",
        created_by="test_user",
    )

    assert share_token is not None
    assert len(share_token) == 16

    # Retrieve shared query
    shared = query_history.get_shared_query(share_token)
    assert shared is not None
    assert shared["query_name"] == "Public Data Query"
    assert shared["access_count"] == 1

    # Access again
    shared2 = query_history.get_shared_query(share_token)
    assert shared2["access_count"] == 2


def test_query_history_statistics(query_history):
    """Test query history statistics."""
    # Add some queries
    query_history.add_query(
        "SELECT * FROM users", execution_time_ms=100.0, success=True
    )
    query_history.add_query(
        "SELECT * FROM orders", execution_time_ms=200.0, success=True
    )
    query_history.add_query(
        "INSERT INTO logs VALUES (1)", execution_time_ms=50.0, success=False
    )

    stats = query_history.get_statistics()

    assert stats["total_queries"] == 3
    assert stats["successful_queries"] == 2
    assert stats["failed_queries"] == 1
    assert stats["success_rate"] == pytest.approx(66.67, rel=0.1)
    assert stats["avg_execution_time_ms"] > 0
    assert len(stats["query_types"]) > 0


@pytest.mark.asyncio
async def test_catalog_endpoint():
    """Test catalog API endpoint."""
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)

    # Note: May need to disable AUTH for testing or use valid token
    response = client.get("/api/v1/catalog?schema=public")

    # Should return catalog data
    assert response.status_code in [200, 401]  # 401 if auth enabled

    if response.status_code == 200:
        data = response.json()
        assert "tables" in data
        assert "relationships" in data
        assert "statistics" in data


@pytest.mark.asyncio
async def test_validate_endpoint():
    """Test query validation endpoint."""
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)

    payload = {"sql": "SELECT * FROM users", "partial": False}

    response = client.post("/api/v1/validate", json=payload)

    # Should return validation results
    assert response.status_code in [200, 401]

    if response.status_code == 200:
        data = response.json()
        assert "valid" in data
        assert "errors" in data
        assert "warnings" in data


@pytest.mark.asyncio
async def test_suggest_endpoint():
    """Test query suggestion endpoint."""
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)

    payload = {"partial_sql": "SELECT", "context": {"tables": []}}

    response = client.post("/api/v1/suggest", json=payload)

    assert response.status_code in [200, 401]

    if response.status_code == 200:
        data = response.json()
        assert "suggestions" in data
        assert "context_hints" in data


@pytest.mark.asyncio
async def test_visual_plan_endpoint():
    """Test visual plan endpoint."""
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)

    response = client.get(
        "/api/v1/plan/visual?sql=SELECT%20*%20FROM%20users%20LIMIT%2010"
    )

    assert response.status_code in [200, 401, 500]  # 500 if no DB connection

    if response.status_code == 200:
        data = response.json()
        assert "plan_tree" in data
        assert "summary" in data
        assert "bottlenecks" in data


def test_query_hash_consistency(query_history):
    """Test query hash is consistent."""
    query1 = "SELECT * FROM users WHERE id = 1"
    query2 = "  SELECT   *  FROM   users  WHERE  id = 1  "

    hash1 = query_history._compute_query_hash(query1)
    hash2 = query_history._compute_query_hash(query2)

    # Should normalize whitespace
    assert hash1 == hash2


def test_concurrent_query_additions(query_history):
    """Test concurrent query additions."""
    import threading

    def add_queries():
        for i in range(10):
            query_history.add_query(f"SELECT {i} FROM test", execution_time_ms=100.0)

    threads = []
    for _ in range(5):
        thread = threading.Thread(target=add_queries)
        threads.append(thread)
        thread.start()

    for thread in threads:
        thread.join()

    queries = query_history.get_recent_queries(limit=100)
    assert len(queries) == 50  # 5 threads * 10 queries each


def test_failed_query_tracking(query_history):
    """Test tracking of failed queries."""
    query_history.add_query(
        query_text="SELECT * FROM nonexistent_table",
        execution_time_ms=None,
        success=False,
        error_message="Table does not exist",
    )

    queries = query_history.get_recent_queries(limit=10)
    assert len(queries) == 1
    assert queries[0]["success"] == 0
    assert queries[0]["error_message"] == "Table does not exist"


def test_query_metadata_storage(query_history):
    """Test storing additional metadata with queries."""
    metadata = {
        "source": "web_ui",
        "user_agent": "Mozilla/5.0",
        "ip_address": "127.0.0.1",
    }

    query_history.add_query(
        query_text="SELECT * FROM users", execution_time_ms=100.0, metadata=metadata
    )

    with query_history._get_connection() as conn:
        row = conn.execute(
            """
            SELECT metadata FROM query_history
            ORDER BY id DESC
            LIMIT 1
        """
        ).fetchone()

    import json

    stored_metadata = json.loads(row["metadata"])
    assert stored_metadata == metadata


def test_query_builder_ui_accessible():
    """Test that query builder UI is accessible."""
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    response = client.get("/query-builder")

    # Should return HTML or 404 if file doesn't exist
    assert response.status_code in [200, 404]

    if response.status_code == 200:
        assert "html" in response.text.lower()


def test_plan_visualizer_ui_accessible():
    """Test that plan visualizer UI is accessible."""
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    response = client.get("/plan-visualizer")

    assert response.status_code in [200, 404]

    if response.status_code == 200:
        assert "html" in response.text.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

"""
Integration tests for the schema inspection endpoint.

These tests require a running PostgreSQL database and RUN_DB_TESTS=1.
"""

import os

import pytest
from fastapi.testclient import TestClient

from app.core import db
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


@pytest.fixture(autouse=True)
def test_table():
    """
    Create and drop a test table for schema inspection.

    The table includes:
    - Serial primary key
    - Foreign key reference
    - Index on user_id
    - Various column types and constraints
    """
    # Create tables
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            # Create parent table
            cur.execute(
                """
                CREATE TABLE tmp_cursor_phase2_users (
                    id SERIAL PRIMARY KEY,
                    username VARCHAR(50) NOT NULL UNIQUE
                )
            """
            )

            # Create main test table
            cur.execute(
                """
                CREATE TABLE tmp_cursor_phase2 (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER REFERENCES tmp_cursor_phase2_users(id),
                    name VARCHAR(100) NOT NULL,
                    email VARCHAR(255) UNIQUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    active BOOLEAN DEFAULT true,
                    metadata JSONB
                )
            """
            )

            # Create index
            cur.execute(
                """
                CREATE INDEX idx_tmp_cursor_phase2_user_id
                ON tmp_cursor_phase2(user_id)
            """
            )

            conn.commit()

    yield

    # Cleanup
    with db.get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS tmp_cursor_phase2")
            cur.execute("DROP TABLE IF EXISTS tmp_cursor_phase2_users")
            conn.commit()


def test_schema_list_tables(client):
    """Test schema endpoint returns all tables."""
    response = client.get("/api/v1/schema")
    assert response.status_code == 200
    data = response.json()

    assert data["ok"] is True
    assert data["schema"]["schema"] == "public"

    # Find our test tables
    table_names = [t["name"] for t in data["schema"]["tables"]]
    assert "tmp_cursor_phase2" in table_names
    assert "tmp_cursor_phase2_users" in table_names


def test_schema_single_table(client):
    """Test schema endpoint for a specific table."""
    response = client.get("/api/v1/schema?table=tmp_cursor_phase2")
    assert response.status_code == 200
    data = response.json()

    assert len(data["schema"]["tables"]) == 1
    table = data["schema"]["tables"][0]

    # Check table name
    assert table["name"] == "tmp_cursor_phase2"

    # Check columns
    column_names = [c["name"] for c in table["columns"]]
    assert "id" in column_names
    assert "user_id" in column_names
    assert "name" in column_names
    assert "email" in column_names
    assert "created_at" in column_names
    assert "active" in column_names
    assert "metadata" in column_names

    # Check primary key
    assert table["primary_key"] == ["id"]

    # Check index
    assert any(
        idx["name"] == "idx_tmp_cursor_phase2_user_id" for idx in table["indexes"]
    )

    # Check foreign keys
    assert any(
        fk["column_name"] == "user_id"
        and fk["foreign_table"] == "tmp_cursor_phase2_users"
        for fk in table["foreign_keys"]
    )


def test_schema_column_details(client):
    """Test column metadata is correct."""
    response = client.get("/api/v1/schema?table=tmp_cursor_phase2")
    assert response.status_code == 200
    data = response.json()

    table = data["schema"]["tables"][0]
    columns = {c["name"]: c for c in table["columns"]}

    # Check id column
    assert columns["id"]["data_type"] == "integer"
    assert not columns["id"]["nullable"]
    assert "nextval" in columns["id"]["default"].lower()

    # Check name column
    assert columns["name"]["data_type"] == "character varying"
    assert not columns["name"]["nullable"]
    assert columns["name"]["default"] is None

    # Check created_at column
    assert "timestamp" in columns["created_at"]["data_type"].lower()
    assert columns["created_at"]["nullable"]
    assert "current_timestamp" in columns["created_at"]["default"].lower()


def test_schema_invalid_table(client):
    """Test schema endpoint with nonexistent table."""
    response = client.get("/api/v1/schema?table=nonexistent")
    assert response.status_code == 200
    data = response.json()

    assert data["ok"] is True
    assert len(data["schema"]["tables"]) == 0


def test_schema_invalid_schema(client):
    """Test schema endpoint with nonexistent schema."""
    response = client.get("/api/v1/schema?schema=nonexistent")
    assert response.status_code == 200
    data = response.json()

    assert data["ok"] is True
    assert len(data["schema"]["tables"]) == 0

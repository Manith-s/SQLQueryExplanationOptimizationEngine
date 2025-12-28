"""
Query History and Template System

Manages user query history, templates, and collaborative features.
"""

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class QueryHistoryManager:
    """Manages query history, templates, and versioning."""

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize query history manager.

        Args:
            db_path: Path to SQLite database. Defaults to query_history.db
        """
        if db_path is None:
            db_path = str(Path.cwd() / "query_history.db")
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize database schema."""
        with self._get_connection() as conn:
            # Query history table
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS query_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    query_hash TEXT NOT NULL,
                    query_text TEXT NOT NULL,
                    query_type TEXT,
                    execution_time_ms REAL,
                    total_cost REAL,
                    rows_returned INTEGER,
                    success BOOLEAN DEFAULT 1,
                    error_message TEXT,
                    user_id TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    metadata TEXT
                )
            """
            )

            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_history_hash
                ON query_history(query_hash)
            """
            )

            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_history_user
                ON query_history(user_id)
            """
            )

            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_history_created
                ON query_history(created_at DESC)
            """
            )

            # Query templates table
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS query_templates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    template_name TEXT NOT NULL UNIQUE,
                    template_sql TEXT NOT NULL,
                    description TEXT,
                    category TEXT,
                    parameters TEXT,
                    usage_count INTEGER DEFAULT 0,
                    created_by TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """
            )

            # Query versions table (for versioning)
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS query_versions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    query_id TEXT NOT NULL,
                    version_number INTEGER NOT NULL,
                    query_text TEXT NOT NULL,
                    change_description TEXT,
                    created_by TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(query_id, version_number)
                )
            """
            )

            # Shared queries table
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS shared_queries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    share_token TEXT NOT NULL UNIQUE,
                    query_text TEXT NOT NULL,
                    query_name TEXT,
                    created_by TEXT,
                    expires_at DATETIME,
                    access_count INTEGER DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """
            )

            conn.commit()

    @contextmanager
    def _get_connection(self):
        """Context manager for database connections."""
        conn = sqlite3.connect(self.db_path, timeout=30.0, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _compute_query_hash(self, query: str) -> str:
        """Compute consistent hash for a query."""
        normalized = " ".join(query.lower().split())
        return hashlib.sha256(normalized.encode()).hexdigest()[:16]

    def add_query(
        self,
        query_text: str,
        execution_time_ms: Optional[float] = None,
        total_cost: Optional[float] = None,
        rows_returned: Optional[int] = None,
        success: bool = True,
        error_message: Optional[str] = None,
        user_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        """
        Add query to history.

        Args:
            query_text: SQL query text
            execution_time_ms: Execution time in milliseconds
            total_cost: Query cost
            rows_returned: Number of rows returned
            success: Whether execution succeeded
            error_message: Error message if failed
            user_id: User identifier
            metadata: Additional metadata

        Returns:
            Query history ID
        """
        query_hash = self._compute_query_hash(query_text)

        # Determine query type
        query_type = self._determine_query_type(query_text)

        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO query_history (
                    query_hash, query_text, query_type, execution_time_ms,
                    total_cost, rows_returned, success, error_message,
                    user_id, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    query_hash,
                    query_text,
                    query_type,
                    execution_time_ms,
                    total_cost,
                    rows_returned,
                    success,
                    error_message,
                    user_id,
                    json.dumps(metadata) if metadata else None,
                ),
            )
            conn.commit()
            return cursor.lastrowid

    def _determine_query_type(self, query: str) -> str:
        """Determine query type from SQL text."""
        query_upper = query.strip().upper()
        if query_upper.startswith("SELECT"):
            return "SELECT"
        elif query_upper.startswith("INSERT"):
            return "INSERT"
        elif query_upper.startswith("UPDATE"):
            return "UPDATE"
        elif query_upper.startswith("DELETE"):
            return "DELETE"
        else:
            return "OTHER"

    def get_recent_queries(
        self,
        limit: int = 50,
        user_id: Optional[str] = None,
        query_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get recent query history.

        Args:
            limit: Maximum number of queries to return
            user_id: Filter by user ID
            query_type: Filter by query type (SELECT, INSERT, etc.)

        Returns:
            List of query history records
        """
        conditions = []
        params = []

        if user_id:
            conditions.append("user_id = ?")
            params.append(user_id)

        if query_type:
            conditions.append("query_type = ?")
            params.append(query_type)

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

        with self._get_connection() as conn:
            rows = conn.execute(
                f"""
                SELECT id, query_hash, query_text, query_type,
                       execution_time_ms, total_cost, rows_returned,
                       success, error_message, created_at
                FROM query_history
                {where_clause}
                ORDER BY created_at DESC
                LIMIT ?
            """,
                params + [limit],
            ).fetchall()

        return [dict(row) for row in rows]

    def get_query_by_hash(self, query_hash: str) -> List[Dict[str, Any]]:
        """Get all executions of a query by its hash."""
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM query_history
                WHERE query_hash = ?
                ORDER BY created_at DESC
            """,
                (query_hash,),
            ).fetchall()

        return [dict(row) for row in rows]

    def create_template(
        self,
        template_name: str,
        template_sql: str,
        description: Optional[str] = None,
        category: Optional[str] = None,
        parameters: Optional[List[str]] = None,
        created_by: Optional[str] = None,
    ) -> int:
        """
        Create a query template.

        Args:
            template_name: Unique template name
            template_sql: SQL template text (can include placeholders)
            description: Template description
            category: Template category
            parameters: List of parameter names
            created_by: Creator user ID

        Returns:
            Template ID
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO query_templates (
                    template_name, template_sql, description, category,
                    parameters, created_by
                ) VALUES (?, ?, ?, ?, ?, ?)
            """,
                (
                    template_name,
                    template_sql,
                    description,
                    category,
                    json.dumps(parameters) if parameters else None,
                    created_by,
                ),
            )
            conn.commit()
            return cursor.lastrowid

    def get_templates(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get query templates, optionally filtered by category."""
        where_clause = "WHERE category = ?" if category else ""
        params = [category] if category else []

        with self._get_connection() as conn:
            rows = conn.execute(
                f"""
                SELECT id, template_name, template_sql, description,
                       category, parameters, usage_count, created_at
                FROM query_templates
                {where_clause}
                ORDER BY usage_count DESC, template_name
            """,
                params,
            ).fetchall()

        results = []
        for row in rows:
            record = dict(row)
            if record["parameters"]:
                record["parameters"] = json.loads(record["parameters"])
            results.append(record)

        return results

    def increment_template_usage(self, template_id: int):
        """Increment template usage count."""
        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE query_templates
                SET usage_count = usage_count + 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """,
                (template_id,),
            )
            conn.commit()

    def create_version(
        self,
        query_id: str,
        query_text: str,
        change_description: Optional[str] = None,
        created_by: Optional[str] = None,
    ) -> Tuple[int, int]:
        """
        Create a new version of a query.

        Args:
            query_id: Query identifier
            query_text: Query text for this version
            change_description: Description of changes
            created_by: User who created this version

        Returns:
            Tuple of (version_id, version_number)
        """
        with self._get_connection() as conn:
            # Get next version number
            result = conn.execute(
                """
                SELECT COALESCE(MAX(version_number), 0) + 1 as next_version
                FROM query_versions
                WHERE query_id = ?
            """,
                (query_id,),
            ).fetchone()

            version_number = result["next_version"]

            cursor = conn.execute(
                """
                INSERT INTO query_versions (
                    query_id, version_number, query_text,
                    change_description, created_by
                ) VALUES (?, ?, ?, ?, ?)
            """,
                (query_id, version_number, query_text, change_description, created_by),
            )
            conn.commit()

            return cursor.lastrowid, version_number

    def get_versions(self, query_id: str) -> List[Dict[str, Any]]:
        """Get all versions of a query."""
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM query_versions
                WHERE query_id = ?
                ORDER BY version_number DESC
            """,
                (query_id,),
            ).fetchall()

        return [dict(row) for row in rows]

    def create_shared_query(
        self,
        query_text: str,
        query_name: Optional[str] = None,
        created_by: Optional[str] = None,
        expires_at: Optional[datetime] = None,
    ) -> str:
        """
        Create a shareable query link.

        Args:
            query_text: SQL query text
            query_name: Optional query name
            created_by: User who created the share
            expires_at: Expiration datetime

        Returns:
            Share token
        """
        # Generate unique share token
        share_token = hashlib.sha256(
            f"{query_text}{datetime.now().isoformat()}".encode()
        ).hexdigest()[:16]

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO shared_queries (
                    share_token, query_text, query_name,
                    created_by, expires_at
                ) VALUES (?, ?, ?, ?, ?)
            """,
                (
                    share_token,
                    query_text,
                    query_name,
                    created_by,
                    expires_at.isoformat() if expires_at else None,
                ),
            )
            conn.commit()

        return share_token

    def get_shared_query(self, share_token: str) -> Optional[Dict[str, Any]]:
        """
        Get shared query by token.

        Args:
            share_token: Share token

        Returns:
            Query data or None if not found/expired
        """
        with self._get_connection() as conn:
            row = conn.execute(
                """
                SELECT * FROM shared_queries
                WHERE share_token = ?
                  AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
            """,
                (share_token,),
            ).fetchone()

            if row:
                # Increment access count
                conn.execute(
                    """
                    UPDATE shared_queries
                    SET access_count = access_count + 1
                    WHERE share_token = ?
                """,
                    (share_token,),
                )
                conn.commit()

                return dict(row)

        return None

    def get_statistics(self) -> Dict[str, Any]:
        """Get query history statistics."""
        with self._get_connection() as conn:
            total_queries = conn.execute(
                "SELECT COUNT(*) as count FROM query_history"
            ).fetchone()["count"]

            successful_queries = conn.execute(
                "SELECT COUNT(*) as count FROM query_history WHERE success = 1"
            ).fetchone()["count"]

            avg_exec_time = conn.execute(
                """
                SELECT AVG(execution_time_ms) as avg_time
                FROM query_history
                WHERE success = 1 AND execution_time_ms IS NOT NULL
            """
            ).fetchone()["avg_time"]

            query_types = conn.execute(
                """
                SELECT query_type, COUNT(*) as count
                FROM query_history
                GROUP BY query_type
                ORDER BY count DESC
            """
            ).fetchall()

            total_templates = conn.execute(
                "SELECT COUNT(*) as count FROM query_templates"
            ).fetchone()["count"]

        return {
            "total_queries": total_queries,
            "successful_queries": successful_queries,
            "failed_queries": total_queries - successful_queries,
            "success_rate": (
                (successful_queries / total_queries * 100) if total_queries > 0 else 0
            ),
            "avg_execution_time_ms": (
                float(f"{avg_exec_time:.3f}") if avg_exec_time else 0
            ),
            "query_types": [dict(row) for row in query_types],
            "total_templates": total_templates,
        }


# Global instance
_query_history: Optional[QueryHistoryManager] = None


def get_query_history() -> QueryHistoryManager:
    """Get or create global query history manager."""
    global _query_history
    if _query_history is None:
        _query_history = QueryHistoryManager()
    return _query_history

"""
Intelligent cache invalidation system with dependency tracking.

Implements:
- Table dependency extraction from queries
- PostgreSQL trigger-based change detection via NOTIFY/LISTEN
- Selective invalidation based on affected rows
- Dependency graph for cascading invalidations
- Probabilistic invalidation for approximate queries
"""

import select
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from threading import Lock, RLock, Thread
from typing import Any, Dict, List, Optional, Set

import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

from app.core.cache_manager import QueryFingerprinter, get_cache_manager
from app.core.config import settings
from app.core.db import get_conn


class InvalidationStrategy(Enum):
    """Cache invalidation strategies."""

    IMMEDIATE = "immediate"  # Invalidate immediately on change
    BATCH = "batch"  # Batch invalidations
    PROBABILISTIC = "probabilistic"  # Probabilistic for approximate queries
    LAZY = "lazy"  # Invalidate on next access (lazy)


class ChangeType(Enum):
    """Database change types."""

    INSERT = "INSERT"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    TRUNCATE = "TRUNCATE"


@dataclass
class TableChange:
    """Record of a table modification."""

    table_name: str
    change_type: ChangeType
    timestamp: datetime
    affected_rows: int = 0
    changed_columns: Set[str] = field(default_factory=set)
    where_clause: Optional[str] = None


@dataclass
class InvalidationRule:
    """Rule for cache invalidation."""

    table: str
    strategy: InvalidationStrategy
    probability: float = 1.0  # For probabilistic invalidation
    delay_seconds: int = 0  # For batched invalidation
    selective_columns: Optional[Set[str]] = (
        None  # Only invalidate if these columns change
    )


@dataclass
class DependencyNode:
    """Node in dependency graph."""

    table: str
    dependent_tables: Set[str] = field(default_factory=set)
    cached_queries: Set[str] = field(default_factory=set)  # Fingerprints
    invalidation_rule: Optional[InvalidationRule] = None


class DependencyGraph:
    """
    Maintains dependency relationships between tables and cached queries.

    Supports cascading invalidations through table relationships.
    """

    def __init__(self):
        """Initialize dependency graph."""
        self.nodes: Dict[str, DependencyNode] = {}
        self.lock = RLock()  # Use reentrant lock for recursive calls

    def add_query_dependency(self, query_fingerprint: str, tables: Set[str]):
        """
        Add query dependency on tables.

        Args:
            query_fingerprint: Unique query identifier
            tables: Set of table names the query depends on
        """
        with self.lock:
            for table in tables:
                table_lower = table.lower()

                if table_lower not in self.nodes:
                    self.nodes[table_lower] = DependencyNode(table=table_lower)

                self.nodes[table_lower].cached_queries.add(query_fingerprint)

    def add_table_dependency(self, parent_table: str, child_table: str):
        """
        Add table-to-table dependency (e.g., foreign key relationship).

        Args:
            parent_table: Parent table name
            child_table: Child table name
        """
        with self.lock:
            parent_lower = parent_table.lower()

            if parent_lower not in self.nodes:
                self.nodes[parent_lower] = DependencyNode(table=parent_lower)

            self.nodes[parent_lower].dependent_tables.add(child_table.lower())

    def get_affected_queries(self, table: str, cascade: bool = True) -> Set[str]:
        """
        Get all query fingerprints affected by a table change.

        Args:
            table: Changed table name
            cascade: Whether to cascade through dependencies

        Returns:
            Set of affected query fingerprints
        """
        affected = set()
        visited = set()

        def _collect_queries(current_table: str):
            if current_table in visited:
                return

            visited.add(current_table)

            with self.lock:
                node = self.nodes.get(current_table)
                if not node:
                    return

                # Add queries directly depending on this table
                affected.update(node.cached_queries)

                # Cascade to dependent tables if enabled
                if cascade:
                    for dep_table in node.dependent_tables:
                        _collect_queries(dep_table)

        _collect_queries(table.lower())
        return affected

    def remove_query(self, query_fingerprint: str):
        """Remove query from all dependencies."""
        with self.lock:
            for node in self.nodes.values():
                node.cached_queries.discard(query_fingerprint)

    def get_statistics(self) -> Dict[str, Any]:
        """Get dependency graph statistics."""
        with self.lock:
            total_queries = sum(
                len(node.cached_queries) for node in self.nodes.values()
            )

            return {
                "tables_tracked": len(self.nodes),
                "total_cached_queries": total_queries,
                "avg_queries_per_table": (
                    total_queries / len(self.nodes) if self.nodes else 0
                ),
                "tables_with_dependencies": sum(
                    1 for node in self.nodes.values() if node.dependent_tables
                ),
            }


class CacheInvalidator:
    """
    Intelligent cache invalidation manager.

    Features:
    - Automatic invalidation on table changes via PostgreSQL NOTIFY
    - Selective invalidation based on changed columns and rows
    - Dependency graph for cascading invalidations
    - Multiple invalidation strategies
    """

    def __init__(
        self,
        cache_manager=None,
        enable_listen: bool = True,
        batch_interval_seconds: int = 5,
    ):
        """
        Initialize cache invalidator.

        Args:
            cache_manager: Cache manager instance (default: singleton)
            enable_listen: Enable PostgreSQL LISTEN for real-time invalidation
            batch_interval_seconds: Interval for batched invalidations
        """
        self.cache_manager = cache_manager or get_cache_manager()
        self.dependency_graph = DependencyGraph()
        self.invalidation_rules: Dict[str, InvalidationRule] = {}

        self.enable_listen = enable_listen
        self.batch_interval_seconds = batch_interval_seconds

        # Pending invalidations (for batching)
        self.pending_invalidations: Dict[str, TableChange] = {}
        self.pending_lock = Lock()

        # Statistics
        self.invalidation_count = 0
        self.selective_invalidation_count = 0
        self.cascade_invalidation_count = 0
        self.stats_lock = Lock()

        # LISTEN connection
        self.listen_conn = None
        self.listen_thread = None
        self.running = False

        if self.enable_listen:
            self._start_listener()

    def register_query(
        self,
        query_fingerprint: str,
        tables: Set[str],
        strategy: InvalidationStrategy = InvalidationStrategy.IMMEDIATE,
    ):
        """
        Register cached query for invalidation tracking.

        Args:
            query_fingerprint: Unique query identifier
            tables: Tables the query depends on
            strategy: Invalidation strategy to use
        """
        self.dependency_graph.add_query_dependency(query_fingerprint, tables)

        # Apply strategy to tables
        for table in tables:
            table_lower = table.lower()
            if table_lower not in self.invalidation_rules:
                self.invalidation_rules[table_lower] = InvalidationRule(
                    table=table_lower, strategy=strategy
                )

    def invalidate_by_table(
        self,
        table: str,
        change_type: ChangeType = ChangeType.UPDATE,
        affected_rows: int = 1,
        changed_columns: Optional[Set[str]] = None,
        cascade: bool = True,
    ) -> int:
        """
        Invalidate cache entries for a table.

        Args:
            table: Table name
            change_type: Type of database change
            affected_rows: Number of rows affected
            changed_columns: Set of changed column names
            cascade: Whether to cascade through dependencies

        Returns:
            Number of cache entries invalidated
        """
        table_lower = table.lower()
        invalidated = 0

        # Get invalidation rule
        rule = self.invalidation_rules.get(table_lower)

        # Check if we should invalidate based on selective columns
        if rule and rule.selective_columns and changed_columns:
            if not rule.selective_columns.intersection(changed_columns):
                # Changed columns don't match selective columns, skip
                return 0

        # Apply invalidation strategy
        if rule:
            if rule.strategy == InvalidationStrategy.PROBABILISTIC:
                # Probabilistic invalidation
                import random

                if random.random() > rule.probability:
                    return 0  # Skip invalidation

            elif rule.strategy == InvalidationStrategy.BATCH:
                # Add to pending batch
                self._add_pending_invalidation(
                    TableChange(
                        table_name=table_lower,
                        change_type=change_type,
                        timestamp=datetime.utcnow(),
                        affected_rows=affected_rows,
                        changed_columns=changed_columns or set(),
                    )
                )
                return 0  # Will be processed in batch

            elif rule.strategy == InvalidationStrategy.LAZY:
                # Lazy invalidation - mark as stale but don't invalidate yet
                # (In a full implementation, this would mark entries for validation on next access)
                return 0

        # Get affected queries
        affected_queries = self.dependency_graph.get_affected_queries(
            table_lower, cascade
        )

        # Invalidate cache
        invalidated += self.cache_manager.invalidate(table=table_lower)

        with self.stats_lock:
            self.invalidation_count += 1
            if changed_columns:
                self.selective_invalidation_count += 1
            if cascade and len(affected_queries) > 0:
                self.cascade_invalidation_count += 1

        # Update table volatility based on change frequency
        self._update_volatility(table_lower, change_type, affected_rows)

        return invalidated

    def invalidate_selective(self, sql: str, where_clause: Optional[str] = None) -> int:
        """
        Selective invalidation based on query patterns.

        Only invalidates queries that might be affected by specific WHERE conditions.

        Args:
            sql: SQL query defining the scope of changes
            where_clause: WHERE clause defining affected rows

        Returns:
            Number of entries invalidated
        """
        # Extract tables from query
        tables = QueryFingerprinter.extract_table_dependencies(sql)

        invalidated = 0
        for table in tables:
            invalidated += self.invalidate_by_table(
                table, change_type=ChangeType.UPDATE, cascade=True
            )

        return invalidated

    def setup_triggers(self, tables: List[str]) -> Dict[str, str]:
        """
        Setup PostgreSQL triggers for change notification.

        Creates triggers that send NOTIFY messages on INSERT/UPDATE/DELETE.

        Args:
            tables: List of table names to monitor

        Returns:
            Dict mapping table names to trigger creation status
        """
        results = {}

        try:
            with get_conn() as conn:
                cur = conn.cursor()

                for table in tables:
                    table_lower = table.lower()

                    # Create trigger function if not exists
                    trigger_func = f"""
                    CREATE OR REPLACE FUNCTION notify_cache_invalidation_{table_lower}()
                    RETURNS TRIGGER AS $$
                    DECLARE
                        payload JSON;
                    BEGIN
                        payload = json_build_object(
                            'table', TG_TABLE_NAME,
                            'operation', TG_OP,
                            'timestamp', extract(epoch from now())
                        );
                        PERFORM pg_notify('cache_invalidation', payload::text);
                        RETURN NEW;
                    END;
                    $$ LANGUAGE plpgsql;
                    """

                    cur.execute(trigger_func)

                    # Create triggers for INSERT, UPDATE, DELETE
                    for operation in ["INSERT", "UPDATE", "DELETE"]:
                        trigger_name = (
                            f"cache_invalidation_{table_lower}_{operation.lower()}"
                        )

                        # Drop existing trigger
                        cur.execute(
                            f"DROP TRIGGER IF EXISTS {trigger_name} ON {table_lower}"
                        )

                        # Create new trigger
                        timing = "AFTER"
                        trigger_sql = f"""
                        CREATE TRIGGER {trigger_name}
                        {timing} {operation} ON {table_lower}
                        FOR EACH ROW
                        EXECUTE FUNCTION notify_cache_invalidation_{table_lower}();
                        """

                        cur.execute(trigger_sql)

                    conn.commit()
                    results[table_lower] = "success"

        except Exception as e:
            results[table] = f"error: {str(e)}"

        return results

    def process_batch_invalidations(self) -> int:
        """
        Process pending batched invalidations.

        Returns:
            Number of entries invalidated
        """
        invalidated = 0

        with self.pending_lock:
            if not self.pending_invalidations:
                return 0

            # Process all pending changes
            for table, _change in self.pending_invalidations.items():
                invalidated += self.cache_manager.invalidate(table=table)

            self.pending_invalidations.clear()

        return invalidated

    def get_statistics(self) -> Dict[str, Any]:
        """Get invalidation statistics."""
        with self.stats_lock:
            stats = {
                "total_invalidations": self.invalidation_count,
                "selective_invalidations": self.selective_invalidation_count,
                "cascade_invalidations": self.cascade_invalidation_count,
                "pending_batch_invalidations": len(self.pending_invalidations),
                "dependency_graph": self.dependency_graph.get_statistics(),
            }

        return stats

    def _start_listener(self):
        """Start PostgreSQL LISTEN thread."""
        try:
            # Use a persistent connection for LISTEN
            self.listen_conn = psycopg2.connect(settings.db_url_psycopg)
            self.listen_conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)

            cur = self.listen_conn.cursor()
            cur.execute("LISTEN cache_invalidation;")
            cur.close()

            self.running = True
            self.listen_thread = Thread(target=self._listen_loop, daemon=True)
            self.listen_thread.start()

        except Exception as e:
            print(f"Failed to start LISTEN thread: {e}")
            self.enable_listen = False

    def _listen_loop(self):
        """Main loop for processing NOTIFY messages."""
        while self.running:
            try:
                if select.select([self.listen_conn], [], [], 5) == ([], [], []):
                    continue

                self.listen_conn.poll()

                while self.listen_conn.notifies:
                    notify = self.listen_conn.notifies.pop(0)
                    self._process_notification(notify.payload)

            except Exception as e:
                print(f"Error in LISTEN loop: {e}")
                time.sleep(1)

    def _process_notification(self, payload: str):
        """Process a NOTIFY payload."""
        try:
            import json

            data = json.loads(payload)

            table = data.get("table")
            operation = data.get("operation")

            if table and operation:
                change_type = ChangeType[operation]
                self.invalidate_by_table(table, change_type=change_type)

        except Exception as e:
            print(f"Error processing notification: {e}")

    def _add_pending_invalidation(self, change: TableChange):
        """Add change to pending batch."""
        with self.pending_lock:
            # Merge with existing pending change if present
            if change.table_name in self.pending_invalidations:
                existing = self.pending_invalidations[change.table_name]
                existing.affected_rows += change.affected_rows
                existing.changed_columns.update(change.changed_columns)
                existing.timestamp = change.timestamp
            else:
                self.pending_invalidations[change.table_name] = change

    def _update_volatility(
        self, table: str, change_type: ChangeType, affected_rows: int
    ):
        """Update table volatility score based on change patterns."""
        # Simple heuristic: more frequent changes = higher volatility
        # In a real system, this would use time-series analysis

        # Get current volatility
        current = self.cache_manager.table_volatility.get(table, 0.5)

        # Adjust based on change type and size
        if change_type == ChangeType.TRUNCATE:
            delta = 0.2  # Large impact
        elif change_type == ChangeType.DELETE:
            delta = 0.1 if affected_rows > 100 else 0.05
        elif change_type == ChangeType.INSERT:
            delta = 0.08 if affected_rows > 100 else 0.03
        else:  # UPDATE
            delta = 0.05 if affected_rows > 100 else 0.02

        # Update with exponential moving average
        new_volatility = min(1.0, current + delta * 0.3)

        self.cache_manager.update_table_volatility(table, new_volatility)

    def stop(self):
        """Stop the invalidator and cleanup."""
        self.running = False

        if self.listen_thread:
            self.listen_thread.join(timeout=2)

        if self.listen_conn:
            try:
                self.listen_conn.close()
            except Exception:
                pass


# Singleton instance
_cache_invalidator: Optional[CacheInvalidator] = None


def get_cache_invalidator() -> CacheInvalidator:
    """Get singleton cache invalidator instance."""
    global _cache_invalidator

    if _cache_invalidator is None:
        _cache_invalidator = CacheInvalidator(
            enable_listen=True, batch_interval_seconds=5
        )

    return _cache_invalidator

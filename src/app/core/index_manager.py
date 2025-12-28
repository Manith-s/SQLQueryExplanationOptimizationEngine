"""
Intelligent Index Lifecycle Manager

Tracks index usage, scores effectiveness, and provides automated recommendations
for optimal database performance.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import settings
from app.core.db import get_conn


@dataclass
class IndexMetrics:
    """Metrics for a single index."""
    schema_name: str
    table_name: str
    index_name: str
    size_bytes: int
    scans: int
    tuples_read: int
    tuples_fetched: int
    is_unique: bool
    is_primary: bool
    columns: List[str]
    index_type: str
    definition: str

    # Computed metrics
    effectiveness_score: float = 0.0
    scan_efficiency: float = 0.0
    usage_frequency: float = 0.0
    maintenance_cost: float = 0.0


@dataclass
class IndexRecommendation:
    """Recommendation for index creation or modification."""
    action: str  # "create", "drop", "recreate"
    priority: int  # 1-10, 10 being highest
    table_name: str
    index_type: str  # "btree", "hash", "gin", "gist", "brin"
    columns: List[str]
    where_clause: Optional[str] = None  # For partial indexes
    expression: Optional[str] = None  # For expression indexes
    rationale: str = ""
    estimated_benefit: float = 0.0
    estimated_cost_bytes: int = 0
    confidence: float = 0.0

    def to_ddl(self, schema: str = "public") -> str:
        """Generate DDL statement for this recommendation."""
        if self.action == "drop":
            return f"DROP INDEX CONCURRENTLY IF EXISTS {schema}.{self.columns[0]}"

        idx_name = f"idx_{self.table_name}_{'_'.join(self.columns)}"

        if self.expression:
            col_spec = self.expression
        else:
            col_spec = ", ".join(self.columns)

        using_clause = f"USING {self.index_type.upper()}" if self.index_type != "btree" else ""
        where_clause = f"WHERE {self.where_clause}" if self.where_clause else ""

        return (
            f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {idx_name} "
            f"ON {schema}.{self.table_name} {using_clause} "
            f"({col_spec}) {where_clause}".strip()
        )


class IndexLifecycleManager:
    """
    Manages the complete lifecycle of database indexes including monitoring,
    analysis, and recommendations.
    """

    def __init__(self, schema: str = "public"):
        self.schema = schema
        self.min_effectiveness_threshold = float(
            settings.__dict__.get("INDEX_MIN_EFFECTIVENESS", 0.2)
        )
        self.min_usage_threshold = int(
            settings.__dict__.get("INDEX_MIN_USAGE_SCANS", 100)
        )

    def get_index_usage_stats(self) -> List[IndexMetrics]:
        """
        Fetch comprehensive index usage statistics from PostgreSQL.

        Returns:
            List of IndexMetrics objects with usage data
        """
        query = """
        SELECT
            schemaname,
            tablename,
            indexname,
            idx_scan,
            idx_tup_read,
            idx_tup_fetch,
            pg_relation_size(indexrelid) as size_bytes,
            indisunique,
            indisprimary,
            pg_get_indexdef(indexrelid) as definition,
            amname as index_type
        FROM pg_stat_user_indexes
        JOIN pg_index ON pg_stat_user_indexes.indexrelid = pg_index.indexrelid
        JOIN pg_class ON pg_index.indexrelid = pg_class.oid
        JOIN pg_am ON pg_class.relam = pg_am.oid
        WHERE schemaname = %s
        ORDER BY idx_scan DESC;
        """

        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (self.schema,))
                    rows = cur.fetchall()

                    metrics_list = []
                    for row in rows:
                        # Parse columns from index definition
                        columns = self._parse_index_columns(row[9])

                        metrics = IndexMetrics(
                            schema_name=row[0],
                            table_name=row[1],
                            index_name=row[2],
                            scans=row[3] or 0,
                            tuples_read=row[4] or 0,
                            tuples_fetched=row[5] or 0,
                            size_bytes=row[6] or 0,
                            is_unique=row[7],
                            is_primary=row[8],
                            definition=row[9],
                            index_type=row[10],
                            columns=columns
                        )

                        # Calculate derived metrics
                        metrics.effectiveness_score = self._calculate_effectiveness_score(metrics)
                        metrics.scan_efficiency = self._calculate_scan_efficiency(metrics)
                        metrics.usage_frequency = self._calculate_usage_frequency(metrics)
                        metrics.maintenance_cost = self._calculate_maintenance_cost(metrics)

                        metrics_list.append(metrics)

                    return metrics_list
        except Exception as e:
            print(f"Error fetching index usage stats: {e}")
            return []

    def _parse_index_columns(self, definition: str) -> List[str]:
        """Extract column names from index definition."""
        try:
            # Extract columns between parentheses
            start = definition.find("(")
            end = definition.find(")")
            if start != -1 and end != -1:
                cols_str = definition[start+1:end]
                # Handle expressions and strip whitespace
                columns = [c.strip() for c in cols_str.split(",")]
                return columns
        except Exception:
            pass
        return []

    def _calculate_effectiveness_score(self, metrics: IndexMetrics) -> float:
        """
        Calculate overall effectiveness score (0.0-1.0) based on multiple factors.

        Factors:
        - Usage frequency
        - Scan efficiency
        - Size vs benefit ratio
        - Age and maintenance cost
        """
        if metrics.is_primary:
            return 1.0  # Primary keys are always considered effective

        # Usage component (40% weight)
        usage_score = min(metrics.scans / max(self.min_usage_threshold, 1), 1.0) * 0.4

        # Efficiency component (30% weight)
        if metrics.tuples_read > 0:
            fetch_ratio = metrics.tuples_fetched / metrics.tuples_read
            efficiency_score = min(fetch_ratio, 1.0) * 0.3
        else:
            efficiency_score = 0.0

        # Size component (20% weight) - smaller is better
        size_mb = metrics.size_bytes / (1024 * 1024)
        size_penalty = max(0, 1.0 - (size_mb / 1000)) * 0.2

        # Unique indexes get bonus (10% weight)
        unique_bonus = 0.1 if metrics.is_unique else 0.0

        total_score = usage_score + efficiency_score + size_penalty + unique_bonus
        return float(f"{min(total_score, 1.0):.3f}")

    def _calculate_scan_efficiency(self, metrics: IndexMetrics) -> float:
        """Calculate how efficiently the index is used when scanned."""
        if metrics.tuples_read == 0:
            return 0.0

        efficiency = metrics.tuples_fetched / metrics.tuples_read
        return float(f"{min(efficiency, 1.0):.3f}")

    def _calculate_usage_frequency(self, metrics: IndexMetrics) -> float:
        """Calculate normalized usage frequency score."""
        # Normalize to 0-1 scale based on threshold
        frequency = min(metrics.scans / max(self.min_usage_threshold * 10, 1), 1.0)
        return float(f"{frequency:.3f}")

    def _calculate_maintenance_cost(self, metrics: IndexMetrics) -> float:
        """
        Estimate maintenance cost based on size and type.
        Returns normalized cost (0.0-1.0).
        """
        # Size cost
        size_mb = metrics.size_bytes / (1024 * 1024)
        size_cost = min(size_mb / 1000, 1.0) * 0.5

        # Type cost (some index types are more expensive to maintain)
        type_costs = {
            "btree": 0.3,
            "hash": 0.2,
            "gin": 0.8,
            "gist": 0.7,
            "brin": 0.1,
            "sp-gist": 0.6
        }
        type_cost = type_costs.get(metrics.index_type.lower(), 0.5) * 0.5

        total_cost = size_cost + type_cost
        return float(f"{total_cost:.3f}")

    def identify_unused_indexes(
        self,
        min_scans: Optional[int] = None,
        exclude_primary: bool = True
    ) -> List[IndexMetrics]:
        """
        Identify indexes that are not being used.

        Args:
            min_scans: Minimum scan threshold (uses default if None)
            exclude_primary: Whether to exclude primary key indexes

        Returns:
            List of unused index metrics
        """
        threshold = min_scans if min_scans is not None else self.min_usage_threshold
        all_indexes = self.get_index_usage_stats()

        unused = []
        for idx in all_indexes:
            if idx.scans < threshold:
                if not (exclude_primary and idx.is_primary):
                    unused.append(idx)

        return unused

    def identify_redundant_indexes(self) -> List[Tuple[IndexMetrics, IndexMetrics, str]]:
        """
        Identify redundant or duplicate indexes.

        Returns:
            List of tuples: (index1, index2, redundancy_reason)
        """
        all_indexes = self.get_index_usage_stats()
        redundant_pairs = []

        # Group by table
        by_table: Dict[str, List[IndexMetrics]] = {}
        for idx in all_indexes:
            if idx.table_name not in by_table:
                by_table[idx.table_name] = []
            by_table[idx.table_name].append(idx)

        # Check each table's indexes for redundancy
        for _table_name, indexes in by_table.items():
            for i, idx1 in enumerate(indexes):
                for idx2 in indexes[i+1:]:
                    reason = self._check_redundancy(idx1, idx2)
                    if reason:
                        redundant_pairs.append((idx1, idx2, reason))

        return redundant_pairs

    def _check_redundancy(
        self,
        idx1: IndexMetrics,
        idx2: IndexMetrics
    ) -> Optional[str]:
        """Check if two indexes are redundant and return reason."""
        # Skip if different types
        if idx1.index_type != idx2.index_type:
            return None

        # Check for exact duplicates
        if idx1.columns == idx2.columns:
            return "Exact duplicate"

        # Check for subset (leftmost prefix rule for btree)
        if idx1.index_type.lower() == "btree":
            # Check if idx1 columns are a prefix of idx2
            if len(idx1.columns) < len(idx2.columns):
                if idx2.columns[:len(idx1.columns)] == idx1.columns:
                    return f"{idx1.index_name} is redundant (prefix of {idx2.index_name})"

            # Check reverse
            if len(idx2.columns) < len(idx1.columns):
                if idx1.columns[:len(idx2.columns)] == idx2.columns:
                    return f"{idx2.index_name} is redundant (prefix of {idx1.index_name})"

        return None

    def generate_recommendations(
        self,
        query_patterns: Optional[List[Dict[str, Any]]] = None,
        table_stats: Optional[Dict[str, Any]] = None
    ) -> List[IndexRecommendation]:
        """
        Generate intelligent index recommendations based on usage patterns.

        Args:
            query_patterns: List of analyzed query patterns
            table_stats: Table statistics for informed decisions

        Returns:
            Prioritized list of index recommendations
        """
        recommendations = []

        # Get current index state
        current_indexes = self.get_index_usage_stats()
        unused = self.identify_unused_indexes()
        redundant = self.identify_redundant_indexes()

        # Recommend dropping unused indexes
        for idx in unused:
            if not idx.is_primary and idx.scans < self.min_usage_threshold // 2:
                rec = IndexRecommendation(
                    action="drop",
                    priority=7,
                    table_name=idx.table_name,
                    index_type=idx.index_type,
                    columns=[idx.index_name],
                    rationale=f"Unused index with only {idx.scans} scans. Size: {idx.size_bytes / 1024 / 1024:.1f} MB",
                    estimated_benefit=float(idx.size_bytes / (1024 * 1024)),  # MB saved
                    estimated_cost_bytes=0,
                    confidence=0.9
                )
                recommendations.append(rec)

        # Recommend dropping redundant indexes
        for idx1, idx2, reason in redundant:
            # Keep the one with more usage
            to_drop = idx1 if idx1.scans < idx2.scans else idx2

            if not to_drop.is_primary:
                rec = IndexRecommendation(
                    action="drop",
                    priority=8,
                    table_name=to_drop.table_name,
                    index_type=to_drop.index_type,
                    columns=[to_drop.index_name],
                    rationale=f"Redundant index: {reason}",
                    estimated_benefit=float(to_drop.size_bytes / (1024 * 1024)),
                    estimated_cost_bytes=0,
                    confidence=0.95
                )
                recommendations.append(rec)

        # Analyze query patterns for new index opportunities
        if query_patterns:
            pattern_recs = self._analyze_query_patterns_for_indexes(
                query_patterns, current_indexes
            )
            recommendations.extend(pattern_recs)

        # Sort by priority (highest first)
        recommendations.sort(key=lambda x: x.priority, reverse=True)

        return recommendations

    def _analyze_query_patterns_for_indexes(
        self,
        patterns: List[Dict[str, Any]],
        current_indexes: List[IndexMetrics]
    ) -> List[IndexRecommendation]:
        """Analyze query patterns to suggest new indexes."""
        recommendations = []

        # Track frequently filtered columns
        column_usage: Dict[str, Dict[str, int]] = {}  # {table: {column: count}}

        for pattern in patterns:
            tables = pattern.get("tables", [])
            filters = pattern.get("filters", [])
            order_by = pattern.get("order_by", [])

            for table in tables:
                if table not in column_usage:
                    column_usage[table] = {}

                # Track filter columns
                for filter_col in filters:
                    col_name = self._extract_column_name(filter_col)
                    if col_name:
                        column_usage[table][col_name] = column_usage[table].get(col_name, 0) + 1

                # Track order by columns
                for order_col in order_by:
                    col_name = self._extract_column_name(order_col)
                    if col_name:
                        column_usage[table][col_name] = column_usage[table].get(col_name, 0) + 1

        # Generate recommendations for frequently used columns without indexes
        for table, columns in column_usage.items():
            for column, count in columns.items():
                if count >= 5:  # Threshold for recommendation
                    # Check if index already exists
                    has_index = any(
                        idx.table_name == table and column in idx.columns
                        for idx in current_indexes
                    )

                    if not has_index:
                        rec = IndexRecommendation(
                            action="create",
                            priority=min(9, 5 + (count // 10)),
                            table_name=table,
                            index_type="btree",
                            columns=[column],
                            rationale=f"Column used in {count} queries without index",
                            estimated_benefit=float(count * 10),  # Arbitrary benefit score
                            estimated_cost_bytes=1024 * 1024,  # Estimate 1MB
                            confidence=0.8
                        )
                        recommendations.append(rec)

        return recommendations

    def _extract_column_name(self, filter_str: str) -> Optional[str]:
        """Extract clean column name from filter string."""
        try:
            # Handle simple cases like "column = value" or "table.column"
            parts = filter_str.split("=")[0].strip().split(".")
            return parts[-1].strip()
        except Exception:
            return None

    def get_index_health_summary(self) -> Dict[str, Any]:
        """
        Generate comprehensive health summary for all indexes.

        Returns:
            Dictionary with health metrics and scores
        """
        all_indexes = self.get_index_usage_stats()
        unused = self.identify_unused_indexes()
        redundant = self.identify_redundant_indexes()

        # Calculate aggregate metrics
        total_size_bytes = sum(idx.size_bytes for idx in all_indexes)
        total_scans = sum(idx.scans for idx in all_indexes)
        avg_effectiveness = (
            sum(idx.effectiveness_score for idx in all_indexes) / len(all_indexes)
            if all_indexes else 0.0
        )

        # Health score (0-100)
        health_score = self._calculate_overall_health_score(
            all_indexes, unused, redundant
        )

        return {
            "health_score": health_score,
            "total_indexes": len(all_indexes),
            "unused_indexes": len(unused),
            "redundant_pairs": len(redundant),
            "total_size_mb": float(f"{total_size_bytes / (1024 * 1024):.2f}"),
            "total_scans": total_scans,
            "avg_effectiveness": float(f"{avg_effectiveness:.3f}"),
            "indexes_by_type": self._group_by_type(all_indexes),
            "top_performers": [
                {
                    "name": idx.index_name,
                    "table": idx.table_name,
                    "scans": idx.scans,
                    "effectiveness": idx.effectiveness_score
                }
                for idx in sorted(all_indexes, key=lambda x: x.effectiveness_score, reverse=True)[:5]
            ],
            "worst_performers": [
                {
                    "name": idx.index_name,
                    "table": idx.table_name,
                    "scans": idx.scans,
                    "effectiveness": idx.effectiveness_score
                }
                for idx in sorted(all_indexes, key=lambda x: x.effectiveness_score)[:5]
            ]
        }

    def _calculate_overall_health_score(
        self,
        all_indexes: List[IndexMetrics],
        unused: List[IndexMetrics],
        redundant: List[Tuple]
    ) -> int:
        """Calculate overall index health score (0-100)."""
        if not all_indexes:
            return 100

        # Factors:
        unused_penalty = (len(unused) / len(all_indexes)) * 30
        redundant_penalty = (len(redundant) / max(len(all_indexes), 1)) * 20

        avg_effectiveness = sum(idx.effectiveness_score for idx in all_indexes) / len(all_indexes)
        effectiveness_score = avg_effectiveness * 50

        final_score = 100 - unused_penalty - redundant_penalty + effectiveness_score - 50
        return int(max(0, min(100, final_score)))

    def _group_by_type(self, indexes: List[IndexMetrics]) -> Dict[str, int]:
        """Group indexes by type with counts."""
        counts: Dict[str, int] = {}
        for idx in indexes:
            counts[idx.index_type] = counts.get(idx.index_type, 0) + 1
        return counts


def get_index_manager(schema: str = "public") -> IndexLifecycleManager:
    """Factory function to get index manager instance."""
    return IndexLifecycleManager(schema=schema)

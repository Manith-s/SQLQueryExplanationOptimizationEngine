"""
Statistics Collector for Database Analysis

Gathers comprehensive table and column statistics, tracks data patterns,
and predicts future characteristics for intelligent index management.
"""

from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
from collections import defaultdict
import statistics

from app.core.db import run_sql, get_conn
from app.core.config import settings


@dataclass
class TableStatistics:
    """Comprehensive statistics for a table."""
    schema_name: str
    table_name: str
    row_count: int
    total_size_bytes: int
    index_size_bytes: int
    toast_size_bytes: int
    last_vacuum: Optional[datetime]
    last_autovacuum: Optional[datetime]
    last_analyze: Optional[datetime]
    n_tup_ins: int  # Inserts since last analyze
    n_tup_upd: int  # Updates since last analyze
    n_tup_del: int  # Deletes since last analyze
    n_live_tup: int
    n_dead_tup: int
    vacuum_count: int
    autovacuum_count: int
    analyze_count: int
    autoanalyze_count: int


@dataclass
class ColumnStatistics:
    """Statistics for a single column."""
    schema_name: str
    table_name: str
    column_name: str
    data_type: str
    null_frac: float  # Fraction of nulls
    avg_width: int  # Average width in bytes
    n_distinct: float  # Number of distinct values (-1 = all unique, >0 = count, 0-1 = fraction)
    correlation: Optional[float]  # Physical order correlation (-1 to 1)
    most_common_vals: Optional[List[Any]]
    most_common_freqs: Optional[List[float]]


@dataclass
class DataGrowthPattern:
    """Data growth pattern for a table."""
    table_name: str
    measurement_start: datetime
    measurement_end: datetime
    initial_row_count: int
    final_row_count: int
    growth_rate_per_day: float
    insert_rate_per_day: float
    update_rate_per_day: float
    delete_rate_per_day: float
    predicted_row_count_30d: int


class StatisticsCollector:
    """
    Collects and analyzes comprehensive database statistics for
    intelligent index management decisions.
    """

    def __init__(self, schema: str = "public"):
        self.schema = schema
        self._growth_history: Dict[str, List[TableStatistics]] = defaultdict(list)

    def collect_table_statistics(
        self,
        table_name: Optional[str] = None
    ) -> List[TableStatistics]:
        """
        Collect comprehensive statistics for tables.

        Args:
            table_name: Specific table to analyze (or None for all)

        Returns:
            List of TableStatistics objects
        """
        query = """
        SELECT
            schemaname,
            relname,
            n_tup_ins,
            n_tup_upd,
            n_tup_del,
            n_live_tup,
            n_dead_tup,
            last_vacuum,
            last_autovacuum,
            last_analyze,
            last_autoanalyze,
            vacuum_count,
            autovacuum_count,
            analyze_count,
            autoanalyze_count
        FROM pg_stat_user_tables
        WHERE schemaname = %s
        """

        params = [self.schema]
        if table_name:
            query += " AND relname = %s"
            params.append(table_name)

        query += " ORDER BY n_live_tup DESC;"

        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, tuple(params))
                    rows = cur.fetchall()

                    stats_list = []
                    for row in rows:
                        # Get size information
                        size_info = self._get_table_size(row[0], row[1])

                        stats = TableStatistics(
                            schema_name=row[0],
                            table_name=row[1],
                            n_tup_ins=row[2] or 0,
                            n_tup_upd=row[3] or 0,
                            n_tup_del=row[4] or 0,
                            n_live_tup=row[5] or 0,
                            n_dead_tup=row[6] or 0,
                            last_vacuum=row[7],
                            last_autovacuum=row[8],
                            last_analyze=row[9],
                            last_autoanalyze=row[10],
                            vacuum_count=row[11] or 0,
                            autovacuum_count=row[12] or 0,
                            analyze_count=row[13] or 0,
                            autoanalyze_count=row[14] or 0,
                            row_count=row[5] or 0,  # n_live_tup
                            **size_info
                        )

                        stats_list.append(stats)

                        # Store for growth tracking
                        self._growth_history[stats.table_name].append(stats)

                    return stats_list

        except Exception as e:
            print(f"Error collecting table statistics: {e}")
            return []

    def _get_table_size(self, schema: str, table: str) -> Dict[str, int]:
        """Get detailed size information for a table."""
        query = """
        SELECT
            pg_total_relation_size(%s::regclass) as total_size,
            pg_relation_size(%s::regclass) as table_size,
            pg_indexes_size(%s::regclass) as index_size,
            pg_total_relation_size(%s::regclass) -
                pg_relation_size(%s::regclass) -
                pg_indexes_size(%s::regclass) as toast_size;
        """

        qualified_name = f"{schema}.{table}"
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, [qualified_name] * 6)
                    row = cur.fetchone()

                    return {
                        "total_size_bytes": row[0] or 0,
                        "index_size_bytes": row[2] or 0,
                        "toast_size_bytes": row[3] or 0
                    }
        except Exception:
            return {
                "total_size_bytes": 0,
                "index_size_bytes": 0,
                "toast_size_bytes": 0
            }

    def collect_column_statistics(
        self,
        table_name: str
    ) -> List[ColumnStatistics]:
        """
        Collect detailed column-level statistics.

        Args:
            table_name: Table to analyze

        Returns:
            List of ColumnStatistics objects
        """
        query = """
        SELECT
            schemaname,
            tablename,
            attname,
            null_frac,
            avg_width,
            n_distinct,
            correlation,
            most_common_vals::text,
            most_common_freqs::text
        FROM pg_stats
        WHERE schemaname = %s AND tablename = %s
        ORDER BY attname;
        """

        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    # Get column data types first
                    col_types = self._get_column_types(table_name)

                    cur.execute(query, (self.schema, table_name))
                    rows = cur.fetchall()

                    stats_list = []
                    for row in rows:
                        col_name = row[2]
                        data_type = col_types.get(col_name, "unknown")

                        # Parse most common values
                        mcv = self._parse_array_literal(row[7]) if row[7] else None
                        mcf = self._parse_array_literal(row[8]) if row[8] else None

                        stats = ColumnStatistics(
                            schema_name=row[0],
                            table_name=row[1],
                            column_name=col_name,
                            data_type=data_type,
                            null_frac=float(row[3] or 0.0),
                            avg_width=int(row[4] or 0),
                            n_distinct=float(row[5] or 0.0),
                            correlation=float(row[6]) if row[6] is not None else None,
                            most_common_vals=mcv,
                            most_common_freqs=mcf
                        )

                        stats_list.append(stats)

                    return stats_list

        except Exception as e:
            print(f"Error collecting column statistics: {e}")
            return []

    def _get_column_types(self, table_name: str) -> Dict[str, str]:
        """Get data types for all columns in a table."""
        query = """
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = %s AND table_name = %s;
        """

        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (self.schema, table_name))
                    return {row[0]: row[1] for row in cur.fetchall()}
        except Exception:
            return {}

    def _parse_array_literal(self, array_str: str) -> Optional[List[Any]]:
        """Parse PostgreSQL array literal string."""
        try:
            # Simple parser for array literals like {val1,val2,val3}
            if not array_str or array_str == "{}":
                return None

            # Remove braces
            content = array_str.strip("{}").strip()
            if not content:
                return None

            # Split by comma (naive, doesn't handle escapes properly)
            values = [v.strip() for v in content.split(",")]
            return values[:10]  # Limit to first 10 values
        except Exception:
            return None

    def analyze_data_distribution(
        self,
        table_name: str,
        column_name: str,
        sample_size: int = 1000
    ) -> Dict[str, Any]:
        """
        Analyze data distribution for a column.

        Args:
            table_name: Table name
            column_name: Column name
            sample_size: Number of samples to analyze

        Returns:
            Distribution analysis
        """
        query = f"""
        SELECT
            {column_name},
            COUNT(*) as frequency
        FROM {self.schema}.{table_name}
        GROUP BY {column_name}
        ORDER BY frequency DESC
        LIMIT %s;
        """

        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (sample_size,))
                    rows = cur.fetchall()

                    if not rows:
                        return {"error": "No data"}

                    values = [r[0] for r in rows if r[0] is not None]
                    frequencies = [r[1] for r in rows]

                    total_count = sum(frequencies)
                    unique_count = len(values)

                    # Calculate cardinality score
                    cardinality = unique_count / max(total_count, 1)

                    # Calculate skewness (concentration in top values)
                    top_10_freq = sum(frequencies[:10])
                    skewness = top_10_freq / max(total_count, 1)

                    return {
                        "column": column_name,
                        "total_sampled": total_count,
                        "unique_values": unique_count,
                        "cardinality": float(f"{cardinality:.3f}"),
                        "skewness": float(f"{skewness:.3f}"),
                        "top_values": [
                            {"value": str(r[0]), "count": r[1], "pct": float(f"{r[1]/total_count*100:.2f}")}
                            for r in rows[:5]
                        ],
                        "distribution_type": self._classify_distribution(cardinality, skewness)
                    }

        except Exception as e:
            return {"error": str(e)}

    def _classify_distribution(self, cardinality: float, skewness: float) -> str:
        """Classify distribution type based on metrics."""
        if cardinality > 0.9:
            return "high_cardinality"  # Good for btree indexes
        elif cardinality < 0.01:
            return "low_cardinality"   # Better for bitmap/partial indexes
        elif skewness > 0.8:
            return "highly_skewed"     # Partial indexes may help
        else:
            return "normal"

    def predict_data_growth(
        self,
        table_name: str,
        days_ahead: int = 30
    ) -> Optional[DataGrowthPattern]:
        """
        Predict future data growth based on historical patterns.

        Args:
            table_name: Table to analyze
            days_ahead: Days to predict ahead

        Returns:
            DataGrowthPattern object or None
        """
        history = self._growth_history.get(table_name, [])

        if len(history) < 2:
            # Not enough historical data
            return None

        # Get oldest and newest measurements
        history_sorted = sorted(history, key=lambda x: x.last_analyze or datetime.min)
        first = history_sorted[0]
        last = history_sorted[-1]

        # Calculate time delta
        time_delta_days = 1.0  # Default to 1 day if timestamps unavailable
        if first.last_analyze and last.last_analyze:
            time_delta = last.last_analyze - first.last_analyze
            time_delta_days = max(time_delta.total_seconds() / 86400, 1.0)

        # Calculate rates
        row_growth = last.row_count - first.row_count
        insert_growth = last.n_tup_ins - first.n_tup_ins
        update_growth = last.n_tup_upd - first.n_tup_upd
        delete_growth = last.n_tup_del - first.n_tup_del

        growth_rate_per_day = row_growth / time_delta_days
        insert_rate_per_day = insert_growth / time_delta_days
        update_rate_per_day = update_growth / time_delta_days
        delete_rate_per_day = delete_growth / time_delta_days

        # Predict future row count
        predicted_rows = last.row_count + int(growth_rate_per_day * days_ahead)

        return DataGrowthPattern(
            table_name=table_name,
            measurement_start=first.last_analyze or datetime.utcnow(),
            measurement_end=last.last_analyze or datetime.utcnow(),
            initial_row_count=first.row_count,
            final_row_count=last.row_count,
            growth_rate_per_day=float(f"{growth_rate_per_day:.2f}"),
            insert_rate_per_day=float(f"{insert_rate_per_day:.2f}"),
            update_rate_per_day=float(f"{update_rate_per_day:.2f}"),
            delete_rate_per_day=float(f"{delete_rate_per_day:.2f}"),
            predicted_row_count_30d=max(0, predicted_rows)
        )

    def analyze_table_bloat(self, table_name: str) -> Dict[str, Any]:
        """
        Analyze table bloat (wasted space due to dead tuples).

        Args:
            table_name: Table to analyze

        Returns:
            Bloat analysis
        """
        query = """
        SELECT
            schemaname,
            tablename,
            n_live_tup,
            n_dead_tup,
            CASE WHEN n_live_tup > 0
                THEN n_dead_tup::float / n_live_tup
                ELSE 0
            END as dead_tuple_ratio,
            last_autovacuum,
            autovacuum_count
        FROM pg_stat_user_tables
        WHERE schemaname = %s AND tablename = %s;
        """

        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(query, (self.schema, table_name))
                    row = cur.fetchone()

                    if not row:
                        return {"error": "Table not found"}

                    dead_ratio = float(row[4])
                    bloat_severity = "critical" if dead_ratio > 0.2 else \
                                   "warning" if dead_ratio > 0.1 else \
                                   "ok"

                    return {
                        "table_name": table_name,
                        "live_tuples": row[2],
                        "dead_tuples": row[3],
                        "dead_tuple_ratio": float(f"{dead_ratio:.3f}"),
                        "bloat_severity": bloat_severity,
                        "last_autovacuum": row[5].isoformat() if row[5] else None,
                        "autovacuum_count": row[6],
                        "recommendation": self._get_bloat_recommendation(dead_ratio)
                    }

        except Exception as e:
            return {"error": str(e)}

    def _get_bloat_recommendation(self, dead_ratio: float) -> str:
        """Get recommendation based on bloat level."""
        if dead_ratio > 0.2:
            return "Critical bloat. Run VACUUM FULL during maintenance window"
        elif dead_ratio > 0.1:
            return "Moderate bloat. Run VACUUM or adjust autovacuum settings"
        else:
            return "Bloat within acceptable range"

    def get_comprehensive_analysis(
        self,
        table_name: str
    ) -> Dict[str, Any]:
        """
        Get comprehensive analysis combining all statistics.

        Args:
            table_name: Table to analyze

        Returns:
            Complete analysis report
        """
        # Collect all statistics
        table_stats_list = self.collect_table_statistics(table_name)
        table_stats = table_stats_list[0] if table_stats_list else None

        column_stats = self.collect_column_statistics(table_name)
        growth_pattern = self.predict_data_growth(table_name)
        bloat_analysis = self.analyze_table_bloat(table_name)

        # Build comprehensive report
        report = {
            "table_name": table_name,
            "schema": self.schema,
            "analyzed_at": datetime.utcnow().isoformat(),
            "table_statistics": {
                "row_count": table_stats.row_count if table_stats else 0,
                "size_mb": float(f"{(table_stats.total_size_bytes if table_stats else 0) / (1024*1024):.2f}"),
                "index_size_mb": float(f"{(table_stats.index_size_bytes if table_stats else 0) / (1024*1024):.2f}"),
                "dead_tuples": table_stats.n_dead_tup if table_stats else 0,
                "last_analyze": table_stats.last_analyze.isoformat() if table_stats and table_stats.last_analyze else None
            },
            "column_analysis": [
                {
                    "column": c.column_name,
                    "type": c.data_type,
                    "null_fraction": float(f"{c.null_frac:.3f}"),
                    "distinct_values": c.n_distinct,
                    "correlation": c.correlation,
                    "avg_bytes": c.avg_width
                }
                for c in column_stats
            ],
            "growth_pattern": {
                "growth_rate_per_day": growth_pattern.growth_rate_per_day if growth_pattern else 0,
                "predicted_rows_30d": growth_pattern.predicted_row_count_30d if growth_pattern else 0,
                "insert_rate_per_day": growth_pattern.insert_rate_per_day if growth_pattern else 0
            } if growth_pattern else None,
            "bloat_analysis": bloat_analysis
        }

        # Add recommendations
        report["recommendations"] = self._generate_recommendations(
            table_stats, column_stats, growth_pattern, bloat_analysis
        )

        return report

    def _generate_recommendations(
        self,
        table_stats: Optional[TableStatistics],
        column_stats: List[ColumnStatistics],
        growth_pattern: Optional[DataGrowthPattern],
        bloat_analysis: Dict[str, Any]
    ) -> List[str]:
        """Generate recommendations based on analysis."""
        recommendations = []

        # Check bloat
        if bloat_analysis.get("bloat_severity") == "critical":
            recommendations.append("⚠️  Critical table bloat detected. Schedule VACUUM FULL")

        # Check for high cardinality columns
        high_card_cols = [c for c in column_stats if c.n_distinct > 1000]
        if high_card_cols:
            recommendations.append(f"✓ High cardinality columns detected: {', '.join(c.column_name for c in high_card_cols[:3])} - Good candidates for btree indexes")

        # Check for low cardinality columns
        low_card_cols = [c for c in column_stats if 0 < c.n_distinct < 10]
        if low_card_cols:
            recommendations.append(f"ℹ️  Low cardinality columns: {', '.join(c.column_name for c in low_card_cols[:3])} - Consider partial indexes for filtered queries")

        # Check growth pattern
        if growth_pattern and growth_pattern.growth_rate_per_day > 1000:
            recommendations.append(f"📈 High growth rate ({growth_pattern.growth_rate_per_day:.0f} rows/day) - Monitor index maintenance costs")

        # Check for skewed null distributions
        high_null_cols = [c for c in column_stats if c.null_frac > 0.5]
        if high_null_cols:
            recommendations.append(f"ℹ️  Columns with >50% nulls: {', '.join(c.column_name for c in high_null_cols[:3])} - Consider partial indexes with IS NOT NULL")

        return recommendations if recommendations else ["✓ No immediate optimization opportunities detected"]


def get_stats_collector(schema: str = "public") -> StatisticsCollector:
    """Factory function to get statistics collector instance."""
    return StatisticsCollector(schema)

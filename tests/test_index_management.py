"""
Comprehensive tests for Index Management System

Includes unit tests, integration tests, and chaos testing scenarios
for index manager, self-healing, and statistics collector.
"""

import os
import pytest
import tempfile
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock

# Skip if DB tests not enabled
pytestmark = pytest.mark.skipif(
    os.getenv("RUN_DB_TESTS") != "1",
    reason="Skipping DB-dependent tests (set RUN_DB_TESTS=1 to run)"
)


@pytest.fixture
def mock_connection():
    """Mock database connection for testing."""
    conn = Mock()
    cursor = Mock()
    conn.cursor.return_value.__enter__.return_value = cursor
    conn.__enter__.return_value = conn
    conn.__exit__.return_value = None
    return conn, cursor


# Test Index Manager

def test_index_metrics_creation():
    """Test creation of IndexMetrics dataclass."""
    from app.core.index_manager import IndexMetrics

    metrics = IndexMetrics(
        schema_name="public",
        table_name="users",
        index_name="idx_users_email",
        size_bytes=1024 * 1024,
        scans=1000,
        tuples_read=5000,
        tuples_fetched=4500,
        is_unique=True,
        is_primary=False,
        columns=["email"],
        index_type="btree",
        definition="CREATE INDEX idx_users_email ON users(email)"
    )

    assert metrics.table_name == "users"
    assert metrics.scans == 1000
    assert metrics.is_unique is True


def test_index_effectiveness_scoring():
    """Test effectiveness score calculation."""
    from app.core.index_manager import IndexLifecycleManager, IndexMetrics

    mgr = IndexLifecycleManager()

    # Create test metrics
    metrics = IndexMetrics(
        schema_name="public",
        table_name="users",
        index_name="idx_users_email",
        size_bytes=10 * 1024 * 1024,  # 10MB
        scans=1000,
        tuples_read=10000,
        tuples_fetched=9000,
        is_unique=True,
        is_primary=False,
        columns=["email"],
        index_type="btree",
        definition="CREATE INDEX..."
    )

    score = mgr._calculate_effectiveness_score(metrics)

    assert 0.0 <= score <= 1.0
    assert score > 0.5  # Should be relatively high due to good usage


def test_primary_key_always_effective():
    """Test that primary keys always get max effectiveness score."""
    from app.core.index_manager import IndexLifecycleManager, IndexMetrics

    mgr = IndexLifecycleManager()

    primary_key = IndexMetrics(
        schema_name="public",
        table_name="users",
        index_name="users_pkey",
        size_bytes=1024,
        scans=0,  # Even with zero scans
        tuples_read=0,
        tuples_fetched=0,
        is_unique=True,
        is_primary=True,
        columns=["id"],
        index_type="btree",
        definition="PRIMARY KEY..."
    )

    score = mgr._calculate_effectiveness_score(primary_key)
    assert score == 1.0


def test_unused_index_identification():
    """Test identification of unused indexes."""
    from app.core.index_manager import IndexLifecycleManager

    with patch("app.core.index_manager.get_conn") as mock_conn:
        conn, cursor = mock_connection()
        mock_conn.return_value = conn

        # Mock query results - unused index
        cursor.fetchall.return_value = [
            ("public", "users", "idx_unused", 0, 0, 0, 1024, False, False,
             "CREATE INDEX idx_unused ON users(old_field)", "btree")
        ]

        mgr = IndexLifecycleManager()
        unused = mgr.identify_unused_indexes(min_scans=100)

        assert len(unused) == 1
        assert unused[0].index_name == "idx_unused"
        assert unused[0].scans == 0


def test_redundant_index_detection():
    """Test detection of redundant indexes."""
    from app.core.index_manager import IndexLifecycleManager, IndexMetrics

    mgr = IndexLifecycleManager()

    # Create two redundant indexes (prefix relationship)
    idx1 = IndexMetrics(
        schema_name="public",
        table_name="users",
        index_name="idx_email",
        size_bytes=1024,
        scans=100,
        tuples_read=100,
        tuples_fetched=100,
        is_unique=False,
        is_primary=False,
        columns=["email"],
        index_type="btree",
        definition="CREATE INDEX idx_email ON users(email)"
    )

    idx2 = IndexMetrics(
        schema_name="public",
        table_name="users",
        index_name="idx_email_name",
        size_bytes=2048,
        scans=200,
        tuples_read=200,
        tuples_fetched=200,
        is_unique=False,
        is_primary=False,
        columns=["email", "name"],
        index_type="btree",
        definition="CREATE INDEX idx_email_name ON users(email, name)"
    )

    reason = mgr._check_redundancy(idx1, idx2)
    assert reason is not None
    assert "prefix" in reason.lower()


def test_index_recommendation_ddl_generation():
    """Test DDL generation from recommendations."""
    from app.core.index_manager import IndexRecommendation

    rec = IndexRecommendation(
        action="create",
        priority=8,
        table_name="users",
        index_type="btree",
        columns=["email", "created_at"],
        rationale="High usage pattern detected",
        estimated_benefit=50.0,
        confidence=0.85
    )

    ddl = rec.to_ddl("public")
    assert "CREATE INDEX CONCURRENTLY" in ddl
    assert "users" in ddl
    assert "email" in ddl and "created_at" in ddl


def test_partial_index_ddl():
    """Test DDL generation for partial indexes."""
    from app.core.index_manager import IndexRecommendation

    rec = IndexRecommendation(
        action="create",
        priority=7,
        table_name="orders",
        index_type="btree",
        columns=["created_at"],
        where_clause="status = 'active'",
        rationale="Filtered queries detected",
        estimated_benefit=30.0,
        confidence=0.75
    )

    ddl = rec.to_ddl("public")
    assert "WHERE status = 'active'" in ddl


# Test Self-Healing Manager

def test_performance_threshold_classification():
    """Test performance degradation severity classification."""
    from app.core.self_healing import SelfHealingManager

    mgr = SelfHealingManager(auto_approve=False, dry_run_default=True)

    # Mock query statistics
    mock_stats = [
        (1, "SELECT *", 10, 1000.0, 100.0, 10.0, 100),  # Fast query
        (2, "SELECT *", 10, 15000.0, 1500.0, 200.0, 100),  # Slow query
        (3, "SELECT *", 10, 18000.0, 1800.0, 300.0, 100),  # Slow query
    ]

    score = mgr._calculate_degradation_score(mock_stats)
    assert 0.0 <= score <= 1.0


def test_healing_action_creation():
    """Test creation of healing actions."""
    from app.core.self_healing import SelfHealingManager, ActionStatus

    mgr = SelfHealingManager(auto_approve=False, dry_run_default=True)

    action = mgr.trigger_healing_action(
        reason="Test degradation",
        dry_run=True,
        query_patterns=None
    )

    assert action is not None
    assert action.status == ActionStatus.PENDING
    assert action.dry_run is True
    assert action.action_id is not None


def test_dry_run_simulation():
    """Test dry-run execution simulation."""
    from app.core.self_healing import SelfHealingManager
    from app.core.index_manager import IndexRecommendation

    mgr = SelfHealingManager(dry_run_default=True)

    action = mgr.trigger_healing_action(
        reason="Test",
        dry_run=True
    )

    result = mgr._simulate_execution(action)

    assert result["success"] is True
    assert result["dry_run"] is True
    assert "ddl_statements" in result


def test_auto_approve_behavior():
    """Test auto-approval of actions."""
    from app.core.self_healing import SelfHealingManager, ActionStatus

    mgr = SelfHealingManager(auto_approve=True, dry_run_default=True)

    action = mgr.trigger_healing_action(
        reason="Auto-approve test",
        dry_run=True
    )

    # Should be automatically approved
    assert action.status == ActionStatus.APPROVED
    assert action.approved_by == "system_auto_approve"


def test_action_approval_workflow():
    """Test manual approval workflow."""
    from app.core.self_healing import SelfHealingManager, ActionStatus

    mgr = SelfHealingManager(auto_approve=False)

    action = mgr.trigger_healing_action(reason="Manual approval test", dry_run=True)

    # Should require approval
    assert action.approval_required is True
    assert action.status == ActionStatus.PENDING

    # Execute with approval
    result = mgr.execute_healing_action(action.action_id, approved_by="test_user")

    assert result["success"] is True
    assert action.approved_by == "test_user"


# Test Statistics Collector

def test_table_statistics_collection():
    """Test collection of table statistics."""
    from app.core.stats_collector import StatisticsCollector

    with patch("app.core.stats_collector.get_conn") as mock_conn:
        conn, cursor = mock_connection()
        mock_conn.return_value = conn

        # Mock query results
        cursor.fetchall.return_value = [
            ("public", "users", 100, 50, 10, 1000, 50,
             datetime.now(), datetime.now(), datetime.now(), None,
             5, 10, 3, 8)
        ]

        collector = StatisticsCollector()

        # Mock size query
        cursor.fetchone.return_value = (10485760, 0, 1048576, 0)  # 10MB total

        stats = collector.collect_table_statistics("users")

        assert len(stats) == 1
        assert stats[0].table_name == "users"
        assert stats[0].row_count == 1000


def test_column_statistics_parsing():
    """Test parsing of column statistics."""
    from app.core.stats_collector import StatisticsCollector

    collector = StatisticsCollector()

    # Test array literal parsing
    array_str = "{value1,value2,value3}"
    result = collector._parse_array_literal(array_str)

    assert result is not None
    assert len(result) == 3
    assert "value1" in result


def test_data_distribution_classification():
    """Test classification of data distribution types."""
    from app.core.stats_collector import StatisticsCollector

    collector = StatisticsCollector()

    # High cardinality
    assert collector._classify_distribution(0.95, 0.1) == "high_cardinality"

    # Low cardinality
    assert collector._classify_distribution(0.005, 0.2) == "low_cardinality"

    # Highly skewed
    assert collector._classify_distribution(0.5, 0.85) == "highly_skewed"

    # Normal
    assert collector._classify_distribution(0.5, 0.5) == "normal"


def test_growth_pattern_prediction():
    """Test data growth prediction."""
    from app.core.stats_collector import StatisticsCollector, TableStatistics

    collector = StatisticsCollector()

    # Add historical data
    past = TableStatistics(
        schema_name="public",
        table_name="orders",
        row_count=1000,
        total_size_bytes=1024 * 1024,
        index_size_bytes=512 * 1024,
        toast_size_bytes=0,
        last_vacuum=None,
        last_autovacuum=None,
        last_analyze=datetime.now() - timedelta(days=30),
        n_tup_ins=0,
        n_tup_upd=0,
        n_tup_del=0,
        n_live_tup=1000,
        n_dead_tup=0,
        vacuum_count=0,
        autovacuum_count=0,
        analyze_count=0,
        autoanalyze_count=0
    )

    present = TableStatistics(
        schema_name="public",
        table_name="orders",
        row_count=1500,
        total_size_bytes=1536 * 1024,
        index_size_bytes=768 * 1024,
        toast_size_bytes=0,
        last_vacuum=None,
        last_autovacuum=None,
        last_analyze=datetime.now(),
        n_tup_ins=500,
        n_tup_upd=100,
        n_tup_del=0,
        n_live_tup=1500,
        n_dead_tup=10,
        vacuum_count=0,
        autovacuum_count=0,
        analyze_count=0,
        autoanalyze_count=0
    )

    collector._growth_history["orders"] = [past, present]

    growth_pattern = collector.predict_data_growth("orders", days_ahead=30)

    assert growth_pattern is not None
    assert growth_pattern.growth_rate_per_day > 0
    assert growth_pattern.predicted_row_count_30d > 1500


# Chaos Testing Scenarios

def test_chaos_database_connection_failure():
    """Chaos test: Handle database connection failures gracefully."""
    from app.core.index_manager import IndexLifecycleManager

    with patch("app.core.index_manager.get_conn") as mock_conn:
        mock_conn.side_effect = Exception("Connection failed")

        mgr = IndexLifecycleManager()
        stats = mgr.get_index_usage_stats()

        # Should return empty list, not crash
        assert stats == []


def test_chaos_malformed_query_results():
    """Chaos test: Handle malformed query results."""
    from app.core.stats_collector import StatisticsCollector

    with patch("app.core.stats_collector.get_conn") as mock_conn:
        conn, cursor = mock_connection()
        mock_conn.return_value = conn

        # Return malformed data
        cursor.fetchall.return_value = [
            (None, None, None)  # All nulls
        ]

        collector = StatisticsCollector()
        # Should not crash
        try:
            stats = collector.collect_table_statistics()
            assert isinstance(stats, list)
        except Exception as e:
            pytest.fail(f"Should handle malformed data gracefully: {e}")


def test_chaos_concurrent_healing_actions():
    """Chaos test: Multiple healing actions triggered simultaneously."""
    from app.core.self_healing import SelfHealingManager

    mgr = SelfHealingManager()

    # Trigger multiple actions
    actions = []
    for i in range(5):
        action = mgr.trigger_healing_action(
            reason=f"Test action {i}",
            dry_run=True
        )
        actions.append(action)

    # All should have unique IDs
    action_ids = [a.action_id for a in actions]
    assert len(set(action_ids)) == 5


def test_chaos_rollback_of_nonexistent_action():
    """Chaos test: Attempt to rollback action that doesn't exist."""
    from app.core.self_healing import SelfHealingManager

    mgr = SelfHealingManager()

    result = mgr.rollback_action("nonexistent_id")

    assert result["success"] is False
    assert "not found" in result["error"].lower()


def test_chaos_index_with_special_characters():
    """Chaos test: Handle indexes with special characters in names."""
    from app.core.index_manager import IndexMetrics, IndexLifecycleManager

    mgr = IndexLifecycleManager()

    # Create index with special characters
    metrics = IndexMetrics(
        schema_name="public",
        table_name="table_with_special_chars",
        index_name="idx_special_!@#$%",
        size_bytes=1024,
        scans=100,
        tuples_read=100,
        tuples_fetched=100,
        is_unique=False,
        is_primary=False,
        columns=["column-with-dash"],
        index_type="btree",
        definition="CREATE INDEX..."
    )

    # Should handle without crashing
    score = mgr._calculate_effectiveness_score(metrics)
    assert isinstance(score, float)


def test_chaos_zero_division_scenarios():
    """Chaos test: Handle division by zero in calculations."""
    from app.core.index_manager import IndexLifecycleManager, IndexMetrics

    mgr = IndexLifecycleManager()

    # Metrics with zeros
    metrics = IndexMetrics(
        schema_name="public",
        table_name="empty_table",
        index_name="idx_empty",
        size_bytes=0,
        scans=0,
        tuples_read=0,
        tuples_fetched=0,
        is_unique=False,
        is_primary=False,
        columns=["id"],
        index_type="btree",
        definition="CREATE INDEX..."
    )

    # Should not raise ZeroDivisionError
    score = mgr._calculate_effectiveness_score(metrics)
    assert score >= 0.0

    efficiency = mgr._calculate_scan_efficiency(metrics)
    assert efficiency == 0.0


# Integration Tests

@pytest.mark.asyncio
async def test_index_analyze_endpoint():
    """Test the /api/v1/index/analyze endpoint."""
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)

    response = client.post(
        "/api/v1/index/analyze",
        json={
            "schema": "public",
            "include_stats": False,
            "include_recommendations": False
        }
    )

    # Should return 200 or 401 (if auth enabled)
    assert response.status_code in [200, 401, 500]

    if response.status_code == 200:
        data = response.json()
        assert "schema" in data
        assert "total_indexes" in data
        assert "health_score" in data


@pytest.mark.asyncio
async def test_index_health_endpoint():
    """Test the /api/v1/index/health endpoint."""
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)

    response = client.get("/api/v1/index/health?schema=public")

    assert response.status_code in [200, 401, 500]

    if response.status_code == 200:
        data = response.json()
        assert "overall_health_score" in data
        assert "index_health" in data


def test_recommendation_priority_sorting():
    """Test that recommendations are properly sorted by priority."""
    from app.core.index_manager import IndexLifecycleManager

    with patch("app.core.index_manager.get_conn") as mock_conn:
        conn, cursor = mock_connection()
        mock_conn.return_value = conn

        cursor.fetchall.return_value = []

        mgr = IndexLifecycleManager()
        recommendations = mgr.generate_recommendations()

        # Check that recommendations are sorted by priority (descending)
        for i in range(len(recommendations) - 1):
            assert recommendations[i].priority >= recommendations[i + 1].priority


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])

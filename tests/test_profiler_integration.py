"""
Integration tests for Query Performance Profiler.

Tests the complete profiler system including:
- Performance metric collection
- Trend analysis calculations
- WebSocket real-time updates
- Profile data persistence and retrieval
- Background task system
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
def temp_profiler_db():
    """Create a temporary SQLite database for testing."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".db", delete=False) as f:
        db_path = f.name

    yield db_path

    # Cleanup
    try:
        Path(db_path).unlink()
    except Exception:
        pass


@pytest.fixture
def profiler(temp_profiler_db):
    """Create a profiler instance with temporary database."""
    from app.core.profiler import QueryProfiler

    return QueryProfiler(db_path=temp_profiler_db)


def test_profiler_initialization(profiler):
    """Test profiler database initialization."""
    # Check that tables are created
    with profiler._get_connection() as conn:
        tables = conn.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type='table'
            ORDER BY name
        """
        ).fetchall()

        table_names = [t["name"] for t in tables]

    assert "query_executions" in table_names
    assert "performance_alerts" in table_names
    assert "optimization_recommendations" in table_names


def test_record_execution(profiler):
    """Test recording query execution."""
    query = "SELECT * FROM users WHERE id = 1"

    query_hash = profiler.record_execution(
        query=query,
        execution_time_ms=123.456,
        total_cost=42.5,
        planning_time_ms=5.2,
        execution_rows=1,
        buffer_hits=100,
        buffer_misses=10,
        metadata={"test": True},
    )

    assert query_hash is not None
    assert len(query_hash) == 16  # SHA256 truncated to 16 chars

    # Verify data was stored
    with profiler._get_connection() as conn:
        row = conn.execute(
            """
            SELECT * FROM query_executions
            WHERE query_hash = ?
        """,
            (query_hash,),
        ).fetchone()

    assert row is not None
    assert row["execution_time_ms"] == 123.456
    assert row["total_cost"] == 42.5
    assert row["cache_hit_rate"] == float(f"{(100 / 110 * 100):.3f}")


def test_query_statistics(profiler):
    """Test query statistics calculation."""
    query = "SELECT * FROM orders WHERE user_id = 42"

    # Record multiple executions
    times = [100.0, 120.0, 110.0, 130.0, 105.0]
    for time_ms in times:
        profiler.record_execution(
            query=query, execution_time_ms=time_ms, total_cost=50.0
        )

    # Get statistics
    stats = profiler.get_query_statistics(query=query, hours=1)

    assert stats["sample_count"] == 5
    assert "execution_time" in stats
    assert stats["execution_time"]["mean"] == 113.0
    assert stats["execution_time"]["median"] == 110.0
    assert stats["execution_time"]["min"] == 100.0
    assert stats["execution_time"]["max"] == 130.0


def test_trend_analysis(profiler):
    """Test performance trend detection."""
    query = "SELECT COUNT(*) FROM logs"

    # Record executions with increasing times (degrading performance)
    for i in range(10):
        time_ms = 100 + (i * 20)  # 100, 120, 140, ..., 280
        profiler.record_execution(query=query, execution_time_ms=time_ms)

    stats = profiler.get_query_statistics(query=query, hours=1)

    assert "trend" in stats
    trend = stats["trend"]
    assert trend["direction"] in ["degrading", "stable", "improving"]

    # With this pattern, should detect degradation
    # First half: 100, 120, 140, 160, 180 (avg = 140)
    # Second half: 200, 220, 240, 260, 280 (avg = 240)
    # Change: (240 - 140) / 140 * 100 = 71.4%
    assert trend["change_pct"] > 50


def test_degradation_alert(profiler):
    """Test performance degradation alert creation."""
    query = "SELECT * FROM products WHERE category = 'electronics'"
    query_hash = profiler._compute_query_hash(query)

    # Record historical fast executions
    for _ in range(10):
        profiler.record_execution(query=query, execution_time_ms=50.0)

    # Record recent slow executions
    for _ in range(10):
        profiler.record_execution(query=query, execution_time_ms=150.0)

    # Check for alerts
    alerts = profiler._get_recent_alerts(query_hash, hours=1)

    # Should have created degradation alert
    assert len(alerts) > 0
    alert = alerts[0]
    assert alert["alert_type"] == "performance_degradation"
    assert alert["severity"] == "warning"


def test_profile_query_execution(profiler):
    """Test comprehensive query profiling."""

    def mock_execution(query):
        """Mock execution function that returns metrics."""
        return {
            "total_cost": 42.5,
            "planning_time_ms": 5.0,
            "execution_rows": 100,
            "buffer_hits": 90,
            "buffer_misses": 10,
        }

    query = "SELECT * FROM users LIMIT 10"

    report = profiler.profile_query_execution(
        query=query, iterations=5, execution_func=mock_execution
    )

    assert report["status"] == "success"
    assert report["iterations_requested"] == 5
    assert report["iterations_successful"] == 5
    assert "execution_time_distribution" in report
    assert "results" in report
    assert len(report["results"]) == 5


def test_query_summaries(profiler):
    """Test retrieving query summaries."""
    # Record executions for multiple queries
    queries = [
        "SELECT * FROM users WHERE id = 1",
        "SELECT * FROM orders WHERE status = 'pending'",
        "SELECT COUNT(*) FROM products",
    ]

    for query in queries:
        for _ in range(3):
            profiler.record_execution(query=query, execution_time_ms=100.0)

    summaries = profiler.get_all_query_summaries(hours=1, limit=10)

    assert len(summaries) == 3
    for summary in summaries:
        assert "query_hash" in summary
        assert "query_text" in summary
        assert "execution_count" in summary
        assert summary["execution_count"] == 3


def test_cleanup_old_data(profiler):
    """Test cleaning up old profiling data."""
    query = "SELECT * FROM temp_table"

    # Record some executions
    for _ in range(5):
        profiler.record_execution(query=query, execution_time_ms=100.0)

    # Cleanup (with 0 days to delete everything)
    deleted = profiler.cleanup_old_data(days=0)

    assert deleted == 5

    # Verify data was deleted
    summaries = profiler.get_all_query_summaries(hours=1)
    assert len(summaries) == 0


def test_sliding_window(profiler):
    """Test sliding window functionality."""
    query = "SELECT * FROM metrics"
    query_hash = profiler._compute_query_hash(query)

    # Record more executions than window size
    window_size = 100
    for i in range(window_size + 50):
        profiler.record_execution(query=query, execution_time_ms=100.0 + i)

    # Check window size is limited
    window = profiler._windows[query_hash]
    assert len(window) <= window_size


def test_cache_hit_rate_calculation(profiler):
    """Test cache hit rate calculation."""
    query = "SELECT * FROM cached_table"

    # Record execution with high cache hits
    profiler.record_execution(
        query=query, execution_time_ms=50.0, buffer_hits=90, buffer_misses=10
    )

    # Get statistics
    stats = profiler.get_query_statistics(query=query, hours=1)

    assert "cache_hit_rate" in stats
    cache_rate = stats["cache_hit_rate"]["mean"]
    assert 85 <= cache_rate <= 95  # Should be ~90%


def test_percentile_calculations(profiler):
    """Test percentile calculations in statistics."""
    query = "SELECT * FROM test_table"

    # Record executions with known distribution
    times = list(range(1, 101))  # 1, 2, 3, ..., 100
    for time_ms in times:
        profiler.record_execution(query=query, execution_time_ms=float(time_ms))

    stats = profiler.get_query_statistics(query=query, hours=1)
    exec_time = stats["execution_time"]

    # Check percentiles
    assert exec_time["p50"] == 50.0  # Median
    assert exec_time["p95"] == 95.0  # 95th percentile
    assert exec_time["p99"] == 99.0  # 99th percentile


@pytest.mark.asyncio
async def test_background_tasks():
    """Test background task system."""
    from app.core.profiler_tasks import ProfilerBackgroundTasks

    tasks = ProfilerBackgroundTasks()

    # Start tasks
    await tasks.start()
    assert tasks.running is True

    # Stop tasks
    await tasks.stop()
    assert tasks.running is False


@pytest.mark.asyncio
async def test_manual_analysis(profiler):
    """Test manual analysis generation."""
    from app.core.profiler_tasks import ProfilerBackgroundTasks

    tasks = ProfilerBackgroundTasks()
    tasks.profiler = profiler

    query = "SELECT * FROM users WHERE email LIKE '%@example.com%'"
    query_hash = profiler._compute_query_hash(query)

    # Record some executions with high execution time
    for _ in range(10):
        profiler.record_execution(
            query=query,
            execution_time_ms=1500.0,  # High execution time
            buffer_hits=50,
            buffer_misses=50,  # Low cache hit rate
        )

    # Run manual analysis
    result = await tasks.run_manual_analysis(query_hash)

    assert result["status"] == "success"
    assert "recommendations" in result
    assert len(result["recommendations"]) > 0

    # Should recommend performance improvements
    rec_types = [r["type"] for r in result["recommendations"]]
    assert "performance" in rec_types or "cache" in rec_types


def test_error_handling_invalid_query(profiler):
    """Test error handling for invalid queries."""
    # Test with None query hash and no SQL
    with pytest.raises(ValueError, match="Either query or query_hash must be provided"):
        profiler.get_query_statistics()


def test_concurrent_recording(profiler):
    """Test concurrent execution recording."""
    import threading

    query = "SELECT * FROM concurrent_test"
    num_threads = 10
    records_per_thread = 5

    def record_executions():
        for _ in range(records_per_thread):
            profiler.record_execution(query=query, execution_time_ms=100.0)

    threads = []
    for _ in range(num_threads):
        thread = threading.Thread(target=record_executions)
        threads.append(thread)
        thread.start()

    for thread in threads:
        thread.join()

    # Verify all records were stored
    stats = profiler.get_query_statistics(query=query, hours=1)
    assert stats["sample_count"] == num_threads * records_per_thread


def test_empty_statistics(profiler):
    """Test statistics for query with no history."""
    query_hash = "nonexistent_hash"

    stats = profiler.get_query_statistics(query_hash=query_hash, hours=1)

    assert stats["sample_count"] == 0
    assert "message" in stats


def test_query_hash_consistency(profiler):
    """Test that query hashing is consistent."""
    query1 = "SELECT * FROM users WHERE id = 1"
    query2 = "  SELECT   *  FROM   users  WHERE  id = 1  "  # Different whitespace

    hash1 = profiler._compute_query_hash(query1)
    hash2 = profiler._compute_query_hash(query2)

    # Should normalize whitespace and produce same hash
    assert hash1 == hash2


def test_recommendation_priority_sorting(profiler):
    """Test that recommendations are sorted by priority."""
    from app.core.profiler_tasks import ProfilerBackgroundTasks

    tasks = ProfilerBackgroundTasks()

    summary = {"avg_time_ms": 1500, "execution_count": 150}  # High time  # High count

    stats = {
        "execution_time": {"mean": 1500, "std_dev": 750},
        "cache_hit_rate": {"mean": 60},  # Low cache rate
        "trend": {"direction": "degrading", "change_pct": 50},
    }

    recommendations = tasks._generate_recommendations(summary, stats)

    # Verify recommendations are sorted by priority (descending)
    priorities = [r["priority"] for r in recommendations]
    assert priorities == sorted(priorities, reverse=True)


def test_large_result_set_handling(profiler):
    """Test handling of large numbers of executions."""
    query = "SELECT * FROM large_table"

    # Record a large number of executions
    for i in range(1000):
        profiler.record_execution(query=query, execution_time_ms=100.0 + (i % 50))

    # Get statistics
    stats = profiler.get_query_statistics(query=query, hours=1)

    assert stats["sample_count"] == 1000
    assert "execution_time" in stats

    # Statistical calculations should still work
    assert stats["execution_time"]["mean"] > 0
    assert stats["execution_time"]["std_dev"] >= 0


@pytest.mark.asyncio
async def test_websocket_message_handling():
    """Test WebSocket message handling."""
    from app.routers.profile import WebSocketConnectionManager

    manager = WebSocketConnectionManager()

    # Test broadcast with no connections (should not error)
    await manager.broadcast({"type": "test", "message": "hello"})

    # Verify no connections
    assert len(manager.active_connections) == 0


def test_profiler_with_missing_metrics(profiler):
    """Test profiler handles missing optional metrics gracefully."""
    query = "SELECT * FROM partial_data"

    # Record execution with only required fields
    query_hash = profiler.record_execution(
        query=query,
        execution_time_ms=123.0,
        # No cost, buffer stats, etc.
    )

    # Get statistics
    stats = profiler.get_query_statistics(query_hash=query_hash, hours=1)

    assert stats["sample_count"] == 1
    assert "execution_time" in stats
    # Should not have cost or cache statistics
    assert "total_cost" not in stats or stats.get("total_cost") == {}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

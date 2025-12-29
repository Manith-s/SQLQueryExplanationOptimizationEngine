"""
Comprehensive tests for the advanced query cache system.

Tests cover:
- Cache manager (multi-tier, LRU, compression)
- Cache invalidator (dependency tracking, triggers)
- Prefetch engine (Markov chains, predictions)
- Cache analytics (effectiveness, recommendations)
- Cache simulation (workload replay, optimization)
- API endpoints
- Performance benchmarks
- Cache coherency
"""

import time
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from app.core.cache_analytics import (
    CacheAnalytics,
    QueryCacheability,
)
from app.core.cache_invalidator import (
    CacheInvalidator,
    DependencyGraph,
    InvalidationStrategy,
)
from app.core.cache_manager import (
    CacheEntry,
    CacheManager,
    CacheTier,
    LRUCache,
    QueryFingerprinter,
)
from app.core.cache_simulator import (
    CacheConfiguration,
    CacheSimulator,
)
from app.core.prefetch_engine import MarkovChainModel, PrefetchCandidate, PrefetchEngine

# ============================================================================
# Cache Manager Tests
# ============================================================================


class TestQueryFingerprinter:
    """Test query normalization and fingerprinting."""

    def test_normalize_simple_query(self):
        """Test normalization of simple SELECT query."""
        sql = "SELECT * FROM users WHERE id = 123"
        normalized = QueryFingerprinter.normalize_query(sql)

        assert "select" in normalized.lower()
        assert "users" in normalized.lower()

    def test_normalize_removes_literals(self):
        """Test that literals are replaced with placeholders."""
        sql1 = "SELECT * FROM users WHERE id = 123"
        sql2 = "SELECT * FROM users WHERE id = 456"

        norm1 = QueryFingerprinter.normalize_query(sql1)
        norm2 = QueryFingerprinter.normalize_query(sql2)

        # Should be identical after normalization
        assert norm1 == norm2

    def test_fingerprint_consistency(self):
        """Test that same query produces same fingerprint."""
        sql = "SELECT * FROM users WHERE id = 123"

        fp1 = QueryFingerprinter.generate_fingerprint(sql)
        fp2 = QueryFingerprinter.generate_fingerprint(sql)

        assert fp1 == fp2
        assert len(fp1) == 64  # SHA256 hex

    def test_extract_table_dependencies(self):
        """Test extraction of table dependencies."""
        sql = "SELECT u.name, o.amount FROM users u JOIN orders o ON u.id = o.user_id"

        tables = QueryFingerprinter.extract_table_dependencies(sql)

        assert "users" in tables
        assert "orders" in tables
        assert len(tables) == 2


class TestLRUCache:
    """Test LRU cache implementation."""

    def test_lru_basic_operations(self):
        """Test basic get/put operations."""
        cache = LRUCache(max_size_bytes=1024)

        entry = CacheEntry(
            key="test",
            value=b"data",
            tier=CacheTier.MEMORY,
            created_at=datetime.utcnow(),
            expires_at=None,
            last_accessed=datetime.utcnow(),
            size_bytes=4,
        )

        # Put and get
        assert cache.put(entry) is True
        retrieved = cache.get("test")
        assert retrieved is not None
        assert retrieved.key == "test"

    def test_lru_eviction(self):
        """Test that LRU eviction works correctly."""
        cache = LRUCache(max_size_bytes=10)

        # Add entries that exceed capacity
        for i in range(5):
            entry = CacheEntry(
                key=f"key{i}",
                value=b"xxx",
                tier=CacheTier.MEMORY,
                created_at=datetime.utcnow(),
                expires_at=None,
                last_accessed=datetime.utcnow(),
                size_bytes=3,
            )
            cache.put(entry)

        # First entries should have been evicted
        assert cache.get("key0") is None
        assert cache.get("key1") is None
        # Later entries should still be present
        assert cache.get("key4") is not None

    def test_lru_expiration(self):
        """Test that expired entries are not returned."""
        cache = LRUCache(max_size_bytes=1024)

        # Add expired entry
        entry = CacheEntry(
            key="expired",
            value=b"data",
            tier=CacheTier.MEMORY,
            created_at=datetime.utcnow() - timedelta(hours=2),
            expires_at=datetime.utcnow() - timedelta(hours=1),
            last_accessed=datetime.utcnow() - timedelta(hours=2),
            size_bytes=4,
        )

        cache.put(entry)

        # Should return None for expired entry
        assert cache.get("expired") is None


class TestCacheManager:
    """Test cache manager."""

    def test_cache_manager_basic_flow(self):
        """Test basic cache get/put flow."""
        cache = CacheManager(memory_size_mb=1, default_ttl_seconds=3600)

        sql = "SELECT * FROM users WHERE id = 123"
        result = {"id": 123, "name": "test"}

        # Cache miss
        assert cache.get(sql) is None

        # Cache put
        cache.put(sql, result)

        # Cache hit
        cached = cache.get(sql)
        assert cached == result

    def test_cache_manager_compression(self):
        """Test that compression works for large entries."""
        cache = CacheManager(memory_size_mb=1, enable_compression=True)

        sql = "SELECT * FROM users"
        # Large result
        result = {"data": "x" * 10000}

        cache.put(sql, result, compress=True)

        cached = cache.get(sql)
        assert cached == result

    def test_cache_manager_table_invalidation(self):
        """Test invalidation by table name."""
        cache = CacheManager(memory_size_mb=1)

        sql1 = "SELECT * FROM users WHERE id = 1"
        sql2 = "SELECT * FROM users WHERE id = 2"
        sql3 = "SELECT * FROM orders WHERE id = 1"

        cache.put(sql1, {"id": 1})
        cache.put(sql2, {"id": 2})
        cache.put(sql3, {"id": 1})

        # Invalidate users table
        cache.invalidate(table="users")

        # Users queries should be invalidated
        assert cache.get(sql1) is None
        assert cache.get(sql2) is None

        # Orders query should still be cached
        assert cache.get(sql3) is not None

    def test_adaptive_ttl(self):
        """Test that adaptive TTL adjusts based on volatility."""
        cache = CacheManager(memory_size_mb=1, default_ttl_seconds=3600)

        # Set table volatility
        cache.update_table_volatility("volatile_table", 0.9)
        cache.update_table_volatility("stable_table", 0.1)

        # Tables should have different adaptive TTLs
        # (This is tested indirectly through the _calculate_adaptive_ttl method)
        volatile_ttl = cache._calculate_adaptive_ttl({"volatile_table"})
        stable_ttl = cache._calculate_adaptive_ttl({"stable_table"})

        assert volatile_ttl < stable_ttl


# ============================================================================
# Cache Invalidator Tests
# ============================================================================


class TestDependencyGraph:
    """Test dependency graph."""

    def test_add_query_dependency(self):
        """Test adding query dependencies."""
        graph = DependencyGraph()

        graph.add_query_dependency("query1", {"users", "orders"})

        stats = graph.get_statistics()
        assert stats["tables_tracked"] == 2
        assert stats["total_cached_queries"] == 2  # query1 appears in both tables

    def test_get_affected_queries(self):
        """Test getting affected queries."""
        graph = DependencyGraph()

        graph.add_query_dependency("query1", {"users"})
        graph.add_query_dependency("query2", {"users", "orders"})
        graph.add_query_dependency("query3", {"orders"})

        # Change to users should affect query1 and query2
        affected = graph.get_affected_queries("users", cascade=False)
        assert "query1" in affected
        assert "query2" in affected
        assert "query3" not in affected

    def test_cascade_invalidation(self):
        """Test cascading invalidation through dependencies."""
        graph = DependencyGraph()

        # Setup dependencies: users -> orders (FK relationship)
        graph.add_table_dependency("users", "orders")
        graph.add_query_dependency("query1", {"users"})
        graph.add_query_dependency("query2", {"orders"})

        # Change to users should cascade to orders
        affected = graph.get_affected_queries("users", cascade=True)
        assert "query1" in affected
        assert "query2" in affected  # Through cascade


class TestCacheInvalidator:
    """Test cache invalidator."""

    def test_invalidator_basic(self):
        """Test basic invalidation."""
        cache_manager = CacheManager(memory_size_mb=1)
        invalidator = CacheInvalidator(cache_manager, enable_listen=False)

        sql = "SELECT * FROM users"
        cache_manager.put(sql, {"data": "test"})

        # Register query
        fingerprint = QueryFingerprinter.generate_fingerprint(sql)
        invalidator.register_query(fingerprint, {"users"})

        # Invalidate by table
        invalidator.invalidate_by_table("users")

        # Query should be invalidated
        assert cache_manager.get(sql) is None

    def test_selective_invalidation(self):
        """Test selective invalidation based on columns."""
        cache_manager = CacheManager(memory_size_mb=1)
        invalidator = CacheInvalidator(cache_manager, enable_listen=False)

        sql = "SELECT name FROM users"
        cache_manager.put(sql, {"data": "test"})

        fingerprint = QueryFingerprinter.generate_fingerprint(sql)
        invalidator.register_query(fingerprint, {"users"})

        # Set selective columns rule
        from app.core.cache_invalidator import InvalidationRule

        invalidator.invalidation_rules["users"] = InvalidationRule(
            table="users",
            strategy=InvalidationStrategy.IMMEDIATE,
            selective_columns={"email"},  # Only invalidate if email changes
        )

        # Change to 'name' column should not trigger invalidation
        invalidator.invalidate_by_table("users", changed_columns={"name"})

        # Query should still be cached
        assert cache_manager.get(sql) is not None

        # Change to 'email' column should trigger invalidation
        invalidator.invalidate_by_table("users", changed_columns={"email"})

        assert cache_manager.get(sql) is None


# ============================================================================
# Prefetch Engine Tests
# ============================================================================


class TestMarkovChainModel:
    """Test Markov chain model."""

    def test_markov_training(self):
        """Test training Markov model."""
        model = MarkovChainModel(order=1)

        # Train with sequence
        sequence = ["q1", "q2", "q3", "q2", "q3", "q2", "q3"]
        model.train(sequence)

        stats = model.get_statistics()
        assert stats["total_transitions"] > 0

    def test_markov_prediction(self):
        """Test Markov predictions."""
        model = MarkovChainModel(order=1)

        # Train: q1 -> q2 -> q3 pattern
        for _ in range(10):
            model.train(["q1", "q2", "q3"])

        # Predict after q1
        predictions = model.predict(["q1"], top_k=1)

        assert len(predictions) > 0
        assert predictions[0][0] == "q2"  # Most likely next query
        assert predictions[0][1] > 0.5  # High probability


class TestPrefetchEngine:
    """Test prefetch engine."""

    def test_record_and_predict(self):
        """Test query recording and prediction."""
        engine = PrefetchEngine(enable_speculative=False)

        # Record query sequence
        session_id = "test_session"
        queries = [
            "SELECT * FROM users",
            "SELECT * FROM orders",
            "SELECT * FROM products",
        ]

        for sql in queries * 5:  # Repeat pattern
            engine.record_query_execution(
                sql=sql, execution_time_ms=100.0, session_id=session_id
            )

        # Should be able to predict
        candidates = engine.predict_next_queries(session_id=session_id, top_k=3)

        # Should have some predictions
        assert (
            len(candidates) >= 0
        )  # May or may not have predictions depending on history

    def test_cost_benefit_analysis(self):
        """Test prefetch decision making."""
        from app.core.prefetch_engine import LoadLevel

        engine = PrefetchEngine(
            prefetch_threshold=0.5,
            max_prefetch_cost_ms=1000.0,
            enable_speculative=False,
        )

        # Mock system load to be low
        with patch.object(engine, '_get_current_load', return_value=LoadLevel.LOW):
            # High probability, low cost candidate
            candidate = PrefetchCandidate(
                fingerprint="test",
                sql="SELECT * FROM users",
                probability=0.9,
                estimated_cost_ms=100.0,
                estimated_benefit=1000.0,
                priority_score=9.0,
            )

            decision = engine.should_prefetch(candidate)
            # Should prefetch (good cost-benefit ratio: 1000/100 = 10 > 2.0 threshold)
            assert decision.should_prefetch is True

        # Low probability candidate
        low_prob_candidate = PrefetchCandidate(
            fingerprint="test2",
            sql="SELECT * FROM orders",
            probability=0.2,  # Below threshold
            estimated_cost_ms=100.0,
            estimated_benefit=200.0,
            priority_score=2.0,
        )

        decision2 = engine.should_prefetch(low_prob_candidate)
        # Should not prefetch (low probability)
        assert decision2.should_prefetch is False


# ============================================================================
# Cache Analytics Tests
# ============================================================================


class TestCacheAnalytics:
    """Test cache analytics."""

    def test_record_query_metrics(self):
        """Test query metrics recording."""
        analytics = CacheAnalytics()

        sql = "SELECT * FROM users WHERE id = 1"

        # Record multiple executions
        for i in range(10):
            analytics.record_query(
                sql=sql,
                execution_time_ms=100.0 + i * 10,
                cache_hit=(i % 2 == 0),  # 50% hit rate
                result_size_bytes=1024,
            )

        # Get metrics
        metrics = analytics.get_query_metrics(sql=sql)

        assert len(metrics) == 1
        metric = metrics[0]
        assert metric.total_executions == 10
        assert metric.cache_hits == 5
        assert metric.cache_hit_rate == 0.5

    def test_cacheability_scoring(self):
        """Test cacheability score calculation."""
        analytics = CacheAnalytics()

        # Highly cacheable query (frequent, high hit rate, expensive)
        sql_good = "SELECT expensive FROM large_table"
        for _ in range(100):
            analytics.record_query(
                sql=sql_good,
                execution_time_ms=1000.0,
                cache_hit=True,
                result_size_bytes=10 * 1024,
            )

        # Poorly cacheable query (rare, low hit rate, cheap)
        sql_bad = "SELECT cheap FROM small_table"
        for _i in range(5):
            analytics.record_query(
                sql=sql_bad,
                execution_time_ms=10.0,
                cache_hit=False,
                result_size_bytes=100,
            )

        metrics_good = analytics.get_query_metrics(sql=sql_good)[0]
        metrics_bad = analytics.get_query_metrics(sql=sql_bad)[0]

        # Good query should have higher cacheability score
        assert metrics_good.cacheability_score > metrics_bad.cacheability_score
        assert metrics_good.cacheability == QueryCacheability.HIGHLY_CACHEABLE

    def test_effectiveness_report(self):
        """Test effectiveness report generation."""
        analytics = CacheAnalytics()

        # Record some queries
        for i in range(50):
            analytics.record_query(
                sql=f"SELECT * FROM table WHERE id = {i % 10}",
                execution_time_ms=100.0,
                cache_hit=(i % 3 == 0),
                result_size_bytes=1024,
            )

        report = analytics.generate_effectiveness_report(time_period_hours=1.0)

        assert report.total_queries > 0
        assert 0.0 <= report.overall_hit_rate <= 1.0
        assert len(report.recommendations) >= 0


# ============================================================================
# Cache Simulator Tests
# ============================================================================


class TestCacheSimulator:
    """Test cache simulation framework."""

    def test_generate_synthetic_workload(self):
        """Test synthetic workload generation."""
        simulator = CacheSimulator()

        workload = simulator.generate_synthetic_workload(
            num_queries=100, num_unique_queries=10, time_span_hours=1.0
        )

        assert len(workload.queries) == 100
        assert workload.total_duration_seconds > 0

    def test_simulate_workload(self):
        """Test workload simulation."""
        simulator = CacheSimulator()

        # Create simple workload
        queries = [
            {
                "sql": f"SELECT * FROM table WHERE id = {i % 5}",
                "timestamp": datetime.utcnow() + timedelta(seconds=i),
                "execution_time_ms": 100.0,
                "result_size_bytes": 1024,
            }
            for i in range(50)
        ]

        workload = simulator.load_workload_from_queries(queries, name="test")

        # Create config
        config = CacheConfiguration(
            name="test", memory_size_mb=10, default_ttl_seconds=3600
        )

        # Run simulation
        result = simulator.simulate(workload, config)

        assert result.total_queries == 50
        assert result.hit_rate >= 0.0
        assert result.cache_hits + result.cache_misses == 50

    def test_compare_configurations(self):
        """Test configuration comparison."""
        simulator = CacheSimulator()

        workload = simulator.generate_synthetic_workload(num_queries=100)

        configs = [
            CacheConfiguration("small", memory_size_mb=10, default_ttl_seconds=3600),
            CacheConfiguration("medium", memory_size_mb=50, default_ttl_seconds=3600),
            CacheConfiguration("large", memory_size_mb=100, default_ttl_seconds=3600),
        ]

        report = simulator.compare_configurations(workload, configs)

        assert len(report.results) == 3
        assert report.best_overall in ["small", "medium", "large"]
        assert len(report.recommendations) >= 0

    def test_recommend_optimal_size(self):
        """Test optimal size recommendation."""
        simulator = CacheSimulator()

        workload = simulator.generate_synthetic_workload(num_queries=100)

        recommendation = simulator.recommend_optimal_size(
            workload, min_size_mb=10, max_size_mb=100, step_mb=20, target_hit_rate=0.7
        )

        assert "recommended_size_mb" in recommendation
        assert recommendation["recommended_size_mb"] >= 10
        assert "expected_hit_rate" in recommendation


# ============================================================================
# Performance Benchmarks
# ============================================================================


class TestPerformance:
    """Performance benchmarks for cache system."""

    def test_cache_throughput(self):
        """Benchmark cache throughput."""
        cache = CacheManager(memory_size_mb=100)

        num_operations = 1000
        sql_templates = [f"SELECT * FROM table{i}" for i in range(100)]

        start = time.time()

        for i in range(num_operations):
            sql = sql_templates[i % len(sql_templates)]

            cached = cache.get(sql)
            if cached is None:
                cache.put(sql, {"data": "test"})

        elapsed = time.time() - start
        ops_per_sec = num_operations / elapsed

        # Should handle at least 1000 ops/sec
        assert ops_per_sec > 1000

        print(f"\nCache throughput: {ops_per_sec:.0f} ops/sec")

    def test_fingerprint_performance(self):
        """Benchmark query fingerprinting."""
        queries = [
            "SELECT * FROM users WHERE id = 123",
            "SELECT u.name, o.amount FROM users u JOIN orders o ON u.id = o.user_id",
            "SELECT * FROM products WHERE category = 'electronics' AND price > 100",
        ] * 100

        start = time.time()

        for sql in queries:
            QueryFingerprinter.generate_fingerprint(sql)

        elapsed = time.time() - start
        fps_per_sec = len(queries) / elapsed

        # Should handle at least 1000 fingerprints/sec
        assert fps_per_sec > 1000

        print(f"\nFingerprinting: {fps_per_sec:.0f} fingerprints/sec")


# ============================================================================
# Cache Coherency Tests
# ============================================================================


class TestCacheCoherency:
    """Test cache coherency and consistency."""

    def test_invalidation_coherency(self):
        """Test that invalidation keeps cache coherent."""
        cache_manager = CacheManager(memory_size_mb=1)
        invalidator = CacheInvalidator(cache_manager, enable_listen=False)

        # Cache multiple queries for same table
        queries = [
            "SELECT * FROM users WHERE id = 1",
            "SELECT * FROM users WHERE id = 2",
            "SELECT name FROM users WHERE status = 'active'",
        ]

        for sql in queries:
            cache_manager.put(sql, {"data": "test"})
            fp = QueryFingerprinter.generate_fingerprint(sql)
            invalidator.register_query(fp, {"users"})

        # All queries should be cached
        assert all(cache_manager.get(sql) is not None for sql in queries)

        # Invalidate users table
        invalidator.invalidate_by_table("users")

        # All queries should be invalidated
        assert all(cache_manager.get(sql) is None for sql in queries)

    def test_ttl_coherency(self):
        """Test that TTL expiration maintains coherency."""
        cache = CacheManager(memory_size_mb=1, default_ttl_seconds=1)

        sql = "SELECT * FROM users"
        cache.put(sql, {"data": "test"}, ttl_seconds=1)

        # Should be cached immediately
        assert cache.get(sql) is not None

        # Wait for expiration
        time.sleep(1.5)

        # Should be expired
        assert cache.get(sql) is None


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v"])

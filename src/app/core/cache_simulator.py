"""
Cache simulation framework for performance testing and optimization.

Provides:
- Workload replay with different cache configurations
- Performance measurement under various scenarios
- Optimal cache size recommendations
- Memory pressure testing
- Configuration comparison
"""

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.cache_manager import CacheManager


@dataclass
class WorkloadQuery:
    """Single query in a workload."""

    sql: str
    timestamp: datetime
    execution_time_ms: float
    result_size_bytes: int
    session_id: Optional[str] = None
    user_id: Optional[str] = None


@dataclass
class Workload:
    """Collection of queries for simulation."""

    queries: List[WorkloadQuery]
    name: str = "workload"
    description: str = ""
    total_duration_seconds: float = 0.0

    def __post_init__(self):
        """Calculate workload duration."""
        if self.queries:
            start = min(q.timestamp for q in self.queries)
            end = max(q.timestamp for q in self.queries)
            self.total_duration_seconds = (end - start).total_seconds()


@dataclass
class CacheConfiguration:
    """Cache configuration for simulation."""

    name: str
    memory_size_mb: int
    default_ttl_seconds: int
    enable_compression: bool = True
    enable_disk: bool = False
    disk_dir: Optional[Path] = None


@dataclass
class SimulationResult:
    """Results from a cache simulation run."""

    config_name: str
    total_queries: int
    cache_hits: int
    cache_misses: int
    hit_rate: float
    miss_rate: float
    total_execution_time_ms: float
    time_saved_by_cache_ms: float
    avg_query_time_ms: float
    evictions: int
    peak_memory_bytes: int
    avg_memory_bytes: int
    memory_utilization: float
    compression_savings_bytes: int = 0
    disk_hits: int = 0

    def efficiency_score(self) -> float:
        """
        Calculate overall efficiency score (0-100).

        Combines hit rate, time savings, and memory efficiency.
        """
        # Hit rate component (50%)
        hit_rate_score = self.hit_rate * 50

        # Time savings component (30%)
        time_savings_ratio = self.time_saved_by_cache_ms / max(
            self.total_execution_time_ms, 1
        )
        time_score = min(time_savings_ratio * 100, 30)

        # Memory efficiency component (20%)
        memory_score = (1.0 - self.memory_utilization) * 20

        return hit_rate_score + time_score + memory_score


@dataclass
class ComparisonReport:
    """Comparison of multiple simulation results."""

    configurations: List[str]
    results: List[SimulationResult]
    best_overall: str
    best_hit_rate: str
    best_time_savings: str
    best_memory_efficiency: str
    recommendations: List[str]


class CacheSimulator:
    """
    Cache simulation framework for testing and optimization.

    Simulates cache behavior under different configurations and workloads
    to determine optimal settings.
    """

    def __init__(self):
        """Initialize cache simulator."""
        self.workloads: Dict[str, Workload] = {}

    def load_workload_from_queries(
        self, queries: List[Dict[str, Any]], name: str = "custom", description: str = ""
    ) -> Workload:
        """
        Load workload from query list.

        Args:
            queries: List of query dictionaries
            name: Workload name
            description: Workload description

        Returns:
            Loaded workload
        """
        workload_queries = []

        for q in queries:
            wq = WorkloadQuery(
                sql=q["sql"],
                timestamp=q.get("timestamp", datetime.utcnow()),
                execution_time_ms=q.get("execution_time_ms", 100.0),
                result_size_bytes=q.get("result_size_bytes", 1024),
                session_id=q.get("session_id"),
                user_id=q.get("user_id"),
            )
            workload_queries.append(wq)

        workload = Workload(
            queries=workload_queries, name=name, description=description
        )

        self.workloads[name] = workload
        return workload

    def load_workload_from_file(self, file_path: Path) -> Workload:
        """
        Load workload from JSON file.

        File format:
        {
            "name": "workload_name",
            "description": "...",
            "queries": [
                {
                    "sql": "SELECT ...",
                    "timestamp": "2024-01-01T00:00:00",
                    "execution_time_ms": 150.0,
                    "result_size_bytes": 2048
                },
                ...
            ]
        }

        Args:
            file_path: Path to workload file

        Returns:
            Loaded workload
        """
        with open(file_path, "r") as f:
            data = json.load(f)

        queries = []
        for q in data["queries"]:
            timestamp = (
                datetime.fromisoformat(q["timestamp"])
                if isinstance(q["timestamp"], str)
                else q["timestamp"]
            )

            queries.append(
                {
                    "sql": q["sql"],
                    "timestamp": timestamp,
                    "execution_time_ms": q.get("execution_time_ms", 100.0),
                    "result_size_bytes": q.get("result_size_bytes", 1024),
                    "session_id": q.get("session_id"),
                    "user_id": q.get("user_id"),
                }
            )

        return self.load_workload_from_queries(
            queries=queries,
            name=data.get("name", "workload"),
            description=data.get("description", ""),
        )

    def generate_synthetic_workload(
        self,
        num_queries: int = 1000,
        num_unique_queries: int = 50,
        time_span_hours: float = 1.0,
        zipf_alpha: float = 1.5,
    ) -> Workload:
        """
        Generate synthetic workload for testing.

        Uses Zipf distribution to model realistic query frequency patterns.

        Args:
            num_queries: Total number of queries
            num_unique_queries: Number of unique query templates
            time_span_hours: Time span for queries
            zipf_alpha: Zipf distribution parameter (higher = more skewed)

        Returns:
            Generated workload
        """
        import numpy as np

        # Generate unique query templates
        templates = []
        for i in range(num_unique_queries):
            templates.append(f"SELECT * FROM table_{i % 10} WHERE id = {{id}}")

        # Generate query distribution using Zipf
        ranks = np.arange(1, num_unique_queries + 1)
        probabilities = 1.0 / (ranks**zipf_alpha)
        probabilities /= probabilities.sum()

        # Generate queries
        queries = []
        start_time = datetime.utcnow()
        time_increment = (time_span_hours * 3600) / num_queries

        for i in range(num_queries):
            # Sample query template
            template_idx = np.random.choice(num_unique_queries, p=probabilities)
            sql = templates[template_idx].format(id=np.random.randint(1, 1000))

            # Generate timestamp
            timestamp = start_time + timedelta(seconds=i * time_increment)

            # Generate execution time (lognormal distribution)
            execution_time_ms = max(10.0, np.random.lognormal(4.0, 1.0))

            # Generate result size
            result_size_bytes = max(100, int(np.random.lognormal(8.0, 2.0)))

            queries.append(
                {
                    "sql": sql,
                    "timestamp": timestamp,
                    "execution_time_ms": execution_time_ms,
                    "result_size_bytes": result_size_bytes,
                    "session_id": f"session_{i % 10}",
                }
            )

        return self.load_workload_from_queries(
            queries=queries,
            name="synthetic",
            description=f"Synthetic workload with {num_queries} queries, {num_unique_queries} unique, Zipf α={zipf_alpha}",
        )

    def simulate(
        self, workload: Workload, config: CacheConfiguration, verbose: bool = False
    ) -> SimulationResult:
        """
        Simulate cache behavior for a workload.

        Args:
            workload: Workload to replay
            config: Cache configuration to test
            verbose: Print progress information

        Returns:
            Simulation results
        """
        # Create cache manager with specified config
        cache = CacheManager(
            memory_size_mb=config.memory_size_mb,
            disk_cache_dir=config.disk_dir if config.enable_disk else None,
            enable_compression=config.enable_compression,
            default_ttl_seconds=config.default_ttl_seconds,
        )

        # Simulation state
        hits = 0
        misses = 0
        total_exec_time_ms = 0.0
        time_saved_ms = 0.0
        memory_samples = []

        # Replay workload
        for i, query in enumerate(workload.queries):
            if verbose and i % 100 == 0:
                print(f"Processing query {i+1}/{len(workload.queries)}...")

            # Try to get from cache
            cached_result = cache.get(query.sql)

            if cached_result is not None:
                # Cache hit
                hits += 1
                # Assume cached access is near-instant (1ms)
                total_exec_time_ms += 1.0
                time_saved_ms += query.execution_time_ms - 1.0
            else:
                # Cache miss
                misses += 1
                total_exec_time_ms += query.execution_time_ms

                # Simulate query execution and cache result
                # Generate dummy result based on size
                result = b"x" * query.result_size_bytes

                cache.put(
                    sql=query.sql, result=result, compress=config.enable_compression
                )

            # Sample memory usage
            memory_stats = cache.memory_cache.get_stats()
            memory_samples.append(memory_stats["size_bytes"])

        # Calculate statistics
        total_queries = len(workload.queries)
        hit_rate = hits / total_queries if total_queries > 0 else 0.0
        miss_rate = misses / total_queries if total_queries > 0 else 0.0
        avg_query_time = (
            total_exec_time_ms / total_queries if total_queries > 0 else 0.0
        )

        cache_stats = cache.get_statistics()

        peak_memory = max(memory_samples) if memory_samples else 0
        avg_memory = sum(memory_samples) / len(memory_samples) if memory_samples else 0
        memory_utilization = (
            peak_memory / (config.memory_size_mb * 1024 * 1024)
            if config.memory_size_mb > 0
            else 0.0
        )

        return SimulationResult(
            config_name=config.name,
            total_queries=total_queries,
            cache_hits=hits,
            cache_misses=misses,
            hit_rate=hit_rate,
            miss_rate=miss_rate,
            total_execution_time_ms=total_exec_time_ms,
            time_saved_by_cache_ms=time_saved_ms,
            avg_query_time_ms=avg_query_time,
            evictions=cache_stats.evictions,
            peak_memory_bytes=peak_memory,
            avg_memory_bytes=int(avg_memory),
            memory_utilization=memory_utilization,
        )

    def compare_configurations(
        self,
        workload: Workload,
        configurations: List[CacheConfiguration],
        verbose: bool = False,
    ) -> ComparisonReport:
        """
        Compare multiple cache configurations on the same workload.

        Args:
            workload: Workload to test
            configurations: List of configurations to compare
            verbose: Print progress

        Returns:
            Comparison report with recommendations
        """
        results = []

        for config in configurations:
            if verbose:
                print(f"\nSimulating configuration: {config.name}")
                print(
                    f"  Memory: {config.memory_size_mb}MB, TTL: {config.default_ttl_seconds}s"
                )

            result = self.simulate(workload, config, verbose=verbose)
            results.append(result)

            if verbose:
                print(f"  Hit Rate: {result.hit_rate:.1%}")
                print(f"  Time Saved: {result.time_saved_by_cache_ms:.0f}ms")
                print(f"  Efficiency Score: {result.efficiency_score():.1f}")

        # Determine best configurations
        best_overall = max(results, key=lambda r: r.efficiency_score())
        best_hit_rate = max(results, key=lambda r: r.hit_rate)
        best_time_savings = max(results, key=lambda r: r.time_saved_by_cache_ms)
        best_memory = min(results, key=lambda r: r.memory_utilization)

        # Generate recommendations
        recommendations = self._generate_comparison_recommendations(results, workload)

        return ComparisonReport(
            configurations=[c.name for c in configurations],
            results=results,
            best_overall=best_overall.config_name,
            best_hit_rate=best_hit_rate.config_name,
            best_time_savings=best_time_savings.config_name,
            best_memory_efficiency=best_memory.config_name,
            recommendations=recommendations,
        )

    def recommend_optimal_size(
        self,
        workload: Workload,
        min_size_mb: int = 10,
        max_size_mb: int = 1000,
        step_mb: int = 50,
        target_hit_rate: float = 0.8,
    ) -> Dict[str, Any]:
        """
        Recommend optimal cache size for a workload.

        Args:
            workload: Workload to analyze
            min_size_mb: Minimum cache size to test
            max_size_mb: Maximum cache size to test
            step_mb: Step size for testing
            target_hit_rate: Target hit rate

        Returns:
            Recommendation with optimal size and analysis
        """
        configurations = []

        for size_mb in range(min_size_mb, max_size_mb + 1, step_mb):
            configurations.append(
                CacheConfiguration(
                    name=f"{size_mb}MB",
                    memory_size_mb=size_mb,
                    default_ttl_seconds=3600,
                )
            )

        # Run simulations
        results = []
        for config in configurations:
            result = self.simulate(workload, config)
            results.append((config.memory_size_mb, result))

        # Find smallest size that meets target hit rate
        optimal_size = max_size_mb
        optimal_result = None

        for size_mb, result in results:
            if result.hit_rate >= target_hit_rate:
                if size_mb < optimal_size:
                    optimal_size = size_mb
                    optimal_result = result

        # If no config meets target, use best hit rate
        if optimal_result is None:
            optimal_result = max(results, key=lambda x: x[1].hit_rate)[1]
            optimal_size = optimal_result.peak_memory_bytes // (1024 * 1024)

        return {
            "recommended_size_mb": optimal_size,
            "expected_hit_rate": optimal_result.hit_rate,
            "expected_time_savings_ms": optimal_result.time_saved_by_cache_ms,
            "efficiency_score": optimal_result.efficiency_score(),
            "all_results": [
                {
                    "size_mb": size_mb,
                    "hit_rate": result.hit_rate,
                    "time_saved_ms": result.time_saved_by_cache_ms,
                    "efficiency": result.efficiency_score(),
                }
                for size_mb, result in results
            ],
        }

    def test_memory_pressure(
        self,
        workload: Workload,
        cache_size_mb: int,
        pressure_levels: List[float] = None,
    ) -> Dict[str, Any]:
        """
        Test cache behavior under different memory pressure levels.

        Args:
            workload: Workload to test
            cache_size_mb: Base cache size
            pressure_levels: Memory pressure multipliers

        Returns:
            Results for each pressure level
        """
        if pressure_levels is None:
            pressure_levels = [0.5, 0.8, 0.95, 1.0, 1.2]
        results = {}

        for pressure in pressure_levels:
            # Adjust cache size based on pressure
            # Higher pressure = less available memory
            effective_size = int(cache_size_mb / pressure)

            config = CacheConfiguration(
                name=f"pressure_{pressure}x",
                memory_size_mb=max(10, effective_size),
                default_ttl_seconds=3600,
            )

            result = self.simulate(workload, config)

            results[f"{pressure}x"] = {
                "effective_size_mb": config.memory_size_mb,
                "hit_rate": result.hit_rate,
                "evictions": result.evictions,
                "avg_query_time_ms": result.avg_query_time_ms,
                "efficiency_score": result.efficiency_score(),
            }

        return results

    def _generate_comparison_recommendations(
        self, results: List[SimulationResult], workload: Workload
    ) -> List[str]:
        """Generate recommendations based on comparison results."""
        recommendations = []

        # Analyze hit rate variance
        hit_rates = [r.hit_rate for r in results]
        hit_rate_variance = max(hit_rates) - min(hit_rates)

        if hit_rate_variance > 0.2:
            best = max(results, key=lambda r: r.hit_rate)
            recommendations.append(
                f"Significant hit rate variation detected ({hit_rate_variance:.1%}). "
                f"Consider using '{best.config_name}' configuration for best hit rate ({best.hit_rate:.1%})"
            )

        # Analyze memory efficiency
        overutilized = [r for r in results if r.memory_utilization > 0.9]
        if overutilized:
            recommendations.append(
                f"{len(overutilized)} configuration(s) are over 90% memory utilization. "
                "Consider increasing cache size to reduce eviction pressure."
            )

        underutilized = [r for r in results if r.memory_utilization < 0.5]
        if underutilized:
            recommendations.append(
                f"{len(underutilized)} configuration(s) are under 50% memory utilization. "
                "Consider reducing cache size to optimize resource usage."
            )

        # Analyze time savings
        best_time = max(results, key=lambda r: r.time_saved_by_cache_ms)
        avg_time_saved = sum(r.time_saved_by_cache_ms for r in results) / len(results)

        if best_time.time_saved_by_cache_ms > avg_time_saved * 1.5:
            recommendations.append(
                f"Configuration '{best_time.config_name}' saves significantly more time "
                f"({best_time.time_saved_by_cache_ms:.0f}ms vs {avg_time_saved:.0f}ms average). "
                "This may be worth the additional resources."
            )

        return recommendations


# Singleton instance
_cache_simulator: Optional[CacheSimulator] = None


def get_cache_simulator() -> CacheSimulator:
    """Get singleton cache simulator instance."""
    global _cache_simulator

    if _cache_simulator is None:
        _cache_simulator = CacheSimulator()

    return _cache_simulator

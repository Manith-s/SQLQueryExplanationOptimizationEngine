"""
Locust Load Testing Suite for QEO API

This file implements realistic user behaviors and load patterns for testing
the QEO API under various conditions. It complements the K6 tests with
more complex user flows and Python-based scenarios.

Usage:
    # Run with 100 users ramping up over 60 seconds
    locust -f locustfile.py --host=http://localhost:8000 --users 100 --spawn-rate 10

    # Run headless with specific duration
    locust -f locustfile.py --host=http://localhost:8000 --users 100 --spawn-rate 10 --run-time 10m --headless

    # Run with custom scenario
    locust -f locustfile.py --host=http://localhost:8000 --headless --tags data-scientist

    # Run distributed across multiple workers
    locust -f locustfile.py --master --host=http://localhost:8000
    locust -f locustfile.py --worker --master-host=localhost
"""

import random
import time
from typing import Dict, List

from locust import HttpUser, TaskSet, between, events, tag, task
from locust.runners import MasterRunner

# Realistic test queries grouped by complexity
SIMPLE_QUERIES = [
    "SELECT * FROM users WHERE id = 42",
    "SELECT count(*) FROM orders WHERE status = 'pending'",
    "SELECT name, email FROM users WHERE created_at > '2024-01-01'",
]

MEDIUM_QUERIES = [
    "SELECT * FROM orders WHERE user_id = 123 ORDER BY created_at DESC LIMIT 10",
    "SELECT u.name, COUNT(o.id) FROM users u JOIN orders o ON u.id = o.user_id GROUP BY u.name",
    "SELECT * FROM products WHERE category = 'electronics' AND price > 100 ORDER BY price DESC",
]

COMPLEX_QUERIES = [
    """
    SELECT u.name, COUNT(o.id) as order_count, SUM(o.total) as total_spent
    FROM users u
    LEFT JOIN orders o ON u.id = o.user_id
    WHERE u.created_at > NOW() - INTERVAL '1 year'
    GROUP BY u.id, u.name
    HAVING COUNT(o.id) > 5
    ORDER BY total_spent DESC
    LIMIT 100
    """,
    """
    SELECT p.name, p.category, AVG(oi.quantity) as avg_quantity
    FROM products p
    JOIN order_items oi ON p.id = oi.product_id
    JOIN orders o ON oi.order_id = o.id
    WHERE o.created_at > NOW() - INTERVAL '30 days'
    GROUP BY p.id, p.name, p.category
    ORDER BY avg_quantity DESC
    """,
    """
    WITH monthly_sales AS (
        SELECT DATE_TRUNC('month', created_at) as month, SUM(total) as revenue
        FROM orders
        WHERE status = 'completed'
        GROUP BY DATE_TRUNC('month', created_at)
    )
    SELECT month, revenue, LAG(revenue) OVER (ORDER BY month) as prev_revenue
    FROM monthly_sales
    ORDER BY month DESC
    """,
]

# Workload files for batch testing
WORKLOAD_QUERIES = SIMPLE_QUERIES + MEDIUM_QUERIES[:2]


class QEOTaskSet(TaskSet):
    """Base task set with common QEO API operations"""

    def on_start(self):
        """Initialize user session"""
        self.client.verify = False  # Allow self-signed certs in dev
        self.session_queries = []

    @task(10)
    @tag("health")
    def health_check(self):
        """Verify API health"""
        self.client.get("/health", name="/health")

    @task(5)
    @tag("lint")
    def lint_simple_query(self):
        """Lint a simple SQL query"""
        query = random.choice(SIMPLE_QUERIES)
        self.client.post(
            "/api/v1/lint",
            json={"sql": query},
            name="/api/v1/lint [simple]",
        )

    @task(3)
    @tag("lint")
    def lint_complex_query(self):
        """Lint a complex SQL query"""
        query = random.choice(COMPLEX_QUERIES)
        self.client.post(
            "/api/v1/lint",
            json={"sql": query},
            name="/api/v1/lint [complex]",
        )

    @task(8)
    @tag("explain")
    def explain_without_analyze(self):
        """Get EXPLAIN plan without ANALYZE"""
        query = random.choice(SIMPLE_QUERIES + MEDIUM_QUERIES)
        self.client.post(
            "/api/v1/explain",
            json={"sql": query, "analyze": False},
            name="/api/v1/explain [no analyze]",
        )

    @task(4)
    @tag("explain")
    def explain_with_analyze(self):
        """Get EXPLAIN ANALYZE plan"""
        query = random.choice(SIMPLE_QUERIES)
        response = self.client.post(
            "/api/v1/explain",
            json={"sql": query, "analyze": True, "timeout_ms": 5000},
            name="/api/v1/explain [with analyze]",
        )

        if response.status_code == 200:
            data = response.json()
            # Track queries with high cost
            if data.get("plan", {}).get("Total Cost", 0) > 1000:
                self.session_queries.append(query)

    @task(6)
    @tag("optimize")
    def optimize_without_whatif(self):
        """Optimize query using heuristics only"""
        query = random.choice(MEDIUM_QUERIES)
        self.client.post(
            "/api/v1/optimize",
            json={"sql": query, "what_if": False, "top_k": 5},
            name="/api/v1/optimize [heuristic]",
        )

    @task(3)
    @tag("optimize", "whatif")
    def optimize_with_whatif(self):
        """Optimize query using HypoPG what-if analysis"""
        query = random.choice(MEDIUM_QUERIES + COMPLEX_QUERIES)
        self.client.post(
            "/api/v1/optimize",
            json={"sql": query, "what_if": True, "top_k": 8, "analyze": False},
            name="/api/v1/optimize [what-if]",
        )

    @task(2)
    @tag("schema")
    def fetch_schema(self):
        """Fetch database schema metadata"""
        self.client.get(
            "/api/v1/schema",
            params={"schema": "public"},
            name="/api/v1/schema",
        )

    @task(1)
    @tag("schema")
    def fetch_table_schema(self):
        """Fetch specific table schema"""
        tables = ["users", "orders", "products", "order_items"]
        table = random.choice(tables)
        self.client.get(
            "/api/v1/schema",
            params={"schema": "public", "table": table},
            name="/api/v1/schema [table]",
        )


class DataAnalystUser(HttpUser):
    """
    Simulates a data analyst running ad-hoc queries
    - Frequently runs EXPLAIN and OPTIMIZE
    - Uses what-if analysis for complex queries
    - Iterates on query improvements
    """

    wait_time = between(2, 5)
    weight = 3

    @tag("data-analyst")
    @task(5)
    def analyze_query(self):
        """Analyze and optimize a query iteratively"""
        query = random.choice(COMPLEX_QUERIES)

        # Step 1: Lint the query
        self.client.post("/api/v1/lint", json={"sql": query}, name="[DA] Lint")

        time.sleep(1)

        # Step 2: Get EXPLAIN plan
        explain_response = self.client.post(
            "/api/v1/explain",
            json={"sql": query, "analyze": False},
            name="[DA] Explain",
        )

        if explain_response.status_code == 200:
            time.sleep(2)

            # Step 3: Get optimization suggestions
            optimize_response = self.client.post(
                "/api/v1/optimize",
                json={"sql": query, "what_if": True, "top_k": 10},
                name="[DA] Optimize",
            )

            if optimize_response.status_code == 200:
                data = optimize_response.json()
                suggestions = data.get("suggestions", [])

                # If there are rewrite suggestions, try the first one
                rewrites = [s for s in suggestions if s.get("kind") == "rewrite"]
                if rewrites and rewrites[0].get("altSql"):
                    time.sleep(1)
                    improved_query = rewrites[0]["altSql"]
                    self.client.post(
                        "/api/v1/explain",
                        json={"sql": improved_query, "analyze": False},
                        name="[DA] Explain Improved",
                    )

    @tag("data-analyst")
    @task(2)
    def batch_workload_analysis(self):
        """Analyze multiple queries as a workload"""
        queries = random.sample(WORKLOAD_QUERIES, k=min(5, len(WORKLOAD_QUERIES)))

        self.client.post(
            "/api/v1/workload",
            json={"sqls": queries, "top_k": 10, "what_if": True},
            name="[DA] Workload",
        )


class BackendDeveloperUser(HttpUser):
    """
    Simulates a backend developer optimizing application queries
    - Tests specific queries frequently
    - Uses schema endpoints to understand database structure
    - Focuses on query performance
    """

    wait_time = between(1, 3)
    weight = 2

    @tag("backend-dev")
    @task(5)
    def optimize_app_query(self):
        """Optimize a specific application query"""
        query = random.choice(MEDIUM_QUERIES)

        # Check current performance
        self.client.post(
            "/api/v1/explain",
            json={"sql": query, "analyze": True, "timeout_ms": 3000},
            name="[BD] Explain",
        )

        time.sleep(0.5)

        # Get optimization suggestions
        self.client.post(
            "/api/v1/optimize",
            json={"sql": query, "what_if": True, "top_k": 5},
            name="[BD] Optimize",
        )

    @tag("backend-dev")
    @task(3)
    def explore_schema(self):
        """Explore database schema for query design"""
        # Fetch overall schema
        schema_response = self.client.get(
            "/api/v1/schema", params={"schema": "public"}, name="[BD] Schema"
        )

        if schema_response.status_code == 200:
            data = schema_response.json()
            tables = [t["tableName"] for t in data.get("tables", [])]

            if tables:
                time.sleep(0.5)
                # Fetch details for a specific table
                table = random.choice(tables)
                self.client.get(
                    "/api/v1/schema",
                    params={"schema": "public", "table": table},
                    name="[BD] Table Schema",
                )


class DBAdministratorUser(HttpUser):
    """
    Simulates a DBA monitoring and optimizing database performance
    - Runs workload analysis
    - Focuses on index recommendations
    - Monitors query patterns
    """

    wait_time = between(3, 8)
    weight = 1

    @tag("dba")
    @task(3)
    def analyze_workload(self):
        """Analyze entire workload for optimization opportunities"""
        # Use all query types for comprehensive analysis
        queries = random.sample(
            SIMPLE_QUERIES + MEDIUM_QUERIES + COMPLEX_QUERIES,
            k=min(10, len(SIMPLE_QUERIES + MEDIUM_QUERIES + COMPLEX_QUERIES)),
        )

        self.client.post(
            "/api/v1/workload",
            json={"sqls": queries, "top_k": 15, "what_if": True},
            name="[DBA] Workload Analysis",
        )

    @tag("dba")
    @task(2)
    def audit_expensive_queries(self):
        """Identify and optimize expensive queries"""
        query = random.choice(COMPLEX_QUERIES)

        # Get detailed execution plan
        explain_response = self.client.post(
            "/api/v1/explain",
            json={"sql": query, "analyze": True, "timeout_ms": 10000},
            name="[DBA] Analyze Expensive",
        )

        if explain_response.status_code == 200:
            time.sleep(2)

            # Get optimization recommendations
            self.client.post(
                "/api/v1/optimize",
                json={"sql": query, "what_if": True, "top_k": 10},
                name="[DBA] Optimize Expensive",
            )


class CasualUser(HttpUser):
    """
    Simulates a casual user performing basic operations
    - Simple queries
    - Basic linting and explain operations
    - Lower frequency
    """

    wait_time = between(5, 15)
    weight = 4

    tasks = [QEOTaskSet]


# Custom statistics tracking
request_stats: Dict[str, List[float]] = {}


@events.request.add_listener
def on_request(
    request_type, name, response_time, response_length, exception, context, **kwargs
):
    """Track custom statistics per request"""
    if name not in request_stats:
        request_stats[name] = []
    request_stats[name].append(response_time)


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Generate summary statistics at test completion"""
    if not isinstance(environment.runner, MasterRunner):
        print("\n" + "=" * 80)
        print("QEO LOAD TEST SUMMARY")
        print("=" * 80)

        for endpoint, times in sorted(request_stats.items()):
            if times:
                avg = sum(times) / len(times)
                p95 = sorted(times)[int(len(times) * 0.95)] if len(times) > 20 else max(times)
                p99 = sorted(times)[int(len(times) * 0.99)] if len(times) > 100 else max(times)

                print(f"\n{endpoint}:")
                print(f"  Requests: {len(times)}")
                print(f"  Avg: {avg:.2f}ms")
                print(f"  P95: {p95:.2f}ms")
                print(f"  P99: {p99:.2f}ms")

        print("\n" + "=" * 80)


# Example custom scenarios
class StressTestUser(HttpUser):
    """
    High-frequency stress testing user
    - Minimal wait time
    - Focus on core endpoints
    """

    wait_time = between(0.1, 0.5)
    weight = 10

    @tag("stress")
    @task(10)
    def rapid_optimize(self):
        """Rapidly fire optimization requests"""
        query = random.choice(SIMPLE_QUERIES + MEDIUM_QUERIES)
        self.client.post(
            "/api/v1/optimize",
            json={"sql": query, "what_if": False, "top_k": 3},
            name="[STRESS] Optimize",
        )

    @tag("stress")
    @task(5)
    def rapid_explain(self):
        """Rapidly fire explain requests"""
        query = random.choice(SIMPLE_QUERIES)
        self.client.post(
            "/api/v1/explain",
            json={"sql": query, "analyze": False},
            name="[STRESS] Explain",
        )


class SoakTestUser(HttpUser):
    """
    Long-running soak testing user
    - Moderate frequency
    - Mix of all operations
    - Designed for extended runs
    """

    wait_time = between(10, 30)
    weight = 5

    tasks = [QEOTaskSet]

    @tag("soak")
    @task(1)
    def comprehensive_workflow(self):
        """Execute a complete workflow to test all systems"""
        query = random.choice(COMPLEX_QUERIES)

        # Full workflow
        self.client.post("/api/v1/lint", json={"sql": query}, name="[SOAK] Lint")
        time.sleep(2)

        self.client.post(
            "/api/v1/explain", json={"sql": query, "analyze": False}, name="[SOAK] Explain"
        )
        time.sleep(3)

        self.client.post(
            "/api/v1/optimize",
            json={"sql": query, "what_if": True, "top_k": 8},
            name="[SOAK] Optimize",
        )
        time.sleep(5)

        self.client.get("/api/v1/schema", params={"schema": "public"}, name="[SOAK] Schema")

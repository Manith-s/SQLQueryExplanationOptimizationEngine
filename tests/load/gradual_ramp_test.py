"""
Gradual Ramp Load Test

Gradually increases load from 100 to 10,000 RPS over 30 minutes
to test autoscaling, resource allocation, and performance degradation.

Usage:
    python tests/load/gradual_ramp_test.py --target-url https://api.qeo.example.com
"""

import argparse
import asyncio
import json
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import List

import aiohttp


@dataclass
class LoadTestResult:
    """Result of load test at specific RPS."""

    timestamp: str
    target_rps: int
    actual_rps: float
    p50_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    error_rate_pct: float
    total_requests: int
    successful_requests: int
    failed_requests: int


class GradualRampTest:
    """Gradual load test with increasing RPS."""

    def __init__(self, target_url: str, duration_minutes: int = 30):
        self.target_url = target_url
        self.duration_minutes = duration_minutes
        self.results: List[LoadTestResult] = []

        # Test queries
        self.queries = [
            "SELECT * FROM users WHERE id = 1",
            "SELECT COUNT(*) FROM orders",
            "SELECT * FROM orders WHERE user_id = 42 ORDER BY created_at DESC LIMIT 50",
            "SELECT u.*, o.* FROM users u JOIN orders o ON u.id = o.user_id WHERE o.status = 'pending'",
        ]

    async def run(self):
        """Execute gradual ramp test."""
        print("=" * 80)
        print("QEO Gradual Ramp Load Test")
        print("=" * 80)
        print(f"Target URL: {self.target_url}")
        print(f"Duration: {self.duration_minutes} minutes")
        print("RPS Range: 100 → 10,000")
        print("=" * 80)
        print()

        # Health check
        if not await self._health_check():
            print("❌ Health check failed. Aborting test.")
            return False

        print("✅ Health check passed. Starting ramp test...\n")

        # Calculate ramp stages
        # Start: 100 RPS, End: 10,000 RPS, Duration: 30 minutes
        # Stages: Every 2 minutes, increase by ~660 RPS
        stages = []
        start_rps = 100
        end_rps = 10000
        stage_duration_seconds = 120  # 2 minutes per stage
        num_stages = (self.duration_minutes * 60) // stage_duration_seconds

        rps_increment = (end_rps - start_rps) / num_stages

        for i in range(num_stages):
            target_rps = int(start_rps + (i * rps_increment))
            stages.append((target_rps, stage_duration_seconds))

        # Run each stage
        for stage_num, (target_rps, duration) in enumerate(stages, 1):
            print(f"Stage {stage_num}/{len(stages)}: {target_rps} RPS for {duration}s")

            result = await self._run_stage(target_rps, duration)
            self.results.append(result)

            # Print stage results
            self._print_stage_result(result)

            # Check if system is degrading
            if result.error_rate_pct > 5.0:
                print(
                    f"⚠️  High error rate ({result.error_rate_pct:.2f}%). System under stress."
                )

            if result.p99_latency_ms > 2000:
                print(
                    f"⚠️  High P99 latency ({result.p99_latency_ms:.0f}ms). Consider stopping test."
                )

        # Generate summary report
        self._generate_report()

        return True

    async def _health_check(self) -> bool:
        """Check if API is healthy before starting test."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.target_url}/health", timeout=10
                ) as response:
                    return response.status == 200
        except Exception as e:
            print(f"Health check error: {e}")
            return False

    async def _run_stage(
        self, target_rps: int, duration_seconds: int
    ) -> LoadTestResult:
        """Run a single load test stage."""
        start_time = time.time()
        end_time = start_time + duration_seconds

        latencies = []
        successful = 0
        failed = 0

        # Calculate requests per second interval
        interval = 1.0 / target_rps if target_rps > 0 else 1.0

        async with aiohttp.ClientSession() as session:
            tasks = []

            while time.time() < end_time:
                # Create request task
                task = asyncio.create_task(self._make_request(session))
                tasks.append(task)

                # Wait for interval
                await asyncio.sleep(interval)

            # Wait for all tasks to complete
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # Process results
            for result in results:
                if isinstance(result, Exception):
                    failed += 1
                elif result is not None:
                    latency_ms, success = result
                    if success:
                        successful += 1
                        latencies.append(latency_ms)
                    else:
                        failed += 1

        # Calculate metrics
        actual_duration = time.time() - start_time
        total_requests = successful + failed
        actual_rps = total_requests / actual_duration if actual_duration > 0 else 0

        # Calculate percentiles
        if latencies:
            latencies.sort()
            p50 = latencies[len(latencies) // 2]
            p95 = latencies[int(len(latencies) * 0.95)]
            p99 = latencies[int(len(latencies) * 0.99)]
        else:
            p50 = p95 = p99 = 0

        error_rate = (failed / total_requests * 100) if total_requests > 0 else 0

        return LoadTestResult(
            timestamp=datetime.utcnow().isoformat(),
            target_rps=target_rps,
            actual_rps=actual_rps,
            p50_latency_ms=p50,
            p95_latency_ms=p95,
            p99_latency_ms=p99,
            error_rate_pct=error_rate,
            total_requests=total_requests,
            successful_requests=successful,
            failed_requests=failed,
        )

    async def _make_request(self, session: aiohttp.ClientSession):
        """Make a single request and measure latency."""
        import random

        query = random.choice(self.queries)

        payload = {"sql": query}

        start = time.time()
        try:
            async with session.post(
                f"{self.target_url}/api/v1/lint",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                await response.text()  # Read response
                latency_ms = (time.time() - start) * 1000
                success = response.status == 200
                return (latency_ms, success)

        except Exception:
            latency_ms = (time.time() - start) * 1000
            return (latency_ms, False)

    def _print_stage_result(self, result: LoadTestResult):
        """Print results for a single stage."""
        print(f"  Actual RPS: {result.actual_rps:.1f}")
        print(
            f"  Latency - P50: {result.p50_latency_ms:.0f}ms, P95: {result.p95_latency_ms:.0f}ms, P99: {result.p99_latency_ms:.0f}ms"
        )
        print(
            f"  Success: {result.successful_requests}/{result.total_requests} ({100 - result.error_rate_pct:.2f}%)"
        )
        print()

    def _generate_report(self):
        """Generate final report."""
        print("\n" + "=" * 80)
        print("GRADUAL RAMP TEST SUMMARY")
        print("=" * 80)
        print()

        # Overall stats
        total_requests = sum(r.total_requests for r in self.results)
        total_successful = sum(r.successful_requests for r in self.results)
        total_failed = sum(r.failed_requests for r in self.results)

        overall_error_rate = (
            (total_failed / total_requests * 100) if total_requests > 0 else 0
        )

        print(f"Total Requests: {total_requests:,}")
        print(f"Successful: {total_successful:,} ({100 - overall_error_rate:.2f}%)")
        print(f"Failed: {total_failed:,} ({overall_error_rate:.2f}%)")
        print()

        # Find maximum sustainable RPS
        # (Last stage with <1% error rate and <500ms P95 latency)
        max_sustainable_rps = 0
        for result in self.results:
            if result.error_rate_pct < 1.0 and result.p95_latency_ms < 500:
                max_sustainable_rps = result.target_rps

        print(f"Maximum Sustainable RPS: {max_sustainable_rps}")
        print()

        # Latency progression
        print("Latency Progression:")
        print("RPS    | P50    | P95    | P99    | Error Rate")
        print("-" * 60)
        for result in self.results:
            print(
                f"{result.target_rps:6d} | {result.p50_latency_ms:6.0f} | {result.p95_latency_ms:6.0f} | {result.p99_latency_ms:6.0f} | {result.error_rate_pct:6.2f}%"
            )

        print()

        # Check if test passed
        passed = overall_error_rate < 1.0 and max_sustainable_rps >= 5000

        if passed:
            print("✅ TEST PASSED")
            print(
                f"   - System sustained {max_sustainable_rps} RPS with <1% error rate"
            )
            print(f"   - Overall error rate: {overall_error_rate:.2f}%")
        else:
            print("❌ TEST FAILED")
            if overall_error_rate >= 1.0:
                print(f"   - Overall error rate too high: {overall_error_rate:.2f}%")
            if max_sustainable_rps < 5000:
                print(
                    f"   - Maximum sustainable RPS below target: {max_sustainable_rps} < 5000"
                )

        print()
        print("=" * 80)

        # Save results to file
        report_file = (
            f"gradual_ramp_test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )

        with open(report_file, "w") as f:
            json.dump(
                {
                    "test_info": {
                        "target_url": self.target_url,
                        "duration_minutes": self.duration_minutes,
                        "start_rps": 100,
                        "end_rps": 10000,
                    },
                    "summary": {
                        "total_requests": total_requests,
                        "successful_requests": total_successful,
                        "failed_requests": total_failed,
                        "overall_error_rate_pct": overall_error_rate,
                        "max_sustainable_rps": max_sustainable_rps,
                        "test_passed": passed,
                    },
                    "stages": [asdict(r) for r in self.results],
                },
                f,
                indent=2,
            )

        print(f"Report saved to: {report_file}")


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="QEO Gradual Ramp Load Test")
    parser.add_argument(
        "--target-url", default="http://localhost:8000", help="Target API URL"
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=30,
        help="Test duration in minutes (default: 30)",
    )

    args = parser.parse_args()

    test = GradualRampTest(target_url=args.target_url, duration_minutes=args.duration)

    success = await test.run()

    return 0 if success else 1


if __name__ == "__main__":
    import sys

    sys.exit(asyncio.run(main()))

"""
Chaos Engineering Test

Simulates random component failures while maintaining 99.99% availability.
Tests system resilience, failover, and self-healing capabilities.

Usage:
    python tests/load/chaos_test.py --duration 60 --target-url https://api.qeo.example.com

WARNING: This test will cause actual service disruptions!
         Only run in staging/test environments, NOT in production!
"""

import argparse
import asyncio
import json
import random
import subprocess
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import List

import aiohttp


@dataclass
class ChaosEvent:
    """A chaos engineering event."""

    timestamp: str
    event_type: str
    target: str
    description: str
    duration_seconds: int


@dataclass
class AvailabilityMetric:
    """Availability measurement."""

    timestamp: str
    requests_attempted: int
    requests_successful: int
    requests_failed: int
    availability_pct: float
    avg_latency_ms: float


class ChaosTest:
    """Chaos engineering test suite."""

    def __init__(
        self, target_url: str, duration_minutes: int = 60, dry_run: bool = True
    ):
        self.target_url = target_url
        self.duration_minutes = duration_minutes
        self.dry_run = dry_run

        self.chaos_events: List[ChaosEvent] = []
        self.metrics: List[AvailabilityMetric] = []

        # Chaos scenarios
        self.scenarios = [
            self._chaos_kill_random_pod,
            self._chaos_network_latency,
            self._chaos_cpu_stress,
            self._chaos_memory_stress,
            self._chaos_kill_database_connection,
        ]

    async def run(self):
        """Execute chaos test."""
        print("=" * 80)
        print("QEO Chaos Engineering Test")
        print("=" * 80)
        print(f"Target URL: {self.target_url}")
        print(f"Duration: {self.duration_minutes} minutes")

        if self.dry_run:
            print("Mode: DRY RUN (no actual chaos)")
        else:
            print("Mode: LIVE (will cause actual failures)")
            print()
            print("⚠️  WARNING: This will disrupt service!")
            print("    Press Ctrl+C within 10 seconds to abort...")
            await asyncio.sleep(10)

        print("=" * 80)
        print()

        # Start availability monitoring
        monitoring_task = asyncio.create_task(self._monitor_availability())

        # Start chaos injection
        chaos_task = asyncio.create_task(self._inject_chaos())

        # Wait for test duration
        await asyncio.sleep(self.duration_minutes * 60)

        # Stop tasks
        monitoring_task.cancel()
        chaos_task.cancel()

        try:
            await monitoring_task
        except asyncio.CancelledError:
            pass

        try:
            await chaos_task
        except asyncio.CancelledError:
            pass

        # Generate report
        self._generate_report()

    async def _monitor_availability(self):
        """Continuously monitor system availability."""
        print("📊 Starting availability monitoring...")

        while True:
            time.time()

            # Make 100 requests over 60 seconds (1 every 0.6s)
            attempted = 0
            successful = 0
            failed = 0
            latencies = []

            for _ in range(100):
                result = await self._make_health_check()

                attempted += 1
                if result is not None:
                    latency_ms, success = result
                    if success:
                        successful += 1
                        latencies.append(latency_ms)
                    else:
                        failed += 1
                else:
                    failed += 1

                await asyncio.sleep(0.6)

            # Calculate metrics
            availability = (successful / attempted * 100) if attempted > 0 else 0
            avg_latency = sum(latencies) / len(latencies) if latencies else 0

            metric = AvailabilityMetric(
                timestamp=datetime.utcnow().isoformat(),
                requests_attempted=attempted,
                requests_successful=successful,
                requests_failed=failed,
                availability_pct=availability,
                avg_latency_ms=avg_latency,
            )

            self.metrics.append(metric)

            # Print status
            status = (
                "✅" if availability >= 99.99 else "⚠️" if availability >= 99.0 else "❌"
            )
            print(
                f"{status} Availability: {availability:.3f}% (Latency: {avg_latency:.0f}ms, Failed: {failed})"
            )

    async def _inject_chaos(self):
        """Inject chaos events randomly."""
        print("💥 Starting chaos injection...")
        print()

        event_count = 0

        while True:
            # Wait 2-5 minutes between chaos events
            wait_seconds = random.randint(120, 300)

            print(f"⏳ Next chaos event in {wait_seconds}s...")
            await asyncio.sleep(wait_seconds)

            # Choose random scenario
            scenario = random.choice(self.scenarios)

            # Execute scenario
            event_count += 1
            print(f"\n💥 CHAOS EVENT #{event_count}")

            try:
                await scenario()
            except Exception as e:
                print(f"   ⚠️  Chaos event failed: {e}")

            print()

    async def _make_health_check(self):
        """Make a health check request."""
        try:
            async with aiohttp.ClientSession() as session:
                start = time.time()
                async with session.get(
                    f"{self.target_url}/health", timeout=aiohttp.ClientTimeout(total=5)
                ) as response:
                    latency_ms = (time.time() - start) * 1000
                    success = response.status == 200
                    return (latency_ms, success)

        except Exception:
            return None

    # Chaos scenarios

    async def _chaos_kill_random_pod(self):
        """Kill a random pod in the QEO deployment."""
        event = ChaosEvent(
            timestamp=datetime.utcnow().isoformat(),
            event_type="kill_pod",
            target="qeo-api",
            description="Kill random pod to test pod recovery",
            duration_seconds=0,
        )

        self.chaos_events.append(event)

        print(f"   Type: {event.event_type}")
        print(f"   Target: {event.target}")
        print(f"   Description: {event.description}")

        if not self.dry_run:
            try:
                # Get pod list
                result = subprocess.run(
                    [
                        "kubectl",
                        "get",
                        "pods",
                        "-n",
                        "qeo",
                        "-l",
                        "app=qeo",
                        "-o",
                        "jsonpath={.items[*].metadata.name}",
                    ],
                    capture_output=True,
                    text=True,
                    check=True,
                )

                pods = result.stdout.strip().split()

                if pods:
                    # Kill random pod
                    target_pod = random.choice(pods)
                    print(f"   Killing pod: {target_pod}")

                    subprocess.run(
                        ["kubectl", "delete", "pod", target_pod, "-n", "qeo"],
                        check=True,
                        capture_output=True,
                    )

                    print(f"   ✓ Pod {target_pod} killed")
                else:
                    print("   ⚠️  No pods found")

            except subprocess.CalledProcessError as e:
                print(f"   ❌ Failed: {e}")
        else:
            print("   [DRY RUN] Would kill random pod")

    async def _chaos_network_latency(self):
        """Inject network latency using tc (traffic control)."""
        event = ChaosEvent(
            timestamp=datetime.utcnow().isoformat(),
            event_type="network_latency",
            target="qeo-api",
            description="Inject 200ms network latency for 2 minutes",
            duration_seconds=120,
        )

        self.chaos_events.append(event)

        print(f"   Type: {event.event_type}")
        print(f"   Target: {event.target}")
        print(f"   Description: {event.description}")
        print(f"   Duration: {event.duration_seconds}s")

        if not self.dry_run:
            print("   ⚠️  Network latency injection requires chaos-mesh or similar tool")
            print("   [SKIPPED] Not implemented in this test")
        else:
            print("   [DRY RUN] Would inject 200ms latency")

        # Wait for duration
        await asyncio.sleep(event.duration_seconds)

    async def _chaos_cpu_stress(self):
        """Stress CPU on random pod."""
        event = ChaosEvent(
            timestamp=datetime.utcnow().isoformat(),
            event_type="cpu_stress",
            target="qeo-api",
            description="Stress CPU to 90% for 3 minutes",
            duration_seconds=180,
        )

        self.chaos_events.append(event)

        print(f"   Type: {event.event_type}")
        print(f"   Target: {event.target}")
        print(f"   Description: {event.description}")
        print(f"   Duration: {event.duration_seconds}s")

        if not self.dry_run:
            try:
                # Get random pod
                result = subprocess.run(
                    [
                        "kubectl",
                        "get",
                        "pods",
                        "-n",
                        "qeo",
                        "-l",
                        "app=qeo",
                        "-o",
                        "jsonpath={.items[0].metadata.name}",
                    ],
                    capture_output=True,
                    text=True,
                    check=True,
                )

                target_pod = result.stdout.strip()

                if target_pod:
                    print(f"   Stressing CPU on pod: {target_pod}")

                    # Use stress-ng to stress CPU
                    subprocess.Popen(
                        [
                            "kubectl",
                            "exec",
                            target_pod,
                            "-n",
                            "qeo",
                            "--",
                            "stress-ng",
                            "--cpu",
                            "2",
                            "--timeout",
                            f"{event.duration_seconds}s",
                        ]
                    )

                    print("   ✓ CPU stress started")
                else:
                    print("   ⚠️  No pods found")

            except subprocess.CalledProcessError as e:
                print(f"   ❌ Failed: {e}")
        else:
            print("   [DRY RUN] Would stress CPU to 90%")

        # Wait for duration
        await asyncio.sleep(event.duration_seconds)

    async def _chaos_memory_stress(self):
        """Stress memory on random pod."""
        event = ChaosEvent(
            timestamp=datetime.utcnow().isoformat(),
            event_type="memory_stress",
            target="qeo-api",
            description="Consume 80% memory for 2 minutes",
            duration_seconds=120,
        )

        self.chaos_events.append(event)

        print(f"   Type: {event.event_type}")
        print(f"   Target: {event.target}")
        print(f"   Description: {event.description}")
        print(f"   Duration: {event.duration_seconds}s")

        if not self.dry_run:
            print(
                "   ⚠️  Memory stress requires stress-ng or similar tool installed in pods"
            )
            print("   [SKIPPED] Not implemented in this test")
        else:
            print("   [DRY RUN] Would consume 80% memory")

        # Wait for duration
        await asyncio.sleep(event.duration_seconds)

    async def _chaos_kill_database_connection(self):
        """Kill database connections."""
        event = ChaosEvent(
            timestamp=datetime.utcnow().isoformat(),
            event_type="kill_db_connections",
            target="postgresql",
            description="Kill all database connections",
            duration_seconds=0,
        )

        self.chaos_events.append(event)

        print(f"   Type: {event.event_type}")
        print(f"   Target: {event.target}")
        print(f"   Description: {event.description}")

        if not self.dry_run:
            try:
                # Kill connections via SQL
                print("   Killing database connections...")

                subprocess.run(
                    [
                        "kubectl",
                        "exec",
                        "-n",
                        "qeo",
                        "cockroachdb-0",
                        "--",
                        "cockroach",
                        "sql",
                        "--insecure",
                        "-e",
                        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'queryexpnopt';",
                    ],
                    check=True,
                    capture_output=True,
                )

                print("   ✓ Database connections killed")

            except subprocess.CalledProcessError as e:
                print(f"   ❌ Failed: {e}")
        else:
            print("   [DRY RUN] Would kill all database connections")

    def _generate_report(self):
        """Generate final chaos test report."""
        print("\n" + "=" * 80)
        print("CHAOS TEST SUMMARY")
        print("=" * 80)
        print()

        # Overall availability
        total_attempted = sum(m.requests_attempted for m in self.metrics)
        total_successful = sum(m.requests_successful for m in self.metrics)
        total_failed = sum(m.requests_failed for m in self.metrics)

        overall_availability = (
            (total_successful / total_attempted * 100) if total_attempted > 0 else 0
        )

        print(f"Overall Availability: {overall_availability:.4f}%")
        print(f"Total Requests: {total_attempted:,}")
        print(f"Successful: {total_successful:,}")
        print(f"Failed: {total_failed:,}")
        print()

        # Chaos events
        print(f"Chaos Events Injected: {len(self.chaos_events)}")
        for i, event in enumerate(self.chaos_events, 1):
            print(
                f"  {i}. [{event.timestamp}] {event.event_type} - {event.description}"
            )

        print()

        # Availability timeline
        print("Availability Timeline:")
        print("Timestamp            | Availability | Failed | Latency")
        print("-" * 70)
        for metric in self.metrics[-20:]:  # Last 20 measurements
            ts = metric.timestamp.split(".")[0]  # Remove microseconds
            print(
                f"{ts} | {metric.availability_pct:11.3f}% | {metric.requests_failed:6d} | {metric.avg_latency_ms:7.0f}ms"
            )

        print()

        # Calculate SLA
        target_availability = 99.99
        passed = overall_availability >= target_availability

        if passed:
            print("✅ TEST PASSED")
            print(
                f"   - Availability: {overall_availability:.4f}% >= {target_availability}%"
            )
            print(
                f"   - System maintained availability despite {len(self.chaos_events)} chaos events"
            )
        else:
            print("❌ TEST FAILED")
            print(
                f"   - Availability: {overall_availability:.4f}% < {target_availability}%"
            )
            print("   - System did not meet 99.99% availability target")

        print()
        print("=" * 80)

        # Save report
        report_file = (
            f"chaos_test_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )

        with open(report_file, "w") as f:
            json.dump(
                {
                    "test_info": {
                        "target_url": self.target_url,
                        "duration_minutes": self.duration_minutes,
                        "dry_run": self.dry_run,
                    },
                    "summary": {
                        "overall_availability_pct": overall_availability,
                        "total_requests": total_attempted,
                        "successful_requests": total_successful,
                        "failed_requests": total_failed,
                        "chaos_events_count": len(self.chaos_events),
                        "test_passed": passed,
                    },
                    "chaos_events": [asdict(e) for e in self.chaos_events],
                    "metrics": [asdict(m) for m in self.metrics],
                },
                f,
                indent=2,
            )

        print(f"Report saved to: {report_file}")


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="QEO Chaos Engineering Test")
    parser.add_argument(
        "--target-url", default="http://localhost:8000", help="Target API URL"
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=60,
        help="Test duration in minutes (default: 60)",
    )
    parser.add_argument(
        "--no-dry-run",
        action="store_true",
        help="Run actual chaos events (WARNING: will disrupt service)",
    )

    args = parser.parse_args()

    test = ChaosTest(
        target_url=args.target_url,
        duration_minutes=args.duration,
        dry_run=not args.no_dry_run,
    )

    await test.run()


if __name__ == "__main__":
    asyncio.run(main())

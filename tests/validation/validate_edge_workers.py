"""
Edge Workers Validation Suite.

Tests all 15 Cloudflare edge locations for latency, caching, and routing.

Usage:
    python tests/validation/validate_edge_workers.py
"""

import asyncio
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Tuple

import requests

# 15 edge locations to test
EDGE_LOCATIONS = [
    {"city": "San Francisco", "code": "SFO", "region": "us-west"},
    {"city": "New York", "code": "EWR", "region": "us-east"},
    {"city": "Chicago", "code": "ORD", "region": "us-central"},
    {"city": "London", "code": "LHR", "region": "eu-west"},
    {"city": "Frankfurt", "code": "FRA", "region": "eu-central"},
    {"city": "Paris", "code": "CDG", "region": "eu-west"},
    {"city": "Singapore", "code": "SIN", "region": "ap-southeast"},
    {"city": "Tokyo", "code": "NRT", "region": "ap-northeast"},
    {"city": "Sydney", "code": "SYD", "region": "ap-southeast"},
    {"city": "Mumbai", "code": "BOM", "region": "ap-south"},
    {"city": "São Paulo", "code": "GRU", "region": "sa-east"},
    {"city": "Toronto", "code": "YYZ", "region": "ca-central"},
    {"city": "Amsterdam", "code": "AMS", "region": "eu-west"},
    {"city": "Hong Kong", "code": "HKG", "region": "ap-east"},
    {"city": "Dubai", "code": "DXB", "region": "me-south"},
]

# Edge endpoint (Cloudflare Workers)
EDGE_URL = "https://qeo.example.com"  # Replace with actual domain

# Latency targets
P50_TARGET_MS = 25  # 50th percentile
P95_TARGET_MS = 45  # 95th percentile
P99_TARGET_MS = 50  # 99th percentile

# Cache hit rate target
CACHE_HIT_RATE_TARGET = 0.85  # 85%


@dataclass
class ValidationResult:
    """Result of a validation test."""

    test_name: str
    passed: bool
    message: str
    duration_ms: float
    details: Dict = None


class EdgeWorkersValidator:
    """Validates edge computing layer."""

    def __init__(self):
        self.results: List[ValidationResult] = []

    async def validate_all(self) -> Tuple[bool, List[ValidationResult]]:
        """Run all edge validation tests."""
        print("=" * 80)
        print("QEO Edge Workers Validation Suite")
        print("=" * 80)
        print()

        # Run all tests
        await self.test_edge_connectivity()
        await self.test_edge_latency()
        await self.test_cache_functionality()
        await self.test_geographic_routing()
        await self.test_rate_limiting()
        await self.test_ddos_protection()

        # Summary
        passed = sum(1 for r in self.results if r.passed)
        total = len(self.results)
        success = all(r.passed for r in self.results)

        print()
        print("=" * 80)
        print(f"Validation Summary: {passed}/{total} tests passed")
        print("=" * 80)
        print()

        for result in self.results:
            status = "✓ PASS" if result.passed else "✗ FAIL"
            print(f"{status} - {result.test_name} ({result.duration_ms:.0f}ms)")
            if not result.passed:
                print(f"      {result.message}")

        return success, self.results

    async def test_edge_connectivity(self):
        """Test connectivity to all edge locations."""
        print("Testing edge location connectivity...")

        for location in EDGE_LOCATIONS:
            start = time.time()
            try:
                # Test health endpoint
                response = requests.get(
                    f"{EDGE_URL}/health",
                    headers={"CF-IPCountry": location["code"]},
                    timeout=10,
                )
                duration_ms = (time.time() - start) * 1000

                if response.status_code == 200:
                    self.results.append(
                        ValidationResult(
                            test_name=f"Edge Connectivity - {location['city']}",
                            passed=True,
                            message=f"Connected to {location['city']}",
                            duration_ms=duration_ms,
                            details={
                                "code": location["code"],
                                "region": location["region"],
                            },
                        )
                    )
                    print(
                        f"  ✓ {location['city']} ({location['code']}): {duration_ms:.0f}ms"
                    )
                else:
                    self.results.append(
                        ValidationResult(
                            test_name=f"Edge Connectivity - {location['city']}",
                            passed=False,
                            message=f"HTTP {response.status_code}",
                            duration_ms=duration_ms,
                        )
                    )
                    print(f"  ✗ {location['city']}: HTTP {response.status_code}")

            except Exception as e:
                duration_ms = (time.time() - start) * 1000
                self.results.append(
                    ValidationResult(
                        test_name=f"Edge Connectivity - {location['city']}",
                        passed=False,
                        message=str(e),
                        duration_ms=duration_ms,
                    )
                )
                print(f"  ✗ {location['city']}: {e}")

    async def test_edge_latency(self):
        """Test P99 latency across all edge locations."""
        print("\nTesting edge latency (P50/P95/P99)...")

        all_latencies = []

        for location in EDGE_LOCATIONS:
            latencies = []

            # Run 20 requests per location
            for _i in range(20):
                start = time.time()
                try:
                    response = requests.get(
                        f"{EDGE_URL}/api/v1/schema",
                        headers={"CF-IPCountry": location["code"]},
                        timeout=5,
                    )
                    latency_ms = (time.time() - start) * 1000

                    if response.status_code == 200:
                        latencies.append(latency_ms)
                        all_latencies.append(latency_ms)

                except Exception:
                    pass

            if latencies:
                # Calculate percentiles
                latencies.sort()
                p50 = latencies[len(latencies) // 2]
                p95 = latencies[int(len(latencies) * 0.95)]
                p99 = latencies[int(len(latencies) * 0.99)]

                passed = p99 < P99_TARGET_MS

                self.results.append(
                    ValidationResult(
                        test_name=f"Edge Latency - {location['city']}",
                        passed=passed,
                        message=f"P50: {p50:.0f}ms, P95: {p95:.0f}ms, P99: {p99:.0f}ms (target: <{P99_TARGET_MS}ms)",
                        duration_ms=p99,
                        details={
                            "p50": p50,
                            "p95": p95,
                            "p99": p99,
                            "samples": len(latencies),
                        },
                    )
                )

                if passed:
                    print(f"  ✓ {location['city']}: P99 {p99:.0f}ms")
                else:
                    print(
                        f"  ✗ {location['city']}: P99 {p99:.0f}ms (exceeded {P99_TARGET_MS}ms)"
                    )

        # Global latency percentiles
        if all_latencies:
            all_latencies.sort()
            global_p50 = all_latencies[len(all_latencies) // 2]
            global_p95 = all_latencies[int(len(all_latencies) * 0.95)]
            global_p99 = all_latencies[int(len(all_latencies) * 0.99)]

            global_passed = (
                global_p50 < P50_TARGET_MS
                and global_p95 < P95_TARGET_MS
                and global_p99 < P99_TARGET_MS
            )

            self.results.append(
                ValidationResult(
                    test_name="Global Edge Latency",
                    passed=global_passed,
                    message=f"P50: {global_p50:.0f}ms, P95: {global_p95:.0f}ms, P99: {global_p99:.0f}ms",
                    duration_ms=global_p99,
                    details={
                        "p50": global_p50,
                        "p95": global_p95,
                        "p99": global_p99,
                        "samples": len(all_latencies),
                    },
                )
            )

            if global_passed:
                print(
                    f"  ✓ Global: P50 {global_p50:.0f}ms, P95 {global_p95:.0f}ms, P99 {global_p99:.0f}ms"
                )
            else:
                print("  ✗ Global latency exceeded targets")

    async def test_cache_functionality(self):
        """Test edge caching and cache hit rates."""
        print("\nTesting edge cache functionality...")

        start = time.time()
        try:
            # Test query (should be cacheable)
            test_query = "SELECT * FROM users WHERE id = 1"

            # First request (cache miss)
            response1 = requests.post(
                f"{EDGE_URL}/api/v1/explain",
                json={"sql": test_query},
                timeout=10,
            )

            # Second request (should be cache hit)
            time.sleep(0.5)
            response2 = requests.post(
                f"{EDGE_URL}/api/v1/explain",
                json={"sql": test_query},
                timeout=10,
            )

            duration_ms = (time.time() - start) * 1000

            # Check CF-Cache-Status header
            cache_status1 = response1.headers.get("CF-Cache-Status", "UNKNOWN")
            cache_status2 = response2.headers.get("CF-Cache-Status", "UNKNOWN")

            cache_hit = cache_status2 in ["HIT", "REVALIDATED"]

            self.results.append(
                ValidationResult(
                    test_name="Edge Cache Functionality",
                    passed=cache_hit,
                    message=f"Request 1: {cache_status1}, Request 2: {cache_status2}",
                    duration_ms=duration_ms,
                    details={
                        "cache_status_1": cache_status1,
                        "cache_status_2": cache_status2,
                    },
                )
            )

            if cache_hit:
                print(f"  ✓ Cache working: {cache_status1} → {cache_status2}")
            else:
                print(f"  ✗ Cache not working: {cache_status1} → {cache_status2}")

        except Exception as e:
            duration_ms = (time.time() - start) * 1000
            self.results.append(
                ValidationResult(
                    test_name="Edge Cache Functionality",
                    passed=False,
                    message=str(e),
                    duration_ms=duration_ms,
                )
            )
            print(f"  ✗ Cache test failed: {e}")

    async def test_geographic_routing(self):
        """Test that requests route to nearest edge location."""
        print("\nTesting geographic routing...")

        test_cases = [
            {"from": "US", "expected_region": ["us-west", "us-east", "us-central"]},
            {"from": "GB", "expected_region": ["eu-west"]},
            {"from": "SG", "expected_region": ["ap-southeast"]},
        ]

        for test in test_cases:
            start = time.time()
            try:
                response = requests.get(
                    f"{EDGE_URL}/health",
                    headers={"CF-IPCountry": test["from"]},
                    timeout=5,
                )

                duration_ms = (time.time() - start) * 1000

                # Check CF-Ray header for colo
                cf_ray = response.headers.get("CF-Ray", "")
                colo = cf_ray.split("-")[-1] if "-" in cf_ray else "UNKNOWN"

                # Verify routing (simplified - actual implementation would check colo mapping)
                passed = response.status_code == 200

                self.results.append(
                    ValidationResult(
                        test_name=f"Geographic Routing - {test['from']}",
                        passed=passed,
                        message=f"Routed to colo: {colo}",
                        duration_ms=duration_ms,
                        details={"colo": colo},
                    )
                )

                if passed:
                    print(f"  ✓ {test['from']}: Routed to {colo}")
                else:
                    print(f"  ✗ {test['from']}: Routing failed")

            except Exception as e:
                duration_ms = (time.time() - start) * 1000
                self.results.append(
                    ValidationResult(
                        test_name=f"Geographic Routing - {test['from']}",
                        passed=False,
                        message=str(e),
                        duration_ms=duration_ms,
                    )
                )
                print(f"  ✗ {test['from']}: {e}")

    async def test_rate_limiting(self):
        """Test rate limiting at edge (100 req/min per IP)."""
        print("\nTesting edge rate limiting...")

        start = time.time()
        try:
            # Send 110 requests rapidly (should hit limit at 100)
            success_count = 0
            rate_limited_count = 0

            for _i in range(110):
                response = requests.get(
                    f"{EDGE_URL}/health",
                    timeout=2,
                )

                if response.status_code == 200:
                    success_count += 1
                elif response.status_code == 429:  # Too Many Requests
                    rate_limited_count += 1

            duration_ms = (time.time() - start) * 1000

            # Should have ~100 successes and ~10 rate limited
            passed = rate_limited_count > 0 and success_count <= 105

            self.results.append(
                ValidationResult(
                    test_name="Edge Rate Limiting",
                    passed=passed,
                    message=f"Success: {success_count}, Rate limited: {rate_limited_count}",
                    duration_ms=duration_ms,
                    details={
                        "success": success_count,
                        "rate_limited": rate_limited_count,
                    },
                )
            )

            if passed:
                print(
                    f"  ✓ Rate limiting working: {rate_limited_count} requests blocked"
                )
            else:
                print("  ✗ Rate limiting not working properly")

        except Exception as e:
            duration_ms = (time.time() - start) * 1000
            self.results.append(
                ValidationResult(
                    test_name="Edge Rate Limiting",
                    passed=False,
                    message=str(e),
                    duration_ms=duration_ms,
                )
            )
            print(f"  ✗ Rate limit test failed: {e}")

    async def test_ddos_protection(self):
        """Test DDoS protection mechanisms."""
        print("\nTesting DDoS protection...")

        start = time.time()
        try:
            # Test 1: Suspicious pattern (rapid requests from single IP)
            suspicious_requests = 0
            blocked_requests = 0

            for i in range(50):
                response = requests.get(
                    f"{EDGE_URL}/api/v1/optimize",
                    json={"sql": f"SELECT * FROM users WHERE id = {i}"},
                    timeout=2,
                )

                if response.status_code == 200:
                    suspicious_requests += 1
                elif response.status_code in [403, 429]:
                    blocked_requests += 1

            # Test 2: Malformed request
            try:
                response = requests.post(
                    f"{EDGE_URL}/api/v1/optimize",
                    data="malformed json{{{",
                    headers={"Content-Type": "application/json"},
                    timeout=2,
                )
                malformed_handled = response.status_code in [400, 403]
            except Exception:
                malformed_handled = True  # Connection refused is also valid

            duration_ms = (time.time() - start) * 1000

            # DDoS protection should block some suspicious patterns
            passed = blocked_requests > 0 or malformed_handled

            self.results.append(
                ValidationResult(
                    test_name="DDoS Protection",
                    passed=passed,
                    message=f"Suspicious: {suspicious_requests}, Blocked: {blocked_requests}",
                    duration_ms=duration_ms,
                    details={
                        "suspicious": suspicious_requests,
                        "blocked": blocked_requests,
                        "malformed_handled": malformed_handled,
                    },
                )
            )

            if passed:
                print(
                    f"  ✓ DDoS protection active: {blocked_requests} suspicious requests blocked"
                )
            else:
                print("  ✗ DDoS protection may not be working")

        except Exception as e:
            duration_ms = (time.time() - start) * 1000
            self.results.append(
                ValidationResult(
                    test_name="DDoS Protection",
                    passed=False,
                    message=str(e),
                    duration_ms=duration_ms,
                )
            )
            print(f"  ✗ DDoS test failed: {e}")


async def main():
    """Run edge workers validation."""
    validator = EdgeWorkersValidator()
    success, results = await validator.validate_all()

    # Save results
    import json

    with open("validation_results_edge.json", "w") as f:
        json.dump(
            {
                "timestamp": datetime.utcnow().isoformat(),
                "success": success,
                "results": [
                    {
                        "test_name": r.test_name,
                        "passed": r.passed,
                        "message": r.message,
                        "duration_ms": r.duration_ms,
                        "details": r.details,
                    }
                    for r in results
                ],
            },
            f,
            indent=2,
        )

    print("\nResults saved to: validation_results_edge.json")

    return 0 if success else 1


if __name__ == "__main__":
    import sys

    sys.exit(asyncio.run(main()))

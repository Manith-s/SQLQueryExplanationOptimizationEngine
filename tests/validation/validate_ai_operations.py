"""
AI Operations Validation Suite.

Tests AutonomousOpsAI for incident detection and remediation.

Usage:
    python tests/validation/validate_ai_operations.py
"""

import asyncio
import time
from datetime import datetime
from typing import List
import requests

from app.ml.autonomous import AutonomousOpsAI, SystemState, IncidentType


class AIOperationsValidator:
    """Validates AI autonomous operations."""

    def __init__(self):
        self.ai = AutonomousOpsAI()
        self.results = []

    async def validate_all(self):
        """Run all AI validation tests."""
        print("=" * 80)
        print("AI Autonomous Operations Validation")
        print("=" * 80)
        print()

        await self.test_incident_detection()
        await self.test_action_recommendation()
        await self.test_confidence_scoring()
        await self.test_learning_capability()
        await self.test_human_override()
        await self.test_api_integration()

        # Summary
        passed = sum(1 for r in self.results if r["passed"])
        total = len(self.results)

        print()
        print("=" * 80)
        print(f"AI Validation Summary: {passed}/{total} tests passed")
        print("=" * 80)

        for result in self.results:
            status = "✓ PASS" if result["passed"] else "✗ FAIL"
            print(f"{status} - {result['test_name']}")
            if not result["passed"]:
                print(f"      {result['message']}")

        return all(r["passed"] for r in self.results)

    async def test_incident_detection(self):
        """Test AI can detect various incident types."""
        print("Testing incident detection...")

        test_cases = [
            {
                "name": "High Latency",
                "state": SystemState(
                    cpu_usage_pct=70.0,
                    memory_usage_pct=65.0,
                    p95_latency_ms=1500.0,  # High!
                    error_rate_pct=2.0,
                    qps=5000,
                    cache_hit_rate_pct=75.0,
                    active_connections=150,
                    disk_usage_pct=45.0,
                    timestamp=datetime.utcnow(),
                ),
                "expected": IncidentType.HIGH_LATENCY,
            },
            {
                "name": "Memory Leak",
                "state": SystemState(
                    cpu_usage_pct=60.0,
                    memory_usage_pct=95.0,  # High!
                    p95_latency_ms=800.0,
                    error_rate_pct=1.5,
                    qps=4000,
                    cache_hit_rate_pct=80.0,
                    active_connections=120,
                    disk_usage_pct=40.0,
                    timestamp=datetime.utcnow(),
                ),
                "expected": IncidentType.MEMORY_LEAK,
            },
            {
                "name": "High Error Rate",
                "state": SystemState(
                    cpu_usage_pct=55.0,
                    memory_usage_pct=60.0,
                    p95_latency_ms=750.0,
                    error_rate_pct=8.0,  # High!
                    qps=3500,
                    cache_hit_rate_pct=70.0,
                    active_connections=100,
                    disk_usage_pct=38.0,
                    timestamp=datetime.utcnow(),
                ),
                "expected": IncidentType.HIGH_ERROR_RATE,
            },
        ]

        for test in test_cases:
            incident = self.ai.detect_incident(test["state"])

            if incident == test["expected"]:
                self.results.append({
                    "test_name": f"Incident Detection - {test['name']}",
                    "passed": True,
                    "message": f"Correctly detected {incident.value}",
                })
                print(f"  ✓ {test['name']}: Detected {incident.value}")
            else:
                self.results.append({
                    "test_name": f"Incident Detection - {test['name']}",
                    "passed": False,
                    "message": f"Expected {test['expected'].value}, got {incident}",
                })
                print(f"  ✗ {test['name']}: Expected {test['expected'].value}, got {incident}")

    async def test_action_recommendation(self):
        """Test AI recommends appropriate actions."""
        print("\nTesting action recommendation...")

        state = SystemState(
            cpu_usage_pct=70.0,
            memory_usage_pct=65.0,
            p95_latency_ms=1500.0,
            error_rate_pct=2.0,
            qps=5000,
            cache_hit_rate_pct=75.0,
            active_connections=150,
            disk_usage_pct=45.0,
            timestamp=datetime.utcnow(),
        )

        incident = self.ai.detect_incident(state)
        action = self.ai.recommend_action(incident, state)

        # Check action is reasonable
        if action and action.confidence > 0:
            self.results.append({
                "test_name": "Action Recommendation",
                "passed": True,
                "message": f"Recommended {action.action_type.value} with {action.confidence:.0%} confidence",
            })
            print(f"  ✓ Recommended: {action.action_type.value} ({action.confidence:.0%})")
            print(f"    Reasoning: {action.reasoning[:100]}...")
        else:
            self.results.append({
                "test_name": "Action Recommendation",
                "passed": False,
                "message": "No action recommended or zero confidence",
            })
            print(f"  ✗ No valid action recommended")

    async def test_confidence_scoring(self):
        """Test confidence scores are within expected ranges."""
        print("\nTesting confidence scoring...")

        state = SystemState(
            cpu_usage_pct=70.0,
            memory_usage_pct=65.0,
            p95_latency_ms=1200.0,
            error_rate_pct=2.5,
            qps=5000,
            cache_hit_rate_pct=75.0,
            active_connections=150,
            disk_usage_pct=45.0,
            timestamp=datetime.utcnow(),
        )

        incident = self.ai.detect_incident(state)
        action = self.ai.recommend_action(incident, state)

        # Confidence should be between 0 and 1
        if 0 <= action.confidence <= 1:
            self.results.append({
                "test_name": "Confidence Scoring - Range",
                "passed": True,
                "message": f"Confidence: {action.confidence:.3f} (valid range)",
            })
            print(f"  ✓ Confidence score valid: {action.confidence:.3f}")
        else:
            self.results.append({
                "test_name": "Confidence Scoring - Range",
                "passed": False,
                "message": f"Confidence: {action.confidence} (out of range)",
            })
            print(f"  ✗ Confidence out of range: {action.confidence}")

        # For initial deployment, expect at least 70% confidence for known issues
        target_confidence = 0.70

        if action.confidence >= target_confidence:
            self.results.append({
                "test_name": "Confidence Scoring - Threshold",
                "passed": True,
                "message": f"Confidence {action.confidence:.0%} meets {target_confidence:.0%} target",
            })
            print(f"  ✓ Confidence meets target: {action.confidence:.0%} >= {target_confidence:.0%}")
        else:
            self.results.append({
                "test_name": "Confidence Scoring - Threshold",
                "passed": False,
                "message": f"Confidence {action.confidence:.0%} below {target_confidence:.0%}",
            })
            print(f"  ✗ Confidence below target: {action.confidence:.0%} < {target_confidence:.0%}")

    async def test_learning_capability(self):
        """Test AI can learn from outcomes."""
        print("\nTesting learning capability...")

        # Initial state
        initial_q_table_size = len(self.ai._q_table)

        # Simulate some outcomes
        for i in range(5):
            state = SystemState(
                cpu_usage_pct=70.0 + i * 2,
                memory_usage_pct=65.0,
                p95_latency_ms=1200.0,
                error_rate_pct=2.5,
                qps=5000,
                cache_hit_rate_pct=75.0,
                active_connections=150,
                disk_usage_pct=45.0,
                timestamp=datetime.utcnow(),
            )

            incident = self.ai.detect_incident(state)
            action = self.ai.recommend_action(incident, state)
            outcome = self.ai.execute_action(action, state)

        # Check Q-table grew
        final_q_table_size = len(self.ai._q_table)

        if final_q_table_size > initial_q_table_size:
            self.results.append({
                "test_name": "Learning Capability - Q-Table Growth",
                "passed": True,
                "message": f"Q-table grew from {initial_q_table_size} to {final_q_table_size}",
            })
            print(f"  ✓ Q-table grew: {initial_q_table_size} → {final_q_table_size}")
        else:
            self.results.append({
                "test_name": "Learning Capability - Q-Table Growth",
                "passed": False,
                "message": f"Q-table did not grow ({final_q_table_size})",
            })
            print(f"  ✗ Q-table did not grow")

    async def test_human_override(self):
        """Test human override tracking."""
        print("\nTesting human override tracking...")

        # Get initial stats
        initial_overrides = self.ai._human_overrides

        # Simulate human override
        state = SystemState(
            cpu_usage_pct=70.0,
            memory_usage_pct=65.0,
            p95_latency_ms=1200.0,
            error_rate_pct=2.5,
            qps=5000,
            cache_hit_rate_pct=75.0,
            active_connections=150,
            disk_usage_pct=45.0,
            timestamp=datetime.utcnow(),
        )

        incident = self.ai.detect_incident(state)
        action = self.ai.recommend_action(incident, state)

        from app.ml.autonomous.ops_ai import ActionType
        self.ai.record_human_override(action, ActionType.ROLLBACK_DEPLOYMENT)

        # Check override was recorded
        if self.ai._human_overrides > initial_overrides:
            self.results.append({
                "test_name": "Human Override Tracking",
                "passed": True,
                "message": f"Override recorded ({self.ai._human_overrides} total)",
            })
            print(f"  ✓ Override tracked: {self.ai._human_overrides} total")
        else:
            self.results.append({
                "test_name": "Human Override Tracking",
                "passed": False,
                "message": "Override not recorded",
            })
            print(f"  ✗ Override not recorded")

    async def test_api_integration(self):
        """Test AI operations API endpoints."""
        print("\nTesting API integration...")

        try:
            # Test stats endpoint
            response = requests.get(
                "http://localhost:8000/api/v1/ai/stats",
                timeout=5,
            )

            if response.status_code == 200:
                data = response.json()

                # Check expected fields
                required_fields = ["total_actions", "autonomy_level", "q_table_size"]
                has_all_fields = all(field in data for field in required_fields)

                if has_all_fields:
                    self.results.append({
                        "test_name": "API Integration - Stats Endpoint",
                        "passed": True,
                        "message": f"Stats API working, autonomy: {data.get('autonomy_level', 0):.0%}",
                    })
                    print(f"  ✓ Stats API working")
                    print(f"    Actions: {data.get('total_actions', 0)}")
                    print(f"    Autonomy: {data.get('autonomy_level', 0):.0%}")
                else:
                    self.results.append({
                        "test_name": "API Integration - Stats Endpoint",
                        "passed": False,
                        "message": "Missing required fields in response",
                    })
                    print(f"  ✗ Missing fields in response")
            else:
                self.results.append({
                    "test_name": "API Integration - Stats Endpoint",
                    "passed": False,
                    "message": f"HTTP {response.status_code}",
                })
                print(f"  ✗ HTTP {response.status_code}")

        except Exception as e:
            self.results.append({
                "test_name": "API Integration - Stats Endpoint",
                "passed": False,
                "message": str(e),
            })
            print(f"  ✗ API error: {e}")


async def main():
    """Run AI operations validation."""
    validator = AIOperationsValidator()
    success = await validator.validate_all()

    # Save results
    import json
    with open("validation_results_ai.json", "w") as f:
        json.dump(
            {
                "timestamp": datetime.utcnow().isoformat(),
                "success": success,
                "results": validator.results,
            },
            f,
            indent=2,
        )

    print(f"\nResults saved to: validation_results_ai.json")

    return 0 if success else 1


if __name__ == "__main__":
    import sys
    sys.exit(asyncio.run(main()))

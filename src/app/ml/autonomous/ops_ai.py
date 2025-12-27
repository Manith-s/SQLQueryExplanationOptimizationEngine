"""
AI-Powered Autonomous Operations System.

Uses reinforcement learning to:
- Monitor system health 24/7
- Automatically detect and respond to incidents
- Learn optimal responses over time
- Gradually increase automation confidence
- Explain decisions for transparency
"""

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Tuple
import json

import numpy as np

logger = logging.getLogger(__name__)


class IncidentType(str, Enum):
    """Types of incidents the AI can handle."""

    HIGH_LATENCY = "high_latency"
    HIGH_ERROR_RATE = "high_error_rate"
    MEMORY_LEAK = "memory_leak"
    CPU_SPIKE = "cpu_spike"
    DATABASE_SLOW = "database_slow"
    CACHE_MISS_RATE = "cache_miss_rate"
    CIRCUIT_BREAKER_OPEN = "circuit_breaker_open"
    REGION_FAILURE = "region_failure"
    DISK_SPACE_LOW = "disk_space_low"


class ActionType(str, Enum):
    """Possible remediation actions."""

    RESTART_POD = "restart_pod"
    SCALE_UP = "scale_up"
    SCALE_DOWN = "scale_down"
    CLEAR_CACHE = "clear_cache"
    REINDEX_TABLE = "reindex_table"
    KILL_SLOW_QUERIES = "kill_slow_queries"
    INCREASE_CONNECTION_POOL = "increase_connection_pool"
    FAILOVER_TO_BACKUP = "failover_to_backup"
    ROLLBACK_DEPLOYMENT = "rollback_deployment"
    DO_NOTHING = "do_nothing"
    ESCALATE_TO_HUMAN = "escalate_to_human"


@dataclass
class SystemState:
    """Current system state metrics."""

    cpu_usage_pct: float
    memory_usage_pct: float
    p95_latency_ms: float
    error_rate_pct: float
    qps: int  # Queries per second
    cache_hit_rate_pct: float
    active_connections: int
    disk_usage_pct: float
    timestamp: datetime
    region: str = "us-east-1"


@dataclass
class Action:
    """Remediation action."""

    action_type: ActionType
    confidence: float  # 0-1
    reasoning: str
    estimated_impact: str  # "low", "medium", "high"
    estimated_duration_seconds: int
    risk_level: str  # "low", "medium", "high"
    parameters: Dict = None


@dataclass
class ActionOutcome:
    """Result of executing an action."""

    action: Action
    success: bool
    duration_seconds: float
    state_before: SystemState
    state_after: SystemState
    human_feedback: Optional[str] = None  # "good", "bad", "needs_improvement"
    incident_resolved: bool = False


class AutonomousOpsAI:
    """
    Reinforcement Learning agent for autonomous operations.

    Architecture:
    - State: System metrics (CPU, memory, latency, errors, etc.)
    - Actions: Remediation actions (restart, scale, reindex, etc.)
    - Rewards: Based on incident resolution success and speed
    - Learning: Q-learning with experience replay

    Confidence-based automation:
    - >90% confidence: Auto-fix without human
    - 70-90%: Auto-fix with notification
    - <70%: Alert human for approval
    """

    # Confidence thresholds
    AUTO_FIX_THRESHOLD = 0.90
    NOTIFY_THRESHOLD = 0.70

    # Learning parameters
    LEARNING_RATE = 0.1
    DISCOUNT_FACTOR = 0.95
    EXPLORATION_RATE = 0.1  # Start with 10% exploration

    def __init__(self):
        # Q-table: maps (state, action) -> expected reward
        self._q_table = {}

        # Experience replay buffer
        self._experience_buffer = []
        self._max_buffer_size = 10000

        # Action history for learning
        self._action_history = []

        # Human override statistics
        self._human_overrides = 0
        self._total_actions = 0

        # Confidence tracking
        self._confidence_history = []

        logger.info("AutonomousOpsAI initialized")

    def detect_incident(self, state: SystemState) -> Optional[IncidentType]:
        """
        Detect if current state indicates an incident.

        Returns incident type if detected, None if system healthy.
        """
        # High latency
        if state.p95_latency_ms > 1000:  # >1s
            return IncidentType.HIGH_LATENCY

        # High error rate
        if state.error_rate_pct > 5.0:  # >5%
            return IncidentType.HIGH_ERROR_RATE

        # Memory leak detection (>90% memory)
        if state.memory_usage_pct > 90:
            return IncidentType.MEMORY_LEAK

        # CPU spike
        if state.cpu_usage_pct > 85:
            return IncidentType.CPU_SPIKE

        # Low cache hit rate
        if state.cache_hit_rate_pct < 50:
            return IncidentType.CACHE_MISS_RATE

        # Disk space low
        if state.disk_usage_pct > 85:
            return IncidentType.DISK_SPACE_LOW

        return None

    def recommend_action(
        self,
        incident: IncidentType,
        state: SystemState,
    ) -> Action:
        """
        Recommend best action for incident using learned Q-values.

        Returns action with confidence score.
        """
        # Get possible actions for this incident type
        possible_actions = self._get_possible_actions(incident)

        # Calculate Q-value for each action
        action_values = []
        for action_type in possible_actions:
            state_key = self._state_to_key(state)
            q_value = self._q_table.get((state_key, action_type), 0.0)
            action_values.append((q_value, action_type))

        # Sort by Q-value (highest first)
        action_values.sort(reverse=True, key=lambda x: x[0])

        # Best action
        best_q_value, best_action_type = action_values[0]

        # Calculate confidence based on Q-value distribution
        confidence = self._calculate_confidence(action_values)

        # Build action with reasoning
        reasoning = self._explain_action(incident, best_action_type, state)

        action = Action(
            action_type=best_action_type,
            confidence=float(f"{confidence:.3f}"),
            reasoning=reasoning,
            estimated_impact=self._estimate_impact(best_action_type),
            estimated_duration_seconds=self._estimate_duration(best_action_type),
            risk_level=self._assess_risk(best_action_type),
            parameters=self._get_action_parameters(best_action_type, state),
        )

        return action

    def should_auto_execute(self, action: Action) -> Tuple[bool, str]:
        """
        Determine if action should be executed automatically.

        Returns: (should_execute, reason)
        """
        if action.confidence >= self.AUTO_FIX_THRESHOLD:
            return True, f"High confidence ({action.confidence:.0%}) - auto-executing"

        elif action.confidence >= self.NOTIFY_THRESHOLD:
            return True, f"Medium confidence ({action.confidence:.0%}) - executing with notification"

        else:
            return False, f"Low confidence ({action.confidence:.0%}) - escalating to human"

    def execute_action(self, action: Action, state: SystemState) -> ActionOutcome:
        """
        Execute remediation action.

        This is a simulation - in production, would actually execute actions
        via kubectl, APIs, etc.
        """
        start_time = time.time()

        logger.info(
            f"Executing action: {action.action_type.value} "
            f"(confidence: {action.confidence:.0%})"
        )

        # Simulate action execution
        success = True  # In production, check actual result

        # Simulate new state after action
        state_after = self._simulate_state_after_action(state, action)

        duration = time.time() - start_time

        outcome = ActionOutcome(
            action=action,
            success=success,
            duration_seconds=duration,
            state_before=state,
            state_after=state_after,
            incident_resolved=self._is_incident_resolved(state_after),
        )

        # Update statistics
        self._total_actions += 1

        # Learn from outcome
        self._learn_from_outcome(outcome)

        return outcome

    def _get_possible_actions(self, incident: IncidentType) -> List[ActionType]:
        """Get possible actions for an incident type."""
        action_map = {
            IncidentType.HIGH_LATENCY: [
                ActionType.SCALE_UP,
                ActionType.RESTART_POD,
                ActionType.CLEAR_CACHE,
                ActionType.REINDEX_TABLE,
                ActionType.KILL_SLOW_QUERIES,
            ],
            IncidentType.HIGH_ERROR_RATE: [
                ActionType.RESTART_POD,
                ActionType.ROLLBACK_DEPLOYMENT,
                ActionType.FAILOVER_TO_BACKUP,
            ],
            IncidentType.MEMORY_LEAK: [
                ActionType.RESTART_POD,
                ActionType.SCALE_UP,
            ],
            IncidentType.CPU_SPIKE: [
                ActionType.SCALE_UP,
                ActionType.KILL_SLOW_QUERIES,
                ActionType.RESTART_POD,
            ],
            IncidentType.CACHE_MISS_RATE: [
                ActionType.CLEAR_CACHE,
                ActionType.SCALE_UP,
            ],
            IncidentType.DISK_SPACE_LOW: [
                ActionType.DO_NOTHING,  # Needs manual cleanup
                ActionType.ESCALATE_TO_HUMAN,
            ],
        }

        return action_map.get(incident, [ActionType.ESCALATE_TO_HUMAN])

    def _state_to_key(self, state: SystemState) -> str:
        """Convert state to hashable key for Q-table."""
        # Discretize continuous values for Q-table
        cpu_bucket = int(state.cpu_usage_pct / 10) * 10
        mem_bucket = int(state.memory_usage_pct / 10) * 10
        latency_bucket = int(state.p95_latency_ms / 100) * 100
        error_bucket = int(state.error_rate_pct)

        return f"cpu:{cpu_bucket},mem:{mem_bucket},lat:{latency_bucket},err:{error_bucket}"

    def _calculate_confidence(self, action_values: List[Tuple[float, ActionType]]) -> float:
        """
        Calculate confidence in top action based on Q-value distribution.

        High confidence if top action significantly better than alternatives.
        """
        if len(action_values) < 2:
            return 0.5  # Medium confidence if only one action

        best_q = action_values[0][0]
        second_best_q = action_values[1][0]

        # If best Q-value is much higher than second best, high confidence
        if best_q > 0 and second_best_q > 0:
            ratio = best_q / second_best_q
            if ratio > 1.5:
                confidence = 0.95
            elif ratio > 1.2:
                confidence = 0.85
            elif ratio > 1.1:
                confidence = 0.75
            else:
                confidence = 0.65
        elif best_q > 0:
            confidence = 0.80  # Only best has positive Q-value
        else:
            confidence = 0.50  # No learned preference yet

        return confidence

    def _explain_action(
        self,
        incident: IncidentType,
        action: ActionType,
        state: SystemState,
    ) -> str:
        """Generate human-readable explanation for action."""
        explanations = {
            (IncidentType.HIGH_LATENCY, ActionType.SCALE_UP):
                f"P95 latency at {state.p95_latency_ms:.0f}ms (target: <1000ms). "
                f"Current QPS: {state.qps}. Scaling up will add capacity to handle load.",

            (IncidentType.MEMORY_LEAK, ActionType.RESTART_POD):
                f"Memory usage at {state.memory_usage_pct:.0f}% (threshold: 90%). "
                f"Restarting pod will clear leaked memory.",

            (IncidentType.HIGH_ERROR_RATE, ActionType.ROLLBACK_DEPLOYMENT):
                f"Error rate at {state.error_rate_pct:.1f}% (threshold: 5%). "
                f"Recent deployment likely caused issue. Rolling back to last known good version.",
        }

        key = (incident, action)
        return explanations.get(
            key,
            f"Action {action.value} recommended for {incident.value} based on historical success rate"
        )

    def _estimate_impact(self, action: ActionType) -> str:
        """Estimate impact level of action."""
        impact_map = {
            ActionType.RESTART_POD: "medium",
            ActionType.SCALE_UP: "low",
            ActionType.SCALE_DOWN: "low",
            ActionType.CLEAR_CACHE: "medium",
            ActionType.REINDEX_TABLE: "high",
            ActionType.ROLLBACK_DEPLOYMENT: "high",
            ActionType.FAILOVER_TO_BACKUP: "high",
        }
        return impact_map.get(action, "medium")

    def _estimate_duration(self, action: ActionType) -> int:
        """Estimate action duration in seconds."""
        duration_map = {
            ActionType.RESTART_POD: 60,
            ActionType.SCALE_UP: 120,
            ActionType.CLEAR_CACHE: 30,
            ActionType.REINDEX_TABLE: 600,
            ActionType.ROLLBACK_DEPLOYMENT: 180,
            ActionType.FAILOVER_TO_BACKUP: 300,
        }
        return duration_map.get(action, 120)

    def _assess_risk(self, action: ActionType) -> str:
        """Assess risk level of action."""
        risk_map = {
            ActionType.RESTART_POD: "low",
            ActionType.SCALE_UP: "low",
            ActionType.CLEAR_CACHE: "medium",
            ActionType.ROLLBACK_DEPLOYMENT: "medium",
            ActionType.REINDEX_TABLE: "high",
            ActionType.FAILOVER_TO_BACKUP: "high",
        }
        return risk_map.get(action, "medium")

    def _get_action_parameters(
        self,
        action: ActionType,
        state: SystemState,
    ) -> Dict:
        """Get specific parameters for action execution."""
        if action == ActionType.SCALE_UP:
            # Calculate target replicas based on load
            current_replicas = 5  # Would get from k8s in production
            target_replicas = min(30, int(current_replicas * 1.5))
            return {"target_replicas": target_replicas}

        elif action == ActionType.RESTART_POD:
            return {"pod_selector": "app=qeo,component=api"}

        return {}

    def _simulate_state_after_action(
        self,
        state: SystemState,
        action: Action,
    ) -> SystemState:
        """Simulate what state will be after action (for learning)."""
        # Simplified simulation - in production, measure actual state
        new_state = SystemState(
            cpu_usage_pct=state.cpu_usage_pct,
            memory_usage_pct=state.memory_usage_pct,
            p95_latency_ms=state.p95_latency_ms,
            error_rate_pct=state.error_rate_pct,
            qps=state.qps,
            cache_hit_rate_pct=state.cache_hit_rate_pct,
            active_connections=state.active_connections,
            disk_usage_pct=state.disk_usage_pct,
            timestamp=datetime.utcnow(),
            region=state.region,
        )

        # Simulate action effects
        if action.action_type == ActionType.SCALE_UP:
            new_state.cpu_usage_pct *= 0.7  # 30% reduction
            new_state.p95_latency_ms *= 0.6  # 40% improvement

        elif action.action_type == ActionType.RESTART_POD:
            new_state.memory_usage_pct = 60  # Reset to baseline
            new_state.p95_latency_ms *= 0.9  # Slight improvement

        elif action.action_type == ActionType.CLEAR_CACHE:
            new_state.cache_hit_rate_pct = 0  # Cache cleared
            new_state.p95_latency_ms *= 1.2  # Temporarily worse

        return new_state

    def _is_incident_resolved(self, state: SystemState) -> bool:
        """Check if incident is resolved in new state."""
        return (
            state.p95_latency_ms < 1000
            and state.error_rate_pct < 5.0
            and state.memory_usage_pct < 85
            and state.cpu_usage_pct < 80
        )

    def _learn_from_outcome(self, outcome: ActionOutcome):
        """Update Q-table based on action outcome (Q-learning)."""
        # Calculate reward
        reward = self._calculate_reward(outcome)

        # Get state keys
        state_before_key = self._state_to_key(outcome.state_before)
        state_after_key = self._state_to_key(outcome.state_after)
        action = outcome.action.action_type

        # Current Q-value
        current_q = self._q_table.get((state_before_key, action), 0.0)

        # Max Q-value for next state
        next_state_actions = self._get_possible_actions(
            self.detect_incident(outcome.state_after) or IncidentType.HIGH_LATENCY
        )
        max_next_q = max(
            [self._q_table.get((state_after_key, a), 0.0) for a in next_state_actions]
            + [0.0]
        )

        # Q-learning update
        new_q = current_q + self.LEARNING_RATE * (
            reward + self.DISCOUNT_FACTOR * max_next_q - current_q
        )

        # Update Q-table
        self._q_table[(state_before_key, action)] = new_q

        # Store in experience buffer
        self._experience_buffer.append(outcome)
        if len(self._experience_buffer) > self._max_buffer_size:
            self._experience_buffer.pop(0)

        logger.info(
            f"Learned from outcome: reward={reward:.2f}, "
            f"Q({state_before_key}, {action})={new_q:.3f}"
        )

    def _calculate_reward(self, outcome: ActionOutcome) -> float:
        """
        Calculate reward for reinforcement learning.

        Positive rewards for:
        - Incident resolution
        - Fast resolution
        - Low-risk actions

        Negative rewards for:
        - Failed actions
        - Making things worse
        - High-risk actions that didn't work
        """
        reward = 0.0

        # Big positive reward for resolving incident
        if outcome.incident_resolved:
            reward += 100.0

        # Reward for improvement even if not fully resolved
        latency_improvement = (
            outcome.state_before.p95_latency_ms - outcome.state_after.p95_latency_ms
        )
        reward += latency_improvement / 10  # Small reward per ms improvement

        error_improvement = (
            outcome.state_before.error_rate_pct - outcome.state_after.error_rate_pct
        )
        reward += error_improvement * 5  # 5 points per % improvement

        # Penalty for failed actions
        if not outcome.success:
            reward -= 50.0

        # Penalty for making things worse
        if outcome.state_after.p95_latency_ms > outcome.state_before.p95_latency_ms:
            reward -= 20.0

        # Bonus for fast resolution
        if outcome.duration_seconds < 60:
            reward += 10.0

        # Incorporate human feedback if available
        if outcome.human_feedback:
            if outcome.human_feedback == "good":
                reward += 20.0
            elif outcome.human_feedback == "bad":
                reward -= 30.0

        return reward

    def record_human_override(self, action: Action, human_action: ActionType):
        """Record when human overrides AI decision (for learning)."""
        self._human_overrides += 1
        logger.warning(
            f"Human override: AI suggested {action.action_type.value}, "
            f"human chose {human_action.value}"
        )
        # Could use this to update Q-values

    def get_autonomy_level(self) -> float:
        """
        Get current autonomy level (0-1).

        Starts low and increases as AI proves reliable.
        """
        if self._total_actions < 10:
            return 0.3  # Low autonomy initially

        # Calculate success rate
        successful_actions = len([
            o for o in self._experience_buffer if o.incident_resolved
        ])
        success_rate = successful_actions / min(self._total_actions, len(self._experience_buffer))

        # Factor in human override rate
        override_rate = self._human_overrides / self._total_actions

        # Autonomy increases with success, decreases with overrides
        autonomy = success_rate * (1 - override_rate)

        return min(0.95, autonomy)  # Cap at 95% (always keep human in loop)

    def get_stats(self) -> Dict:
        """Get AI statistics."""
        return {
            "total_actions": self._total_actions,
            "human_overrides": self._human_overrides,
            "autonomy_level": float(f"{self.get_autonomy_level():.3f}"),
            "q_table_size": len(self._q_table),
            "experience_buffer_size": len(self._experience_buffer),
            "avg_confidence": (
                float(f"{np.mean(self._confidence_history):.3f}")
                if self._confidence_history
                else 0.0
            ),
        }

"""
Predictive query prefetching engine with intelligent pattern analysis.

Implements:
- Query pattern analysis and sequence detection
- Markov chain model for query prediction
- Speculative execution during low-load periods
- Session-aware prefetching
- Cost-benefit analysis for prefetch decisions
"""

import time
import hashlib
from typing import Any, Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import defaultdict, deque
from threading import Thread, Lock
from enum import Enum
import asyncio

from app.core.cache_manager import get_cache_manager, QueryFingerprinter
from app.core.db import get_conn, run_explain


class PrefetchStrategy(Enum):
    """Prefetch strategies."""
    MARKOV = "markov"  # Markov chain prediction
    SEQUENTIAL = "sequential"  # Sequential pattern detection
    TEMPORAL = "temporal"  # Time-based patterns
    COLLABORATIVE = "collaborative"  # Multi-user pattern detection


class LoadLevel(Enum):
    """System load levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class QueryExecution:
    """Record of a query execution."""
    fingerprint: str
    sql: str
    timestamp: datetime
    execution_time_ms: float
    session_id: Optional[str] = None
    user_id: Optional[str] = None
    result_size_bytes: int = 0
    cache_hit: bool = False


@dataclass
class QuerySequence:
    """Sequence of queries in a session."""
    session_id: str
    queries: List[QueryExecution] = field(default_factory=list)
    start_time: datetime = field(default_factory=datetime.utcnow)
    end_time: Optional[datetime] = None

    def duration_seconds(self) -> float:
        """Get sequence duration."""
        end = self.end_time or datetime.utcnow()
        return (end - self.start_time).total_seconds()


@dataclass
class PrefetchCandidate:
    """Candidate query for prefetching."""
    fingerprint: str
    sql: str
    probability: float
    estimated_cost_ms: float
    estimated_benefit: float
    priority_score: float = 0.0
    reason: str = ""


@dataclass
class PrefetchDecision:
    """Decision about whether to prefetch a query."""
    should_prefetch: bool
    candidate: PrefetchCandidate
    reason: str
    cost_benefit_ratio: float


class MarkovChainModel:
    """
    Markov chain model for query sequence prediction.

    Learns transition probabilities between queries to predict next queries.
    """

    def __init__(self, order: int = 1):
        """
        Initialize Markov model.

        Args:
            order: Order of Markov chain (1 = first-order, 2 = second-order, etc.)
        """
        self.order = order

        # Transition counts: (state) -> (next_query) -> count
        self.transitions: Dict[Tuple[str, ...], Dict[str, int]] = defaultdict(lambda: defaultdict(int))

        # Total transitions from each state
        self.state_counts: Dict[Tuple[str, ...], int] = defaultdict(int)

        self.lock = Lock()

    def train(self, sequence: List[str]):
        """
        Train model on a query sequence.

        Args:
            sequence: List of query fingerprints
        """
        if len(sequence) <= self.order:
            return

        with self.lock:
            for i in range(len(sequence) - self.order):
                # Get state (current n queries)
                state = tuple(sequence[i:i + self.order])

                # Get next query
                next_query = sequence[i + self.order]

                # Update transitions
                self.transitions[state][next_query] += 1
                self.state_counts[state] += 1

    def predict(self, recent_queries: List[str], top_k: int = 5) -> List[Tuple[str, float]]:
        """
        Predict next queries based on recent history.

        Args:
            recent_queries: Recent query fingerprints
            top_k: Number of predictions to return

        Returns:
            List of (fingerprint, probability) tuples
        """
        if len(recent_queries) < self.order:
            return []

        # Get current state
        state = tuple(recent_queries[-self.order:])

        with self.lock:
            if state not in self.transitions:
                return []

            # Calculate probabilities
            total = self.state_counts[state]
            if total == 0:
                return []

            predictions = []
            for next_query, count in self.transitions[state].items():
                probability = count / total
                predictions.append((next_query, probability))

            # Sort by probability descending
            predictions.sort(key=lambda x: x[1], reverse=True)

            return predictions[:top_k]

    def get_statistics(self) -> Dict[str, Any]:
        """Get model statistics."""
        with self.lock:
            total_states = len(self.state_counts)
            total_transitions = sum(self.state_counts.values())
            avg_transitions_per_state = total_transitions / total_states if total_states > 0 else 0

            return {
                "order": self.order,
                "total_states": total_states,
                "total_transitions": total_transitions,
                "avg_transitions_per_state": avg_transitions_per_state
            }


class PrefetchEngine:
    """
    Intelligent query prefetching engine.

    Features:
    - Pattern-based query prediction using Markov chains
    - Session-aware prefetching
    - Load-aware speculative execution
    - Cost-benefit analysis for prefetch decisions
    """

    def __init__(
        self,
        cache_manager=None,
        max_history_size: int = 10000,
        prefetch_threshold: float = 0.3,
        max_prefetch_cost_ms: float = 1000.0,
        enable_speculative: bool = True
    ):
        """
        Initialize prefetch engine.

        Args:
            cache_manager: Cache manager instance
            max_history_size: Maximum query history to maintain
            prefetch_threshold: Minimum probability threshold for prefetching
            max_prefetch_cost_ms: Maximum cost for a prefetch operation
            enable_speculative: Enable speculative execution
        """
        self.cache_manager = cache_manager or get_cache_manager()
        self.max_history_size = max_history_size
        self.prefetch_threshold = prefetch_threshold
        self.max_prefetch_cost_ms = max_prefetch_cost_ms
        self.enable_speculative = enable_speculative

        # Query history
        self.query_history: deque[QueryExecution] = deque(maxlen=max_history_size)
        self.session_sequences: Dict[str, QuerySequence] = {}
        self.history_lock = Lock()

        # Prediction models
        self.markov_model = MarkovChainModel(order=2)
        self.user_models: Dict[str, MarkovChainModel] = {}

        # Prefetch statistics
        self.prefetch_attempts = 0
        self.prefetch_successes = 0  # Prefetched query was actually requested
        self.prefetch_failures = 0  # Prefetched but never used
        self.stats_lock = Lock()

        # Speculative execution
        self.speculative_thread = None
        self.running = False

        if self.enable_speculative:
            self._start_speculative_execution()

        # Query fingerprint to SQL mapping
        self.fingerprint_to_sql: Dict[str, str] = {}

    def record_query_execution(
        self,
        sql: str,
        execution_time_ms: float,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        result_size_bytes: int = 0,
        cache_hit: bool = False
    ):
        """
        Record a query execution for pattern analysis.

        Args:
            sql: SQL query text
            execution_time_ms: Execution time in milliseconds
            session_id: Optional session identifier
            user_id: Optional user identifier
            result_size_bytes: Size of result set
            cache_hit: Whether result came from cache
        """
        fingerprint = QueryFingerprinter.generate_fingerprint(sql)

        execution = QueryExecution(
            fingerprint=fingerprint,
            sql=sql,
            timestamp=datetime.utcnow(),
            execution_time_ms=execution_time_ms,
            session_id=session_id,
            user_id=user_id,
            result_size_bytes=result_size_bytes,
            cache_hit=cache_hit
        )

        with self.history_lock:
            self.query_history.append(execution)
            self.fingerprint_to_sql[fingerprint] = sql

            # Update session sequence
            if session_id:
                if session_id not in self.session_sequences:
                    self.session_sequences[session_id] = QuerySequence(session_id=session_id)

                self.session_sequences[session_id].queries.append(execution)

        # Train models periodically
        if len(self.query_history) % 100 == 0:
            self._train_models()

    def predict_next_queries(
        self,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
        top_k: int = 5
    ) -> List[PrefetchCandidate]:
        """
        Predict next likely queries.

        Args:
            session_id: Session to predict for
            user_id: User to predict for
            top_k: Number of predictions to return

        Returns:
            List of prefetch candidates
        """
        candidates = []

        # Get recent query history
        recent_queries = []

        with self.history_lock:
            if session_id and session_id in self.session_sequences:
                # Use session-specific history
                sequence = self.session_sequences[session_id]
                recent_queries = [q.fingerprint for q in sequence.queries[-10:]]
            else:
                # Use global history
                recent_queries = [q.fingerprint for q in list(self.query_history)[-10:]]

        if not recent_queries:
            return []

        # Get predictions from Markov model
        predictions = self.markov_model.predict(recent_queries, top_k=top_k * 2)

        # Get user-specific predictions if available
        if user_id and user_id in self.user_models:
            user_predictions = self.user_models[user_id].predict(recent_queries, top_k=top_k)
            # Merge predictions (weighted average)
            pred_dict = {}
            for fp, prob in predictions:
                pred_dict[fp] = prob * 0.6  # Global model weight

            for fp, prob in user_predictions:
                if fp in pred_dict:
                    pred_dict[fp] += prob * 0.4  # User model weight
                else:
                    pred_dict[fp] = prob * 0.4

            predictions = [(fp, prob) for fp, prob in pred_dict.items()]
            predictions.sort(key=lambda x: x[1], reverse=True)

        # Convert to candidates
        for fingerprint, probability in predictions[:top_k]:
            if probability < self.prefetch_threshold:
                continue

            sql = self.fingerprint_to_sql.get(fingerprint)
            if not sql:
                continue

            # Estimate cost
            estimated_cost = self._estimate_query_cost(fingerprint)

            # Calculate benefit
            estimated_benefit = self._estimate_benefit(fingerprint, probability)

            # Priority score combines probability and benefit
            priority_score = probability * estimated_benefit / max(estimated_cost, 1.0)

            candidates.append(PrefetchCandidate(
                fingerprint=fingerprint,
                sql=sql,
                probability=probability,
                estimated_cost_ms=estimated_cost,
                estimated_benefit=estimated_benefit,
                priority_score=priority_score,
                reason=f"Markov prediction (p={probability:.3f})"
            ))

        # Sort by priority score
        candidates.sort(key=lambda c: c.priority_score, reverse=True)

        return candidates

    def should_prefetch(self, candidate: PrefetchCandidate) -> PrefetchDecision:
        """
        Decide whether to prefetch a query based on cost-benefit analysis.

        Args:
            candidate: Prefetch candidate

        Returns:
            Prefetch decision with reasoning
        """
        # Check if already cached
        cached_result = self.cache_manager.get(candidate.sql)
        if cached_result is not None:
            return PrefetchDecision(
                should_prefetch=False,
                candidate=candidate,
                reason="Already cached",
                cost_benefit_ratio=0.0
            )

        # Check cost threshold
        if candidate.estimated_cost_ms > self.max_prefetch_cost_ms:
            return PrefetchDecision(
                should_prefetch=False,
                candidate=candidate,
                reason=f"Cost too high ({candidate.estimated_cost_ms:.0f}ms > {self.max_prefetch_cost_ms:.0f}ms)",
                cost_benefit_ratio=0.0
            )

        # Check current system load
        load = self._get_current_load()
        if load in [LoadLevel.HIGH, LoadLevel.CRITICAL]:
            return PrefetchDecision(
                should_prefetch=False,
                candidate=candidate,
                reason=f"System load too high ({load.value})",
                cost_benefit_ratio=0.0
            )

        # Calculate cost-benefit ratio
        cost_benefit_ratio = candidate.estimated_benefit / max(candidate.estimated_cost_ms, 1.0)

        # Decide based on cost-benefit ratio
        threshold_ratio = 2.0  # Benefit should be at least 2x cost

        if cost_benefit_ratio >= threshold_ratio:
            return PrefetchDecision(
                should_prefetch=True,
                candidate=candidate,
                reason=f"Good cost-benefit ratio ({cost_benefit_ratio:.2f})",
                cost_benefit_ratio=cost_benefit_ratio
            )
        else:
            return PrefetchDecision(
                should_prefetch=False,
                candidate=candidate,
                reason=f"Cost-benefit ratio too low ({cost_benefit_ratio:.2f} < {threshold_ratio})",
                cost_benefit_ratio=cost_benefit_ratio
            )

    def execute_prefetch(self, candidate: PrefetchCandidate) -> bool:
        """
        Execute a prefetch operation.

        Args:
            candidate: Query to prefetch

        Returns:
            True if prefetch succeeded
        """
        try:
            start_time = time.time()

            # Execute query
            with get_conn() as conn:
                cur = conn.cursor()
                cur.execute(candidate.sql)
                result = cur.fetchall()

            execution_time = (time.time() - start_time) * 1000

            # Cache result
            self.cache_manager.put(
                sql=candidate.sql,
                result=result,
                ttl_seconds=3600,  # 1 hour for prefetched results
                compress=True
            )

            with self.stats_lock:
                self.prefetch_attempts += 1

            return True

        except Exception as e:
            print(f"Prefetch failed: {e}")
            return False

    def warm_cache(
        self,
        queries: List[str],
        parallel: bool = True
    ) -> Dict[str, Any]:
        """
        Warm cache with specified queries.

        Args:
            queries: List of SQL queries to execute
            parallel: Execute in parallel (if True)

        Returns:
            Warming statistics
        """
        successful = 0
        failed = 0
        total_time_ms = 0

        start = time.time()

        for sql in queries:
            fingerprint = QueryFingerprinter.generate_fingerprint(sql)

            candidate = PrefetchCandidate(
                fingerprint=fingerprint,
                sql=sql,
                probability=1.0,
                estimated_cost_ms=0.0,
                estimated_benefit=1000.0,
                reason="Manual cache warming"
            )

            if self.execute_prefetch(candidate):
                successful += 1
            else:
                failed += 1

        total_time_ms = (time.time() - start) * 1000

        return {
            "total_queries": len(queries),
            "successful": successful,
            "failed": failed,
            "total_time_ms": total_time_ms,
            "avg_time_per_query_ms": total_time_ms / len(queries) if queries else 0
        }

    def get_statistics(self) -> Dict[str, Any]:
        """Get prefetch statistics."""
        with self.stats_lock:
            success_rate = (
                self.prefetch_successes / self.prefetch_attempts
                if self.prefetch_attempts > 0
                else 0.0
            )

            stats = {
                "total_prefetch_attempts": self.prefetch_attempts,
                "prefetch_successes": self.prefetch_successes,
                "prefetch_failures": self.prefetch_failures,
                "success_rate": success_rate,
                "query_history_size": len(self.query_history),
                "active_sessions": len(self.session_sequences),
                "markov_model": self.markov_model.get_statistics(),
                "user_models": len(self.user_models)
            }

        return stats

    def _train_models(self):
        """Train prediction models on current history."""
        with self.history_lock:
            # Train global Markov model
            global_sequence = [q.fingerprint for q in self.query_history]
            self.markov_model.train(global_sequence)

            # Train user-specific models
            user_sequences = defaultdict(list)
            for query in self.query_history:
                if query.user_id:
                    user_sequences[query.user_id].append(query.fingerprint)

            for user_id, sequence in user_sequences.items():
                if user_id not in self.user_models:
                    self.user_models[user_id] = MarkovChainModel(order=2)

                self.user_models[user_id].train(sequence)

    def _estimate_query_cost(self, fingerprint: str) -> float:
        """
        Estimate query execution cost.

        Args:
            fingerprint: Query fingerprint

        Returns:
            Estimated cost in milliseconds
        """
        # Look up historical execution time
        with self.history_lock:
            executions = [q for q in self.query_history if q.fingerprint == fingerprint]

            if executions:
                # Use average of recent executions
                recent = executions[-5:]
                avg_time = sum(q.execution_time_ms for q in recent) / len(recent)
                return avg_time

        # No history, use conservative estimate
        return 500.0

    def _estimate_benefit(self, fingerprint: str, probability: float) -> float:
        """
        Estimate benefit of prefetching a query.

        Benefit is higher for:
        - High probability queries
        - Expensive queries (avoid repeat cost)
        - Frequently accessed queries

        Args:
            fingerprint: Query fingerprint
            probability: Probability of query being executed

        Returns:
            Estimated benefit score
        """
        # Base benefit from probability
        benefit = probability * 1000.0

        # Boost for expensive queries
        cost = self._estimate_query_cost(fingerprint)
        if cost > 100:
            benefit *= (cost / 100.0)

        # Boost for frequently accessed queries
        with self.history_lock:
            access_count = sum(1 for q in self.query_history if q.fingerprint == fingerprint)
            if access_count > 10:
                benefit *= 1.5

        return benefit

    def _get_current_load(self) -> LoadLevel:
        """
        Get current system load level.

        In a real implementation, this would check:
        - CPU usage
        - Active connections
        - Query queue length
        - Cache hit rate

        Returns:
            Current load level
        """
        # Simple heuristic based on cache statistics
        cache_stats = self.cache_manager.get_statistics()

        if cache_stats.hit_rate < 0.3:
            return LoadLevel.HIGH
        elif cache_stats.hit_rate < 0.5:
            return LoadLevel.MEDIUM
        else:
            return LoadLevel.LOW

    def _start_speculative_execution(self):
        """Start background thread for speculative prefetching."""
        self.running = True
        self.speculative_thread = Thread(target=self._speculative_loop, daemon=True)
        self.speculative_thread.start()

    def _speculative_loop(self):
        """Main loop for speculative prefetching."""
        while self.running:
            try:
                # Only prefetch during low load
                if self._get_current_load() == LoadLevel.LOW:
                    # Get predictions
                    candidates = self.predict_next_queries(top_k=3)

                    for candidate in candidates:
                        decision = self.should_prefetch(candidate)

                        if decision.should_prefetch:
                            self.execute_prefetch(candidate)

                # Sleep between prefetch cycles
                time.sleep(10)

            except Exception as e:
                print(f"Error in speculative loop: {e}")
                time.sleep(5)

    def stop(self):
        """Stop the prefetch engine."""
        self.running = False

        if self.speculative_thread:
            self.speculative_thread.join(timeout=2)


# Singleton instance
_prefetch_engine: Optional[PrefetchEngine] = None


def get_prefetch_engine() -> PrefetchEngine:
    """Get singleton prefetch engine instance."""
    global _prefetch_engine

    if _prefetch_engine is None:
        _prefetch_engine = PrefetchEngine(
            prefetch_threshold=0.3,
            max_prefetch_cost_ms=1000.0,
            enable_speculative=True
        )

    return _prefetch_engine

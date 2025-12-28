"""
Comprehensive resilience system for production-ready operation.

Implements:
- Circuit breakers for failure isolation
- Retry logic with exponential backoff and jitter
- Bulkhead pattern for resource isolation
- Fallback mechanisms for degraded operation
- Adaptive timeout management
"""

import random
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from functools import wraps
from threading import Lock, Semaphore
from typing import Any, Callable, Dict, Optional

from app.core.observability import get_observability


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, rejecting requests
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker."""

    failure_threshold: int = 5  # Failures before opening
    success_threshold: int = 2  # Successes before closing from half-open
    timeout_seconds: float = 60.0  # Time to wait before trying again
    half_open_max_calls: int = 3  # Max calls in half-open state
    sliding_window_size: int = 100  # Size of metrics window


@dataclass
class RetryConfig:
    """Configuration for retry logic."""

    max_attempts: int = 3
    base_delay_seconds: float = 1.0
    max_delay_seconds: float = 60.0
    exponential_base: float = 2.0
    jitter: bool = True
    retry_on_exceptions: tuple = (Exception,)


@dataclass
class BulkheadConfig:
    """Configuration for bulkhead pattern."""

    max_concurrent: int = 10
    max_waiting: int = 20
    timeout_seconds: float = 30.0


class CircuitBreaker:
    """
    Circuit breaker implementation for failure isolation.

    Prevents cascading failures by breaking the circuit when
    a service is experiencing issues.
    """

    def __init__(self, name: str, config: Optional[CircuitBreakerConfig] = None):
        """
        Initialize circuit breaker.

        Args:
            name: Circuit breaker name
            config: Optional configuration
        """
        self.name = name
        self.config = config or CircuitBreakerConfig()

        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.half_open_calls = 0

        # Sliding window for tracking recent calls
        self.call_history: deque = deque(maxlen=self.config.sliding_window_size)

        self.lock = Lock()
        self.obs = get_observability()

        # Update metrics
        self._update_state_metric()

    def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute function through circuit breaker.

        Args:
            func: Function to execute
            *args: Function arguments
            **kwargs: Function keyword arguments

        Returns:
            Function result

        Raises:
            CircuitBreakerOpenError: If circuit is open
        """
        with self.lock:
            # Check if circuit is open
            if self.state == CircuitState.OPEN:
                # Check if timeout has passed
                if self._should_attempt_reset():
                    self.state = CircuitState.HALF_OPEN
                    self.half_open_calls = 0
                    self.obs.logger.info(
                        f"Circuit breaker {self.name} transitioning to HALF_OPEN",
                        circuit=self.name,
                    )
                    self._update_state_metric()
                else:
                    self.obs.logger.warning(
                        f"Circuit breaker {self.name} is OPEN, rejecting call",
                        circuit=self.name,
                    )
                    raise CircuitBreakerOpenError(f"Circuit {self.name} is open")

            # Check half-open call limit
            if self.state == CircuitState.HALF_OPEN:
                if self.half_open_calls >= self.config.half_open_max_calls:
                    raise CircuitBreakerOpenError(
                        f"Circuit {self.name} half-open call limit reached"
                    )
                self.half_open_calls += 1

        # Execute function
        start_time = time.time()
        try:
            result = func(*args, **kwargs)
            self._record_success(time.time() - start_time)
            return result
        except Exception:
            self._record_failure(time.time() - start_time)
            raise

    def _record_success(self, duration: float):
        """Record successful call."""
        with self.lock:
            self.call_history.append(("success", duration, datetime.utcnow()))

            if self.state == CircuitState.HALF_OPEN:
                self.success_count += 1

                if self.success_count >= self.config.success_threshold:
                    self.state = CircuitState.CLOSED
                    self.failure_count = 0
                    self.success_count = 0
                    self.obs.logger.info(
                        f"Circuit breaker {self.name} CLOSED after recovery",
                        circuit=self.name,
                    )
                    self._update_state_metric()

            elif self.state == CircuitState.CLOSED:
                # Reset failure count on success
                self.failure_count = 0

    def _record_failure(self, duration: float):
        """Record failed call."""
        with self.lock:
            self.call_history.append(("failure", duration, datetime.utcnow()))
            self.failure_count += 1
            self.last_failure_time = datetime.utcnow()

            self.obs.metrics.circuit_breaker_failures.labels(circuit=self.name).inc()

            # Check if we should open circuit
            if self.state == CircuitState.CLOSED:
                if self.failure_count >= self.config.failure_threshold:
                    self.state = CircuitState.OPEN
                    self.obs.logger.error(
                        f"Circuit breaker {self.name} OPENED after {self.failure_count} failures",
                        circuit=self.name,
                        failure_count=self.failure_count,
                    )
                    self._update_state_metric()

            elif self.state == CircuitState.HALF_OPEN:
                self.state = CircuitState.OPEN
                self.success_count = 0
                self.obs.logger.error(
                    f"Circuit breaker {self.name} reopened after failure in HALF_OPEN",
                    circuit=self.name,
                )
                self._update_state_metric()

    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset."""
        if self.last_failure_time is None:
            return True

        elapsed = (datetime.utcnow() - self.last_failure_time).total_seconds()
        return elapsed >= self.config.timeout_seconds

    def _update_state_metric(self):
        """Update Prometheus metric for circuit state."""
        state_value = {
            CircuitState.CLOSED: 0,
            CircuitState.HALF_OPEN: 1,
            CircuitState.OPEN: 2,
        }[self.state]

        self.obs.metrics.circuit_breaker_state.labels(circuit=self.name).set(
            state_value
        )

    def get_state(self) -> CircuitState:
        """Get current circuit state."""
        with self.lock:
            return self.state

    def get_statistics(self) -> Dict[str, Any]:
        """Get circuit breaker statistics."""
        with self.lock:
            recent_calls = list(self.call_history)

            successes = sum(1 for call in recent_calls if call[0] == "success")
            failures = sum(1 for call in recent_calls if call[0] == "failure")

            return {
                "name": self.name,
                "state": self.state.value,
                "failure_count": self.failure_count,
                "success_count": self.success_count,
                "recent_calls": len(recent_calls),
                "recent_successes": successes,
                "recent_failures": failures,
                "success_rate": successes / len(recent_calls) if recent_calls else 0.0,
            }


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open."""

    pass


class Retry:
    """
    Retry mechanism with exponential backoff and jitter.

    Automatically retries failed operations with intelligent backoff.
    """

    def __init__(self, config: Optional[RetryConfig] = None):
        """
        Initialize retry mechanism.

        Args:
            config: Optional retry configuration
        """
        self.config = config or RetryConfig()
        self.obs = get_observability()

    def execute(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute function with retry logic.

        Args:
            func: Function to execute
            *args: Function arguments
            **kwargs: Function keyword arguments

        Returns:
            Function result

        Raises:
            Last exception if all retries fail
        """
        last_exception = None

        for attempt in range(1, self.config.max_attempts + 1):
            try:
                return func(*args, **kwargs)
            except self.config.retry_on_exceptions as e:
                last_exception = e

                if attempt == self.config.max_attempts:
                    self.obs.logger.error(
                        f"All {self.config.max_attempts} retry attempts failed",
                        function=func.__name__,
                        error=str(e),
                    )
                    raise

                # Calculate backoff delay
                delay = self._calculate_delay(attempt)

                self.obs.logger.warning(
                    f"Retry attempt {attempt}/{self.config.max_attempts} after {delay:.2f}s",
                    function=func.__name__,
                    attempt=attempt,
                    delay=delay,
                    error=str(e),
                )

                time.sleep(delay)

        # Should never reach here, but just in case
        if last_exception:
            raise last_exception

    def _calculate_delay(self, attempt: int) -> float:
        """
        Calculate backoff delay with exponential backoff and jitter.

        Args:
            attempt: Attempt number (1-based)

        Returns:
            Delay in seconds
        """
        # Exponential backoff
        delay = min(
            self.config.base_delay_seconds
            * (self.config.exponential_base ** (attempt - 1)),
            self.config.max_delay_seconds,
        )

        # Add jitter to avoid thundering herd
        if self.config.jitter:
            delay = delay * (0.5 + random.random() * 0.5)

        return delay


class Bulkhead:
    """
    Bulkhead pattern for resource isolation.

    Limits concurrent executions to prevent resource exhaustion.
    """

    def __init__(self, name: str, config: Optional[BulkheadConfig] = None):
        """
        Initialize bulkhead.

        Args:
            name: Bulkhead name
            config: Optional configuration
        """
        self.name = name
        self.config = config or BulkheadConfig()

        self.semaphore = Semaphore(self.config.max_concurrent)
        self.waiting_semaphore = Semaphore(self.config.max_waiting)

        self.active_calls = 0
        self.waiting_calls = 0
        self.total_calls = 0
        self.rejected_calls = 0

        self.lock = Lock()
        self.obs = get_observability()

    def execute(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute function through bulkhead.

        Args:
            func: Function to execute
            *args: Function arguments
            **kwargs: Function keyword arguments

        Returns:
            Function result

        Raises:
            BulkheadFullError: If bulkhead is full
        """
        with self.lock:
            self.total_calls += 1

        # Try to acquire waiting slot
        if not self.waiting_semaphore.acquire(blocking=False):
            with self.lock:
                self.rejected_calls += 1

            self.obs.logger.warning(
                f"Bulkhead {self.name} waiting queue full, rejecting call",
                bulkhead=self.name,
                active=self.active_calls,
                waiting=self.waiting_calls,
            )
            raise BulkheadFullError(f"Bulkhead {self.name} waiting queue full")

        try:
            with self.lock:
                self.waiting_calls += 1

            # Acquire execution slot with timeout
            acquired = self.semaphore.acquire(timeout=self.config.timeout_seconds)

            if not acquired:
                with self.lock:
                    self.waiting_calls -= 1
                    self.rejected_calls += 1

                self.obs.logger.warning(
                    f"Bulkhead {self.name} timeout waiting for slot",
                    bulkhead=self.name,
                    timeout=self.config.timeout_seconds,
                )
                raise BulkheadTimeoutError(f"Bulkhead {self.name} timeout")

            try:
                with self.lock:
                    self.waiting_calls -= 1
                    self.active_calls += 1

                # Execute function
                return func(*args, **kwargs)

            finally:
                with self.lock:
                    self.active_calls -= 1
                self.semaphore.release()

        finally:
            self.waiting_semaphore.release()

    def get_statistics(self) -> Dict[str, Any]:
        """Get bulkhead statistics."""
        with self.lock:
            return {
                "name": self.name,
                "max_concurrent": self.config.max_concurrent,
                "max_waiting": self.config.max_waiting,
                "active_calls": self.active_calls,
                "waiting_calls": self.waiting_calls,
                "total_calls": self.total_calls,
                "rejected_calls": self.rejected_calls,
                "rejection_rate": (
                    self.rejected_calls / self.total_calls
                    if self.total_calls > 0
                    else 0.0
                ),
            }


class BulkheadFullError(Exception):
    """Raised when bulkhead is full."""

    pass


class BulkheadTimeoutError(Exception):
    """Raised when bulkhead times out."""

    pass


class Fallback:
    """
    Fallback mechanism for degraded operation.

    Provides alternative implementations when primary fails.
    """

    def __init__(self):
        """Initialize fallback mechanism."""
        self.obs = get_observability()

    def execute(self, primary: Callable, fallback: Callable, *args, **kwargs) -> Any:
        """
        Execute with fallback.

        Args:
            primary: Primary function to execute
            fallback: Fallback function if primary fails
            *args: Function arguments
            **kwargs: Function keyword arguments

        Returns:
            Result from primary or fallback
        """
        try:
            return primary(*args, **kwargs)
        except Exception as e:
            self.obs.logger.warning(
                "Primary function failed, using fallback",
                primary=primary.__name__,
                fallback=fallback.__name__,
                error=str(e),
            )

            try:
                return fallback(*args, **kwargs)
            except Exception as fallback_error:
                self.obs.logger.error(
                    "Both primary and fallback failed",
                    primary=primary.__name__,
                    fallback=fallback.__name__,
                    primary_error=str(e),
                    fallback_error=str(fallback_error),
                )
                raise


# Global registry of circuit breakers and bulkheads
_circuit_breakers: Dict[str, CircuitBreaker] = {}
_bulkheads: Dict[str, Bulkhead] = {}
_lock = Lock()


def get_circuit_breaker(
    name: str, config: Optional[CircuitBreakerConfig] = None
) -> CircuitBreaker:
    """
    Get or create circuit breaker.

    Args:
        name: Circuit breaker name
        config: Optional configuration

    Returns:
        Circuit breaker instance
    """
    with _lock:
        if name not in _circuit_breakers:
            _circuit_breakers[name] = CircuitBreaker(name, config)
        return _circuit_breakers[name]


def get_bulkhead(name: str, config: Optional[BulkheadConfig] = None) -> Bulkhead:
    """
    Get or create bulkhead.

    Args:
        name: Bulkhead name
        config: Optional configuration

    Returns:
        Bulkhead instance
    """
    with _lock:
        if name not in _bulkheads:
            _bulkheads[name] = Bulkhead(name, config)
        return _bulkheads[name]


# Convenience decorators


def circuit_breaker(name: str, config: Optional[CircuitBreakerConfig] = None):
    """
    Circuit breaker decorator.

    Args:
        name: Circuit breaker name
        config: Optional configuration

    Returns:
        Decorator
    """

    def decorator(func: Callable) -> Callable:
        cb = get_circuit_breaker(name, config)

        @wraps(func)
        def wrapper(*args, **kwargs):
            return cb.call(func, *args, **kwargs)

        return wrapper

    return decorator


def retry(config: Optional[RetryConfig] = None):
    """
    Retry decorator.

    Args:
        config: Optional retry configuration

    Returns:
        Decorator
    """

    def decorator(func: Callable) -> Callable:
        retry_instance = Retry(config)

        @wraps(func)
        def wrapper(*args, **kwargs):
            return retry_instance.execute(func, *args, **kwargs)

        return wrapper

    return decorator


def bulkhead(name: str, config: Optional[BulkheadConfig] = None):
    """
    Bulkhead decorator.

    Args:
        name: Bulkhead name
        config: Optional configuration

    Returns:
        Decorator
    """

    def decorator(func: Callable) -> Callable:
        bh = get_bulkhead(name, config)

        @wraps(func)
        def wrapper(*args, **kwargs):
            return bh.execute(func, *args, **kwargs)

        return wrapper

    return decorator


def with_fallback(fallback_func: Callable):
    """
    Fallback decorator.

    Args:
        fallback_func: Fallback function

    Returns:
        Decorator
    """

    def decorator(func: Callable) -> Callable:
        fallback_instance = Fallback()

        @wraps(func)
        def wrapper(*args, **kwargs):
            return fallback_instance.execute(func, fallback_func, *args, **kwargs)

        return wrapper

    return decorator

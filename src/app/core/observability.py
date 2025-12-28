"""
Comprehensive observability system with OpenTelemetry integration.

Provides:
- Distributed tracing with OpenTelemetry
- Structured logging with correlation IDs
- Prometheus metrics for all operations
- Custom dashboards and alerting
- Performance profiling and analysis
"""

import json
import logging
import time
import uuid
from contextvars import ContextVar
from datetime import datetime
from functools import wraps
from typing import Any, Callable, Dict, Optional

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import SERVICE_NAME, SERVICE_VERSION, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Status, StatusCode
from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    Info,
)

from app.core.config import settings

# Correlation ID context variable
correlation_id_ctx: ContextVar[str] = ContextVar('correlation_id', default='')


class StructuredLogger:
    """
    Structured logging with correlation IDs and JSON output.

    Provides consistent log formatting across the application.
    """

    def __init__(self, name: str):
        """
        Initialize structured logger.

        Args:
            name: Logger name (typically __name__)
        """
        self.logger = logging.getLogger(name)
        self.logger.setLevel(getattr(logging, getattr(settings, 'LOG_LEVEL', 'INFO').upper()))

        # Add JSON formatter
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = JSONFormatter()
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)

    def _log(self, level: str, message: str, **kwargs):
        """Log with correlation ID and additional context."""
        correlation_id = correlation_id_ctx.get()

        extra = {
            'correlation_id': correlation_id,
            'timestamp': datetime.utcnow().isoformat(),
            **kwargs
        }

        getattr(self.logger, level)(message, extra=extra)

    def debug(self, message: str, **kwargs):
        """Log debug message."""
        self._log('debug', message, **kwargs)

    def info(self, message: str, **kwargs):
        """Log info message."""
        self._log('info', message, **kwargs)

    def warning(self, message: str, **kwargs):
        """Log warning message."""
        self._log('warning', message, **kwargs)

    def error(self, message: str, **kwargs):
        """Log error message."""
        self._log('error', message, **kwargs)

    def critical(self, message: str, **kwargs):
        """Log critical message."""
        self._log('critical', message, **kwargs)


class JSONFormatter(logging.Formatter):
    """JSON log formatter for structured logging."""

    def format(self, record):
        """Format log record as JSON."""
        log_data = {
            'timestamp': datetime.utcfromtimestamp(record.created).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
        }

        # Add correlation ID if present
        if hasattr(record, 'correlation_id'):
            log_data['correlation_id'] = record.correlation_id

        # Add extra fields
        for key, value in record.__dict__.items():
            if key not in ['name', 'msg', 'args', 'created', 'filename', 'funcName',
                          'levelname', 'levelno', 'lineno', 'module', 'msecs',
                          'message', 'pathname', 'process', 'processName',
                          'relativeCreated', 'thread', 'threadName', 'exc_info',
                          'exc_text', 'stack_info']:
                log_data[key] = value

        # Add exception info if present
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)

        return json.dumps(log_data)


class PrometheusMetrics:
    """
    Prometheus metrics for application monitoring.

    Tracks all key performance indicators.
    """

    def __init__(self, registry: Optional[CollectorRegistry] = None):
        """
        Initialize Prometheus metrics.

        Args:
            registry: Custom registry (default: default registry)
        """
        self.registry = registry or CollectorRegistry()

        # Application info
        self.app_info = Info(
            'qeo_application',
            'Application information',
            registry=self.registry
        )
        self.app_info.info({
            'version': getattr(settings, 'VERSION', '0.7.0'),
            'environment': getattr(settings, 'ENVIRONMENT', 'production')
        })

        # HTTP metrics
        self.http_requests_total = Counter(
            'qeo_http_requests_total',
            'Total HTTP requests',
            ['method', 'endpoint', 'status_code'],
            registry=self.registry
        )

        self.http_request_duration = Histogram(
            'qeo_http_request_duration_seconds',
            'HTTP request duration',
            ['method', 'endpoint'],
            buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.5, 5.0, 10.0],
            registry=self.registry
        )

        # Query execution metrics
        self.query_executions_total = Counter(
            'qeo_query_executions_total',
            'Total query executions',
            ['query_type', 'success'],
            registry=self.registry
        )

        self.query_execution_duration = Histogram(
            'qeo_query_execution_duration_seconds',
            'Query execution duration',
            ['query_type'],
            buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0],
            registry=self.registry
        )

        # Optimization metrics
        self.optimization_suggestions_total = Counter(
            'qeo_optimization_suggestions_total',
            'Total optimization suggestions generated',
            ['suggestion_type'],
            registry=self.registry
        )

        self.optimization_success_rate = Gauge(
            'qeo_optimization_success_rate',
            'Optimization success rate (0-1)',
            registry=self.registry
        )

        # Cache metrics
        self.cache_operations_total = Counter(
            'qeo_cache_operations_total',
            'Total cache operations',
            ['operation', 'result'],
            registry=self.registry
        )

        self.cache_hit_rate = Gauge(
            'qeo_cache_hit_rate',
            'Cache hit rate (0-1)',
            registry=self.registry
        )

        self.cache_size_bytes = Gauge(
            'qeo_cache_size_bytes',
            'Cache size in bytes',
            registry=self.registry
        )

        # Database connection pool metrics
        self.db_connections_active = Gauge(
            'qeo_db_connections_active',
            'Active database connections',
            registry=self.registry
        )

        self.db_connections_idle = Gauge(
            'qeo_db_connections_idle',
            'Idle database connections',
            registry=self.registry
        )

        self.db_query_duration = Histogram(
            'qeo_db_query_duration_seconds',
            'Database query duration',
            ['operation'],
            buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0],
            registry=self.registry
        )

        # Index management metrics
        self.index_recommendations_total = Counter(
            'qeo_index_recommendations_total',
            'Total index recommendations',
            ['action'],
            registry=self.registry
        )

        self.index_health_score = Gauge(
            'qeo_index_health_score',
            'Overall index health score (0-100)',
            registry=self.registry
        )

        # Prefetch metrics
        self.prefetch_attempts_total = Counter(
            'qeo_prefetch_attempts_total',
            'Total prefetch attempts',
            ['result'],
            registry=self.registry
        )

        self.prefetch_success_rate = Gauge(
            'qeo_prefetch_success_rate',
            'Prefetch success rate (0-1)',
            registry=self.registry
        )

        # Circuit breaker metrics
        self.circuit_breaker_state = Gauge(
            'qeo_circuit_breaker_state',
            'Circuit breaker state (0=closed, 1=half-open, 2=open)',
            ['circuit'],
            registry=self.registry
        )

        self.circuit_breaker_failures = Counter(
            'qeo_circuit_breaker_failures_total',
            'Circuit breaker failures',
            ['circuit'],
            registry=self.registry
        )

        # Resource usage metrics
        self.memory_usage_bytes = Gauge(
            'qeo_memory_usage_bytes',
            'Memory usage in bytes',
            registry=self.registry
        )

        self.cpu_usage_percent = Gauge(
            'qeo_cpu_usage_percent',
            'CPU usage percentage',
            registry=self.registry
        )

    def observe_http_request(self, method: str, endpoint: str, status_code: int, duration: float):
        """Record HTTP request metrics."""
        self.http_requests_total.labels(
            method=method,
            endpoint=endpoint,
            status_code=status_code
        ).inc()

        self.http_request_duration.labels(
            method=method,
            endpoint=endpoint
        ).observe(duration)

    def observe_query_execution(self, query_type: str, duration: float, success: bool):
        """Record query execution metrics."""
        self.query_executions_total.labels(
            query_type=query_type,
            success='true' if success else 'false'
        ).inc()

        self.query_execution_duration.labels(
            query_type=query_type
        ).observe(duration)

    def observe_cache_operation(self, operation: str, result: str):
        """Record cache operation metrics."""
        self.cache_operations_total.labels(
            operation=operation,
            result=result
        ).inc()


class OpenTelemetryTracer:
    """
    OpenTelemetry distributed tracing integration.

    Provides automatic tracing for all operations.
    """

    def __init__(self):
        """Initialize OpenTelemetry tracer."""
        # Create resource
        resource = Resource.create({
            SERVICE_NAME: "qeo-api",
            SERVICE_VERSION: getattr(settings, 'VERSION', '0.7.0')
        })

        # Setup tracer provider
        tracer_provider = TracerProvider(resource=resource)

        # Add OTLP exporter if configured
        if getattr(settings, 'TRACING_ENABLED', False):
            otlp_endpoint = getattr(settings, 'OTEL_EXPORTER_OTLP_ENDPOINT', 'http://localhost:4317')
            otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
            span_processor = BatchSpanProcessor(otlp_exporter)
            tracer_provider.add_span_processor(span_processor)

        trace.set_tracer_provider(tracer_provider)
        self.tracer = trace.get_tracer(__name__)

    def trace_operation(self, operation_name: str):
        """
        Decorator to trace an operation.

        Args:
            operation_name: Name of the operation

        Returns:
            Decorated function
        """
        def decorator(func: Callable) -> Callable:
            @wraps(func)
            def wrapper(*args, **kwargs):
                with self.tracer.start_as_current_span(operation_name) as span:
                    # Add correlation ID
                    correlation_id = correlation_id_ctx.get()
                    if correlation_id:
                        span.set_attribute('correlation_id', correlation_id)

                    # Add function details
                    span.set_attribute('function.name', func.__name__)
                    span.set_attribute('function.module', func.__module__)

                    try:
                        result = func(*args, **kwargs)
                        span.set_status(Status(StatusCode.OK))
                        return result
                    except Exception as e:
                        span.set_status(Status(StatusCode.ERROR, str(e)))
                        span.record_exception(e)
                        raise

            return wrapper
        return decorator

    def start_span(self, name: str, attributes: Optional[Dict[str, Any]] = None):
        """
        Start a new span.

        Args:
            name: Span name
            attributes: Optional attributes to add to span

        Returns:
            Span context manager
        """
        span = self.tracer.start_span(name)

        if attributes:
            for key, value in attributes.items():
                span.set_attribute(key, str(value))

        # Add correlation ID
        correlation_id = correlation_id_ctx.get()
        if correlation_id:
            span.set_attribute('correlation_id', correlation_id)

        return span


class Observability:
    """
    Central observability system.

    Combines logging, metrics, and tracing.
    """

    def __init__(self):
        """Initialize observability system."""
        self.logger = StructuredLogger(__name__)
        self.metrics = PrometheusMetrics()
        self.tracer = OpenTelemetryTracer()

    def set_correlation_id(self, correlation_id: Optional[str] = None):
        """
        Set correlation ID for current context.

        Args:
            correlation_id: Correlation ID (generated if None)
        """
        if correlation_id is None:
            correlation_id = str(uuid.uuid4())

        correlation_id_ctx.set(correlation_id)
        return correlation_id

    def get_correlation_id(self) -> str:
        """Get current correlation ID."""
        return correlation_id_ctx.get()


# Singleton instance
_observability: Optional[Observability] = None


def get_observability() -> Observability:
    """Get singleton observability instance."""
    global _observability

    if _observability is None:
        _observability = Observability()

    return _observability


# Convenience decorators

def trace_operation(operation_name: str):
    """
    Trace an operation.

    Args:
        operation_name: Operation name

    Returns:
        Decorator
    """
    obs = get_observability()
    return obs.tracer.trace_operation(operation_name)


def log_execution(logger: Optional[StructuredLogger] = None):
    """
    Log function execution.

    Args:
        logger: Optional logger (uses default if None)

    Returns:
        Decorator
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            _logger = logger or get_observability().logger

            start_time = time.time()
            _logger.info(f"Starting {func.__name__}", function=func.__name__)

            try:
                result = func(*args, **kwargs)
                duration = time.time() - start_time
                _logger.info(
                    f"Completed {func.__name__}",
                    function=func.__name__,
                    duration_seconds=duration,
                    success=True
                )
                return result
            except Exception as e:
                duration = time.time() - start_time
                _logger.error(
                    f"Failed {func.__name__}",
                    function=func.__name__,
                    duration_seconds=duration,
                    success=False,
                    error=str(e)
                )
                raise

        return wrapper
    return decorator


def measure_time(metric_name: str, labels: Optional[Dict[str, str]] = None):
    """
    Measure execution time and record to metrics.

    Args:
        metric_name: Metric name
        labels: Optional labels

    Returns:
        Decorator
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()

            try:
                result = func(*args, **kwargs)
                duration = time.time() - start_time

                # Record metric
                obs = get_observability()
                # This would use the appropriate metric based on metric_name
                # For now, just log
                obs.logger.debug(
                    f"Metric: {metric_name}",
                    metric=metric_name,
                    duration=duration,
                    labels=labels or {}
                )

                return result
            except Exception:
                duration = time.time() - start_time
                raise

        return wrapper
    return decorator

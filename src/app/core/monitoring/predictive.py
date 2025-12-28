"""
Predictive Monitoring: Time series forecasting and anomaly detection.

Features:
- Fetch historical metrics from Prometheus (30 days)
- Time series forecasting using Prophet or ARIMA
- Anomaly detection using Isolation Forest
- Early warning 2 hours before predicted SLO breach
- Pattern recognition for recurring issues
"""

import logging
import warnings
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Tuple

import numpy as np
import requests
from prometheus_client import Counter, Gauge, Histogram

# Suppress prophet warnings if using it
warnings.filterwarnings("ignore")

logger = logging.getLogger(__name__)

# Prometheus metrics for predictive monitoring
prediction_accuracy = Gauge(
    "qeo_prediction_accuracy",
    "Accuracy of predictions vs actuals",
    ["metric"],
)
anomalies_detected = Counter(
    "qeo_anomalies_detected_total",
    "Total anomalies detected",
    ["type", "metric"],
)
slo_breach_predicted = Counter(
    "qeo_slo_breach_predicted_total",
    "SLO breaches predicted ahead of time",
    ["sli"],
)
forecast_latency_seconds = Histogram(
    "qeo_forecast_latency_seconds",
    "Time to generate forecast",
    ["metric"],
)


class AnomalyType(str, Enum):
    """Types of anomalies."""

    SPIKE = "spike"  # Sudden increase
    DROP = "drop"  # Sudden decrease
    PLATEAU = "plateau"  # Unexpected flat line
    OSCILLATION = "oscillation"  # Rapid fluctuations
    TREND = "trend"  # Sustained abnormal trend


@dataclass
class Anomaly:
    """Detected anomaly."""

    metric_name: str
    timestamp: datetime
    value: float
    expected_range: Tuple[float, float]  # (min, max)
    anomaly_type: AnomalyType
    severity: float  # 0-1, how far from expected
    context: str  # Human-readable explanation


@dataclass
class Forecast:
    """Time series forecast."""

    metric_name: str
    forecast_horizon_hours: int
    predictions: List[
        Tuple[datetime, float, float, float]
    ]  # (time, value, lower, upper)
    confidence: float  # 0-1
    method: str  # "prophet", "arima", "linear"
    generated_at: datetime


class PredictionEngine:
    """
    ML-based prediction engine.

    Uses multiple methods:
    1. Prophet (Facebook): Handles seasonality well
    2. ARIMA: Good for stationary series
    3. Exponential Smoothing: Fast fallback
    4. Isolation Forest: Anomaly detection
    """

    def __init__(self, prometheus_url: str = "http://prometheus:9090"):
        self.prometheus_url = prometheus_url
        self._model_cache = {}  # Cache trained models
        logger.info(f"PredictionEngine initialized with Prometheus: {prometheus_url}")

    def fetch_metric_history(
        self,
        metric_query: str,
        days: int = 30,
    ) -> List[Tuple[datetime, float]]:
        """
        Fetch historical metric data from Prometheus.

        Args:
            metric_query: PromQL query
            days: Number of days of history to fetch

        Returns:
            List of (timestamp, value) tuples
        """
        try:
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(days=days)

            # Query Prometheus range API
            url = f"{self.prometheus_url}/api/v1/query_range"
            params = {
                "query": metric_query,
                "start": start_time.timestamp(),
                "end": end_time.timestamp(),
                "step": "5m",  # 5-minute resolution
            }

            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()

            if data["status"] != "success":
                logger.error(f"Prometheus query failed: {data}")
                return []

            # Parse results
            results = []
            for result in data.get("data", {}).get("result", []):
                for timestamp, value in result.get("values", []):
                    try:
                        dt = datetime.fromtimestamp(float(timestamp))
                        val = float(value)
                        results.append((dt, val))
                    except (ValueError, TypeError) as e:
                        logger.warning(f"Skipping invalid data point: {e}")
                        continue

            logger.info(f"Fetched {len(results)} data points for {metric_query}")
            return sorted(results, key=lambda x: x[0])

        except Exception as e:
            logger.error(f"Error fetching metric history: {e}", exc_info=True)
            return []

    def forecast_metric(
        self,
        metric_name: str,
        history: List[Tuple[datetime, float]],
        horizon_hours: int = 24,
    ) -> Optional[Forecast]:
        """
        Generate time series forecast.

        Args:
            metric_name: Name of the metric
            history: Historical data points
            horizon_hours: How far ahead to forecast

        Returns:
            Forecast object or None if unable to forecast
        """
        if len(history) < 100:
            logger.warning(
                f"Insufficient data for forecasting {metric_name}: {len(history)} points"
            )
            return None

        try:
            start_time = datetime.utcnow()

            # Try Prophet first (best for seasonality)
            forecast = self._forecast_with_prophet(metric_name, history, horizon_hours)

            if forecast:
                elapsed = (datetime.utcnow() - start_time).total_seconds()
                forecast_latency_seconds.labels(metric=metric_name).observe(elapsed)
                return forecast

            # Fallback to simple exponential smoothing
            forecast = self._forecast_with_exponential_smoothing(
                metric_name, history, horizon_hours
            )

            if forecast:
                elapsed = (datetime.utcnow() - start_time).total_seconds()
                forecast_latency_seconds.labels(metric=metric_name).observe(elapsed)

            return forecast

        except Exception as e:
            logger.error(f"Error forecasting {metric_name}: {e}", exc_info=True)
            return None

    def _forecast_with_prophet(
        self,
        metric_name: str,
        history: List[Tuple[datetime, float]],
        horizon_hours: int,
    ) -> Optional[Forecast]:
        """
        Forecast using Facebook Prophet.

        Prophet is excellent for:
        - Handling missing data
        - Detecting seasonality (daily, weekly)
        - Incorporating holidays/events
        """
        try:
            from prophet import Prophet

            # Prepare data in Prophet format
            df_data = {"ds": [], "y": []}
            for ts, value in history:
                # Skip NaN/inf values
                if not np.isfinite(value):
                    continue
                df_data["ds"].append(ts)
                df_data["y"].append(value)

            if len(df_data["ds"]) < 100:
                return None

            # Train Prophet model
            model = Prophet(
                changepoint_prior_scale=0.05,  # Flexibility of trend changes
                seasonality_prior_scale=10.0,  # Seasonality strength
                daily_seasonality=True,
                weekly_seasonality=True,
                yearly_seasonality=False,  # Not enough data
                interval_width=0.95,  # 95% confidence interval
            )

            import pandas as pd

            df = pd.DataFrame(df_data)
            model.fit(df)

            # Generate future dates
            future = model.make_future_dataframe(
                periods=horizon_hours * 12, freq="5T"
            )  # 5min intervals
            forecast_df = model.predict(future)

            # Extract predictions for future only
            predictions = []
            last_history_time = history[-1][0]

            for _, row in forecast_df.iterrows():
                pred_time = row["ds"].to_pydatetime()
                if pred_time <= last_history_time:
                    continue

                predictions.append(
                    (
                        pred_time,
                        float(row["yhat"]),
                        float(row["yhat_lower"]),
                        float(row["yhat_upper"]),
                    )
                )

                if len(predictions) >= horizon_hours * 12:  # 5min resolution
                    break

            # Calculate confidence based on prediction interval width
            avg_interval_width = np.mean(
                [
                    (upper - lower) / value if value != 0 else 0
                    for _, value, lower, upper in predictions[
                        : min(100, len(predictions))
                    ]
                ]
            )
            confidence = max(0.0, min(1.0, 1.0 - avg_interval_width))

            return Forecast(
                metric_name=metric_name,
                forecast_horizon_hours=horizon_hours,
                predictions=predictions,
                confidence=float(f"{confidence:.3f}"),
                method="prophet",
                generated_at=datetime.utcnow(),
            )

        except ImportError:
            logger.warning("Prophet not installed, falling back to simpler method")
            return None
        except Exception as e:
            logger.error(f"Prophet forecasting failed: {e}", exc_info=True)
            return None

    def _forecast_with_exponential_smoothing(
        self,
        metric_name: str,
        history: List[Tuple[datetime, float]],
        horizon_hours: int,
    ) -> Optional[Forecast]:
        """
        Simple exponential smoothing forecast.

        Fast fallback method when Prophet is unavailable.
        """
        try:
            values = np.array([v for _, v in history if np.isfinite(v)])
            if len(values) < 50:
                return None

            # Simple exponential smoothing
            alpha = 0.3  # Smoothing factor
            smoothed = [values[0]]
            for val in values[1:]:
                smoothed.append(alpha * val + (1 - alpha) * smoothed[-1])

            # Project forward
            last_value = smoothed[-1]
            trend = (
                smoothed[-1] - smoothed[-50]
            ) / 50  # Average trend over last 50 points

            predictions = []
            last_time = history[-1][0]
            interval_minutes = 5

            for i in range(1, horizon_hours * 12 + 1):  # 5min resolution
                pred_time = last_time + timedelta(minutes=i * interval_minutes)
                pred_value = last_value + trend * i

                # Estimate uncertainty (increases with distance)
                std_dev = (
                    np.std(values[-100:]) if len(values) >= 100 else np.std(values)
                )
                uncertainty = std_dev * (1 + i / 100)  # Grows with forecast horizon

                predictions.append(
                    (
                        pred_time,
                        float(f"{pred_value:.3f}"),
                        float(f"{pred_value - 1.96 * uncertainty:.3f}"),
                        float(f"{pred_value + 1.96 * uncertainty:.3f}"),
                    )
                )

            return Forecast(
                metric_name=metric_name,
                forecast_horizon_hours=horizon_hours,
                predictions=predictions,
                confidence=0.7,  # Lower confidence for simple method
                method="exponential_smoothing",
                generated_at=datetime.utcnow(),
            )

        except Exception as e:
            logger.error(f"Exponential smoothing failed: {e}", exc_info=True)
            return None

    def detect_anomalies(
        self,
        metric_name: str,
        history: List[Tuple[datetime, float]],
        window_size: int = 100,
    ) -> List[Anomaly]:
        """
        Detect anomalies using Isolation Forest and statistical methods.

        Args:
            metric_name: Name of the metric
            history: Historical data points
            window_size: Size of sliding window for detection

        Returns:
            List of detected anomalies
        """
        if len(history) < window_size:
            return []

        anomalies = []

        try:
            # Statistical anomaly detection (z-score)
            anomalies.extend(
                self._detect_statistical_anomalies(metric_name, history, window_size)
            )

            # Try Isolation Forest if sklearn available
            try:
                import importlib.util

                if importlib.util.find_spec("sklearn.ensemble") is not None:
                    iso_anomalies = self._detect_isolation_forest_anomalies(
                        metric_name, history, window_size
                    )
                    anomalies.extend(iso_anomalies)
            except ImportError:
                logger.debug("sklearn not available, skipping Isolation Forest")

            # Remove duplicates (keep highest severity)
            unique_anomalies = {}
            for anomaly in anomalies:
                key = (anomaly.metric_name, anomaly.timestamp)
                if (
                    key not in unique_anomalies
                    or anomaly.severity > unique_anomalies[key].severity
                ):
                    unique_anomalies[key] = anomaly

            result = list(unique_anomalies.values())
            logger.info(f"Detected {len(result)} anomalies for {metric_name}")

            # Update metrics
            for anomaly in result:
                anomalies_detected.labels(
                    type=anomaly.anomaly_type.value,
                    metric=metric_name,
                ).inc()

            return result

        except Exception as e:
            logger.error(f"Error detecting anomalies: {e}", exc_info=True)
            return []

    def _detect_statistical_anomalies(
        self,
        metric_name: str,
        history: List[Tuple[datetime, float]],
        window_size: int,
    ) -> List[Anomaly]:
        """Detect anomalies using z-score method."""
        anomalies = []

        values = np.array([v for _, v in history if np.isfinite(v)])
        if len(values) < window_size:
            return []

        # Sliding window analysis
        for i in range(window_size, len(history)):
            window = values[i - window_size : i]
            current_value = values[i]

            mean = np.mean(window)
            std = np.std(window)

            if std == 0:
                continue

            z_score = abs((current_value - mean) / std)

            # Anomaly if z-score > 3 (3 standard deviations)
            if z_score > 3:
                # Determine anomaly type
                if current_value > mean + 3 * std:
                    anomaly_type = AnomalyType.SPIKE
                else:
                    anomaly_type = AnomalyType.DROP

                severity = min(1.0, z_score / 10)  # Cap at 1.0

                anomalies.append(
                    Anomaly(
                        metric_name=metric_name,
                        timestamp=history[i][0],
                        value=float(f"{current_value:.3f}"),
                        expected_range=(
                            float(f"{mean - 2 * std:.3f}"),
                            float(f"{mean + 2 * std:.3f}"),
                        ),
                        anomaly_type=anomaly_type,
                        severity=float(f"{severity:.3f}"),
                        context=f"Value {current_value:.3f} is {z_score:.1f} std devs from mean {mean:.3f}",
                    )
                )

        return anomalies

    def _detect_isolation_forest_anomalies(
        self,
        metric_name: str,
        history: List[Tuple[datetime, float]],
        window_size: int,
    ) -> List[Anomaly]:
        """Detect anomalies using Isolation Forest (unsupervised ML)."""
        from sklearn.ensemble import IsolationForest

        anomalies = []

        # Prepare features: value, rate of change, rolling mean
        features = []
        for i in range(window_size, len(history)):
            value = history[i][1]
            prev_value = history[i - 1][1]
            rolling_mean = np.mean([v for _, v in history[i - window_size : i]])

            features.append(
                [
                    value,
                    value - prev_value,  # Rate of change
                    (
                        value / rolling_mean if rolling_mean != 0 else 1.0
                    ),  # Deviation from mean
                ]
            )

        if len(features) < 10:
            return []

        features_array = np.array(features)

        # Train Isolation Forest
        model = IsolationForest(
            contamination=0.05,  # Expect 5% anomalies
            random_state=42,
            n_estimators=100,
        )
        predictions = model.fit_predict(features_array)

        # Extract anomalies (prediction == -1)
        for i, pred in enumerate(predictions):
            if pred == -1:
                idx = window_size + i
                value = history[idx][1]

                # Calculate expected range from recent window
                recent_values = [v for _, v in history[idx - 20 : idx]]
                mean = np.mean(recent_values)
                std = np.std(recent_values)

                anomalies.append(
                    Anomaly(
                        metric_name=metric_name,
                        timestamp=history[idx][0],
                        value=float(f"{value:.3f}"),
                        expected_range=(
                            float(f"{mean - 2 * std:.3f}"),
                            float(f"{mean + 2 * std:.3f}"),
                        ),
                        anomaly_type=(
                            AnomalyType.SPIKE if value > mean else AnomalyType.DROP
                        ),
                        severity=0.7,  # Fixed severity for ML-detected anomalies
                        context=f"ML-detected anomaly: value {value:.3f} deviates from pattern",
                    )
                )

        return anomalies


class PredictiveMonitor:
    """
    High-level predictive monitoring interface.

    Monitors critical metrics and provides:
    - 24-hour forecasts
    - Anomaly detection
    - SLO breach predictions
    - Early warning alerts
    """

    # Metrics to monitor
    MONITORED_METRICS = {
        "availability": "qeo:sli:availability:ratio_rate5m",
        "latency_p95": "qeo:http_request_duration:p95",
        "error_rate": "qeo:http_error_ratio:rate5m",
        "cpu_usage": 'rate(container_cpu_usage_seconds_total{pod=~"qeo-api-.*"}[5m])',
        "memory_usage": 'container_memory_usage_bytes{pod=~"qeo-api-.*"} / 1024 / 1024 / 1024',
    }

    def __init__(self, prometheus_url: str = "http://prometheus:9090"):
        self.engine = PredictionEngine(prometheus_url)
        self._forecasts_cache = {}
        self._last_update = {}
        logger.info("PredictiveMonitor initialized")

    def update_forecasts(self) -> Dict[str, Forecast]:
        """
        Update forecasts for all monitored metrics.

        Returns:
            Dictionary mapping metric name to forecast
        """
        forecasts = {}

        for metric_name, query in self.MONITORED_METRICS.items():
            try:
                # Fetch 30 days of history
                history = self.engine.fetch_metric_history(query, days=30)

                if not history:
                    logger.warning(f"No history available for {metric_name}")
                    continue

                # Generate 24-hour forecast
                forecast = self.engine.forecast_metric(
                    metric_name, history, horizon_hours=24
                )

                if forecast:
                    forecasts[metric_name] = forecast
                    self._forecasts_cache[metric_name] = forecast
                    self._last_update[metric_name] = datetime.utcnow()

            except Exception as e:
                logger.error(
                    f"Error updating forecast for {metric_name}: {e}", exc_info=True
                )

        logger.info(f"Updated forecasts for {len(forecasts)} metrics")
        return forecasts

    def check_slo_breach_predictions(self) -> List[Dict]:
        """
        Check if any forecasts predict SLO breaches within 2 hours.

        Returns:
            List of predicted breach alerts
        """
        alerts = []
        breach_window = timedelta(hours=2)
        now = datetime.utcnow()

        # SLO thresholds
        thresholds = {
            "availability": 0.995,  # 99.5%
            "latency_p95": 1.0,  # 1 second
            "error_rate": 0.05,  # 5%
        }

        for metric_name, threshold in thresholds.items():
            if metric_name not in self._forecasts_cache:
                continue

            forecast = self._forecasts_cache[metric_name]

            # Check predictions within 2-hour window
            for pred_time, pred_value, _lower, _upper in forecast.predictions:
                if pred_time <= now or pred_time > now + breach_window:
                    continue

                # Check if predicted value breaches SLO
                is_breach = False
                if metric_name == "availability" and pred_value < threshold:
                    is_breach = True
                elif (
                    metric_name in ["latency_p95", "error_rate"]
                    and pred_value > threshold
                ):
                    is_breach = True

                if is_breach:
                    alerts.append(
                        {
                            "metric": metric_name,
                            "predicted_breach_time": pred_time.isoformat(),
                            "predicted_value": float(f"{pred_value:.3f}"),
                            "threshold": threshold,
                            "minutes_until_breach": int(
                                (pred_time - now).total_seconds() / 60
                            ),
                            "confidence": forecast.confidence,
                            "recommendation": f"Take preventive action now to avoid SLO breach in {int((pred_time - now).total_seconds() / 60)} minutes",
                        }
                    )

                    slo_breach_predicted.labels(sli=metric_name).inc()
                    logger.warning(
                        f"Predicted SLO breach for {metric_name} at {pred_time}"
                    )

        return alerts

    def detect_all_anomalies(self, days: int = 7) -> Dict[str, List[Anomaly]]:
        """
        Detect anomalies across all monitored metrics.

        Args:
            days: Number of days to analyze

        Returns:
            Dictionary mapping metric name to list of anomalies
        """
        all_anomalies = {}

        for metric_name, query in self.MONITORED_METRICS.items():
            try:
                history = self.engine.fetch_metric_history(query, days=days)

                if not history:
                    continue

                anomalies = self.engine.detect_anomalies(
                    metric_name, history, window_size=100
                )

                if anomalies:
                    all_anomalies[metric_name] = anomalies
                    logger.info(f"Found {len(anomalies)} anomalies for {metric_name}")

            except Exception as e:
                logger.error(
                    f"Error detecting anomalies for {metric_name}: {e}", exc_info=True
                )

        return all_anomalies

    def get_forecast(self, metric_name: str) -> Optional[Forecast]:
        """Get cached forecast for a metric."""
        return self._forecasts_cache.get(metric_name)

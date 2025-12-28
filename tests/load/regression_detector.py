#!/usr/bin/env python3
"""
Performance Regression Detector for QEO Load Tests

Analyzes load test results (from K6, Locust, or benchmark runs) and compares
against baseline metrics to detect performance regressions.

Usage:
    # Establish baseline from current run
    python regression_detector.py --establish-baseline --source k6 --input summary.json

    # Check for regressions against baseline
    python regression_detector.py --check --source k6 --input summary.json

    # Compare two specific runs
    python regression_detector.py --compare --baseline run1.json --current run2.json

    # Generate regression report
    python regression_detector.py --check --source locust --input stats.json --report-html report.html

Features:
    - Multi-source support (K6, Locust, custom benchmarks)
    - Statistical analysis (mean, p95, p99, standard deviation)
    - Configurable thresholds per metric
    - HTML and JSON report generation
    - CI/CD integration ready
"""

import argparse
import json
import statistics
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class MetricThreshold:
    """Threshold configuration for a metric"""

    warning_percent: float = 10.0  # Warn if metric degrades by this percentage
    critical_percent: float = 25.0  # Fail if metric degrades by this percentage
    improvement_percent: float = -5.0  # Note improvements


@dataclass
class Metric:
    """Performance metric"""

    name: str
    value: float
    unit: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RegressionResult:
    """Result of regression analysis"""

    metric_name: str
    baseline_value: float
    current_value: float
    delta_percent: float
    status: str  # "pass", "warning", "critical", "improved"
    message: str
    threshold: MetricThreshold = field(default_factory=MetricThreshold)


class BaselineStore:
    """Manages baseline metric storage and retrieval"""

    def __init__(self, baseline_file: Path):
        self.baseline_file = baseline_file

    def save(self, metrics: Dict[str, Metric], metadata: Dict[str, Any]):
        """Save baseline metrics"""
        data = {
            "timestamp": datetime.utcnow().isoformat(),
            "metadata": metadata,
            "metrics": {
                name: {
                    "value": metric.value,
                    "unit": metric.unit,
                    "metadata": metric.metadata,
                }
                for name, metric in metrics.items()
            },
        }

        self.baseline_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.baseline_file, "w") as f:
            json.dump(data, f, indent=2)

        print(f"✓ Baseline saved to {self.baseline_file}")

    def load(self) -> Optional[Dict[str, Metric]]:
        """Load baseline metrics"""
        if not self.baseline_file.exists():
            return None

        with open(self.baseline_file) as f:
            data = json.load(f)

        metrics = {}
        for name, metric_data in data["metrics"].items():
            metrics[name] = Metric(
                name=name,
                value=metric_data["value"],
                unit=metric_data.get("unit", ""),
                metadata=metric_data.get("metadata", {}),
            )

        return metrics


class K6Parser:
    """Parse K6 summary.json output"""

    @staticmethod
    def parse(input_file: Path) -> Dict[str, Metric]:
        """Parse K6 summary JSON"""
        with open(input_file) as f:
            data = json.load(f)

        metrics = {}

        # HTTP request duration metrics
        http_req_duration = data.get("metrics", {}).get("http_req_duration", {})
        if http_req_duration:
            values = http_req_duration.get("values", {})
            metrics["http_req_duration_avg"] = Metric(
                "http_req_duration_avg", values.get("avg", 0), "ms"
            )
            metrics["http_req_duration_p95"] = Metric(
                "http_req_duration_p95", values.get("p(95)", 0), "ms"
            )
            metrics["http_req_duration_p99"] = Metric(
                "http_req_duration_p99", values.get("p(99)", 0), "ms"
            )
            metrics["http_req_duration_max"] = Metric(
                "http_req_duration_max", values.get("max", 0), "ms"
            )

        # Request rate metrics
        http_reqs = data.get("metrics", {}).get("http_reqs", {})
        if http_reqs:
            metrics["http_reqs_rate"] = Metric(
                "http_reqs_rate", http_reqs.get("values", {}).get("rate", 0), "req/s"
            )
            metrics["http_reqs_count"] = Metric(
                "http_reqs_count",
                http_reqs.get("values", {}).get("count", 0),
                "requests",
            )

        # Error rate metrics
        http_req_failed = data.get("metrics", {}).get("http_req_failed", {})
        if http_req_failed:
            fail_rate = http_req_failed.get("values", {}).get("rate", 0)
            metrics["http_req_failed_rate"] = Metric(
                "http_req_failed_rate", fail_rate * 100, "%"
            )

        # Custom metrics (if present)
        for metric_name in ["query_latency", "cache_hits", "cache_misses"]:
            custom_metric = data.get("metrics", {}).get(metric_name, {})
            if custom_metric:
                values = custom_metric.get("values", {})
                if "avg" in values:
                    metrics[f"{metric_name}_avg"] = Metric(
                        f"{metric_name}_avg", values["avg"], "ms"
                    )
                if "p(95)" in values:
                    metrics[f"{metric_name}_p95"] = Metric(
                        f"{metric_name}_p95", values["p(95)"], "ms"
                    )

        # Cache hit rate calculation
        if "cache_hits" in metrics and "cache_misses" in metrics:
            hits = metrics["cache_hits_avg"].value
            misses = metrics["cache_misses_avg"].value
            total = hits + misses
            hit_rate = (hits / total * 100) if total > 0 else 0
            metrics["cache_hit_rate"] = Metric("cache_hit_rate", hit_rate, "%")

        return metrics


class LocustParser:
    """Parse Locust stats.json output"""

    @staticmethod
    def parse(input_file: Path) -> Dict[str, Metric]:
        """Parse Locust statistics JSON"""
        with open(input_file) as f:
            data = json.load(f)

        metrics = {}

        # Aggregate statistics
        stats = data.get("stats", [])
        if stats:
            # Get aggregated row (last entry usually)
            agg = next((s for s in stats if s.get("name") == "Aggregated"), stats[-1])

            metrics["response_time_avg"] = Metric(
                "response_time_avg", agg.get("avg_response_time", 0), "ms"
            )
            metrics["response_time_p95"] = Metric(
                "response_time_p95", agg.get("response_times", {}).get("0.95", 0), "ms"
            )
            metrics["response_time_p99"] = Metric(
                "response_time_p99", agg.get("response_times", {}).get("0.99", 0), "ms"
            )
            metrics["request_rate"] = Metric(
                "request_rate", agg.get("current_rps", 0), "req/s"
            )
            metrics["error_rate"] = Metric(
                "error_rate", agg.get("fail_ratio", 0) * 100, "%"
            )
            metrics["total_requests"] = Metric(
                "total_requests", agg.get("num_requests", 0), "requests"
            )

        return metrics


class BenchmarkParser:
    """Parse custom benchmark JSON output"""

    @staticmethod
    def parse(input_file: Path) -> Dict[str, Metric]:
        """Parse custom benchmark JSON"""
        with open(input_file) as f:
            data = json.load(f)

        metrics = {}

        # Extract metrics from benchmark results
        for scenario_name, scenario_data in data.get("scenarios", {}).items():
            # Query execution times
            exec_times = scenario_data.get("execution_times_ms", [])
            if exec_times:
                metrics[f"{scenario_name}_avg"] = Metric(
                    f"{scenario_name}_avg", statistics.mean(exec_times), "ms"
                )
                metrics[f"{scenario_name}_p95"] = Metric(
                    f"{scenario_name}_p95",
                    K6Parser._percentile(exec_times, 0.95),
                    "ms",
                )
                metrics[f"{scenario_name}_p99"] = Metric(
                    f"{scenario_name}_p99",
                    K6Parser._percentile(exec_times, 0.99),
                    "ms",
                )

            # Other metrics
            for key, value in scenario_data.items():
                if isinstance(value, (int, float)) and key not in [
                    "execution_times_ms"
                ]:
                    metrics[f"{scenario_name}_{key}"] = Metric(
                        f"{scenario_name}_{key}", value, ""
                    )

        return metrics

    @staticmethod
    def _percentile(data: List[float], percentile: float) -> float:
        """Calculate percentile"""
        if not data:
            return 0.0
        sorted_data = sorted(data)
        index = int(len(sorted_data) * percentile)
        return sorted_data[min(index, len(sorted_data) - 1)]


class RegressionDetector:
    """Main regression detection logic"""

    def __init__(self, thresholds: Optional[Dict[str, MetricThreshold]] = None):
        self.thresholds = thresholds or {}
        self.default_threshold = MetricThreshold()

    def compare(
        self, baseline: Dict[str, Metric], current: Dict[str, Metric]
    ) -> List[RegressionResult]:
        """Compare current metrics against baseline"""
        results = []

        for metric_name in sorted(set(baseline.keys()) | set(current.keys())):
            baseline_metric = baseline.get(metric_name)
            current_metric = current.get(metric_name)

            if baseline_metric is None:
                # New metric in current run
                results.append(
                    RegressionResult(
                        metric_name=metric_name,
                        baseline_value=0,
                        current_value=current_metric.value,
                        delta_percent=0,
                        status="new",
                        message=f"New metric: {current_metric.value:.2f} {current_metric.unit}",
                    )
                )
                continue

            if current_metric is None:
                # Metric missing in current run
                results.append(
                    RegressionResult(
                        metric_name=metric_name,
                        baseline_value=baseline_metric.value,
                        current_value=0,
                        delta_percent=0,
                        status="missing",
                        message="Metric missing in current run",
                    )
                )
                continue

            # Calculate delta percentage
            delta_percent = (
                ((current_metric.value - baseline_metric.value) / baseline_metric.value)
                * 100
                if baseline_metric.value != 0
                else 0
            )

            # Get threshold for this metric
            threshold = self.thresholds.get(metric_name, self.default_threshold)

            # Determine status
            status, message = self._evaluate_status(
                metric_name,
                baseline_metric.value,
                current_metric.value,
                delta_percent,
                threshold,
                current_metric.unit,
            )

            results.append(
                RegressionResult(
                    metric_name=metric_name,
                    baseline_value=baseline_metric.value,
                    current_value=current_metric.value,
                    delta_percent=delta_percent,
                    status=status,
                    message=message,
                    threshold=threshold,
                )
            )

        return results

    def _evaluate_status(
        self,
        metric_name: str,
        baseline_value: float,
        current_value: float,
        delta_percent: float,
        threshold: MetricThreshold,
        unit: str,
    ) -> Tuple[str, str]:
        """Evaluate regression status"""
        # Determine if metric should be inverted (e.g., error rate)
        invert = any(
            term in metric_name.lower()
            for term in ["error", "fail", "latency", "duration", "time"]
        )

        # Normalize delta for evaluation
        eval_delta = delta_percent if not invert else -delta_percent

        if eval_delta <= threshold.improvement_percent:
            return (
                "improved",
                f"✓ Improved by {abs(delta_percent):.1f}%: {baseline_value:.2f} → {current_value:.2f} {unit}",
            )
        elif eval_delta >= threshold.critical_percent:
            return (
                "critical",
                f"✗ CRITICAL regression: {abs(delta_percent):.1f}% worse: {baseline_value:.2f} → {current_value:.2f} {unit}",
            )
        elif eval_delta >= threshold.warning_percent:
            return (
                "warning",
                f"⚠ WARNING: {abs(delta_percent):.1f}% degradation: {baseline_value:.2f} → {current_value:.2f} {unit}",
            )
        else:
            return (
                "pass",
                f"✓ Within threshold: {baseline_value:.2f} → {current_value:.2f} {unit} ({delta_percent:+.1f}%)",
            )


class ReportGenerator:
    """Generate regression reports"""

    @staticmethod
    def generate_console(results: List[RegressionResult]):
        """Print console report"""
        print("\n" + "=" * 80)
        print("PERFORMANCE REGRESSION REPORT")
        print("=" * 80)

        status_counts = {"pass": 0, "warning": 0, "critical": 0, "improved": 0}

        for result in results:
            if result.status in status_counts:
                status_counts[result.status] += 1

            print(f"\n{result.message}")

        print("\n" + "=" * 80)
        print("SUMMARY")
        print("=" * 80)
        print(f"Total metrics: {len(results)}")
        print(f"✓ Passed: {status_counts['pass']}")
        print(f"✓ Improved: {status_counts['improved']}")
        print(f"⚠ Warnings: {status_counts['warning']}")
        print(f"✗ Critical: {status_counts['critical']}")
        print("=" * 80)

        # Return exit code
        if status_counts["critical"] > 0:
            return 2  # Critical regressions
        elif status_counts["warning"] > 0:
            return 1  # Warnings only
        else:
            return 0  # All pass

    @staticmethod
    def generate_json(results: List[RegressionResult], output_file: Path):
        """Generate JSON report"""
        data = {
            "timestamp": datetime.utcnow().isoformat(),
            "summary": {
                "total": len(results),
                "passed": sum(1 for r in results if r.status == "pass"),
                "warnings": sum(1 for r in results if r.status == "warning"),
                "critical": sum(1 for r in results if r.status == "critical"),
                "improved": sum(1 for r in results if r.status == "improved"),
            },
            "results": [
                {
                    "metric": r.metric_name,
                    "baseline": r.baseline_value,
                    "current": r.current_value,
                    "delta_percent": r.delta_percent,
                    "status": r.status,
                    "message": r.message,
                }
                for r in results
            ],
        }

        with open(output_file, "w") as f:
            json.dump(data, f, indent=2)

        print(f"✓ JSON report saved to {output_file}")

    @staticmethod
    def generate_html(results: List[RegressionResult], output_file: Path):
        """Generate HTML report"""
        status_counts = {
            "pass": sum(1 for r in results if r.status == "pass"),
            "warning": sum(1 for r in results if r.status == "warning"),
            "critical": sum(1 for r in results if r.status == "critical"),
            "improved": sum(1 for r in results if r.status == "improved"),
        }

        html = f"""
<!DOCTYPE html>
<html>
<head>
    <title>Performance Regression Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 20px; box-shadow: 0 0 10px rgba(0,0,0,0.1); }}
        h1 {{ color: #333; border-bottom: 3px solid #4CAF50; padding-bottom: 10px; }}
        .summary {{ display: flex; gap: 20px; margin: 20px 0; }}
        .stat {{ flex: 1; padding: 20px; text-align: center; border-radius: 5px; }}
        .stat h3 {{ margin: 0; font-size: 2em; }}
        .stat p {{ margin: 5px 0 0 0; color: #666; }}
        .stat.pass {{ background: #e8f5e9; color: #2e7d32; }}
        .stat.improved {{ background: #e3f2fd; color: #1565c0; }}
        .stat.warning {{ background: #fff3e0; color: #e65100; }}
        .stat.critical {{ background: #ffebee; color: #c62828; }}
        table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
        th {{ background: #4CAF50; color: white; padding: 12px; text-align: left; }}
        td {{ padding: 10px; border-bottom: 1px solid #ddd; }}
        tr:hover {{ background: #f5f5f5; }}
        .status {{ padding: 5px 10px; border-radius: 3px; font-weight: bold; display: inline-block; }}
        .status.pass {{ background: #e8f5e9; color: #2e7d32; }}
        .status.improved {{ background: #e3f2fd; color: #1565c0; }}
        .status.warning {{ background: #fff3e0; color: #e65100; }}
        .status.critical {{ background: #ffebee; color: #c62828; }}
        .delta.positive {{ color: #c62828; }}
        .delta.negative {{ color: #2e7d32; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Performance Regression Report</h1>
        <p>Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}</p>

        <div class="summary">
            <div class="stat pass">
                <h3>{status_counts['pass']}</h3>
                <p>Passed</p>
            </div>
            <div class="stat improved">
                <h3>{status_counts['improved']}</h3>
                <p>Improved</p>
            </div>
            <div class="stat warning">
                <h3>{status_counts['warning']}</h3>
                <p>Warnings</p>
            </div>
            <div class="stat critical">
                <h3>{status_counts['critical']}</h3>
                <p>Critical</p>
            </div>
        </div>

        <h2>Detailed Results</h2>
        <table>
            <thead>
                <tr>
                    <th>Metric</th>
                    <th>Baseline</th>
                    <th>Current</th>
                    <th>Delta</th>
                    <th>Status</th>
                </tr>
            </thead>
            <tbody>
"""

        for result in results:
            delta_class = (
                "negative"
                if result.delta_percent < 0
                else "positive" if result.delta_percent > 0 else ""
            )
            html += f"""
                <tr>
                    <td><strong>{result.metric_name}</strong></td>
                    <td>{result.baseline_value:.2f}</td>
                    <td>{result.current_value:.2f}</td>
                    <td class="delta {delta_class}">{result.delta_percent:+.1f}%</td>
                    <td><span class="status {result.status}">{result.status.upper()}</span></td>
                </tr>
"""

        html += """
            </tbody>
        </table>
    </div>
</body>
</html>
"""

        with open(output_file, "w") as f:
            f.write(html)

        print(f"✓ HTML report saved to {output_file}")


def main():
    parser = argparse.ArgumentParser(
        description="Performance regression detector for QEO load tests"
    )

    # Operation mode
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument(
        "--establish-baseline", action="store_true", help="Establish new baseline"
    )
    mode_group.add_argument(
        "--check", action="store_true", help="Check for regressions against baseline"
    )
    mode_group.add_argument(
        "--compare", action="store_true", help="Compare two specific runs"
    )

    # Input source
    parser.add_argument(
        "--source",
        choices=["k6", "locust", "benchmark"],
        default="k6",
        help="Load test source",
    )
    parser.add_argument("--input", type=Path, help="Input file (summary.json, etc.)")
    parser.add_argument("--baseline", type=Path, help="Baseline file (for --compare)")
    parser.add_argument("--current", type=Path, help="Current run file (for --compare)")

    # Output options
    parser.add_argument(
        "--baseline-file",
        type=Path,
        default=Path("tests/load/baseline.json"),
        help="Baseline storage file",
    )
    parser.add_argument(
        "--report-json", type=Path, help="Generate JSON report to this file"
    )
    parser.add_argument(
        "--report-html", type=Path, help="Generate HTML report to this file"
    )

    # Threshold configuration
    parser.add_argument(
        "--warning-threshold",
        type=float,
        default=10.0,
        help="Warning threshold percentage",
    )
    parser.add_argument(
        "--critical-threshold",
        type=float,
        default=25.0,
        help="Critical threshold percentage",
    )

    args = parser.parse_args()

    # Select parser
    parsers = {
        "k6": K6Parser,
        "locust": LocustParser,
        "benchmark": BenchmarkParser,
    }
    parser_cls = parsers[args.source]

    # Configure thresholds
    default_threshold = MetricThreshold(
        warning_percent=args.warning_threshold,
        critical_percent=args.critical_threshold,
    )

    baseline_store = BaselineStore(args.baseline_file)
    detector = RegressionDetector(thresholds={})
    detector.default_threshold = default_threshold

    if args.establish_baseline:
        if not args.input:
            print("Error: --input required for --establish-baseline", file=sys.stderr)
            sys.exit(1)

        metrics = parser_cls.parse(args.input)
        baseline_store.save(metrics, {"source": args.source})
        print(f"✓ Established baseline with {len(metrics)} metrics")
        sys.exit(0)

    elif args.check:
        if not args.input:
            print("Error: --input required for --check", file=sys.stderr)
            sys.exit(1)

        baseline_metrics = baseline_store.load()
        if not baseline_metrics:
            print(f"Error: No baseline found at {args.baseline_file}", file=sys.stderr)
            print("Run with --establish-baseline first", file=sys.stderr)
            sys.exit(1)

        current_metrics = parser_cls.parse(args.input)
        results = detector.compare(baseline_metrics, current_metrics)

        # Generate reports
        exit_code = ReportGenerator.generate_console(results)

        if args.report_json:
            ReportGenerator.generate_json(results, args.report_json)

        if args.report_html:
            ReportGenerator.generate_html(results, args.report_html)

        sys.exit(exit_code)

    elif args.compare:
        if not args.baseline or not args.current:
            print(
                "Error: --baseline and --current required for --compare",
                file=sys.stderr,
            )
            sys.exit(1)

        baseline_metrics = parser_cls.parse(args.baseline)
        current_metrics = parser_cls.parse(args.current)
        results = detector.compare(baseline_metrics, current_metrics)

        exit_code = ReportGenerator.generate_console(results)

        if args.report_json:
            ReportGenerator.generate_json(results, args.report_json)

        if args.report_html:
            ReportGenerator.generate_html(results, args.report_html)

        sys.exit(exit_code)


if __name__ == "__main__":
    main()

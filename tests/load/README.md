# QEO Load Testing Suite

Comprehensive load testing and chaos engineering suite for the QEO API.

## Overview

This directory contains tools for:
- **Load Testing**: K6 and Locust-based performance testing
- **Chaos Engineering**: LitmusChaos experiments for resilience testing
- **Regression Detection**: Automated performance regression analysis

## Prerequisites

### For K6 Load Tests
```bash
# Install K6
# macOS
brew install k6

# Windows (Chocolatey)
choco install k6

# Linux
sudo apt-key adv --keyserver hkp://keyserver.ubuntu.com:80 --recv-keys C5AD17C747E3415A3642D57D77C6C491D6AC1D00
echo "deb https://dl.k6.io/deb stable main" | sudo tee /etc/apt/sources.list.d/k6.list
sudo apt-get update
sudo apt-get install k6
```

### For Locust Load Tests
```bash
# Install Locust
pip install locust

# Or install with QEO dev dependencies
pip install -e ".[dev]"
```

### For Chaos Engineering
```bash
# Install LitmusChaos operator (requires Kubernetes cluster)
kubectl apply -f https://litmuschaos.github.io/litmus/litmus-operator-v3.0.0.yaml

# Install chaos experiments
kubectl apply -f https://hub.litmuschaos.io/api/chaos/master?file=charts/generic/experiments.yaml

# Verify installation
kubectl get pods -n litmus
```

## K6 Load Tests

### Running Tests

**Run all scenarios sequentially:**
```bash
k6 run k6-load-test.js
```

**Run specific scenario:**
```bash
# Baseline test (100 RPS for 30 minutes)
k6 run --scenario=baseline k6-load-test.js

# Stress test (ramp to 1000 RPS)
k6 run --scenario=stress k6-load-test.js

# Spike test (sudden 500 RPS surge)
k6 run --scenario=spike k6-load-test.js

# Soak test (200 RPS for 2 hours)
k6 run --scenario=soak k6-load-test.js
```

**Run with custom target:**
```bash
BASE_URL=http://staging.example.com k6 run k6-load-test.js
```

**Run with authentication:**
```bash
API_TOKEN=your_token_here k6 run k6-load-test.js
```

**Export results to InfluxDB:**
```bash
k6 run --out influxdb=http://localhost:8086/k6 k6-load-test.js
```

**Generate summary output:**
```bash
k6 run --summary-export=summary.json k6-load-test.js
```

### K6 Scenarios

| Scenario | Type | Duration | Target | Purpose |
|----------|------|----------|--------|---------|
| **Baseline** | Constant | 30m | 100 RPS | Performance baseline |
| **Stress** | Ramping | 16m | 0-1000 RPS | Find breaking point |
| **Spike** | Ramping | 5.5m | 50-500 RPS | Test spike handling |
| **Soak** | Constant | 2h | 200 RPS | Memory leak detection |

### K6 Metrics

The K6 tests track:
- **HTTP request duration** (P50, P95, P99)
- **Request rate** (RPS)
- **Error rate** (custom metric)
- **Query latency** (custom metric)
- **Cache hits/misses** (custom metrics)

### K6 Thresholds

Tests will fail if:
- P95 latency > 500ms (baseline: 300ms)
- P99 latency > 1000ms
- HTTP error rate > 1%
- Custom error rate > 5%

## Locust Load Tests

### Running Tests

**Interactive mode (Web UI):**
```bash
# Start Locust web server
locust -f locustfile.py --host=http://localhost:8000

# Open browser to http://localhost:8089
# Configure users and spawn rate in UI
```

**Headless mode:**
```bash
# Run with 100 users ramping up over 10 seconds for 10 minutes
locust -f locustfile.py --host=http://localhost:8000 \
    --users 100 --spawn-rate 10 --run-time 10m --headless
```

**Run specific user type:**
```bash
# Run only data analyst users
locust -f locustfile.py --host=http://localhost:8000 \
    --tags data-analyst --headless --users 50 --spawn-rate 5 --run-time 5m

# Run only backend developer users
locust -f locustfile.py --host=http://localhost:8000 \
    --tags backend-dev --headless --users 30 --spawn-rate 3 --run-time 5m

# Run only DBA users
locust -f locustfile.py --host=http://localhost:8000 \
    --tags dba --headless --users 10 --spawn-rate 1 --run-time 5m
```

**Distributed load generation:**
```bash
# Start master
locust -f locustfile.py --master --host=http://localhost:8000

# Start workers (on same or different machines)
locust -f locustfile.py --worker --master-host=localhost
locust -f locustfile.py --worker --master-host=localhost
locust -f locustfile.py --worker --master-host=localhost
```

**Export results:**
```bash
# Generate CSV reports
locust -f locustfile.py --host=http://localhost:8000 \
    --users 100 --spawn-rate 10 --run-time 5m --headless \
    --csv=results

# This generates:
#   - results_stats.csv
#   - results_stats_history.csv
#   - results_failures.csv
```

### Locust User Types

The test suite simulates different user personas:

#### 1. Data Analyst User (weight: 3)
- **Behavior**: Iterative query analysis and optimization
- **Wait time**: 2-5 seconds between actions
- **Tasks**:
  - Lint → Explain → Optimize → Re-explain with improvements
  - Batch workload analysis (5 queries)

#### 2. Backend Developer User (weight: 2)
- **Behavior**: Optimizing specific application queries
- **Wait time**: 1-3 seconds between actions
- **Tasks**:
  - EXPLAIN ANALYZE for performance checks
  - Optimize with what-if analysis
  - Explore schema for query design

#### 3. DB Administrator User (weight: 1)
- **Behavior**: Workload analysis and monitoring
- **Wait time**: 3-8 seconds between actions
- **Tasks**:
  - Comprehensive workload analysis (10 queries)
  - Audit expensive queries

#### 4. Casual User (weight: 4)
- **Behavior**: Basic operations
- **Wait time**: 5-15 seconds between actions
- **Tasks**:
  - Simple lint, explain, optimize operations
  - Health checks

#### 5. Stress Test User (weight: 10)
- **Behavior**: Rapid-fire requests
- **Wait time**: 0.1-0.5 seconds
- **Use case**: Stress testing

#### 6. Soak Test User (weight: 5)
- **Behavior**: Complete workflows
- **Wait time**: 10-30 seconds
- **Use case**: Long-running stability tests

### Locust Metrics

Locust automatically tracks:
- Response time (avg, median, P95, P99)
- Request rate (RPS)
- Error rate
- Number of users
- Custom statistics per endpoint

## Chaos Engineering

### Running Chaos Experiments

**Deploy chaos experiments:**
```bash
# Apply all experiments
kubectl apply -f chaos-experiments.yaml

# Check running experiments
kubectl get chaosengine -n qeo

# View experiment logs
kubectl logs -f <chaos-runner-pod> -n qeo
```

**Run specific experiment:**
```bash
# Extract specific experiment from YAML and apply
kubectl apply -f - <<EOF
<paste experiment YAML>
EOF
```

**Monitor experiment:**
```bash
# Check ChaosEngine status
kubectl describe chaosengine qeo-pod-delete -n qeo

# Check ChaosResult
kubectl get chaosresult -n qeo

# View detailed results
kubectl describe chaosresult <result-name> -n qeo
```

**Stop experiment:**
```bash
# Set engineState to stop
kubectl patch chaosengine qeo-pod-delete -n qeo \
    --type=merge -p '{"spec":{"engineState":"stop"}}'

# Or delete the ChaosEngine
kubectl delete chaosengine qeo-pod-delete -n qeo
```

### Available Chaos Experiments

| Experiment | Type | Duration | Description |
|------------|------|----------|-------------|
| **pod-delete** | Availability | 60s | Deletes 50% of QEO pods to test recovery |
| **network-latency** | Performance | 120s | Adds 2000ms latency to database connections |
| **cpu-stress** | Resource | 180s | Consumes 2 CPU cores at 100% |
| **memory-stress** | Resource | 180s | Consumes 500MB of memory |
| **db-pod-delete** | Database | 60s | Deletes PostgreSQL pod |
| **disk-fill** | Storage | 120s | Fills 80% of /tmp disk space |
| **network-partition** | Network | 90s | 100% packet loss to database |
| **container-kill** | Availability | 60s | Sends SIGKILL to containers |

### Chaos Probes

Each experiment includes probes to verify system behavior:
- **cmdProbe**: Execute commands to check system state
- **httpProbe**: HTTP health checks
- **k8sProbe**: Kubernetes resource checks
- **promProbe**: Prometheus metric checks

### Chaos Schedule

Automated chaos testing runs daily at 2 AM:
```yaml
spec:
  schedule:
    repeat:
      properties:
        minChaosInterval: 24h
```

To enable/disable:
```bash
# Disable scheduled chaos
kubectl delete chaosschedule qeo-chaos-schedule -n qeo

# Re-enable
kubectl apply -f chaos-experiments.yaml
```

## Performance Regression Detection

### Establishing Baseline

**From K6 results:**
```bash
# Run K6 test with summary export
k6 run --summary-export=summary.json k6-load-test.js

# Establish baseline
python regression_detector.py --establish-baseline --source k6 --input summary.json
```

**From Locust results:**
```bash
# Run Locust with stats export
locust -f locustfile.py --host=http://localhost:8000 \
    --users 100 --spawn-rate 10 --run-time 5m --headless \
    --json

# Establish baseline
python regression_detector.py --establish-baseline --source locust --input stats.json
```

### Checking for Regressions

```bash
# Run new test
k6 run --summary-export=summary-new.json k6-load-test.js

# Check for regressions
python regression_detector.py --check --source k6 --input summary-new.json

# With custom thresholds
python regression_detector.py --check --source k6 --input summary-new.json \
    --warning-threshold 15 --critical-threshold 30

# Generate reports
python regression_detector.py --check --source k6 --input summary-new.json \
    --report-json regression-report.json \
    --report-html regression-report.html
```

### Comparing Two Runs

```bash
# Compare two specific K6 runs
python regression_detector.py --compare \
    --source k6 \
    --baseline baseline-run.json \
    --current current-run.json \
    --report-html comparison.html
```

### CI/CD Integration

```bash
# In your CI pipeline
k6 run --summary-export=summary.json k6-load-test.js

# Check for regressions (exits with non-zero if regression detected)
python regression_detector.py --check --source k6 --input summary.json \
    --report-json regression-report.json

# Upload reports as artifacts
# Exit code: 0 = pass, 1 = warnings, 2 = critical regressions
```

### Regression Thresholds

Default thresholds:
- **Warning**: 10% degradation
- **Critical**: 25% degradation
- **Improvement**: -5% or better

Customize per metric by editing `regression_detector.py`:
```python
thresholds = {
    "http_req_duration_p95": MetricThreshold(
        warning_percent=5.0,
        critical_percent=15.0,
        improvement_percent=-3.0
    ),
    "cache_hit_rate": MetricThreshold(
        warning_percent=2.0,
        critical_percent=5.0,
    ),
}
```

## Example Workflows

### Complete Performance Test

```bash
#!/bin/bash
# Run comprehensive performance test

# 1. Start baseline test
echo "Running baseline test..."
k6 run --scenario=baseline --summary-export=baseline.json k6-load-test.js

# 2. Establish baseline
python regression_detector.py --establish-baseline --source k6 --input baseline.json

# 3. Run stress test
echo "Running stress test..."
k6 run --scenario=stress --summary-export=stress.json k6-load-test.js

# 4. Check for regressions
python regression_detector.py --check --source k6 --input stress.json \
    --report-html stress-regression.html

# 5. Run soak test
echo "Running soak test..."
k6 run --scenario=soak --summary-export=soak.json k6-load-test.js

# 6. Check for regressions
python regression_detector.py --check --source k6 --input soak.json \
    --report-html soak-regression.html
```

### Chaos + Load Testing

```bash
#!/bin/bash
# Run load test with concurrent chaos

# 1. Start load test in background
k6 run --scenario=stress k6-load-test.js &
K6_PID=$!

# 2. Wait for ramp-up
sleep 120

# 3. Apply chaos
kubectl apply -f chaos-experiments.yaml

# 4. Wait for chaos completion
sleep 180

# 5. Check K6 results
wait $K6_PID

# 6. Analyze chaos results
kubectl get chaosresult -n qeo
```

### Daily Performance Monitoring

```bash
#!/bin/bash
# Daily automated performance check

# 1. Run overnight soak test
k6 run --scenario=soak --summary-export=daily-$(date +%Y%m%d).json k6-load-test.js

# 2. Check for regressions
python regression_detector.py --check \
    --source k6 \
    --input daily-$(date +%Y%m%d).json \
    --report-html daily-report-$(date +%Y%m%d).html

# 3. Send report to Slack/email
if [ $? -ne 0 ]; then
    # Send alert on regression
    curl -X POST https://hooks.slack.com/services/YOUR/WEBHOOK/URL \
        -H 'Content-Type: application/json' \
        -d "{\"text\": \"Performance regression detected: $(date)\"}"
fi
```

## Interpreting Results

### K6 Results

**Good:**
- P95 < 500ms
- P99 < 1000ms
- Error rate < 1%
- Stable response times across duration

**Warning Signs:**
- P95 > 500ms
- Increasing memory usage over time
- Error rate 1-5%
- High variance in response times

**Critical:**
- P95 > 1000ms
- Error rate > 5%
- Timeouts or connection failures
- OOM kills during soak test

### Locust Results

**Good:**
- Linear scaling with user count
- Error rate < 1%
- Stable P95/P99 latencies
- No failures at target concurrency

**Warning Signs:**
- Non-linear scaling
- Error rate 1-5%
- Increasing latency with user count

**Critical:**
- Failed requests > 5%
- Timeouts or connection errors
- Server errors (5xx)

### Chaos Experiment Results

**Pass:**
- All probes succeed
- Service remains available
- Automatic recovery within SLA
- No data loss

**Fail:**
- Probes fail
- Service unavailable
- Manual intervention required
- Data corruption or loss

## Troubleshooting

### K6 Issues

**Problem**: Connection refused errors
```bash
# Check QEO API is running
curl http://localhost:8000/health

# Check network connectivity
ping localhost
```

**Problem**: Out of memory during test
```bash
# Reduce VUs or use distributed testing
k6 run --vus 50 --duration 5m k6-load-test.js
```

### Locust Issues

**Problem**: Locust can't find module
```bash
# Install dependencies
pip install locust

# Or use venv
python -m venv venv
source venv/bin/activate
pip install -r requirements-dev.txt
```

**Problem**: Too many open files
```bash
# Increase file descriptor limit (macOS/Linux)
ulimit -n 10000
```

### Chaos Experiment Issues

**Problem**: ChaosEngine stuck in "Running"
```bash
# Check chaos-runner logs
kubectl logs -n qeo -l chaosUID=<engine-uid>

# Force delete if needed
kubectl delete chaosengine <name> -n qeo --force --grace-period=0
```

**Problem**: Experiment didn't affect pods
```bash
# Check label selectors match
kubectl get pods -n qeo -l app=qeo

# Verify chaos-runner has permissions
kubectl get rolebinding qeo-chaos-rolebinding -n qeo -o yaml
```

## Best Practices

1. **Always establish baseline** before running regression checks
2. **Run soak tests overnight** to catch memory leaks
3. **Combine load + chaos tests** to verify resilience
4. **Monitor Prometheus metrics** during load tests
5. **Review regression reports** after each test
6. **Schedule regular chaos experiments** (daily/weekly)
7. **Test in staging first** before production load tests
8. **Use distributed load generation** for high RPS tests
9. **Archive test results** for historical comparison
10. **Document any threshold adjustments**

## References

- [K6 Documentation](https://k6.io/docs/)
- [Locust Documentation](https://docs.locust.io/)
- [LitmusChaos Documentation](https://litmuschaos.github.io/litmus/)
- [QEO API Documentation](../../docs/API.md)
- [QEO Production Deployment](../../docs/PRODUCTION_DEPLOYMENT.md)

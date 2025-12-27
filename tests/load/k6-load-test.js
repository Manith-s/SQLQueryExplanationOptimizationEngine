/**
 * K6 Load Testing Suite for QEO API
 *
 * Scenarios:
 * - Baseline: Constant load for performance baseline
 * - Stress: Ramp up to find breaking point
 * - Spike: Sudden traffic surge
 * - Soak: Extended load for memory leak detection
 *
 * Usage:
 *   k6 run --out influxdb=http://localhost:8086/k6 k6-load-test.js
 *   k6 run --scenario=baseline k6-load-test.js
 *   k6 run --scenario=stress k6-load-test.js
 */

import http from 'k6/http';
import { check, group, sleep } from 'k6';
import { Rate, Trend, Counter } from 'k6/metrics';
import { randomIntBetween, randomItem } from 'https://jslib.k6.io/k6-utils/1.2.0/index.js';

// Custom metrics
const errorRate = new Rate('errors');
const queryLatency = new Trend('query_latency');
const cacheHits = new Counter('cache_hits');
const cacheMisses = new Counter('cache_misses');

// Configuration
const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';
const API_TOKEN = __ENV.API_TOKEN || '';

// Test scenarios
export const options = {
  scenarios: {
    // Baseline: 100 RPS for 30 minutes
    baseline: {
      executor: 'constant-arrival-rate',
      duration: '30m',
      rate: 100,
      timeUnit: '1s',
      preAllocatedVUs: 50,
      maxVUs: 100,
      exec: 'baselineScenario',
      tags: { scenario: 'baseline' },
    },

    // Stress: Ramp from 0 to 1000 RPS over 10 minutes
    stress: {
      executor: 'ramping-arrival-rate',
      startRate: 0,
      timeUnit: '1s',
      preAllocatedVUs: 100,
      maxVUs: 500,
      exec: 'stressScenario',
      stages: [
        { duration: '2m', target: 100 },   // Warm-up
        { duration: '5m', target: 500 },   // Ramp up
        { duration: '2m', target: 1000 },  // Peak
        { duration: '5m', target: 1000 },  // Hold at peak
        { duration: '2m', target: 0 },     // Ramp down
      ],
      tags: { scenario: 'stress' },
    },

    // Spike: Sudden jump to 500 RPS
    spike: {
      executor: 'ramping-arrival-rate',
      startRate: 50,
      timeUnit: '1s',
      preAllocatedVUs: 50,
      maxVUs: 300,
      exec: 'spikeScenario',
      stages: [
        { duration: '1m', target: 50 },    // Normal load
        { duration: '30s', target: 500 },  // Spike
        { duration: '2m', target: 500 },   // Hold
        { duration: '1m', target: 50 },    // Recovery
        { duration: '1m', target: 50 },    // Normal
      ],
      tags: { scenario: 'spike' },
    },

    // Soak: 200 RPS for 2 hours (memory leak detection)
    soak: {
      executor: 'constant-arrival-rate',
      duration: '2h',
      rate: 200,
      timeUnit: '1s',
      preAllocatedVUs: 100,
      maxVUs: 200,
      exec: 'soakScenario',
      tags: { scenario: 'soak' },
    },
  },

  // Thresholds
  thresholds: {
    http_req_duration: ['p(95)<500', 'p(99)<1000'], // 95% < 500ms, 99% < 1s
    http_req_failed: ['rate<0.01'],                  // Error rate < 1%
    errors: ['rate<0.05'],                           // Custom error rate < 5%
    'http_req_duration{scenario:baseline}': ['p(95)<300'],
    'http_req_duration{scenario:stress}': ['p(95)<1000'],
  },
};

// Test data
const testQueries = [
  'SELECT * FROM users WHERE id = 42',
  'SELECT * FROM orders WHERE user_id = 123 ORDER BY created_at DESC LIMIT 10',
  'SELECT COUNT(*) FROM products WHERE category = \'electronics\'',
  'SELECT u.name, COUNT(o.id) FROM users u JOIN orders o ON u.id = o.user_id GROUP BY u.name',
  'SELECT * FROM sessions WHERE created_at > NOW() - INTERVAL \'1 day\'',
];

const testOptimizations = [
  {
    sql: 'SELECT * FROM users',
    expectedType: 'rewrite',
  },
  {
    sql: 'SELECT * FROM orders WHERE user_id = 42 ORDER BY created_at DESC',
    expectedType: 'index',
  },
];

// Helper functions
function setupHeaders() {
  const headers = {
    'Content-Type': 'application/json',
  };

  if (API_TOKEN) {
    headers['Authorization'] = `Bearer ${API_TOKEN}`;
  }

  return headers;
}

function checkResponse(response, expectedStatus = 200) {
  const checks = {
    'status is correct': (r) => r.status === expectedStatus,
    'response time < 2s': (r) => r.timings.duration < 2000,
    'response has body': (r) => r.body.length > 0,
  };

  const result = check(response, checks);
  errorRate.add(!result);

  return result;
}

// Baseline scenario: Normal operations
export function baselineScenario() {
  group('Health Check', () => {
    const response = http.get(`${BASE_URL}/health`, {
      headers: setupHeaders(),
    });

    checkResponse(response);
    sleep(0.5);
  });

  group('Explain Query', () => {
    const payload = JSON.stringify({
      sql: randomItem(testQueries),
      analyze: false,
    });

    const response = http.post(`${BASE_URL}/api/v1/explain`, payload, {
      headers: setupHeaders(),
    });

    checkResponse(response);
    queryLatency.add(response.timings.duration);
    sleep(randomIntBetween(1, 3));
  });

  group('Optimize Query', () => {
    const testCase = randomItem(testOptimizations);
    const payload = JSON.stringify({
      sql: testCase.sql,
      what_if: true,
    });

    const response = http.post(`${BASE_URL}/api/v1/optimize`, payload, {
      headers: setupHeaders(),
    });

    const success = checkResponse(response);

    if (success) {
      try {
        const data = JSON.parse(response.body);
        if (data.cached) {
          cacheHits.add(1);
        } else {
          cacheMisses.add(1);
        }
      } catch (e) {
        // Ignore JSON parse errors
      }
    }

    sleep(randomIntBetween(2, 5));
  });

  group('Cache Statistics', () => {
    const response = http.get(`${BASE_URL}/api/v1/cache/stats`, {
      headers: setupHeaders(),
    });

    checkResponse(response);
    sleep(1);
  });
}

// Stress scenario: High load testing
export function stressScenario() {
  const startTime = Date.now();

  group('Concurrent Optimizations', () => {
    const batch = http.batch([
      ['POST', `${BASE_URL}/api/v1/optimize`, JSON.stringify({ sql: testQueries[0] }), { headers: setupHeaders() }],
      ['POST', `${BASE_URL}/api/v1/optimize`, JSON.stringify({ sql: testQueries[1] }), { headers: setupHeaders() }],
      ['POST', `${BASE_URL}/api/v1/optimize`, JSON.stringify({ sql: testQueries[2] }), { headers: setupHeaders() }],
    ]);

    batch.forEach(response => {
      checkResponse(response);
      queryLatency.add(response.timings.duration);
    });
  });

  // Minimal sleep under stress
  sleep(0.1);
}

// Spike scenario: Sudden traffic surge
export function spikeScenario() {
  group('Quick Operations', () => {
    const response = http.get(`${BASE_URL}/health`, {
      headers: setupHeaders(),
    });

    checkResponse(response);
  });

  // No sleep to simulate spike
}

// Soak scenario: Extended load for memory leak detection
export function soakScenario() {
  baselineScenario();

  // Additional operations for comprehensive coverage
  group('Index Management', () => {
    const response = http.get(`${BASE_URL}/api/v1/index/health?schema=public`, {
      headers: setupHeaders(),
    });

    checkResponse(response);
    sleep(5);
  });

  group('Prefetch Candidates', () => {
    const response = http.get(`${BASE_URL}/api/v1/cache/prefetch/candidates?top_k=5`, {
      headers: setupHeaders(),
    });

    checkResponse(response);
    sleep(3);
  });
}

// Setup function (runs once)
export function setup() {
  console.log(`Starting load test against ${BASE_URL}`);
  console.log('Verifying API is reachable...');

  const response = http.get(`${BASE_URL}/health`);

  if (response.status !== 200) {
    throw new Error(`API is not healthy: ${response.status}`);
  }

  console.log('API is healthy, proceeding with tests');

  return {
    startTime: Date.now(),
  };
}

// Teardown function (runs once at end)
export function teardown(data) {
  console.log(`Test completed in ${(Date.now() - data.startTime) / 1000}s`);
  console.log('Generating summary report...');
}

// Custom summary handler
export function handleSummary(data) {
  return {
    'stdout': textSummary(data, { indent: ' ', enableColors: true }),
    'summary.json': JSON.stringify(data, null, 2),
    'summary.html': htmlReport(data),
  };
}

// Generate text summary
function textSummary(data, options) {
  const indent = options.indent || '';
  const enableColors = options.enableColors || false;

  let summary = '';

  summary += `${indent}Test Summary:\n`;
  summary += `${indent}  Scenario: ${data.root_group.name}\n`;
  summary += `${indent}  Duration: ${data.metrics.iteration_duration.values.avg.toFixed(2)}ms avg\n`;
  summary += `${indent}  Requests: ${data.metrics.http_reqs.values.count}\n`;
  summary += `${indent}  Errors: ${data.metrics.http_req_failed.values.rate.toFixed(2)}%\n`;
  summary += `${indent}  P95 Latency: ${data.metrics.http_req_duration.values['p(95)'].toFixed(2)}ms\n`;
  summary += `${indent}  P99 Latency: ${data.metrics.http_req_duration.values['p(99)'].toFixed(2)}ms\n`;

  return summary;
}

// Generate HTML report
function htmlReport(data) {
  return `
    <!DOCTYPE html>
    <html>
    <head>
      <title>K6 Load Test Report</title>
      <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        table { border-collapse: collapse; width: 100%; }
        th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
        th { background-color: #4CAF50; color: white; }
        .pass { color: green; }
        .fail { color: red; }
      </style>
    </head>
    <body>
      <h1>K6 Load Test Report</h1>
      <h2>Summary</h2>
      <table>
        <tr><th>Metric</th><th>Value</th></tr>
        <tr><td>Total Requests</td><td>${data.metrics.http_reqs.values.count}</td></tr>
        <tr><td>Error Rate</td><td>${(data.metrics.http_req_failed.values.rate * 100).toFixed(2)}%</td></tr>
        <tr><td>P95 Latency</td><td>${data.metrics.http_req_duration.values['p(95)'].toFixed(2)}ms</td></tr>
        <tr><td>P99 Latency</td><td>${data.metrics.http_req_duration.values['p(99)'].toFixed(2)}ms</td></tr>
      </table>
    </body>
    </html>
  `;
}

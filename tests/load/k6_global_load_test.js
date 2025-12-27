/**
 * K6 Global Load Test
 *
 * Simulates 50,000 concurrent users from multiple geographic locations
 * testing all QEO endpoints with realistic query patterns.
 *
 * Usage:
 *   k6 run --vus 50000 --duration 10m tests/load/k6_global_load_test.js
 *
 * Requirements:
 *   - k6 (https://k6.io/docs/getting-started/installation/)
 *   - k6 cloud account for distributed testing (optional)
 */

import http from 'k6/http';
import { check, group, sleep } from 'k6';
import { Rate, Trend, Counter } from 'k6/metrics';

// Custom metrics
const errorRate = new Rate('errors');
const latencyTrend = new Trend('latency');
const requestsCounter = new Counter('requests');
const cacheHitRate = new Rate('cache_hits');

// Test configuration
export const options = {
  stages: [
    { duration: '2m', target: 5000 },   // Ramp up to 5k users
    { duration: '3m', target: 25000 },  // Ramp to 25k users
    { duration: '5m', target: 50000 },  // Ramp to 50k users
    { duration: '10m', target: 50000 }, // Sustained 50k users
    { duration: '2m', target: 0 },      // Ramp down
  ],
  thresholds: {
    'http_req_duration': ['p(95)<500', 'p(99)<1000'], // 95% < 500ms, 99% < 1s
    'http_req_failed': ['rate<0.01'],                 // <1% errors
    'errors': ['rate<0.01'],                          // <1% error rate
    'cache_hits': ['rate>0.80'],                      // >80% cache hit rate
  },
  // Distributed load from multiple regions
  ext: {
    loadimpact: {
      projectID: 3545561,
      name: "QEO Global Load Test",
      distribution: {
        'amazon:us:ashburn': { loadZone: 'amazon:us:ashburn', percent: 30 },
        'amazon:ie:dublin': { loadZone: 'amazon:ie:dublin', percent: 25 },
        'amazon:sg:singapore': { loadZone: 'amazon:sg:singapore', percent: 20 },
        'amazon:au:sydney': { loadZone: 'amazon:au:sydney', percent: 15 },
        'amazon:br:sao paulo': { loadZone: 'amazon:br:sao paulo', percent: 10 },
      }
    }
  }
};

// Test data - realistic SQL queries
const QUERIES = [
  // Simple queries (should be cached, fast)
  'SELECT * FROM users WHERE id = 1',
  'SELECT COUNT(*) FROM orders',
  'SELECT * FROM products LIMIT 10',

  // Medium complexity queries
  'SELECT u.id, u.name, COUNT(o.id) as order_count FROM users u LEFT JOIN orders o ON u.id = o.user_id GROUP BY u.id, u.name',
  'SELECT * FROM orders WHERE user_id = 42 ORDER BY created_at DESC LIMIT 50',
  'SELECT product_id, SUM(quantity) as total FROM order_items GROUP BY product_id ORDER BY total DESC LIMIT 20',

  // Complex queries (should trigger optimizer)
  'SELECT u.*, o.* FROM users u JOIN orders o ON u.id = o.user_id WHERE o.status = \'pending\' AND o.total > 100',
  'SELECT DATE(created_at) as date, COUNT(*) as count, AVG(total) as avg_total FROM orders WHERE created_at > NOW() - INTERVAL \'30 days\' GROUP BY DATE(created_at) ORDER BY date',
  'WITH monthly_stats AS (SELECT user_id, DATE_TRUNC(\'month\', created_at) as month, SUM(total) as total FROM orders GROUP BY user_id, month) SELECT * FROM monthly_stats WHERE total > 1000',
];

// API endpoints to test
const BASE_URL = __ENV.API_URL || 'https://api.qeo.example.com';

/**
 * Main test scenario
 */
export default function() {
  const scenario = Math.random();

  if (scenario < 0.4) {
    // 40% - Lint endpoint (simple, fast)
    testLintEndpoint();
  } else if (scenario < 0.7) {
    // 30% - Explain endpoint
    testExplainEndpoint();
  } else if (scenario < 0.95) {
    // 25% - Optimize endpoint
    testOptimizeEndpoint();
  } else {
    // 5% - Workload endpoint (most expensive)
    testWorkloadEndpoint();
  }

  // Think time (realistic user behavior)
  sleep(Math.random() * 3 + 1); // 1-4 seconds
}

/**
 * Test /lint endpoint
 */
function testLintEndpoint() {
  group('Lint Query', () => {
    const query = QUERIES[Math.floor(Math.random() * QUERIES.length)];

    const payload = JSON.stringify({
      sql: query
    });

    const params = {
      headers: {
        'Content-Type': 'application/json',
        'X-User-ID': `user_${__VU}`,
      },
    };

    const response = http.post(`${BASE_URL}/api/v1/lint`, payload, params);

    requestsCounter.add(1);

    const success = check(response, {
      'lint: status 200': (r) => r.status === 200,
      'lint: has errors field': (r) => r.json().hasOwnProperty('errors'),
      'lint: response time < 200ms': (r) => r.timings.duration < 200,
    });

    if (!success) {
      errorRate.add(1);
    } else {
      errorRate.add(0);
    }

    latencyTrend.add(response.timings.duration);

    // Check cache header
    if (response.headers['CF-Cache-Status'] === 'HIT') {
      cacheHitRate.add(1);
    } else {
      cacheHitRate.add(0);
    }
  });
}

/**
 * Test /explain endpoint
 */
function testExplainEndpoint() {
  group('Explain Query', () => {
    const query = QUERIES[Math.floor(Math.random() * QUERIES.length)];

    const payload = JSON.stringify({
      sql: query,
      analyze: false, // Use EXPLAIN only, not EXPLAIN ANALYZE
    });

    const params = {
      headers: {
        'Content-Type': 'application/json',
        'X-User-ID': `user_${__VU}`,
      },
    };

    const response = http.post(`${BASE_URL}/api/v1/explain`, payload, params);

    requestsCounter.add(1);

    const success = check(response, {
      'explain: status 200': (r) => r.status === 200,
      'explain: has plan': (r) => r.json().hasOwnProperty('plan'),
      'explain: response time < 500ms': (r) => r.timings.duration < 500,
    });

    if (!success) {
      errorRate.add(1);
    } else {
      errorRate.add(0);
    }

    latencyTrend.add(response.timings.duration);

    if (response.headers['CF-Cache-Status'] === 'HIT') {
      cacheHitRate.add(1);
    } else {
      cacheHitRate.add(0);
    }
  });
}

/**
 * Test /optimize endpoint
 */
function testOptimizeEndpoint() {
  group('Optimize Query', () => {
    const query = QUERIES[Math.floor(Math.random() * QUERIES.length)];

    const payload = JSON.stringify({
      sql: query,
      analyze: false,
      what_if: true,  // Enable HypoPG cost-based ranking
      top_k: 5,
    });

    const params = {
      headers: {
        'Content-Type': 'application/json',
        'X-User-ID': `user_${__VU}`,
      },
    };

    const response = http.post(`${BASE_URL}/api/v1/optimize`, payload, params);

    requestsCounter.add(1);

    const success = check(response, {
      'optimize: status 200': (r) => r.status === 200,
      'optimize: has suggestions': (r) => r.json().hasOwnProperty('suggestions'),
      'optimize: response time < 1s': (r) => r.timings.duration < 1000,
    });

    if (!success) {
      errorRate.add(1);
    } else {
      errorRate.add(0);
    }

    latencyTrend.add(response.timings.duration);

    if (response.headers['CF-Cache-Status'] === 'HIT') {
      cacheHitRate.add(1);
    } else {
      cacheHitRate.add(0);
    }
  });
}

/**
 * Test /workload endpoint (most resource intensive)
 */
function testWorkloadEndpoint() {
  group('Workload Analysis', () => {
    // Multiple queries for workload analysis
    const queries = [];
    for (let i = 0; i < 5; i++) {
      queries.push(QUERIES[Math.floor(Math.random() * QUERIES.length)]);
    }

    const payload = JSON.stringify({
      sqls: queries,
      top_k: 10,
      what_if: false,  // Disable what-if for workload to reduce load
    });

    const params = {
      headers: {
        'Content-Type': 'application/json',
        'X-User-ID': `user_${__VU}`,
      },
    };

    const response = http.post(`${BASE_URL}/api/v1/workload`, payload, params);

    requestsCounter.add(1);

    const success = check(response, {
      'workload: status 200': (r) => r.status === 200,
      'workload: has results': (r) => r.json().hasOwnProperty('summary'),
      'workload: response time < 2s': (r) => r.timings.duration < 2000,
    });

    if (!success) {
      errorRate.add(1);
    } else {
      errorRate.add(0);
    }

    latencyTrend.add(response.timings.duration);
  });
}

/**
 * Setup function (runs once per VU)
 */
export function setup() {
  console.log('🚀 Starting QEO Global Load Test');
  console.log(`   Target: ${BASE_URL}`);
  console.log(`   Peak Load: 50,000 concurrent users`);
  console.log(`   Geographic Distribution: US (30%), EU (25%), APAC (35%), SA (10%)`);
  console.log('');

  // Health check
  const healthResponse = http.get(`${BASE_URL}/health`);

  if (healthResponse.status !== 200) {
    throw new Error(`API not healthy: ${healthResponse.status}`);
  }

  console.log('✓ API health check passed');

  return {
    startTime: new Date().toISOString()
  };
}

/**
 * Teardown function (runs once at end)
 */
export function teardown(data) {
  console.log('');
  console.log('📊 Load Test Complete');
  console.log(`   Started: ${data.startTime}`);
  console.log(`   Ended: ${new Date().toISOString()}`);
  console.log('');
  console.log('Results saved by k6 automatically');
}

/**
 * Handle summary report
 */
export function handleSummary(data) {
  return {
    'load_test_summary.json': JSON.stringify(data, null, 2),
    'stdout': textSummary(data, { indent: ' ', enableColors: true }),
  };
}

/**
 * Generate text summary
 */
function textSummary(data, options = {}) {
  const indent = options.indent || '';
  const enableColors = options.enableColors || false;

  let summary = '';

  summary += `\n${indent}========================================\n`;
  summary += `${indent}QEO Global Load Test Results\n`;
  summary += `${indent}========================================\n\n`;

  // Requests
  const requests = data.metrics.http_reqs;
  if (requests) {
    summary += `${indent}Total Requests: ${requests.values.count}\n`;
    summary += `${indent}Requests/sec: ${requests.values.rate.toFixed(2)}\n\n`;
  }

  // Latency
  const duration = data.metrics.http_req_duration;
  if (duration) {
    summary += `${indent}Latency:\n`;
    summary += `${indent}  P50: ${duration.values.p50.toFixed(2)}ms\n`;
    summary += `${indent}  P95: ${duration.values.p95.toFixed(2)}ms\n`;
    summary += `${indent}  P99: ${duration.values.p99.toFixed(2)}ms\n\n`;
  }

  // Error rate
  const failed = data.metrics.http_req_failed;
  if (failed) {
    summary += `${indent}Error Rate: ${(failed.values.rate * 100).toFixed(2)}%\n`;
  }

  // Cache hit rate
  if (data.metrics.cache_hits) {
    summary += `${indent}Cache Hit Rate: ${(data.metrics.cache_hits.values.rate * 100).toFixed(2)}%\n`;
  }

  summary += `\n${indent}========================================\n`;

  return summary;
}

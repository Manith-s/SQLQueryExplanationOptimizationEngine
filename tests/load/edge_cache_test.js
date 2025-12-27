/**
 * Edge Cache Performance Test
 *
 * Validates 85% cache hit rate and measures edge caching effectiveness.
 *
 * Usage:
 *   k6 run --vus 100 --duration 10m tests/load/edge_cache_test.js
 *
 * Requirements:
 *   - k6 (https://k6.io/)
 *   - Cloudflare Workers edge deployment
 */

import http from 'k6/http';
import { check, group, sleep } from 'k6';
import { Rate, Trend, Counter, Gauge } from 'k6/metrics';

// Custom metrics
const cacheHitRate = new Rate('cache_hits');
const cacheMissRate = new Rate('cache_misses');
const cacheRevalidateRate = new Rate('cache_revalidates');
const edgeLatency = new Trend('edge_latency_ms');
const originLatency = new Trend('origin_latency_ms');
const cacheHitCounter = new Counter('cache_hit_count');
const cacheMissCounter = new Counter('cache_miss_count');
const currentCacheHitRate = new Gauge('current_cache_hit_rate_pct');

// Test configuration
export const options = {
  stages: [
    { duration: '1m', target: 50 },   // Warm up
    { duration: '8m', target: 100 },  // Sustained load
    { duration: '1m', target: 0 },    // Cool down
  ],
  thresholds: {
    'cache_hits': ['rate>0.85'],              // >85% cache hit rate
    'edge_latency_ms': ['p(95)<50'],          // P95 < 50ms
    'http_req_failed': ['rate<0.01'],         // <1% errors
    'current_cache_hit_rate_pct': ['value>85'], // Real-time hit rate > 85%
  },
};

// Edge endpoint
const EDGE_URL = __ENV.EDGE_URL || 'https://qeo.example.com';

// Test queries (varying complexity for cache testing)
const QUERIES = {
  // Simple queries - should be cached with long TTL (5 minutes)
  simple: [
    'SELECT * FROM users WHERE id = 1',
    'SELECT * FROM users WHERE id = 2',
    'SELECT * FROM users WHERE id = 3',
    'SELECT COUNT(*) FROM orders',
    'SELECT COUNT(*) FROM products',
  ],

  // Medium queries - cached with medium TTL (1 minute)
  medium: [
    'SELECT * FROM orders WHERE user_id = 42 ORDER BY created_at DESC LIMIT 50',
    'SELECT * FROM orders WHERE user_id = 99 ORDER BY created_at DESC LIMIT 50',
    'SELECT product_id, SUM(quantity) FROM order_items GROUP BY product_id LIMIT 20',
  ],

  // Schema queries - cached with long TTL (1 hour)
  schema: [
    'SELECT table_name FROM information_schema.tables',
    'SELECT column_name, data_type FROM information_schema.columns WHERE table_name = \'users\'',
  ],

  // Complex queries - cached with short TTL (1 minute)
  complex: [
    'SELECT u.*, o.* FROM users u JOIN orders o ON u.id = o.user_id WHERE o.status = \'pending\' AND o.total > 100',
    'SELECT DATE(created_at) as date, COUNT(*) as count FROM orders GROUP BY DATE(created_at) ORDER BY date DESC LIMIT 30',
  ],
};

// Query distribution (realistic workload)
const QUERY_DISTRIBUTION = {
  simple: 0.50,   // 50% simple queries
  medium: 0.30,   // 30% medium queries
  schema: 0.15,   // 15% schema queries
  complex: 0.05,  // 5% complex queries
};

/**
 * Main test scenario
 */
export default function() {
  // Select query type based on distribution
  const rand = Math.random();
  let queryType;

  if (rand < QUERY_DISTRIBUTION.simple) {
    queryType = 'simple';
  } else if (rand < QUERY_DISTRIBUTION.simple + QUERY_DISTRIBUTION.medium) {
    queryType = 'medium';
  } else if (rand < QUERY_DISTRIBUTION.simple + QUERY_DISTRIBUTION.medium + QUERY_DISTRIBUTION.schema) {
    queryType = 'schema';
  } else {
    queryType = 'complex';
  }

  // Make request
  testCachePerformance(queryType);

  // Think time
  sleep(Math.random() * 2 + 0.5); // 0.5-2.5 seconds
}

/**
 * Test cache performance for specific query type
 */
function testCachePerformance(queryType) {
  group(`Cache Test - ${queryType}`, () => {
    const queries = QUERIES[queryType];
    const query = queries[Math.floor(Math.random() * queries.length)];

    // Endpoint depends on query type
    let endpoint;
    if (queryType === 'schema') {
      endpoint = '/api/v1/schema';
    } else {
      endpoint = '/api/v1/lint';
    }

    const payload = JSON.stringify({
      sql: query
    });

    const params = {
      headers: {
        'Content-Type': 'application/json',
        'X-Test-VU': `${__VU}`,
        'X-Test-Iter': `${__ITER}`,
      },
    };

    const response = http.post(`${EDGE_URL}${endpoint}`, payload, params);

    // Check response
    const success = check(response, {
      'status 200': (r) => r.status === 200,
      'has response': (r) => r.body && r.body.length > 0,
    });

    if (!success) {
      return;
    }

    // Analyze cache status
    const cacheStatus = response.headers['CF-Cache-Status'] || 'UNKNOWN';
    const cfRay = response.headers['CF-Ray'] || 'unknown';
    const age = parseInt(response.headers['Age'] || '0', 10);

    // Record latency
    const latency = response.timings.duration;

    if (cacheStatus === 'HIT') {
      // Cache hit
      cacheHitRate.add(1);
      cacheMissRate.add(0);
      cacheRevalidateRate.add(0);
      cacheHitCounter.add(1);
      edgeLatency.add(latency);

      // Cache hits should be fast
      check(response, {
        'cache hit latency < 50ms': (r) => r.timings.duration < 50,
      });

    } else if (cacheStatus === 'MISS' || cacheStatus === 'EXPIRED') {
      // Cache miss - went to origin
      cacheHitRate.add(0);
      cacheMissRate.add(1);
      cacheRevalidateRate.add(0);
      cacheMissCounter.add(1);
      originLatency.add(latency);

    } else if (cacheStatus === 'REVALIDATED') {
      // Revalidated with origin
      cacheHitRate.add(0);
      cacheMissRate.add(0);
      cacheRevalidateRate.add(1);
      originLatency.add(latency);

    } else {
      // Unknown status (treat as miss)
      cacheHitRate.add(0);
      cacheMissRate.add(1);
      cacheRevalidateRate.add(0);
      cacheMissCounter.add(1);
    }

    // Update current hit rate gauge
    const currentHitRate = (cacheHitCounter.add(0) / (cacheHitCounter.add(0) + cacheMissCounter.add(0))) * 100;
    currentCacheHitRate.add(currentHitRate);

    // Log cache details periodically
    if (__ITER % 100 === 0) {
      console.log(`[${queryType}] Cache: ${cacheStatus}, Latency: ${latency.toFixed(0)}ms, Age: ${age}s, Ray: ${cfRay}`);
    }
  });
}

/**
 * Setup function
 */
export function setup() {
  console.log('🚀 Starting Edge Cache Performance Test');
  console.log(`   Target: ${EDGE_URL}`);
  console.log(`   Goal: >85% cache hit rate, <50ms P95 latency`);
  console.log('');

  // Health check
  const healthResponse = http.get(`${EDGE_URL}/health`);

  if (healthResponse.status !== 200) {
    throw new Error(`Edge not healthy: ${healthResponse.status}`);
  }

  // Check if edge is actually Cloudflare
  const cfRay = healthResponse.headers['CF-Ray'];
  if (cfRay) {
    console.log(`✓ Cloudflare edge detected (Ray: ${cfRay})`);
  } else {
    console.log('⚠️  Cloudflare headers not detected (may not be testing edge)');
  }

  console.log('');

  return {
    startTime: new Date().toISOString()
  };
}

/**
 * Teardown function
 */
export function teardown(data) {
  console.log('');
  console.log('📊 Edge Cache Test Complete');
  console.log(`   Started: ${data.startTime}`);
  console.log(`   Ended: ${new Date().toISOString()}`);
}

/**
 * Handle summary
 */
export function handleSummary(data) {
  const cacheHits = data.metrics.cache_hit_count ? data.metrics.cache_hit_count.values.count : 0;
  const cacheMisses = data.metrics.cache_miss_count ? data.metrics.cache_miss_count.values.count : 0;
  const totalRequests = cacheHits + cacheMisses;
  const hitRate = totalRequests > 0 ? (cacheHits / totalRequests * 100) : 0;

  const summary = {
    timestamp: new Date().toISOString(),
    cache_performance: {
      total_requests: totalRequests,
      cache_hits: cacheHits,
      cache_misses: cacheMisses,
      hit_rate_pct: hitRate,
      target_hit_rate_pct: 85,
      test_passed: hitRate >= 85,
    },
    latency: {
      edge_p50: data.metrics.edge_latency_ms ? data.metrics.edge_latency_ms.values.p50 : null,
      edge_p95: data.metrics.edge_latency_ms ? data.metrics.edge_latency_ms.values.p95 : null,
      edge_p99: data.metrics.edge_latency_ms ? data.metrics.edge_latency_ms.values.p99 : null,
      origin_p50: data.metrics.origin_latency_ms ? data.metrics.origin_latency_ms.values.p50 : null,
      origin_p95: data.metrics.origin_latency_ms ? data.metrics.origin_latency_ms.values.p95 : null,
      origin_p99: data.metrics.origin_latency_ms ? data.metrics.origin_latency_ms.values.p99 : null,
    },
    k6_data: data,
  };

  return {
    'edge_cache_test_summary.json': JSON.stringify(summary, null, 2),
    'stdout': textSummary(summary, { enableColors: true }),
  };
}

/**
 * Generate text summary
 */
function textSummary(summary, options = {}) {
  let text = '';

  text += '\n========================================\n';
  text += 'Edge Cache Performance Test Results\n';
  text += '========================================\n\n';

  // Cache performance
  const cache = summary.cache_performance;
  text += 'Cache Performance:\n';
  text += `  Total Requests: ${cache.total_requests.toLocaleString()}\n`;
  text += `  Cache Hits: ${cache.cache_hits.toLocaleString()} (${cache.hit_rate_pct.toFixed(2)}%)\n`;
  text += `  Cache Misses: ${cache.cache_misses.toLocaleString()} (${(100 - cache.hit_rate_pct).toFixed(2)}%)\n`;
  text += `  Target Hit Rate: ${cache.target_hit_rate_pct}%\n`;
  text += '\n';

  // Latency comparison
  const latency = summary.latency;
  text += 'Latency Comparison:\n';
  text += '  Edge (cache hits):\n';
  if (latency.edge_p50) {
    text += `    P50: ${latency.edge_p50.toFixed(2)}ms\n`;
    text += `    P95: ${latency.edge_p95.toFixed(2)}ms\n`;
    text += `    P99: ${latency.edge_p99.toFixed(2)}ms\n`;
  } else {
    text += '    No data\n';
  }

  text += '  Origin (cache misses):\n';
  if (latency.origin_p50) {
    text += `    P50: ${latency.origin_p50.toFixed(2)}ms\n`;
    text += `    P95: ${latency.origin_p95.toFixed(2)}ms\n`;
    text += `    P99: ${latency.origin_p99.toFixed(2)}ms\n`;
  } else {
    text += '    No data\n';
  }

  text += '\n';

  // Calculate improvement
  if (latency.edge_p95 && latency.origin_p95) {
    const improvement = ((latency.origin_p95 - latency.edge_p95) / latency.origin_p95 * 100);
    text += `  Edge P95 is ${improvement.toFixed(1)}% faster than origin\n`;
    text += '\n';
  }

  // Test result
  if (cache.test_passed) {
    text += '✅ TEST PASSED\n';
    text += `   Cache hit rate ${cache.hit_rate_pct.toFixed(2)}% >= ${cache.target_hit_rate_pct}%\n`;
  } else {
    text += '❌ TEST FAILED\n';
    text += `   Cache hit rate ${cache.hit_rate_pct.toFixed(2)}% < ${cache.target_hit_rate_pct}%\n`;
  }

  text += '\n========================================\n';

  return text;
}

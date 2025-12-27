# QEO API Documentation

Complete API reference for the Query Explanation & Optimization Engine.

## Base URL

```
http://localhost:8000
```

## Authentication

API endpoints under `/api/v1/*` require Bearer token authentication when `AUTH_ENABLED=true` in your environment configuration.

### Authentication Header

```
Authorization: Bearer YOUR_API_KEY
```

### Enabling Authentication

Set in `.env`:
```bash
AUTH_ENABLED=true
API_KEY=your-secure-api-key-here
```

### Endpoints Without Authentication

The following endpoints are always public:
- `GET /health`
- `GET /healthz`
- `GET /` (root)

## Rate Limiting

Rate limits are enforced per IP address:

| Endpoint Pattern | Rate Limit |
|-----------------|------------|
| `/api/v1/optimize` | 10 requests/minute |
| All other `/api/v1/*` endpoints | 100 requests/minute |
| Public endpoints (`/health`, etc.) | No limit |

### Rate Limit Headers

When rate limited (HTTP 429), responses include:
```
X-RateLimit-Limit: <limit>
X-RateLimit-Reset: <seconds>
Retry-After: <seconds>
```

## Common Response Patterns

### Success Response
```json
{
  "ok": true,
  ...additional fields
}
```

### Error Response
```json
{
  "detail": "Error message description"
}
```

## Endpoints

### Health Check

#### `GET /health`

Check API and database health status.

**Authentication**: None required

**Response**: 200 OK
```json
{
  "status": "healthy",
  "database": "connected",
  "hypopg": "available"
}
```

---

### SQL Linting

#### `POST /api/v1/lint`

Validate and lint SQL syntax without executing the query.

**Authentication**: Required (if enabled)

**Request Body**:
```json
{
  "sql": "SELECT * FROM users WHERE id = 1"
}
```

**Response**: 200 OK
```json
{
  "ok": true,
  "sql": "SELECT * FROM users WHERE id = 1",
  "errors": [],
  "warnings": [
    {
      "type": "best_practice",
      "message": "Avoid using SELECT * in production queries",
      "line": 1
    }
  ],
  "info": {
    "type": "SELECT",
    "tables": ["users"],
    "columns": ["*"]
  }
}
```

**Fields**:
- `ok` (boolean): Always true for lint endpoint
- `sql` (string): The analyzed SQL query
- `errors` (array): Syntax or parsing errors
- `warnings` (array): Best practice violations
- `info` (object): Parsed query structure

**Example with Errors**:
```json
{
  "ok": true,
  "sql": "SELCT * FROM users",
  "errors": [
    {
      "type": "syntax",
      "message": "Invalid SQL syntax: unexpected token 'SELCT'",
      "line": 1
    }
  ],
  "warnings": []
}
```

---

### Query Explanation

#### `POST /api/v1/explain`

Get execution plan analysis and natural language explanation of a SQL query.

**Authentication**: Required (if enabled)

**Request Body**:
```json
{
  "sql": "SELECT * FROM orders WHERE user_id = 42 ORDER BY created_at DESC LIMIT 10",
  "analyze": false,
  "timeout_ms": 10000,
  "nl": true,
  "audience": "practitioner",
  "style": "concise",
  "length": "medium"
}
```

**Parameters**:
- `sql` (string, required): SQL query to analyze
- `analyze` (boolean, optional): Run EXPLAIN ANALYZE (executes query). Default: `false`
- `timeout_ms` (integer, optional): Statement timeout in milliseconds. Default: `10000`
- `nl` (boolean, optional): Include natural language explanation. Default: `false`
- `audience` (string, optional): Target audience for explanation. Values: `"beginner"`, `"practitioner"`, `"dba"`. Default: `"practitioner"`
- `style` (string, optional): Explanation style. Values: `"concise"`, `"detailed"`, `"verbose"`. Default: `"concise"`
- `length` (string, optional): Explanation length. Values: `"short"`, `"medium"`, `"long"`. Default: `"short"`

**Response**: 200 OK
```json
{
  "ok": true,
  "sql": "SELECT * FROM orders WHERE user_id = 42 ORDER BY created_at DESC LIMIT 10",
  "plan": {
    "Node Type": "Limit",
    "Plans": [...],
    "Total Cost": 150.25,
    "Plan Rows": 10
  },
  "warnings": [
    {
      "type": "seq_scan",
      "message": "Sequential scan on large table 'orders'",
      "severity": "high"
    }
  ],
  "metrics": {
    "estimatedCost": 150.25,
    "estimatedRows": 10,
    "ioOps": 250
  },
  "explanation": "This query filters orders by user_id and sorts by creation date..."
}
```

**Fields**:
- `ok` (boolean): Request success status
- `sql` (string): Analyzed SQL query
- `plan` (object): PostgreSQL EXPLAIN plan JSON
- `warnings` (array): Performance warnings from plan analysis
- `metrics` (object): Key metrics extracted from plan
- `explanation` (string, optional): Natural language explanation (if `nl: true`)

---

### Query Optimization

#### `POST /api/v1/optimize`

Get optimization suggestions including query rewrites and index recommendations.

**Authentication**: Required (if enabled)

**Rate Limit**: 10 requests/minute

**Request Body**:
```json
{
  "sql": "SELECT * FROM orders WHERE user_id = 42 ORDER BY created_at DESC LIMIT 50",
  "analyze": false,
  "timeout_ms": 10000,
  "top_k": 10,
  "what_if": true
}
```

**Parameters**:
- `sql` (string, required): SQL query to optimize
- `analyze` (boolean, optional): Run EXPLAIN ANALYZE. Default: `false`
- `timeout_ms` (integer, optional): Statement timeout. Default: `10000`
- `top_k` (integer, optional): Maximum suggestions to return (1-50). Default: `10`
- `what_if` (boolean, optional): Enable HypoPG cost-based evaluation. Default: `false`

**Response**: 200 OK
```json
{
  "ok": true,
  "sql": "SELECT * FROM orders WHERE user_id = 42 ORDER BY created_at DESC LIMIT 50",
  "suggestions": [
    {
      "kind": "rewrite",
      "title": "Replace SELECT * with explicit columns",
      "rationale": "Reduces I/O by only fetching needed columns",
      "impact": "medium",
      "confidence": 0.85,
      "statements": [],
      "alt_sql": "SELECT id, user_id, created_at, total FROM orders WHERE user_id = 42 ORDER BY created_at DESC LIMIT 50",
      "score": 0.850
    },
    {
      "kind": "index",
      "title": "CREATE INDEX ON orders (user_id, created_at DESC)",
      "rationale": "Supports equality filter and descending order",
      "impact": "high",
      "confidence": 0.92,
      "statements": [
        "CREATE INDEX CONCURRENTLY idx_orders_user_id_created_at ON orders (user_id, created_at DESC);"
      ],
      "score": 0.920,
      "estReductionPct": 75.5,
      "estCostBefore": 1250.50,
      "estCostAfter": 306.37,
      "estCostDelta": -944.13,
      "width": 2
    }
  ],
  "summary": {
    "score": 0.885,
    "totalSuggestions": 2,
    "highImpact": 1,
    "mediumImpact": 1,
    "lowImpact": 0
  },
  "plan": {...},
  "warnings": [...],
  "metrics": {...},
  "ranking": "cost_based",
  "whatIf": {
    "enabled": true,
    "available": true,
    "trialsRun": 3,
    "filteredByPct": 1
  },
  "advisorsRan": ["rewrite", "index"],
  "dataSources": ["ast", "plan", "schema", "stats"],
  "actualTopK": 2
}
```

**Suggestion Fields**:
- `kind` (string): `"rewrite"` or `"index"`
- `title` (string): Human-readable suggestion title
- `rationale` (string): Why this suggestion helps
- `impact` (string): `"low"`, `"medium"`, or `"high"`
- `confidence` (float): Confidence score 0.0-1.0
- `statements` (array): SQL DDL statements (for index suggestions)
- `alt_sql` (string, optional): Rewritten query (for rewrite suggestions)
- `score` (float): Overall suggestion score (rounded to 3 decimals)
- `estReductionPct` (float, optional): Estimated cost reduction % (HypoPG)
- `estCostBefore/After/Delta` (float, optional): Cost metrics (HypoPG)
- `width` (integer, optional): Number of columns in index

**What-If Analysis** (when `what_if: true`):
- Creates hypothetical indexes using HypoPG
- Measures actual cost impact
- Filters suggestions below `WHATIF_MIN_COST_REDUCTION_PCT` threshold
- Ranks by cost reduction (best first)

**Error Cases**:
- **400 Bad Request**: Invalid SQL or parameters
- **408 Request Timeout**: Query exceeded timeout
- **429 Too Many Requests**: Rate limit exceeded
- **500 Internal Server Error**: Database or server error

---

### Schema Inspection

#### `GET /api/v1/schema`

Retrieve database schema metadata including tables, columns, and indexes.

**Authentication**: Required (if enabled)

**Query Parameters**:
- `schema` (string, optional): Filter by schema name (default: all schemas)
- `table` (string, optional): Filter by table name (default: all tables)

**Response**: 200 OK
```json
{
  "schemas": [
    {
      "schema": "public",
      "tables": [
        {
          "table": "orders",
          "columns": [
            {
              "name": "id",
              "type": "integer",
              "nullable": false,
              "default": "nextval('orders_id_seq'::regclass)"
            },
            {
              "name": "user_id",
              "type": "integer",
              "nullable": false
            },
            {
              "name": "created_at",
              "type": "timestamp without time zone",
              "nullable": false,
              "default": "CURRENT_TIMESTAMP"
            }
          ],
          "indexes": [
            {
              "name": "orders_pkey",
              "columns": ["id"],
              "unique": true,
              "primary": true
            },
            {
              "name": "idx_orders_user_id",
              "columns": ["user_id"],
              "unique": false,
              "primary": false
            }
          ],
          "rowCount": 150000
        }
      ]
    }
  ]
}
```

**Examples**:

Filter by schema:
```bash
curl "http://localhost:8000/api/v1/schema?schema=public" \
  -H "Authorization: Bearer YOUR_API_KEY"
```

Filter by table:
```bash
curl "http://localhost:8000/api/v1/schema?table=orders" \
  -H "Authorization: Bearer YOUR_API_KEY"
```

---

### Workload Analysis

#### `POST /api/v1/workload`

Analyze multiple SQL queries together to identify patterns and generate workload-level optimization recommendations.

**Authentication**: Required (if enabled)

**Request Body**:
```json
{
  "sqls": [
    "SELECT * FROM orders WHERE user_id = 1",
    "SELECT * FROM orders WHERE user_id = 2",
    "SELECT COUNT(*) FROM orders",
    "SELECT * FROM orders ORDER BY created_at DESC LIMIT 100"
  ],
  "top_k": 10,
  "what_if": false
}
```

**Parameters**:
- `sqls` (array, required): List of SQL queries to analyze
- `top_k` (integer, optional): Maximum merged suggestions (1-50). Default: `10`
- `what_if` (boolean, optional): Enable HypoPG analysis. Default: `false`

**Response**: 200 OK
```json
{
  "ok": true,
  "suggestions": [
    {
      "kind": "index",
      "title": "CREATE INDEX ON orders (user_id)",
      "frequency": 2,
      "score": 1.850,
      ...
    }
  ],
  "perQuery": [
    {
      "sql": "SELECT * FROM orders WHERE user_id = 1",
      "suggestions": [...],
      "patterns": ["SELECT_STAR"],
      "warnings": [...],
      "patternGroup": "a3f2b8c1"
    }
  ],
  "workloadStats": {
    "totalQueries": 4,
    "analyzedQueries": 4,
    "skippedQueries": 0,
    "uniquePatterns": 3
  },
  "topPatterns": [
    {
      "pattern": "SELECT_STAR",
      "count": 3,
      "percentage": 75.0
    },
    {
      "pattern": "NO_WHERE_CLAUSE",
      "count": 2,
      "percentage": 50.0
    }
  ],
  "groupedQueries": [
    {
      "patternHash": "a3f2b8c1",
      "count": 2,
      "exampleSql": "SELECT * FROM orders WHERE user_id = 1",
      "patterns": ["SELECT_STAR"]
    }
  ],
  "workloadRecommendations": [
    {
      "title": "Multiple queries use SELECT *",
      "description": "3 queries use SELECT * which can fetch unnecessary data",
      "impact": "medium",
      "action": "Replace SELECT * with explicit column lists to reduce I/O",
      "affectedQueries": 3
    },
    {
      "title": "High-impact index #1: CREATE INDEX ON orders (user_id)",
      "description": "Supports equality filters on user_id column",
      "impact": "high",
      "action": "CREATE INDEX CONCURRENTLY idx_orders_user_id ON orders (user_id);",
      "affectedQueries": 2,
      "score": 0.925
    }
  ],
  "cached": false
}
```

**Detected Patterns**:
- `SELECT_STAR`: Using `SELECT *`
- `NO_WHERE_CLAUSE`: Missing WHERE clause
- `CARTESIAN_JOIN`: Join without condition
- `ORDER_WITHOUT_LIMIT`: ORDER BY without LIMIT
- `SUBQUERY_IN_SELECT`: Subquery in SELECT list
- `LARGE_SEQ_SCAN`: Sequential scan on large table (>10K rows)
- `MULTIPLE_JOINS`: 3+ JOINs in query

**Caching**:
- Results are cached for 5 minutes
- Cache key based on query list, top_k, and what_if settings
- `cached: true` indicates cache hit

---

## Error Codes

| Status Code | Description |
|-------------|-------------|
| 200 | Success |
| 400 | Bad Request - Invalid SQL or parameters |
| 403 | Forbidden - Invalid or missing API key |
| 408 | Request Timeout - Query exceeded timeout |
| 429 | Too Many Requests - Rate limit exceeded |
| 500 | Internal Server Error - Database or server error |

## Client Examples

### Python

```python
import requests

API_URL = "http://localhost:8000"
API_KEY = "your-api-key"

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

# Optimize query
response = requests.post(
    f"{API_URL}/api/v1/optimize",
    headers=headers,
    json={
        "sql": "SELECT * FROM orders WHERE user_id = 42",
        "what_if": True,
        "top_k": 5
    }
)

data = response.json()
for suggestion in data["suggestions"]:
    print(f"{suggestion['title']} (impact: {suggestion['impact']})")
```

### cURL

```bash
# With authentication
curl -X POST http://localhost:8000/api/v1/optimize \
  -H "Authorization: Bearer your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "sql": "SELECT * FROM orders WHERE user_id = 42",
    "what_if": true
  }'

# Without authentication (if AUTH_ENABLED=false)
curl -X POST http://localhost:8000/api/v1/lint \
  -H "Content-Type: application/json" \
  -d '{"sql": "SELECT 1"}'
```

### JavaScript/Node.js

```javascript
const fetch = require('node-fetch');

const API_URL = 'http://localhost:8000';
const API_KEY = 'your-api-key';

async function optimizeQuery(sql) {
  const response = await fetch(`${API_URL}/api/v1/optimize`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${API_KEY}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      sql: sql,
      what_if: true,
      top_k: 10
    })
  });

  return await response.json();
}

optimizeQuery('SELECT * FROM orders WHERE user_id = 42')
  .then(data => console.log(data.suggestions));
```

## Environment Variables Reference

See `.env.example` for complete list. Key variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `DB_URL` | `postgresql+psycopg2://...` | PostgreSQL connection string |
| `AUTH_ENABLED` | `false` | Enable API key authentication |
| `API_KEY` | `dev-key-12345` | API key for Bearer auth |
| `WHATIF_ENABLED` | `true` | Enable HypoPG cost-based analysis |
| `WHATIF_MAX_TRIALS` | `8` | Max hypothetical indexes to test |
| `WHATIF_MIN_COST_REDUCTION_PCT` | `5` | Min cost reduction to suggest index |
| `OPT_MIN_ROWS_FOR_INDEX` | `10000` | Min table size for index suggestions |
| `METRICS_ENABLED` | `false` | Expose Prometheus /metrics endpoint |
| `LLM_PROVIDER` | `dummy` | LLM provider (`dummy` or `ollama`) |

## Rate Limit Best Practices

1. **Implement Exponential Backoff**: When receiving 429, wait before retrying
2. **Batch Workload Analysis**: Use `/workload` endpoint instead of multiple `/optimize` calls
3. **Cache Results**: Workload endpoint caches for 5 minutes
4. **Monitor Headers**: Check `X-RateLimit-*` headers to track usage

## Next Steps

- See [DEPLOYMENT.md](DEPLOYMENT.md) for production deployment
- See [README.md](../README.md) for setup instructions
- Visit `http://localhost:8000/docs` for interactive API documentation

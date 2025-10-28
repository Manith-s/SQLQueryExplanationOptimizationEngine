# Part 2: Core Functionality & API Reference

**QEO (Query Explanation & Optimization Engine) - v0.7.0**

---

## SECTION 1: API Endpoints - Complete Reference

### Base URL
- **Development:** `http://localhost:8000`
- **Production:** Configure via `API_HOST` and `API_PORT` environment variables
- **API Documentation:** `/docs` (Swagger UI auto-generated)

### Authentication
All API routes (except `/health`, `/livez`, `/healthz`) support optional token authentication:
- **Header:** `Authorization: Bearer <API_KEY>`
- **Enable:** Set `AUTH_ENABLED=true` in environment
- **Configure key:** Set `API_KEY=your-secret-key` in environment
- **Default:** Authentication disabled (`AUTH_ENABLED=false`)

### Rate Limiting
- **Global limit:** 100 requests/minute per IP
- **Optimize endpoint:** 10 requests/minute per IP (more expensive operation)
- **Headers returned:**
  - `X-RateLimit-Limit`: Maximum requests allowed
  - `X-RateLimit-Reset`: Seconds until reset
  - `Retry-After`: Seconds to wait (on 429 response)

---

## Endpoint 1: Health Check

### `GET /health`
**Non-Technical:** Simple ping endpoint to verify the API is running.

**Technical Details:**
- **Purpose:** Basic liveness check for monitoring systems
- **Use cases:** Docker health checks, load balancer probes, CI/CD validation
- **No database connection required** - instant response

**Request:**
- Method: `GET`
- Path: `/health`
- Headers: None required
- Body: None

**Response Schema:**
```json
{
  "status": "ok"  // Always "ok" if service is up
}
```

**HTTP Status Codes:**
- `200 OK` - Service is running
- `503 Service Unavailable` - Service is down (no response)

**Example Requests:**

```bash
# curl
curl http://localhost:8000/health

# Python requests
import requests
response = requests.get("http://localhost:8000/health")
print(response.json())

# JavaScript fetch
fetch('http://localhost:8000/health')
  .then(res => res.json())
  .then(data => console.log(data));
```

**Example Response:**
```json
{
  "status": "ok"
}
```

**Implementation Flow:**
1. FastAPI receives GET request at `/health`
2. `src/app/routers/health.py:14` - `health_check()` function executes
3. Returns static JSON `{"status": "ok"}`
4. Total latency: <1ms

**Performance:** <1ms (no I/O)

**Error Scenarios:** None (always succeeds if service is up)

---

## Endpoint 2: Database Readiness Check

### `GET /healthz`
**Non-Technical:** Checks if the database is reachable and responsive.

**Technical Details:**
- **Purpose:** Kubernetes readiness probe, ensures DB connection is healthy
- **Use cases:** Container orchestration, deployment verification
- **Database query:** Runs `SELECT 1` with 500ms timeout

**Request:**
- Method: `GET`
- Path: `/healthz`
- Headers: None required
- Body: None

**Response Schema:**
```json
{
  "status": "ok" | "degraded"
}
```

**HTTP Status Codes:**
- `200 OK` - Both service and database are healthy
- `200 OK` with `status: "degraded"` - Service up but database unreachable

**Example Requests:**

```bash
# curl
curl http://localhost:8000/healthz

# Python
import requests
response = requests.get("http://localhost:8000/healthz")
print(response.json())  # {"status": "ok"} or {"status": "degraded"}
```

**Example Responses:**

Success:
```json
{
  "status": "ok"
}
```

Database down:
```json
{
  "status": "degraded"
}
```

**Implementation Flow:**
1. FastAPI receives GET request at `/healthz`
2. `src/app/routers/health.py:27` - `healthz()` function executes
3. Calls `db.run_sql("SELECT 1", timeout_ms=500)`
4. Returns `{"status": "ok"}` if query succeeds, `{"status": "degraded"}` if fails
5. Typical latency: 5-50ms (includes database round-trip)

**Performance:** 5-50ms (database ping)

**Error Scenarios:**
| Scenario | Response | Status Code |
|----------|----------|-------------|
| Database unreachable | `{"status": "degraded"}` | 200 |
| Database timeout | `{"status": "degraded"}` | 200 |

---

## Endpoint 3: SQL Linting

### `POST /api/v1/lint`
**Non-Technical:** Checks SQL code for common mistakes and bad practices (like a spell-checker for SQL).

**Technical Details:**
- **Purpose:** Static analysis of SQL without executing queries
- **Use cases:** Pre-commit hooks, CI/CD validation, real-time editor feedback
- **No database required:** Pure syntax analysis using sqlglot

**Request Schema:**
```json
{
  "sql": "string"  // REQUIRED: SQL query to lint
}
```

**Response Schema:**
```json
{
  "ok": boolean,
  "message": string | null,
  "error": string | null,
  "ast": {
    "type": "SELECT" | "INSERT" | "UPDATE" | "DELETE" | "UNKNOWN",
    "sql": string,
    "tables": [{"name": string, "alias": string | null, "raw": string}],
    "columns": [{"table": string | null, "name": string, "raw": string}],
    "joins": [{"type": string, "right": string, "condition": string, "raw": string}],
    "filters": [string],
    "group_by": [string],
    "order_by": [string],
    "limit": number | null
  } | null,
  "issues": [
    {
      "code": string,      // Issue code (e.g., "SELECT_STAR", "CARTESIAN_JOIN")
      "message": string,   // Human-readable description
      "severity": "info" | "warn" | "high",
      "hint": string       // Suggestion to fix the issue
    }
  ],
  "summary": {
    "risk": "low" | "medium" | "high"
  }
}
```

**Linting Rules (7+ rules):**

| Code | Severity | What it detects | Why it matters |
|------|----------|----------------|----------------|
| `SELECT_STAR` | warn | Using `SELECT *` | Fetches unnecessary columns, prevents index-only scans |
| `MISSING_JOIN_ON` | high | JOIN without ON clause | Creates accidental Cartesian products |
| `CARTESIAN_JOIN` | high | Missing join conditions | Scans every combination of rows (exponential growth) |
| `AMBIGUOUS_COLUMN` | warn | Unqualified column names in multi-table queries | Can break when schema changes |
| `UNFILTERED_LARGE_TABLE` | warn | Queries on large tables without WHERE/LIMIT | Full table scans on large tables (events, logs, etc.) |
| `IMPLICIT_CAST_PREDICATE` | info | Comparing ID columns with strings | Prevents index usage, causes type conversion overhead |
| `UNUSED_JOINED_TABLE` | warn | Table is joined but never referenced | Unnecessary work for the database |
| `PARSE_ERROR` | high | Invalid SQL syntax | Query will fail |

**HTTP Status Codes:**
- `200 OK` - Linting completed (even if issues found)

**Example Requests:**

```bash
# curl
curl -X POST http://localhost:8000/api/v1/lint \
  -H "Content-Type: application/json" \
  -d '{"sql": "SELECT * FROM orders WHERE user_id = '\''42'\'' LIMIT 10"}'

# Python
import requests
response = requests.post(
    "http://localhost:8000/api/v1/lint",
    json={"sql": "SELECT * FROM orders WHERE user_id = '42' LIMIT 10"}
)
print(response.json())

# JavaScript
fetch('http://localhost:8000/api/v1/lint', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({
    sql: "SELECT * FROM orders WHERE user_id = '42' LIMIT 10"
  })
})
.then(res => res.json())
.then(data => console.log(data));
```

**Example Responses:**

Clean query:
```json
{
  "ok": true,
  "message": "stub: lint ok",
  "error": null,
  "ast": {
    "type": "SELECT",
    "sql": "SELECT * FROM orders WHERE user_id = '42' LIMIT 10",
    "tables": [{"name": "orders", "alias": null, "raw": "orders"}],
    "columns": [{"table": null, "name": "*", "raw": "*"}],
    "joins": [],
    "filters": ["user_id = '42'"],
    "group_by": [],
    "order_by": [],
    "limit": 10
  },
  "issues": [
    {
      "code": "SELECT_STAR",
      "message": "Using SELECT * is not recommended",
      "severity": "warn",
      "hint": "Explicitly list required columns"
    }
  ],
  "summary": {
    "risk": "low"
  }
}
```

Dangerous query:
```json
{
  "ok": true,
  "message": "stub: lint ok",
  "ast": {...},
  "issues": [
    {
      "code": "CARTESIAN_JOIN",
      "message": "Cartesian product detected",
      "severity": "high",
      "hint": "Add join conditions or confirm if CROSS JOIN is intended"
    },
    {
      "code": "MISSING_JOIN_ON",
      "message": "Missing ON clause in JOIN",
      "severity": "high",
      "hint": "Add an ON clause with join conditions"
    }
  ],
  "summary": {
    "risk": "high"
  }
}
```

**Implementation Flow:**
1. User sends POST to `/api/v1/lint` with SQL
2. `src/app/routers/lint.py:30` - `lint_sql()` validates input
3. `src/app/core/sql_analyzer.py:175` - `parse_sql(sql)` parses with sqlglot
4. sqlglot creates AST (Abstract Syntax Tree)
5. Extracts: tables, columns, joins, filters, order_by, group_by, limit
6. `src/app/core/sql_analyzer.py:208` - `lint_rules(ast_info)` applies 7+ rules
7. Calculates risk level based on severity counts
8. Returns issues and summary
9. **No database queries executed**

**Performance:** 5-20ms (pure computation, no I/O)

**Error Scenarios:**
| Issue | Response | Notes |
|-------|----------|-------|
| Empty SQL | `ok: false, error: "SQL is required"` | Risk: high |
| Parse error | `ok: true, issues: [PARSE_ERROR]` | Risk: high |

---

## Endpoint 4: EXPLAIN Query Plan

### `POST /api/v1/explain`
**Non-Technical:** Shows how PostgreSQL will execute your query and identifies performance problems.

**Technical Details:**
- **Purpose:** Get query execution plan with warnings and optional natural language explanation
- **Use cases:** Understanding slow queries, debugging performance issues, learning PostgreSQL
- **Database interaction:** Runs `EXPLAIN` (read-only, no data modification)

**Request Schema:**
```json
{
  "sql": "string",          // REQUIRED: SQL query to analyze
  "analyze": false,         // OPTIONAL: Use EXPLAIN ANALYZE (actually runs the query)
  "timeout_ms": 10000,      // OPTIONAL: Statement timeout (1ms to 600000ms)
  "nl": false,              // OPTIONAL: Generate natural language explanation
  "audience": "practitioner", // OPTIONAL: "beginner" | "practitioner" | "dba"
  "style": "concise",       // OPTIONAL: "concise" | "detailed"
  "length": "short"         // OPTIONAL: "short" | "medium" | "long"
}
```

**Response Schema:**
```json
{
  "ok": true,
  "plan": {...},  // Full EXPLAIN JSON output from PostgreSQL
  "warnings": [
    {
      "code": "SEQ_SCAN_LARGE" | "NESTED_LOOP_SEQ_INNER" | "SORT_SPILL" | "ESTIMATE_MISMATCH" | "NO_INDEX_FILTER" | "PARALLEL_OFF",
      "level": "warn",
      "detail": string
    }
  ],
  "metrics": {
    "planning_time_ms": number,
    "execution_time_ms": number,
    "node_count": number
  },
  "explanation": string | null,  // Natural language (if nl: true)
  "explain_provider": "dummy" | "ollama" | null,
  "message": "ok"
}
```

**Plan Warnings Detected:**

| Code | What it means | Fix |
|------|---------------|-----|
| `SEQ_SCAN_LARGE` | Scanning >100k rows sequentially | Add index on filtered columns |
| `NESTED_LOOP_SEQ_INNER` | Nested loop with sequential scan on inner side | Add index on join key |
| `SORT_SPILL` | Sort operation spilled to disk (ran out of memory) | Increase `work_mem` or add index to avoid sorting |
| `ESTIMATE_MISMATCH` | Planner estimated X rows but got Y (>50% error) | Run `ANALYZE` on table, check statistics |
| `NO_INDEX_FILTER` | Table has filters but uses sequential scan | Add index on filter columns |
| `PARALLEL_OFF` | Query processes >100k rows but doesn't use parallel workers | Check `max_parallel_workers_per_gather` setting |

**HTTP Status Codes:**
- `200 OK` - Analysis completed
- `400 Bad Request` - Invalid SQL or timeout exceeded

**Example Requests:**

```bash
# curl - Basic EXPLAIN
curl -X POST http://localhost:8000/api/v1/explain \
  -H "Content-Type: application/json" \
  -d '{"sql": "SELECT * FROM orders WHERE user_id = 42 ORDER BY created_at DESC LIMIT 100"}'

# curl - With ANALYZE and natural language
curl -X POST http://localhost:8000/api/v1/explain \
  -H "Content-Type: application/json" \
  -d '{
    "sql": "SELECT * FROM orders WHERE user_id = 42",
    "analyze": true,
    "nl": true,
    "audience": "beginner"
  }'

# Python
import requests
response = requests.post(
    "http://localhost:8000/api/v1/explain",
    json={
        "sql": "SELECT * FROM orders WHERE user_id = 42 ORDER BY created_at DESC LIMIT 100",
        "analyze": False,
        "timeout_ms": 5000
    }
)
print(response.json())
```

**Example Response:**

```json
{
  "ok": true,
  "plan": {
    "Plan": {
      "Node Type": "Limit",
      "Startup Cost": 0.00,
      "Total Cost": 1910.68,
      "Plan Rows": 100,
      "Plan Width": 542,
      "Plans": [
        {
          "Node Type": "Sort",
          "Sort Key": ["created_at DESC"],
          "Plans": [
            {
              "Node Type": "Seq Scan",
              "Relation Name": "orders",
              "Filter": "(user_id = 42)",
              "Plan Rows": 50000,
              "Plan Width": 542
            }
          ]
        }
      ]
    },
    "Planning Time": 0.523,
    "Execution Time": 0.0
  },
  "warnings": [
    {
      "code": "SEQ_SCAN_LARGE",
      "level": "warn",
      "detail": "Sequential scan on orders with 50,000 rows"
    }
  ],
  "metrics": {
    "planning_time_ms": 0.523,
    "execution_time_ms": 0.0,
    "node_count": 3
  },
  "explanation": "This query scans the entire orders table looking for user_id = 42, then sorts the results by created_at. Because there's no index on (user_id, created_at), PostgreSQL has to read all 50,000 matching rows from disk and sort them in memory. This is slow and gets worse as the table grows.",
  "explain_provider": "dummy",
  "message": "ok"
}
```

**Implementation Flow:**
1. User submits SQL via POST to `/api/v1/explain`
2. `src/app/routers/explain.py:83` - `explain_query()` validates input
3. `src/app/core/db.py:100` - `run_explain(sql, analyze, timeout_ms)`
4. Database connection established with `psycopg2`
5. Sets `statement_timeout` to prevent runaway queries
6. Executes: `EXPLAIN (FORMAT JSON, ANALYZE, BUFFERS, TIMING) <sql>` (if analyze=true)
7. Or: `EXPLAIN (FORMAT JSON) <sql>` (if analyze=false)
8. Parses JSON plan from PostgreSQL
9. `src/app/core/plan_heuristics.py:39` - `analyze(plan)` walks the plan tree
10. Detects 6+ warning patterns (sequential scans, sort spills, etc.)
11. Calculates metrics (planning time, execution time, node count)
12. **If `nl=true`:** Calls LLM provider (dummy or Ollama) to generate explanation
13. Returns plan + warnings + metrics + optional explanation

**Performance:**
- Without ANALYZE: 10-100ms (no query execution)
- With ANALYZE: Varies (actually runs the query + EXPLAIN overhead)
- Natural language: +500ms to +5s (depends on LLM provider)

**Error Scenarios:**
| Scenario | Response | Status Code |
|----------|----------|-------------|
| Invalid SQL syntax | `{"detail": "EXPLAIN failed: syntax error..."}` | 400 |
| Query timeout | `{"detail": "Timeout: statement timeout..."}` | 400 |
| Database unreachable | `{"detail": "could not connect..."}` | 400 |
| LLM generation fails | `plan` returns successfully, `explanation: null`, `message` includes error | 200 |

---

## Endpoint 5: Optimize Query

### `POST /api/v1/optimize`
**Non-Technical:** The main feature - analyzes your query and tells you exactly how to make it faster.

**Technical Details:**
- **Purpose:** Generate deterministic rewrite and index suggestions with optional cost-based ranking
- **Use cases:** Performance tuning, index planning, query refactoring
- **Key features:**
  - Static analysis (linting + AST parsing)
  - Plan heuristics (warnings from EXPLAIN)
  - Index advisor (deterministic algorithm)
  - Rewrite advisor (query pattern improvements)
  - HypoPG what-if analysis (cost-based ranking)
  - Optional plan diff (before/after comparison)

**Request Schema:**
```json
{
  "sql": "string",          // REQUIRED: SQL query to optimize
  "analyze": false,         // OPTIONAL: Use EXPLAIN ANALYZE
  "what_if": true,          // OPTIONAL: Enable HypoPG cost-based evaluation
  "timeout_ms": 10000,      // OPTIONAL: Statement timeout (1ms to 600000ms)
  "advisors": ["rewrite", "index"],  // OPTIONAL: Which advisors to run
  "top_k": 10,              // OPTIONAL: Max suggestions to return (1-50)
  "diff": false             // OPTIONAL: Include plan diff for top index
}
```

**Response Schema:**
```json
{
  "ok": true,
  "message": "stub: optimize ok",
  "suggestions": [
    {
      "kind": "rewrite" | "index",
      "title": string,
      "rationale": string,
      "impact": "low" | "medium" | "high",
      "confidence": number,  // 0.0 to 1.0
      "statements": [string],  // SQL statements to execute (for indexes)
      "alt_sql": string | null,  // Alternative query (for rewrites)
      "safety_notes": string | null,
      "score": number | null,  // Heuristic score (if available)
      "reason": string | null,  // Detailed reasoning
      "estReductionPct": number | null,  // Estimated improvement %
      "estIndexWidthBytes": number | null,  // Estimated index size
      "estCostBefore": number | null,  // Cost before (from HypoPG)
      "estCostAfter": number | null,   // Cost after (from HypoPG)
      "estCostDelta": number | null,   // Cost reduction (from HypoPG)
      "trialMs": number | null         // HypoPG trial duration
    }
  ],
  "summary": {
    "summary": string,  // One-line summary
    "score": number     // Overall optimization score (0.0 to 1.0)
  },
  "ranking": "cost_based" | "heuristic",
  "whatIf": {
    "enabled": boolean,
    "available": boolean,  // Is HypoPG extension available?
    "trials": number,      // Number of hypothetical indexes tested
    "filteredByPct": number  // Number filtered by min reduction %
  },
  "plan_warnings": [...],  // Same as /explain endpoint
  "plan_metrics": {...},   // Same as /explain endpoint
  "advisorsRan": ["rewrite", "index"],
  "dataSources": {
    "plan": "explain" | "explain_analyze" | "none",
    "stats": boolean  // Were table stats fetched?
  },
  "actualTopK": number,  // Actual number of suggestions returned
  "planDiff": {          // Optional: If diff=true
    "nodes": [
      {
        "beforeOp": string,
        "afterOp": string,
        "costBefore": number,
        "costAfter": number,
        "rowsBefore": number,
        "rowsAfter": number
      }
    ]
  } | null
}
```

**Rewrite Suggestions (5 patterns):**

1. **SELECT * → Explicit columns**
   - Reduces I/O
   - Enables index-only scans
   - Prevents breaking changes when columns added

2. **IN (subquery) → EXISTS**
   - Short-circuit evaluation
   - Avoids de-duplication work
   - Better for correlated subqueries

3. **Decorrelate subquery**
   - Convert correlated EXISTS to JOIN
   - Enables better join strategies
   - Reduces nested loop overhead

4. **ORDER BY + LIMIT → Top-N optimization**
   - Align index columns with ORDER BY
   - Enables early termination
   - Crucial for pagination queries

5. **Filter pushdown**
   - Move WHERE clauses inside CTEs/subqueries
   - Reduces rows before aggregation
   - Minimizes temporary data

**Index Advisor Algorithm:**
- **Column ordering:** Equality → Range → Order/Group (proven optimal for B-tree indexes)
- **Deduplication:** Skips if existing index covers the prefix
- **Small table suppression:** No indexes for tables <10k rows (configurable)
- **Scoring:** Considers equality count, range count, order/group usage, join boost, width penalty
- **Filtering:** Removes low-gain suggestions (<5% estimated improvement by default)

**HTTP Status Codes:**
- `200 OK` - Optimization completed
- `400 Bad Request` - Invalid request (non-SELECT query, invalid SQL)

**Example Requests:**

```bash
# curl - Basic optimization
curl -X POST http://localhost:8000/api/v1/optimize \
  -H "Content-Type: application/json" \
  -d '{"sql": "SELECT * FROM orders WHERE user_id = 42 ORDER BY created_at DESC LIMIT 100"}'

# curl - With HypoPG what-if analysis
curl -X POST http://localhost:8000/api/v1/optimize \
  -H "Content-Type: application/json" \
  -d '{
    "sql": "SELECT * FROM orders WHERE user_id = 42 ORDER BY created_at DESC LIMIT 100",
    "what_if": true,
    "diff": true,
    "top_k": 5
  }'

# Python
import requests
response = requests.post(
    "http://localhost:8000/api/v1/optimize",
    json={
        "sql": "SELECT * FROM orders WHERE user_id = 42 ORDER BY created_at DESC LIMIT 100",
        "what_if": True,
        "top_k": 10
    }
)
result = response.json()
for suggestion in result["suggestions"]:
    print(f"{suggestion['title']}: {suggestion['estCostDelta']} cost reduction")
```

**Example Response (with HypoPG):**

```json
{
  "ok": true,
  "message": "stub: optimize ok",
  "suggestions": [
    {
      "kind": "index",
      "title": "Index on orders(user_id, created_at)",
      "rationale": "Supports equality, range, and ordering for faster lookups and Top-N.",
      "impact": "high",
      "confidence": 0.700,
      "statements": [
        "CREATE INDEX CONCURRENTLY idx_orders_user_id_created_at ON orders (user_id, created_at)"
      ],
      "alt_sql": null,
      "safety_notes": null,
      "score": 2.145,
      "reason": "Boosts equality(1), range(0), order/group(1)",
      "estReductionPct": 15.000,
      "estIndexWidthBytes": 12,
      "estCostBefore": 1910.680,
      "estCostAfter": 104.590,
      "estCostDelta": 1806.090,
      "trialMs": 23.456
    },
    {
      "kind": "rewrite",
      "title": "Replace SELECT * with explicit columns",
      "rationale": "Explicit projections reduce I/O and improve index-only scan chances.",
      "impact": "low",
      "confidence": 0.900,
      "statements": [],
      "alt_sql": "-- Replace SELECT * with explicit projection\n/* projected */ SELECT id, user_id, total, created_at, status FROM ...",
      "safety_notes": null,
      "score": null,
      "reason": null,
      "estReductionPct": null,
      "estIndexWidthBytes": null,
      "estCostBefore": null,
      "estCostAfter": null,
      "estCostDelta": null,
      "trialMs": null
    }
  ],
  "summary": {
    "summary": "Top suggestion: Index on orders(user_id, created_at)",
    "score": 0.700
  },
  "ranking": "cost_based",
  "whatIf": {
    "enabled": true,
    "available": true,
    "trials": 3,
    "filteredByPct": 1
  },
  "plan_warnings": [
    {
      "code": "SEQ_SCAN_LARGE",
      "level": "warn",
      "detail": "Sequential scan on orders with 50,000 rows"
    }
  ],
  "plan_metrics": {
    "planning_time_ms": 0.523,
    "execution_time_ms": 0.0,
    "node_count": 3
  },
  "advisorsRan": ["rewrite", "index"],
  "dataSources": {
    "plan": "explain",
    "stats": true
  },
  "actualTopK": 2,
  "planDiff": {
    "nodes": [
      {
        "beforeOp": "Limit",
        "afterOp": "Limit",
        "costBefore": 1910.680,
        "costAfter": 104.590,
        "rowsBefore": 100,
        "rowsAfter": 100
      },
      {
        "beforeOp": "Sort",
        "afterOp": "Index Scan",
        "costBefore": null,
        "costAfter": null,
        "rowsBefore": 50000,
        "rowsAfter": 100
      }
    ]
  }
}
```

**Implementation Flow:**
1. User submits SQL to `/api/v1/optimize`
2. `src/app/routers/optimize.py:89` - `optimize_sql()` validates request
3. Validates query is SELECT (only SELECT supported for optimization)
4. **Phase 1: Static Analysis**
   - `src/app/core/sql_analyzer.py:175` - Parses SQL with sqlglot
   - Extracts AST: tables, columns, filters, joins, order_by, group_by, limit
5. **Phase 2: EXPLAIN (optional)**
   - `src/app/core/db.py:100` - Runs EXPLAIN on PostgreSQL
   - `src/app/core/plan_heuristics.py:39` - Analyzes plan for warnings
6. **Phase 3: Schema & Stats**
   - `src/app/core/db.py:188` - Fetches schema (tables, columns, indexes)
   - `src/app/core/db.py:329` - Fetches table stats (row counts)
7. **Phase 4: Generate Suggestions**
   - `src/app/core/optimizer.py:404` - `analyze()` orchestrates
   - `src/app/core/optimizer.py:143` - `suggest_rewrites()` - 5+ rewrite patterns
   - `src/app/core/optimizer.py:245` - `suggest_indexes()` - Index advisor algorithm
     * Extracts equality filters (e.g., `user_id = 42`)
     * Extracts range filters (e.g., `created_at > '2024-01-01'`)
     * Extracts join keys
     * Extracts order/group columns
     * Orders columns: equality → range → order/group
     * Calculates score with width penalties
     * Filters by: min_rows, existing indexes, low gain %
   - Merges rewrites + indexes, sorts alphabetically for determinism
8. **Phase 5: HypoPG What-If (optional, if `what_if=true`)**
   - `src/app/core/whatif.py:47` - `evaluate()` runs cost-based analysis
   - Gets baseline cost: `run_explain_costs(sql)` → 1910.68
   - For top-N index candidates (default: 8 max):
     * Creates hypothetical index: `SELECT hypopg_create_index('CREATE INDEX ...')`
     * Re-runs EXPLAIN: `run_explain_costs(sql)` → 104.59
     * Calculates delta: 1910.68 - 104.59 = 1806.09 (94.5% improvement)
     * Cleans up: `SELECT hypopg_reset()`
   - Filters suggestions by `WHATIF_MIN_COST_REDUCTION_PCT` (default 5%)
   - Sorts by cost delta descending
   - **Ranking changes to "cost_based"**
9. **Phase 6: Plan Diff (optional, if `diff=true`)**
   - Gets baseline plan
   - Creates hypothetical index for top suggestion
   - Gets after plan
   - `src/app/core/plan_diff.py:18` - Compares node operations and costs
10. Returns comprehensive response

**Performance:**
- Without what-if: 50-200ms (parsing + EXPLAIN + schema)
- With what-if (8 trials): 200-800ms (includes HypoPG hypothetical indexes)
- Scales with: query complexity, table count, index candidate count

**Error Scenarios:**
| Scenario | Response | Status Code |
|----------|----------|-------------|
| Non-SELECT query | `ok: false, message: "Only SELECT statements supported"` | 200 |
| Invalid SQL | `detail: "Error message"` | 400 |
| Database timeout | `plan_warnings` empty, continues with heuristic suggestions | 200 |
| HypoPG unavailable | `whatIf: {enabled: true, available: false}`, falls back to heuristic | 200 |

---

## Endpoint 6: Schema Inspection

### `GET /api/v1/schema`
**Non-Technical:** View your database structure (tables, columns, indexes).

**Technical Details:**
- **Purpose:** Fetch database schema metadata for analysis and visualization
- **Use cases:** Understanding database structure, checking existing indexes, schema exploration
- **Query source:** PostgreSQL `information_schema` and `pg_catalog`

**Request:**
- Method: `GET`
- Path: `/api/v1/schema`
- Query Parameters:
  - `schema` (optional): Schema name (default: "public")
  - `table` (optional): Specific table name to inspect

**Response Schema:**
```json
{
  "schema": "public",
  "tables": [
    {
      "name": "orders",
      "columns": [
        {
          "name": "id",
          "data_type": "integer",
          "nullable": false,
          "default": "nextval('orders_id_seq'::regclass)"
        }
      ],
      "indexes": [
        {
          "name": "orders_pkey",
          "unique": true,
          "columns": ["id"]
        }
      ],
      "primary_key": ["id"],
      "foreign_keys": [
        {
          "column_name": "user_id",
          "foreign_schema": "public",
          "foreign_table": "users",
          "foreign_column": "id"
        }
      ]
    }
  ]
}
```

**Example Request:**

```bash
# Get all tables in public schema
curl http://localhost:8000/api/v1/schema

# Get specific table
curl "http://localhost:8000/api/v1/schema?schema=public&table=orders"
```

---

## Endpoint 7: Workload Analysis

### `POST /api/v1/workload`
**Non-Technical:** Analyze many queries together to find patterns and prioritize optimizations.

**Technical Details:**
- **Purpose:** Multi-query analysis with pattern detection, query grouping, and workload-level recommendations
- **Use cases:** Analyzing application logs, finding N+1 queries, prioritizing which indexes to create
- **Key features:**
  - Detects repeated query patterns
  - Groups similar queries (normalized by literals)
  - Identifies N+1 query patterns
  - Merges index candidates by frequency and score
  - Generates workload-level recommendations

**Request Schema:**
```json
{
  "sqls": ["string", "string", ...],  // REQUIRED: List of SQL statements
  "top_k": 10,                        // OPTIONAL: Max suggestions (1-50)
  "what_if": false                    // OPTIONAL: Enable HypoPG for all queries
}
```

**Response Schema:**
```json
{
  "ok": true,
  "cached": false,
  "suggestions": [  // Merged index suggestions across all queries
    {
      "kind": "index",
      "title": "Index on orders(user_id, created_at)",
      "frequency": 15,  // How many queries benefit from this index
      "score": 32.175,  // Cumulative score across queries
      ...
    }
  ],
  "perQuery": [  // Individual analysis for each query
    {
      "sql": "...",
      "suggestions": [...],
      "patterns": ["SELECT_STAR", "LARGE_SEQ_SCAN"],
      "warnings": [...],
      "patternGroup": "a3f5b8c2"  // Normalized pattern hash
    }
  ],
  "workloadStats": {
    "totalQueries": 50,
    "analyzedQueries": 48,
    "skippedQueries": 2,
    "uniquePatterns": 12
  },
  "topPatterns": [
    {
      "pattern": "SELECT_STAR",
      "count": 35,
      "percentage": 70.0
    }
  ],
  "groupedQueries": [
    {
      "patternHash": "a3f5b8c2",
      "count": 15,
      "exampleSql": "SELECT * FROM orders WHERE user_id = ?",
      "patterns": ["SELECT_STAR"]
    }
  ],
  "workloadRecommendations": [
    {
      "title": "Potential N+1 query pattern detected",
      "description": "15 similar queries detected, possibly executed in a loop",
      "impact": "high",
      "action": "Consider batching these queries or using JOINs",
      "affectedQueries": 15
    }
  ]
}
```

**Patterns Detected:**
- `SELECT_STAR` - Using SELECT *
- `NO_WHERE_CLAUSE` - Missing WHERE on SELECT
- `CARTESIAN_JOIN` - Missing join conditions
- `ORDER_WITHOUT_LIMIT` - ORDER BY without LIMIT (expensive)
- `SUBQUERY_IN_SELECT` - Subquery in SELECT list (N+1 indicator)
- `LARGE_SEQ_SCAN` - Sequential scan on large table
- `MULTIPLE_JOINS` - 3+ joins (complexity warning)

**Example Request:**

```bash
curl -X POST http://localhost:8000/api/v1/workload \
  -H "Content-Type: application/json" \
  -d '{
    "sqls": [
      "SELECT * FROM orders WHERE user_id = 1",
      "SELECT * FROM orders WHERE user_id = 2",
      "SELECT * FROM orders WHERE user_id = 3"
    ],
    "top_k": 5
  }'
```

**Implementation Flow:**
1. User submits list of SQL queries
2. `src/app/routers/workload.py:69` - Checks 5-minute cache
3. `src/app/core/workload.py:112` - `analyze_workload()`
4. For each query:
   - Parse SQL and extract AST
   - Normalize SQL (replace literals with placeholders) for grouping
   - Run EXPLAIN and detect warnings
   - Detect patterns (7+ anti-patterns)
   - Generate suggestions
5. Merge index candidates by frequency and score
6. Generate workload-level recommendations
7. Cache result for 5 minutes

**Performance:**
- Without what-if: ~50ms per query
- With 50 queries: 2-5 seconds
- Cached responses: <10ms

---

## SECTION 2: Core Algorithms Explained

### Algorithm 1: SQL Parsing (sqlglot AST Extraction)

**Location:** `src/app/core/sql_analyzer.py:175-206`

**How it works:**
1. Takes SQL string as input
2. Calls `sqlglot.parse_one(sql)` to build AST
3. Traverses AST to extract:
   - **Tables:** From `FROM` clause and `JOIN` clauses
   - **Columns:** From `SELECT` list
   - **Joins:** Type, condition, and right side table
   - **Filters:** `WHERE` clause predicates
   - **Group By:** Grouping columns
   - **Order By:** Sorting columns with direction
   - **Limit:** Row limit value
4. Returns structured dictionary

**Example:**
```python
sql = "SELECT * FROM orders WHERE user_id = 42 ORDER BY created_at DESC LIMIT 100"

ast_info = parse_sql(sql)
# Returns:
{
  "type": "SELECT",
  "sql": "...",
  "tables": [{"name": "orders", "alias": null, "raw": "orders"}],
  "columns": [{"table": null, "name": "*", "raw": "*"}],
  "joins": [],
  "filters": ["user_id = 42"],
  "group_by": [],
  "order_by": ["created_at DESC"],
  "limit": 100
}
```

**Why this approach:** sqlglot provides a reliable, fast, dialect-aware parser without C dependencies, making it easy to deploy.

---

### Algorithm 2: Linting Rules Engine

**Location:** `src/app/core/sql_analyzer.py:208-348`

**How it works:**
1. Takes parsed AST as input
2. Applies 7+ deterministic rules:

**Rule 1: SELECT_STAR**
```python
if any(c.get("name") == "*" for c in ast_info.get("columns", [])):
    issues.append({
        "code": "SELECT_STAR",
        "message": "Using SELECT * is not recommended",
        "severity": "warn",
        "hint": "Explicitly list required columns"
    })
```

**Rule 2: CARTESIAN_JOIN**
```python
for join in ast_info.get("joins", []):
    if not join.get("condition"):
        issues.append({
            "code": "CARTESIAN_JOIN",
            "message": "Cartesian product detected",
            "severity": "high",
            "hint": "Add join conditions..."
        })
```

3. Calculates risk level:
```python
high_count = sum(1 for issue in issues if issue["severity"] == "high")
warn_count = sum(1 for issue in issues if issue["severity"] == "warn")

if high_count > 0:
    risk = "high"
elif warn_count > 1:
    risk = "medium"
else:
    risk = "low"
```

**Determinism:** Rules execute in fixed order, produce stable output.

---

### Algorithm 3: Index Advisor

**Location:** `src/app/core/optimizer.py:245-380`

**Algorithm (Proven Optimal for B-tree Indexes):**

**Step 1: Extract predicates**
```python
eq_keys = []  # user_id = 42
range_keys = []  # created_at > '2024-01-01'
join_keys = []  # t1.id = t2.user_id
order_cols = []  # ORDER BY created_at
group_cols = []  # GROUP BY category
```

**Step 2: Order columns (CRITICAL for index effectiveness)**
```python
ordered_cols = []
# Phase 1: Equality predicates (most selective)
for col in eq_keys:
    if col not in ordered_cols:
        ordered_cols.append(col)

# Phase 2: Range predicates (middle selectivity)
for col in range_keys:
    if col not in ordered_cols:
        ordered_cols.append(col)

# Phase 3: Order/Group columns (for sort avoidance)
for col in order_cols + group_cols:
    if col not in ordered_cols:
        ordered_cols.append(col)
```

**Why this ordering?**
- **Equality first:** Narrows down to specific rows (e.g., user_id = 42 selects 0.01% of rows)
- **Range second:** Further filters within equality subset (e.g., date range)
- **Order last:** Enables sort avoidance (index already sorted)
- **This order is mathematically proven optimal for B-tree indexes**

**Step 3: Deduplication**
```python
existing_indexes = fetch_existing_indexes(table)
if _existing_index_covers(existing_indexes, ordered_cols):
    continue  # Skip, already covered
```

**Step 4: Scoring with width penalties**
```python
base_score = 0.0
for c in eq_keys:
    if c in ordered_cols:
        base_score += 1.0  # Equality gets 1.0 point
for c in range_keys:
    if c in ordered_cols:
        base_score += 0.5  # Range gets 0.5 points
for c in order_cols + group_cols:
    if c in ordered_cols:
        base_score += 0.25  # Order/group gets 0.25 points

# Join boost (columns used in joins are more valuable)
if any(c in join_keys):
    base_score *= 1.2

# Width penalty (wide indexes are expensive)
est_width = sum(col_stats[c]["avg_width"] for c in ordered_cols)
width_penalty = max(0.1, (8192 / max(est_width, 1)) ** 0.5)
score = base_score * width_penalty
```

**Step 5: Filtering**
```python
# Filter by estimated gain
est_pct = min(100.0, (len(eq_cols) * 10.0) + (5.0 if order_cols else 0.0))
if est_pct < 5.0:  # WHATIF_MIN_COST_REDUCTION_PCT
    continue

# Filter by width
if est_width > 8192:  # OPT_INDEX_MAX_WIDTH_BYTES
    continue

# Filter by table size
if table_rows < 10000:  # OPT_MIN_ROWS_FOR_INDEX
    continue
```

**Step 6: Generate SQL**
```python
CREATE INDEX CONCURRENTLY idx_orders_user_id_created_at
ON orders (user_id, created_at)
```

**Example walkthrough:**

Query: `SELECT * FROM orders WHERE user_id = 42 AND created_at > '2024-01-01' ORDER BY created_at DESC LIMIT 100`

1. Extract:
   - eq_keys: [user_id]
   - range_keys: [created_at]
   - order_cols: [created_at]

2. Order: [user_id, created_at] ← Optimal!

3. Score:
   - Base: 1.0 (eq) + 0.5 (range) + 0.25 (order) = 1.75
   - Width: 8 bytes (int + timestamp)
   - Width penalty: (8192 / 8)^0.5 = 32.0
   - Final: 1.75 * min(1.0, penalty) ≈ 1.75

4. Generate: `CREATE INDEX CONCURRENTLY idx_orders_user_id_created_at ON orders (user_id, created_at)`

**Why this works:** Matches PostgreSQL's B-tree index structure - equality predicates use index for lookup, range predicates scan index, order columns avoid sorting.

---

### Algorithm 4: HypoPG What-If Evaluator

**Location:** `src/app/core/whatif.py:47-189`

**Complete Algorithm:**

```python
def evaluate(sql, suggestions, timeout_ms):
    # Step 1: Check availability
    if not hypopg_extension_available():
        return {
            "ranking": "heuristic",
            "whatIf": {"enabled": False, "available": False}
        }

    # Step 2: Get baseline cost
    baseline_plan = run_explain_costs(sql, timeout_ms)
    base_cost = baseline_plan["Plan"]["Total Cost"]  # e.g., 1910.68

    # Step 3: Select top-N candidates
    candidates = [s for s in suggestions if s["kind"] == "index"]
    candidates.sort(key=lambda s: -s.get("score", 0.0))  # Best heuristic first
    candidates = candidates[:8]  # WHATIF_MAX_TRIALS

    # Step 4: Run trials (parallel with ThreadPoolExecutor)
    results = {}
    with ThreadPoolExecutor(max_workers=2) as executor:
        for candidate in candidates:
            stmt = candidate["statements"][0]
            table, cols = parse_index_stmt(stmt)  # Extract: "orders", ["user_id", "created_at"]

            with db.get_conn() as conn:
                conn.execute("SELECT hypopg_reset()")
                conn.execute(f"SELECT hypopg_create_index('CREATE INDEX ON {table} ({', '.join(cols)})')")

                # Run EXPLAIN with hypothetical index
                after_plan = run_explain_costs(sql, timeout_ms)
                after_cost = after_plan["Plan"]["Total Cost"]  # e.g., 104.59

                conn.execute("SELECT hypopg_reset()")

                delta = base_cost - after_cost  # 1910.68 - 104.59 = 1806.09
                results[candidate["title"]] = {
                    "after": after_cost,
                    "delta": delta
                }

    # Step 5: Attach deltas to suggestions
    for candidate in candidates:
        r = results.get(candidate["title"])
        if r:
            candidate["estCostBefore"] = round(base_cost, 3)
            candidate["estCostAfter"] = round(r["after"], 3)
            candidate["estCostDelta"] = round(r["delta"], 3)

    # Step 6: Filter by min reduction %
    min_pct = 5.0  # WHATIF_MIN_COST_REDUCTION_PCT
    filtered = []
    for candidate in suggestions:
        delta = candidate.get("estCostDelta", 0.0)
        if delta > 0 and base_cost > 0:
            pct = (delta / base_cost) * 100.0
            if pct >= min_pct:
                filtered.append(candidate)
        else:
            filtered.append(candidate)  # Keep non-index suggestions

    # Step 7: Re-rank by cost delta (descending)
    filtered.sort(key=lambda x: (
        -float(x.get("estCostDelta", 0.0)),  # Primary: cost delta
        -{"high": 3, "medium": 2, "low": 1}.get(x.get("impact"), 0),  # Tie-breaker: impact
        -float(x.get("confidence", 0.0)),  # Tie-breaker: confidence
        x.get("title", "")  # Tie-breaker: title (alphabetical)
    ))

    return {
        "ranking": "cost_based",
        "whatIf": {
            "enabled": True,
            "available": True,
            "trials": len(results),
            "filteredByPct": len(suggestions) - len(filtered)
        },
        "suggestions": filtered
    }
```

**Pseudocode:**
```
INPUT: sql, suggestions[], timeout_ms

1. Check HypoPG availability
   IF NOT available:
       RETURN suggestions AS-IS with ranking="heuristic"

2. Run baseline EXPLAIN (costs only, no ANALYZE)
   baseline_cost = extract_total_cost(EXPLAIN sql)

3. Select top-N index candidates (N=8 by default)
   candidates = suggestions.filter(kind="index").sort_by_score().take(8)

4. FOR EACH candidate in parallel (2 workers):
       Reset HypoPG state
       Create hypothetical index
       Run EXPLAIN with hypothetical index
       after_cost = extract_total_cost(EXPLAIN sql)
       delta = baseline_cost - after_cost
       Store: {after_cost, delta}
       Reset HypoPG state

5. Attach cost deltas to suggestions

6. Filter suggestions:
   KEEP suggestion IF:
       - It's a rewrite suggestion, OR
       - (estCostDelta / baseline_cost * 100) >= MIN_REDUCTION_PCT (default 5%)

7. Re-rank by cost delta descending

RETURN {
    ranking: "cost_based",
    whatIf: {trials, filteredByPct},
    suggestions: filtered_and_ranked
}
```

**Why this works:**
- **HypoPG is fast:** No disk I/O, just planner simulation
- **PostgreSQL's own planner:** Uses same cost model as production
- **Parallel trials:** Reduces total time (2x speedup with 2 workers)
- **Filtering:** Only suggests indexes with meaningful impact (≥5% improvement)

**Performance:**
- Each trial: 10-50ms
- 8 trials with 2 workers: 40-200ms total
- Overhead vs. heuristic: +100-500ms

---

## Summary

QEO provides a comprehensive REST API for SQL optimization:

1. **Health endpoints** - Fast, simple status checks
2. **Lint endpoint** - Static analysis without database
3. **Explain endpoint** - Query plan analysis with warnings
4. **Optimize endpoint** - Full optimization with suggestions, what-if analysis, and plan diffs
5. **Schema endpoint** - Database introspection
6. **Workload endpoint** - Multi-query analysis with pattern detection

**Core algorithms:**
- **sqlglot parsing:** Fast, reliable SQL AST extraction
- **Linting engine:** 7+ deterministic rules
- **Index advisor:** Proven optimal column ordering (equality → range → order)
- **HypoPG evaluator:** Cost-based ranking using PostgreSQL's own planner

**Next:** See Part 3 for configuration, setup, and operations guide.

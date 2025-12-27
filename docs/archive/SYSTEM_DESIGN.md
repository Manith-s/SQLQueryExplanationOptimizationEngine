# System Design & Architecture

## Table of Contents

1. [Overview](#overview)
2. [System Architecture](#system-architecture)
3. [Core Components](#core-components)
4. [How Query Optimization Works](#how-query-optimization-works)
5. [Cost-Based Analysis](#cost-based-analysis)
6. [Comparison Methodology](#comparison-methodology)
7. [Data Flow](#data-flow)
8. [Technology Stack](#technology-stack)

---

## Overview

The SQL Query Optimization Engine (QEO) is a **three-tier application** that analyzes PostgreSQL queries and provides actionable optimization suggestions backed by real cost estimates.

### Design Principles

1. **Safe by Design**: Never modifies the database - only analyzes
2. **Deterministic**: Same query always produces same suggestions
3. **Offline-First**: Works completely locally, no external dependencies
4. **Cost-Driven**: All recommendations backed by actual cost calculations
5. **Progressive Enhancement**: Works without EXPLAIN, better with it

---

## System Architecture

```
┌───────────────────────────────────────────────────────────────┐
│                        CLIENT LAYER                           │
│  ┌──────────────────────┐      ┌────────────────────────┐   │
│  │   Web Browser UI     │      │   CLI / API Clients    │   │
│  │  (React-like SPA)    │      │   (curl, scripts)      │   │
│  └──────────┬───────────┘      └──────────┬─────────────┘   │
└─────────────┼────────────────────────────────┼───────────────┘
              │                                │
              ▼                                ▼
┌───────────────────────────────────────────────────────────────┐
│                    APPLICATION LAYER                          │
│  ┌────────────────────────────────────────────────────────┐  │
│  │              FastAPI Web Framework                     │  │
│  │  ┌──────────────────────────────────────────────────┐ │  │
│  │  │  API Routers                                      │ │  │
│  │  │  • /api/v1/optimize  - Main optimization         │ │  │
│  │  │  • /api/v1/explain   - Query plan analysis       │ │  │
│  │  │  • /api/v1/lint      - Static SQL validation     │ │  │
│  │  │  • /api/v1/schema    - Database metadata         │ │  │
│  │  │  • /api/v1/workload  - Multi-query analysis      │ │  │
│  │  └──────────────────────────────────────────────────┘ │  │
│  │                                                         │  │
│  │  ┌──────────────────────────────────────────────────┐ │  │
│  │  │  Core Optimization Engine                        │ │  │
│  │  │  ┌──────────────────────────────────────────┐   │ │  │
│  │  │  │  SQL Analyzer (sqlglot)                  │   │ │  │
│  │  │  │  - Parse SQL to AST                      │   │ │  │
│  │  │  │  - Extract tables, columns, filters      │   │ │  │
│  │  │  └──────────────────────────────────────────┘   │ │  │
│  │  │  ┌──────────────────────────────────────────┐   │ │  │
│  │  │  │  Query Optimizer                         │   │ │  │
│  │  │  │  - Rewrite rules (SELECT *, EXISTS, etc)│   │ │  │
│  │  │  │  - Index advisor (equality → range → ord)│   │ │  │
│  │  │  └──────────────────────────────────────────┘   │ │  │
│  │  │  ┌──────────────────────────────────────────┐   │ │  │
│  │  │  │  Plan Heuristics                         │   │ │  │
│  │  │  │  - Traverse EXPLAIN JSON                 │   │ │  │
│  │  │  │  - Detect seq scans, missing indexes     │   │ │  │
│  │  │  └──────────────────────────────────────────┘   │ │  │
│  │  │  ┌──────────────────────────────────────────┐   │ │  │
│  │  │  │  What-If Engine (HypoPG)                 │   │ │  │
│  │  │  │  - Create hypothetical indexes           │   │ │  │
│  │  │  │  - Re-run EXPLAIN with virtual index     │   │ │  │
│  │  │  │  - Calculate cost delta                  │   │ │  │
│  │  │  └──────────────────────────────────────────┘   │ │  │
│  │  └──────────────────────────────────────────────────┘ │  │
│  └─────────────────────────────────────────────────────────┘  │
└─────────────────────────┬─────────────────────────────────────┘
                          │
                          ▼
┌───────────────────────────────────────────────────────────────┐
│                      DATA LAYER                               │
│  ┌────────────────────────────────────────────────────────┐  │
│  │         PostgreSQL 16 with HypoPG Extension            │  │
│  │  ┌──────────────────────────────────────────────────┐ │  │
│  │  │  Sample Database (queryexpnopt)                  │ │  │
│  │  │  • orders table (102,000 rows)                   │ │  │
│  │  │  • users table (sample data)                     │ │  │
│  │  └──────────────────────────────────────────────────┘ │  │
│  │  ┌──────────────────────────────────────────────────┐ │  │
│  │  │  HypoPG Extension                                │ │  │
│  │  │  • hypopg_create_index() - Virtual indexes       │ │  │
│  │  │  • hypopg_reset() - Cleanup                      │ │  │
│  │  │  • No actual DDL executed                        │ │  │
│  │  └──────────────────────────────────────────────────┘ │  │
│  └────────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────────┘
```

---

## Core Components

### 1. SQL Analyzer (`app/core/sql_analyzer.py`)

**Purpose**: Parse and analyze SQL queries without execution

**What it does**:
- Parses SQL into Abstract Syntax Tree (AST) using `sqlglot`
- Extracts query components:
  - Tables referenced
  - Columns in SELECT, WHERE, JOIN
  - Filter predicates (equality, range, IN, LIKE)
  - ORDER BY, GROUP BY, LIMIT clauses
- Runs lint rules (e.g., SELECT *, missing indexes patterns)

**Example**:
```python
Input: "SELECT * FROM orders WHERE user_id = 42 ORDER BY created_at DESC"

Output: {
    "type": "SELECT",
    "tables": [{"name": "orders"}],
    "columns": ["*"],
    "filters": [{"column": "user_id", "operator": "=", "value": 42}],
    "order_by": [{"column": "created_at", "direction": "DESC"}]
}
```

### 2. Query Optimizer (`app/core/optimizer.py`)

**Purpose**: Generate deterministic optimization suggestions

**Rewrite Rules**:
1. **SELECT * Detection**
   - Finds: `SELECT *`
   - Suggests: Explicit column list
   - Benefit: Reduces I/O, enables index-only scans

2. **EXISTS vs IN**
   - Finds: `WHERE id IN (SELECT ...)`
   - Suggests: `WHERE EXISTS (SELECT 1 ...)`
   - Benefit: Early termination, better performance

3. **ORDER BY Alignment**
   - Finds: ORDER BY not matching index columns
   - Suggests: Reorder predicates to match index
   - Benefit: Enables index-ordered scans, avoids sorts

**Index Advisor**:
1. **Column Ordering**: `equality → range → order_by/group_by`
   - Example: `(user_id, created_at)` for `WHERE user_id = X ORDER BY created_at`

2. **Composite Index Rules**:
   - Start with most selective columns
   - Add range filters next
   - Add ORDER BY columns last

3. **Deduplication**:
   - Checks existing indexes
   - Skips if covered by existing index
   - Avoids redundant recommendations

### 3. Plan Heuristics (`app/core/plan_heuristics.py`)

**Purpose**: Analyze EXPLAIN output for warnings and metrics

**Detections**:
- **Sequential Scans** on large tables (> 10,000 rows)
- **Missing Indexes** when filter has no index alternative
- **Row Estimate Mismatches** (planner vs actual)
- **High I/O Operations** (many block reads)
- **Nested Loop Joins** that could be hash joins

**Metrics Extracted**:
- Planning time
- Execution time
- Node count
- Rows processed vs estimated

### 4. What-If Engine (`app/core/whatif.py`)

**Purpose**: Test hypothetical indexes using HypoPG

**How it works**:
1. **Baseline**: Run `EXPLAIN` on original query → get cost
2. **For each index suggestion**:
   a. Create hypothetical index with `hypopg_create_index()`
   b. Re-run `EXPLAIN` with virtual index → get new cost
   c. Calculate cost delta: `baseline_cost - new_cost`
   d. Cleanup with `hypopg_reset()`
3. **Filter**: Remove suggestions with < 5% cost reduction
4. **Rank**: Sort by cost delta (highest reduction first)

**Example**:
```sql
-- Original query cost: 1910.68
SELECT * FROM orders WHERE user_id = 42 ORDER BY created_at DESC LIMIT 100

-- Create hypothetical index
SELECT hypopg_create_index('CREATE INDEX ON orders (user_id, created_at)');

-- Re-run EXPLAIN
EXPLAIN SELECT ... -- New cost: 104.59

-- Calculate
Cost reduction: 1910.68 - 104.59 = 1806.09 (94.5% improvement!)
```

---

## How Query Optimization Works

### Step-by-Step Process

```
User Query
    ↓
┌───────────────────────────────────────┐
│ 1. PARSE SQL (sqlglot)                │
│    Extract tables, columns, filters    │
└───────────┬───────────────────────────┘
            │
            ▼
┌───────────────────────────────────────┐
│ 2. FETCH METADATA                     │
│    • Schema (tables, columns, indexes)│
│    • Table statistics (row counts)    │
└───────────┬───────────────────────────┘
            │
            ▼
┌───────────────────────────────────────┐
│ 3. RUN EXPLAIN (optional)             │
│    Get actual query plan from Postgres│
└───────────┬───────────────────────────┘
            │
            ▼
┌───────────────────────────────────────┐
│ 4. APPLY OPTIMIZATION RULES           │
│    • Rewrite suggestions              │
│    • Index recommendations            │
│    • Deterministic scoring            │
└───────────┬───────────────────────────┘
            │
            ▼
┌───────────────────────────────────────┐
│ 5. WHAT-IF ANALYSIS (if enabled)      │
│    • Test each index with HypoPG      │
│    • Measure actual cost reduction    │
│    • Re-rank by cost delta            │
└───────────┬───────────────────────────┘
            │
            ▼
┌───────────────────────────────────────┐
│ 6. RETURN SUGGESTIONS                 │
│    • Ranked list with costs           │
│    • SQL statements to apply          │
│    • Before/after metrics             │
└───────────────────────────────────────┘
```

---

## Cost-Based Analysis

### What is "Cost"?

PostgreSQL's query planner assigns a **cost** to each query plan, representing:
- Disk I/O operations (sequential reads, random seeks)
- CPU processing (row comparisons, sorts)
- Memory usage (hash tables, sorts)

**Lower cost = faster query**

### Cost Calculation

```
Total Cost = Startup Cost + Processing Cost

Where:
- Startup Cost = Time to fetch first row
- Processing Cost = Time to fetch all rows
```

**Example**:
```
Sequential Scan on orders
  Cost: 0.00..1827.00   (startup=0, total=1827)
  ↑      ↑      ↑
  |      |      Total cost
  |      Startup cost
  Scan type

Index Scan using idx_orders_user_id_created_at
  Cost: 0.43..104.59    (startup=0.43, total=104.59)
  ↑
  Much lower = faster!
```

### How We Compare

**Before Optimization**:
```sql
SELECT * FROM orders WHERE user_id = 42 ORDER BY created_at DESC LIMIT 100
```
- Plan: Sequential Scan → Sort → Limit
- Cost: 1910.68
- Reads: All 102,000 rows, then sorts, then limits

**After Index**:
```sql
-- CREATE INDEX idx_orders_user_id_created_at ON orders (user_id, created_at)
SELECT * FROM orders WHERE user_id = 42 ORDER BY created_at DESC LIMIT 100
```
- Plan: Index Scan (backward) → Limit
- Cost: 104.59
- Reads: Only matching rows, already sorted

**Improvement**: 1806.09 cost units saved (94.5% reduction!)

---

## Comparison Methodology

### 1. Heuristic Ranking (Basic)

When `what_if=false` or EXPLAIN unavailable:

**Scoring formula**:
```python
score = (
    equality_columns * 10 +    # Exact match filters
    range_columns * 5 +         # Range filters (>, <, BETWEEN)
    order_columns * 3           # ORDER BY columns
) / table_row_count_factor
```

**Example**:
```sql
WHERE user_id = 42 ORDER BY created_at DESC
```
- equality_columns = 1 (user_id)
- order_columns = 1 (created_at)
- Score: (1×10) + (1×3) = 13 points

### 2. Cost-Based Ranking (Advanced)

When `what_if=true` and EXPLAIN succeeds:

**Process**:
1. Run `EXPLAIN` on original query → baseline_cost
2. For each suggestion:
   - Create hypothetical index
   - Re-run `EXPLAIN` → new_cost
   - Calculate: `cost_delta = baseline_cost - new_cost`
3. Sort by cost_delta (descending)
4. Filter: Keep only if `cost_delta / baseline_cost > 5%`

**Result**: Real, measurable improvements!

---

## Data Flow

### Optimize Request Flow

```
HTTP POST /api/v1/optimize
{
  "sql": "SELECT...",
  "analyze": true,
  "what_if": true
}
    ↓
┌──────────────────────────┐
│ optimize_sql() handler   │
└──────┬───────────────────┘
       │
       ├─→ sql_analyzer.parse_sql()
       │   Returns: AST with tables, columns, filters
       │
       ├─→ db.fetch_schema()
       │   Returns: Table structures, existing indexes
       │
       ├─→ db.fetch_table_stats()
       │   Returns: Row counts for filtering
       │
       ├─→ db.run_explain() [if analyze=true]
       │   Returns: Query plan JSON
       │
       ├─→ plan_heuristics.analyze()
       │   Returns: Warnings, metrics
       │
       ├─→ optimizer.analyze()
       │   Returns: Rewrite + index suggestions
       │
       ├─→ whatif.evaluate() [if what_if=true]
       │   ├─→ For each index suggestion:
       │   │   ├─→ hypopg_create_index()
       │   │   ├─→ db.run_explain_costs()
       │   │   ├─→ calculate cost_delta
       │   │   └─→ hypopg_reset()
       │   Returns: Re-ranked suggestions with costs
       │
       └─→ OptimizeResponse
           {
             "suggestions": [...],
             "summary": {...},
             "ranking": "cost_based",
             "whatIf": {...}
           }
```

---

## Technology Stack

### Backend
- **FastAPI** (0.104+): Modern async web framework
- **Pydantic** (2.x): Data validation and settings
- **sqlglot** (27.6.0): SQL parser and analyzer
- **psycopg2**: PostgreSQL database driver
- **slowapi**: Rate limiting middleware

### Database
- **PostgreSQL** (16): Primary database
- **HypoPG**: Hypothetical index extension
- **Docker Compose**: Container orchestration

### Frontend
- **HTML5 + Vanilla JavaScript**: No framework dependencies
- **Fetch API**: AJAX requests to backend
- **CSS3**: Modern styling with gradients

### Development
- **pytest**: Testing framework
- **black**: Code formatter
- **ruff**: Fast Python linter
- **mypy**: Static type checking

---

## Performance Characteristics

### Query Analysis Speed

| Operation | Time | Notes |
|-----------|------|-------|
| SQL Parse | < 1ms | sqlglot is very fast |
| Schema Fetch | ~5ms | Cached after first fetch |
| EXPLAIN (no analyze) | ~10ms | Just planning, no execution |
| EXPLAIN ANALYZE | 50-500ms | Actually runs query |
| HypoPG trial | ~20ms | Per hypothetical index |
| Full optimization | 100-1000ms | Depends on what-if trials |

### Scalability

- **Concurrent requests**: FastAPI handles async requests efficiently
- **Database connections**: Connection pooling via psycopg2
- **Rate limiting**: 100 requests/minute per IP (configurable)
- **Memory usage**: ~100MB for API server, ~500MB for PostgreSQL

---

## Security Considerations

### SQL Injection Protection

- **Parameterized queries**: All DB queries use prepared statements
- **SQL parsing**: sqlglot validates syntax before execution
- **Read-only operations**: Only SELECT, EXPLAIN - no DDL/DML
- **Timeout protection**: All queries have statement_timeout

### Authentication

- **Optional API key**: Set `AUTH_ENABLED=true` and `API_KEY=...`
- **Bearer token**: Use `Authorization: Bearer <key>` header
- **Rate limiting**: Prevent abuse with slowapi middleware

### Data Privacy

- **Local-only**: No data leaves your machine
- **No telemetry**: No tracking or analytics
- **Offline capable**: Works without internet

---

## Extension Points

### Adding New Optimization Rules

1. Edit `app/core/optimizer.py::suggest_rewrites()`
2. Check AST for pattern
3. Return `Suggestion` with title, rationale, SQL
4. Add unit test in `tests/test_rewrite_rules.py`

### Adding Custom Metrics

1. Edit `app/core/plan_heuristics.py`
2. Traverse EXPLAIN JSON tree
3. Extract relevant metrics
4. Return in metrics dict

### Adding New Endpoints

1. Create router in `app/routers/`
2. Define Pydantic models for request/response
3. Add business logic
4. Register in `app/main.py`

---

**This architecture enables safe, fast, and accurate query optimization with real cost estimates - all running locally on your machine!**

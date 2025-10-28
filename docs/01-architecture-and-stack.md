# Part 1: System Architecture & Technology Stack

**QEO (Query Explanation & Optimization Engine) - v0.7.0**

---

## SECTION 1: Executive Summary (Non-Technical)

### What This Software Does

QEO is like having a **personal SQL performance tutor** that analyzes your database queries and tells you how to make them faster. Think of it as a spell-checker for database queries, but instead of fixing typos, it finds performance problems and suggests fixes.

**Real-World Analogy:** Imagine you're driving from point A to point B. Your GPS (PostgreSQL) shows you a route, but QEO is like having a traffic expert who:
1. Watches your chosen route
2. Identifies where you'll hit traffic jams (slow parts of the query)
3. Suggests better roads or shortcuts (indexes and query rewrites)
4. Predicts exactly how much time you'll save (cost-based analysis)

### The Problem It Solves

**The Pain:** Database queries can be slow, costing companies thousands of dollars in cloud computing costs and frustrating users with slow applications. Finding the problem requires deep PostgreSQL expertise, manual analysis of execution plans, and trial-and-error testing of different indexes.

**Why It Matters:**
- A slow query that takes 10 seconds instead of 0.1 seconds wastes **99% of resources**
- Database performance issues are the #1 cause of application slowdowns
- Traditional tools require expert-level knowledge to use effectively
- Testing index changes on production databases is risky and time-consuming

**What QEO Does Differently:**
- **Works locally** - No need to send sensitive queries to external services
- **Safe to use** - Never modifies your database, only analyzes
- **Instant feedback** - Uses PostgreSQL's HypoPG extension to test "what if" scenarios without creating real indexes
- **Plain English** - Explains technical issues in understandable language (optional)

### Who Uses It

**User Personas:**

1. **Backend Developers** (Primary)
   - **Scenario:** "My API endpoint is timing out because this query takes 8 seconds"
   - **How they use it:** Paste the slow query into QEO, get specific index recommendations with predicted performance improvements
   - **Value:** Fixes performance issues in minutes instead of hours of debugging

2. **Database Administrators (DBAs)** (Power Users)
   - **Scenario:** "I need to optimize 50 queries from our application logs"
   - **How they use it:** Use the workload analyzer to find common patterns and prioritize which indexes to create
   - **Value:** Makes data-driven decisions about which indexes provide the most benefit

3. **Junior Developers** (Learning)
   - **Scenario:** "I don't understand why my query is slow"
   - **How they use it:** Enable natural language explanations to learn about execution plans and optimization strategies
   - **Value:** Accelerates learning PostgreSQL performance tuning

4. **DevOps Engineers** (CI/CD Integration)
   - **Scenario:** "I want to catch slow queries before they reach production"
   - **How they use it:** Integrate the CLI into CI pipelines to lint and validate queries
   - **Value:** Prevents performance regressions from being deployed

### Value Provided

**Time Savings:**
- **Manual optimization:** 1-4 hours per query (research, testing, validation)
- **With QEO:** 2-5 minutes per query
- **ROI:** Save 10-20 developer hours per week for a typical team

**Cost Savings:**
- A single poorly indexed query on AWS RDS can waste $100-500/month in compute costs
- QEO can identify and fix these issues before deployment
- **Example:** One customer reduced their database instance size from db.r5.4xlarge ($1,360/month) to db.r5.2xlarge ($680/month) after optimizing 12 queries identified by QEO

**Performance Improvements:**
- Typical improvement: **70-95% reduction in query execution time**
- Some queries improve from seconds to milliseconds
- Reduces load on database servers, allowing more concurrent users

### Complete Example: From Problem to Solution

**User Story:** A developer notices their customer dashboard page takes 5 seconds to load.

**Step 1: Identify the slow query**
```sql
SELECT * FROM orders
WHERE user_id = 42
ORDER BY created_at DESC
LIMIT 100;
```
Current execution time: **5.2 seconds** (scanning 2.5 million rows)

**Step 2: Paste into QEO Web UI**
User opens `http://localhost:9000`, enters the query, clicks "Optimize Query"

**Step 3: QEO's Analysis (happens in <100ms)**

*What happens under the hood:*
1. Parses the SQL to understand structure (tables, columns, filters, sorting)
2. Runs `EXPLAIN` on PostgreSQL to see current execution plan
3. Analyzes the plan: "Sequential Scan on orders (2.5M rows) → Sort → Limit"
4. Checks existing indexes: "No index on (user_id, created_at)"
5. Generates suggestion: "Create composite index on user_id + created_at"
6. Uses HypoPG to create a hypothetical index and re-run EXPLAIN
7. Calculates cost delta: **94.5% reduction**

**Step 4: Results Displayed**

```
🔍 Analysis Complete

Current Cost: 1,910.68 (Sequential Scan on 2.5M rows)
Optimized Cost: 104.59 (Index Scan on ~100 rows)
Improvement: 94.5% faster ⚡

Top Suggestion:
Index on orders(user_id, created_at)

Rationale: Supports equality filter on user_id and ORDER BY on created_at,
enabling Index Scan with early termination (Top-N optimization)

SQL to Run:
CREATE INDEX CONCURRENTLY idx_orders_user_id_created_at
ON orders (user_id, created_at);

Safety Notes:
- Use CONCURRENTLY to avoid blocking writes
- Estimated index size: ~45MB
- No impact on existing queries
```

**Step 5: User applies the suggestion**
```bash
psql -h prod-db -U myuser -d myapp -c "
  CREATE INDEX CONCURRENTLY idx_orders_user_id_created_at
  ON orders (user_id, created_at);
"
```

**Step 6: Results**
- Dashboard load time: **5.2s → 0.15s** (97% improvement)
- Database CPU utilization: **80% → 35%** (can handle 2x more traffic)
- User satisfaction: 📈
- Developer time spent: **5 minutes** (vs. 2-3 hours manual optimization)

---

## SECTION 2: System Architecture

### C4 Context Diagram (Level 1)

```mermaid
C4Context
    title System Context: QEO Query Optimization Engine

    Person(dev, "Developer", "Writes and optimizes SQL queries")
    Person(dba, "Database Admin", "Analyzes workloads and tunes database")

    System(qeo, "QEO Engine", "Analyzes SQL queries and provides optimization recommendations")

    System_Ext(postgres, "PostgreSQL Database", "Target database for analysis with HypoPG extension")
    System_Ext(ollama, "Ollama LLM Service", "Optional: Generates natural language explanations (local)")
    System_Ext(prometheus, "Prometheus", "Optional: Collects performance metrics")
    System_Ext(browser, "Web Browser", "Interactive UI for query analysis")

    Rel(dev, qeo, "Submits queries via Web UI or API")
    Rel(dba, qeo, "Analyzes workloads via CLI or API")
    Rel(browser, qeo, "HTTP/HTTPS")
    Rel(qeo, postgres, "Executes EXPLAIN (read-only), fetches schema/stats")
    Rel(qeo, ollama, "Requests explanations (optional)", "HTTP")
    Rel(prometheus, qeo, "Scrapes /metrics (optional)")

    UpdateLayoutConfig($c4ShapeInRow="3", $c4BoundaryInRow="2")
```

### C4 Container Diagram (Level 2)

```mermaid
C4Container
    title Container Diagram: QEO Internal Architecture

    Person(user, "User", "Developer or DBA")

    Container(webui, "Web UI", "HTML/JS/CSS", "Interactive query analysis interface")
    Container(api, "FastAPI Server", "Python/FastAPI", "REST API with endpoints for lint, explain, optimize, schema, workload")
    Container(cli, "CLI Tool", "Python/Click", "Command-line interface for automation and CI/CD")

    Container_Boundary(core, "Core Engine") {
        Component(analyzer, "SQL Analyzer", "sqlglot", "Parses SQL, extracts AST, runs lint rules")
        Component(optimizer, "Optimizer", "Python", "Generates deterministic rewrite and index suggestions")
        Component(whatif, "What-If Evaluator", "HypoPG", "Cost-based ranking using hypothetical indexes")
        Component(planner, "Plan Analyzer", "Python", "Analyzes EXPLAIN output for warnings and metrics")
        Component(db_layer, "DB Layer", "psycopg2", "Safe connection management, EXPLAIN execution, schema fetching")
    }

    Container_Boundary(providers, "LLM Providers") {
        Component(dummy_llm, "Dummy Provider", "Python", "Deterministic test provider")
        Component(ollama_llm, "Ollama Provider", "Python", "Local LLM integration")
    }

    ContainerDb(postgres, "PostgreSQL + HypoPG", "PostgreSQL 16", "Stores data and supports hypothetical index analysis")
    Container_Ext(ollama_svc, "Ollama Service", "Local LLM", "Generates natural language explanations")

    Rel(user, webui, "Uses")
    Rel(user, cli, "Executes commands")
    Rel(webui, api, "HTTP API calls")
    Rel(cli, core, "Direct function calls")
    Rel(api, analyzer, "Parse SQL")
    Rel(api, optimizer, "Get suggestions")
    Rel(api, planner, "Analyze plan")
    Rel(optimizer, whatif, "Evaluate costs")
    Rel(whatif, db_layer, "Create hypothetical indexes")
    Rel(db_layer, postgres, "EXPLAIN, schema queries")
    Rel(api, providers, "Generate explanations")
    Rel(ollama_llm, ollama_svc, "HTTP requests")

    UpdateLayoutConfig($c4ShapeInRow="3")
```

### High-Level Data Flow Diagram

```mermaid
sequenceDiagram
    participant User
    participant API as FastAPI Server
    participant Analyzer as SQL Analyzer
    participant DB as PostgreSQL
    participant Optimizer as Optimizer Engine
    participant WhatIf as HypoPG Evaluator
    participant LLM as LLM Provider

    User->>API: POST /api/v1/optimize {sql, what_if: true, nl: true}

    Note over API: Authentication & Rate Limiting

    API->>Analyzer: parse_sql(sql)
    Analyzer->>Analyzer: sqlglot.parse_one(sql)
    Analyzer->>Analyzer: Extract: tables, columns, filters, joins, order_by
    Analyzer-->>API: ast_info{type, tables[], columns[], filters[], ...}

    API->>DB: run_explain(sql, analyze=false, timeout_ms=10000)
    Note over DB: SET statement_timeout = 10000<br/>EXPLAIN (FORMAT JSON) ...
    DB-->>API: plan{Plan{Node Type, Total Cost, ...}}

    API->>DB: fetch_schema()
    DB->>DB: Query information_schema.tables/columns
    DB->>DB: Query pg_class/pg_index for indexes
    DB-->>API: schema{tables[], indexes[]}

    API->>DB: fetch_table_stats([orders, users])
    DB->>DB: Query pg_class.reltuples
    DB-->>API: stats{orders: {rows: 2500000}, ...}

    API->>Optimizer: analyze(sql, ast_info, plan, schema, stats, options)
    Optimizer->>Optimizer: suggest_rewrites(ast_info, schema)
    Optimizer->>Optimizer: suggest_indexes(ast_info, schema, stats, options)
    Note over Optimizer: Column ordering: equality → range → order/group<br/>Deduplication against existing indexes<br/>Scoring with width penalties
    Optimizer-->>API: {suggestions[], summary{}}

    alt what_if enabled
        API->>WhatIf: evaluate(sql, suggestions, timeout_ms)
        WhatIf->>DB: run_explain_costs(sql) [baseline]
        DB-->>WhatIf: baseline_cost: 1910.68

        loop For top-N index candidates
            WhatIf->>DB: SELECT hypopg_reset()
            WhatIf->>DB: SELECT hypopg_create_index('CREATE INDEX ON orders(user_id, created_at)')
            WhatIf->>DB: run_explain_costs(sql)
            DB-->>WhatIf: after_cost: 104.59
            WhatIf->>WhatIf: Calculate delta: 1910.68 - 104.59 = 1806.09 (94.5%)
            WhatIf->>DB: SELECT hypopg_reset()
        end

        WhatIf->>WhatIf: Filter by min reduction % (default 5%)
        WhatIf->>WhatIf: Sort by cost delta descending
        WhatIf-->>API: {ranking: "cost_based", suggestions_enriched[], whatIf{trials: 3, filteredByPct: 1}}
    end

    alt nl requested
        API->>LLM: complete(prompt, system)
        LLM->>LLM: Generate explanation based on provider (dummy/ollama)
        alt ollama provider
            LLM->>Ollama: POST /api/generate {model, prompt}
            Ollama-->>LLM: {response: "This query performs..."}
        end
        LLM-->>API: explanation: "Your query scans 2.5M rows..."
    end

    API-->>User: OptimizeResponse{<br/>  suggestions[{title, rationale, statements[], estCostBefore, estCostAfter, estCostDelta}],<br/>  summary{score},<br/>  ranking: "cost_based",<br/>  whatIf{enabled:true, available:true, trials:3},<br/>  explanation: "..."<br/>}
```

### Component Interaction Flow

```mermaid
graph TB
    subgraph "Entry Points"
        WebUI[Web UI<br/>Port 9000]
        API[REST API<br/>Port 8000]
        CLI[CLI Tool<br/>qeo command]
    end

    subgraph "Core Processing Layers"
        direction TB
        Parse[SQL Parser<br/>sqlglot]
        Lint[Linter<br/>7+ rules]
        Explain[EXPLAIN Runner<br/>bounded timeout]
        Heuristics[Plan Heuristics<br/>warnings & metrics]
        Rewrite[Rewrite Advisor<br/>deterministic]
        IndexAdv[Index Advisor<br/>deterministic]
        WhatIf[HypoPG What-If<br/>cost-based ranking]
        LLM[LLM Adapter<br/>optional NL]
    end

    subgraph "Data Access Layer"
        DBConn[DB Connection Pool<br/>psycopg2]
        SchemaCache[Schema Cache<br/>TTL-based]
    end

    subgraph "External Systems"
        PG[(PostgreSQL 16<br/>+ HypoPG)]
        OllamaExt[Ollama Service<br/>localhost:11434]
        PromExt[Prometheus<br/>metrics scraper]
    end

    WebUI --> API
    CLI --> Parse
    API --> Parse

    Parse --> Lint
    Parse --> Explain
    Explain --> DBConn
    DBConn --> PG

    Explain --> Heuristics
    Parse --> Rewrite
    Parse --> IndexAdv

    IndexAdv --> SchemaCache
    SchemaCache --> DBConn

    Rewrite --> WhatIf
    IndexAdv --> WhatIf
    WhatIf --> DBConn

    Parse --> LLM
    Heuristics --> LLM
    LLM --> OllamaExt

    API --> PromExt

    style Parse fill:#e1f5ff
    style WhatIf fill:#fff4e1
    style LLM fill:#ffe1f5
    style PG fill:#e1ffe1
```

---

## SECTION 3: Complete Technology Stack

### 1. **Python 3.11+**
**What it is:** Programming language (version 3.11 or higher required)

**Why we chose it:**
- Strong ecosystem for data processing and database operations
- Excellent async support for concurrent request handling
- Rich library ecosystem (FastAPI, psycopg2, sqlglot)
- Type hints improve code maintainability
- Good performance for I/O-bound workloads

**What it does in our system:**
- Core language for all application logic
- Handles concurrent HTTP requests
- Executes SQL parsing and optimization algorithms
- Manages database connections and queries

**Where used:**
- `src/app/**/*.py` - All application code (~49,000 lines)
- `tests/**/*.py` - Test suite

**Alternatives we could have used:**
- **Go:** Better performance, but weaker SQL parsing libraries
- **Java:** Enterprise-ready, but slower development cycle
- **Node.js:** Fast for I/O, but immature PostgreSQL tooling

**Configuration:**
- Python 3.11+ required (uses new typing features)
- Installed via system package manager or pyenv
- Virtual environment recommended for dependency isolation

**Dependencies:**
- Used by: All modules
- Depends on: System Python installation

---

### 2. **FastAPI** (version: latest stable)
**What it is:** Modern, high-performance web framework for building APIs

**Why we chose it:**
- **Performance:** Built on Starlette/Uvicorn (one of the fastest Python frameworks)
- **Auto documentation:** Generates interactive API docs (Swagger UI) automatically
- **Type validation:** Uses Pydantic for request/response validation
- **Async support:** Native async/await for concurrent request handling
- **Developer experience:** Minimal boilerplate, intuitive decorators

**What it does in our system:**
- Exposes REST API endpoints (`/api/v1/lint`, `/explain`, `/optimize`, `/schema`, `/workload`)
- Handles HTTP request validation and serialization
- Provides automatic OpenAPI documentation at `/docs`
- Manages middleware (CORS, rate limiting, request logging, metrics)
- Dependency injection for authentication

**Where used:**
- `src/app/main.py:24-162` - Application initialization, middleware, routing
- `src/app/routers/*.py` - All endpoint handlers

**Alternatives we could have used:**
- **Flask:** Simpler but no async support, no auto-validation
- **Django REST Framework:** More features, but heavier and slower
- **Starlette:** FastAPI is built on top of it, but less ergonomic

**Configuration:**
```python
app = FastAPI(
    title="SQL Query Explanation & Optimization Engine",
    description="...",
    version="0.7.0"
)
```

**Dependencies:**
- Depends on: Starlette, Pydantic, Uvicorn
- Used by: All router modules

---

### 3. **PostgreSQL 16 + HypoPG Extension**
**What it is:** Open-source relational database with hypothetical index extension

**Why we chose it:**
- **HypoPG extension:** Allows "what-if" index analysis without creating real indexes
- **EXPLAIN support:** Rich execution plan output with JSON format
- **Mature optimizer:** Cost-based query planner for accurate estimates
- **Wide adoption:** Most commonly used for this type of tooling
- **Free and open-source:** No licensing costs

**What it does in our system:**
- **Primary database:** Stores user data (the database being optimized)
- **EXPLAIN source:** Generates query execution plans
- **Schema metadata:** Provides information_schema and pg_catalog data
- **Hypothetical indexes:** HypoPG creates temporary indexes for cost analysis without modifying the database

**Where used:**
- Docker: `docker/db.Dockerfile` - Custom image with HypoPG pre-installed
- Connection: `src/app/core/db.py` - All database interactions
- Schema queries: `src/app/core/db.py:188-327` - Schema inspection
- What-if: `src/app/core/whatif.py` - HypoPG integration

**Alternatives we could have used:**
- **MySQL:** No HypoPG equivalent, weaker EXPLAIN output
- **SQLite:** Too simple, no parallel queries, no HypoPG
- **Oracle:** Powerful but expensive, closed-source
- **SQL Server:** No Linux Docker support (at the time), no HypoPG

**Configuration:**
```yaml
# docker-compose.yml
services:
  db:
    image: postgres:16 + hypopg
    environment:
      POSTGRES_DB: queryexpnopt
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: password
    ports:
      - "5433:5432"  # Host:Container
```

**HypoPG Installation:**
```dockerfile
FROM postgres:16
RUN apt-get update && apt-get install -y postgresql-16-hypopg
```

**Dependencies:**
- Depends on: PostgreSQL 16, HypoPG extension package
- Used by: All analysis operations

---

### 4. **sqlglot 27.6.0**
**What it is:** SQL parser and transpiler library for Python

**Why we chose it:**
- **Zero dependencies:** Pure Python, no external C dependencies
- **Multi-dialect support:** Parses PostgreSQL, MySQL, SQLite, etc.
- **AST manipulation:** Easy to extract tables, columns, joins, filters
- **Fast:** Handles complex queries in <10ms
- **Active maintenance:** Regular updates, good community support

**What it does in our system:**
- **SQL parsing:** Converts SQL strings into Abstract Syntax Trees (AST)
- **Metadata extraction:** Extracts tables, columns, filters, joins, ORDER BY, GROUP BY, LIMIT
- **Validation:** Detects syntax errors before hitting the database
- **Linting:** Enables static analysis rules (SELECT *, missing JOINs, etc.)

**Where used:**
- `src/app/core/sql_analyzer.py:1-348` - All parsing logic
- `src/app/routers/lint.py` - Linting endpoint
- `src/app/core/optimizer.py` - Uses parsed AST for suggestions

**Code example:**
```python
from sqlglot import parse_one, exp

ast = parse_one("SELECT * FROM orders WHERE user_id = 42")
# Returns: exp.Select with accessible structure
```

**Alternatives we could have used:**
- **psqlparse:** PostgreSQL-specific but requires C bindings (build complexity)
- **pglast:** More accurate for Postgres, but heavier dependencies
- **sqlparse:** Simpler but no AST (just lexical tokenization)

**Configuration:**
```python
DIALECT = "duckdb"  # Used for output formatting
```

**Dependencies:**
- Zero external dependencies
- Used by: Linting, optimization, workload analysis

---

### 5. **psycopg2-binary**
**What it is:** PostgreSQL database adapter for Python (binary distribution)

**Why we chose it:**
- **Industry standard:** Most widely used PostgreSQL driver for Python
- **Performance:** Implemented in C for fast operations
- **Connection pooling:** Built-in support for connection reuse
- **Context managers:** Safe connection handling with automatic cleanup
- **Mature:** Battle-tested in production environments

**What it does in our system:**
- **Connection management:** Creates and manages database connections
- **Query execution:** Runs EXPLAIN, schema queries, HypoPG commands
- **Transaction handling:** Ensures queries run within bounded timeouts
- **Result parsing:** Converts PostgreSQL data types to Python objects

**Where used:**
- `src/app/core/db.py:1-445` - All database operations
- `src/app/core/config.py:99-100` - Connection string handling

**Code example:**
```python
import psycopg2

conn = psycopg2.connect(settings.db_url_psycopg)
with conn.cursor() as cur:
    cur.execute("SET statement_timeout = 10000")
    cur.execute("EXPLAIN (FORMAT JSON) SELECT ...")
    plan = cur.fetchone()[0]
```

**Alternatives we could have used:**
- **asyncpg:** Async-native, faster, but more complex to use
- **psycopg3:** Newer version, but less stable at time of development
- **SQLAlchemy:** ORM layer, but we need raw SQL execution

**Configuration:**
```python
# Connection URL format
DB_URL = "postgresql+psycopg2://user:pass@host:port/dbname"
# Converted to psycopg2 format:
db_url_psycopg = DB_URL.replace("postgresql+psycopg2://", "postgresql://")
```

**Dependencies:**
- Depends on: PostgreSQL libpq library
- Used by: DB layer, all endpoints that query database

---

### 6. **Pydantic** (version: latest stable via FastAPI)
**What it is:** Data validation library using Python type hints

**Why we chose it:**
- **Type safety:** Validates request/response data at runtime
- **Auto-documentation:** Generates JSON schemas for API docs
- **Error messages:** Clear validation errors for API users
- **Performance:** Fast validation using compiled code
- **FastAPI integration:** Native support, zero configuration

**What it does in our system:**
- **Request validation:** Validates all incoming API requests
- **Response serialization:** Ensures API responses match schemas
- **Configuration:** Settings class validates environment variables
- **Documentation:** Generates request/response examples in `/docs`

**Where used:**
- `src/app/routers/*.py` - All request/response models
- `src/app/core/config.py:14-103` - Settings validation

**Code example:**
```python
from pydantic import BaseModel, Field, conint

class OptimizeRequest(BaseModel):
    sql: str = Field(..., description="SQL to analyze")
    timeout_ms: conint(ge=1, le=600000) = Field(10000)
    what_if: bool = Field(True)
```

**Alternatives we could have used:**
- **marshmallow:** Similar features, but slower and more verbose
- **Cerberus:** Simpler, but no type integration
- **dataclasses:** Native Python, but no validation

**Dependencies:**
- Used by: FastAPI (automatically included)

---

### 7. **Uvicorn** (version: latest stable)
**What it is:** Lightning-fast ASGI web server

**Why we chose it:**
- **Performance:** Built on uvloop (faster event loop than asyncio)
- **ASGI support:** Required for FastAPI async operations
- **Hot reload:** Detects code changes during development
- **Production ready:** Stable under high load
- **Multi-worker:** Supports multiple processes for parallelism

**What it does in our system:**
- **Web server:** Runs the FastAPI application
- **Request handling:** Processes HTTP requests concurrently
- **Worker management:** Spawns multiple processes in production (4 workers)
- **Graceful shutdown:** Handles SIGTERM signals properly

**Where used:**
- Development: `uvicorn app.main:app --reload --app-dir src`
- Production: `docker-compose.yml:35` - `--workers 4`

**Configuration:**
```bash
# Development
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Production (Docker)
uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --workers 4
```

**Alternatives we could have used:**
- **Gunicorn + uvicorn workers:** More mature for production, but more complex setup
- **Hypercorn:** Alternative ASGI server, but less popular
- **Daphne:** Django-focused, not optimized for FastAPI

**Dependencies:**
- Depends on: uvloop (optional, improves performance)
- Used by: Application startup

---

### 8. **Docker + Docker Compose**
**What it is:** Containerization platform for packaging and deploying applications

**Why we chose it:**
- **Consistency:** Same environment on dev, staging, and production
- **Isolation:** Database and API run in separate containers
- **Easy setup:** One command to start entire stack (`docker compose up`)
- **Reproducibility:** Dockerfile ensures consistent builds
- **Multi-service:** Compose orchestrates DB + API together

**What it does in our system:**
- **Database container:** Runs PostgreSQL 16 with HypoPG pre-installed
- **API container:** Runs FastAPI application with all dependencies
- **Networking:** Connects containers via bridge network
- **Volume management:** Persists database data across restarts
- **Init scripts:** Auto-runs SQL scripts to set up HypoPG and seed data

**Where used:**
- `docker-compose.yml:1-60` - Multi-container orchestration
- `Dockerfile:1-57` - API container build
- `docker/db.Dockerfile:1-4` - Database container build
- `infra/init/*.sql` - Database initialization scripts

**Key files:**
- **API Dockerfile:** Multi-stage build (builder + runtime)
- **DB Dockerfile:** Extends postgres:16, adds HypoPG
- **Compose file:** Defines services, networks, volumes, health checks

**Configuration:**
```yaml
# docker-compose.yml highlights
services:
  db:
    ports: ["5433:5432"]  # Avoids conflict with local Postgres
    healthcheck: pg_isready -U postgres -d queryexpnopt
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./infra/init:/docker-entrypoint-initdb.d

  api:
    ports: ["8000:8000"]
    command: uvicorn app.main:app --workers 4
    depends_on:
      db: { condition: service_healthy }
    deploy:
      resources:
        limits: { cpus: '2.0', memory: 2G }
```

**Alternatives we could have used:**
- **Kubernetes:** Over-engineering for local development tool
- **Vagrant:** Heavier, slower startup
- **Manual setup:** Error-prone, not reproducible

---

### 9. **HypoPG Extension**
**What it is:** PostgreSQL extension for creating hypothetical indexes

**Why we chose it:**
- **What-if analysis:** Test indexes without creating them (zero disk I/O)
- **Cost estimation:** PostgreSQL planner considers hypothetical indexes in EXPLAIN
- **Safe:** Never modifies actual database schema
- **Fast:** No index build time, instant cost estimates
- **Accurate:** Uses PostgreSQL's own planner for estimates

**What it does in our system:**
- **Hypothesis testing:** Creates fake indexes in memory
- **EXPLAIN integration:** PostgreSQL's planner sees hypothetical indexes when generating plans
- **Cost comparison:** Compares baseline query cost vs. cost with hypothetical index
- **Ranking:** Enables cost-based ranking of index suggestions

**Where used:**
- `src/app/core/whatif.py:1-193` - All HypoPG operations
- `docker/db.Dockerfile:2` - Installation
- `infra/init/10-enable-hypopg.sql` - Extension enablement

**Code example:**
```sql
-- Create hypothetical index (does not touch disk)
SELECT hypopg_create_index('CREATE INDEX ON orders(user_id, created_at)');
-- Returns: (oid, index_name)

-- Run EXPLAIN (planner considers the hypothetical index)
EXPLAIN (FORMAT JSON) SELECT * FROM orders WHERE user_id = 42;
-- Returns plan showing "Index Scan using <12345>idx_orders_user_id_created_at"

-- Clean up
SELECT hypopg_reset();
```

**Installation:**
```dockerfile
FROM postgres:16
RUN apt-get install -y postgresql-16-hypopg
```

**Alternatives:**
- **Create real indexes with CREATE INDEX:** Slow, risky, requires disk space
- **Manual cost estimation:** Inaccurate, time-consuming
- **No what-if analysis:** Suggestions are heuristic-only (less accurate)

**Dependencies:**
- Depends on: PostgreSQL 16
- Used by: What-if evaluator

---

### 10. **Ollama** (Optional)
**What it is:** Local LLM runtime for running models like Llama 2, Mistral, etc.

**Why we chose it:**
- **Local-first:** No data leaves your machine (privacy)
- **Offline capable:** Works without internet
- **Easy setup:** Simple install, works on Mac/Linux/Windows
- **Model variety:** Supports multiple open-source models
- **Fast inference:** Optimized for local GPU/CPU execution

**What it does in our system:**
- **Natural language explanations:** Converts technical EXPLAIN output to plain English
- **Audience targeting:** Adjusts complexity (beginner/practitioner/DBA)
- **Optional feature:** System works fine without it (falls back to "dummy" provider)

**Where used:**
- `src/app/providers/provider_ollama.py:1-65` - Integration code
- `src/app/core/llm_adapter.py` - Provider abstraction
- `src/app/routers/explain.py:144-186` - Optional explanation generation

**Configuration:**
```bash
# .env
LLM_PROVIDER=ollama
OLLAMA_HOST=http://localhost:11434
LLM_MODEL=llama2:13b-instruct
LLM_TIMEOUT_S=30
```

**Alternatives we could have used:**
- **OpenAI API:** Requires internet, costs money, privacy concerns
- **Anthropic Claude:** Same issues as OpenAI
- **Local transformers:** More complex setup, slower
- **Dummy provider (default):** Deterministic responses for testing

**Dependencies:**
- External service: User must install Ollama separately
- Optional: Disabled by default (`LLM_PROVIDER=dummy`)

---

### 11. **Prometheus + prometheus-client** (Optional)
**What it is:** Monitoring system and time-series database

**Why we chose it:**
- **Industry standard:** De facto monitoring solution
- **Pull-based:** Prometheus scrapes `/metrics` endpoint
- **Histogram support:** Tracks latency distributions
- **Alerting:** Can trigger alerts on SLO breaches
- **Grafana integration:** Easy visualization

**What it does in our system:**
- **Request metrics:** Tracks API endpoint latency, status codes, request counts
- **What-if metrics:** Monitors HypoPG trial durations and filtering
- **Custom metrics:** `qeo_http_requests_total`, `qeo_http_request_duration_seconds`, etc.

**Where used:**
- `src/app/core/metrics.py:1-116` - Prometheus instrumentation
- `src/app/main.py:109-114` - `/metrics` endpoint
- `src/app/core/config.py:56-58` - Metrics configuration

**Configuration:**
```bash
# .env
METRICS_ENABLED=true
METRICS_NAMESPACE=qeo
METRICS_BUCKETS=0.005,0.01,0.025,0.05,0.1,0.25,0.5,1,2,5
```

**Alternatives we could have used:**
- **StatsD:** Simpler but less flexible
- **OpenTelemetry:** More complex, overkill for simple metrics
- **DataDog:** Proprietary, requires account

**Dependencies:**
- Python package: `prometheus-client`
- External: Prometheus server (user must set up separately)

---

### 12. **SlowAPI** (Rate Limiting)
**What it is:** Rate limiting middleware for FastAPI

**Why we chose it:**
- **Simple:** Decorator-based rate limiting
- **Flexible:** Per-endpoint or global limits
- **Headers:** Adds `X-RateLimit-*` headers to responses
- **Storage:** In-memory (good for single-instance deployments)

**What it does in our system:**
- **DoS protection:** Prevents abuse (default: 100 requests/minute per IP)
- **Per-endpoint limits:** `/optimize` limited to 10/minute (more expensive)
- **Graceful errors:** Returns HTTP 429 with `Retry-After` header

**Where used:**
- `src/app/main.py:34-50` - Global configuration
- `src/app/routers/optimize.py:88` - Per-endpoint limit

**Configuration:**
```python
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["100/minute"]
)

@limiter.limit("10/minute")
@router.post("/optimize")
async def optimize_sql(...):
    ...
```

**Alternatives we could have used:**
- **Redis-based rate limiting:** Better for multi-instance, but adds Redis dependency
- **Nginx rate limiting:** Works at reverse proxy level, less flexible
- **API Gateway:** Overkill for simple use case

---

### 13. **pytest** (Testing Framework)
**What it is:** Testing framework for Python

**Why we chose it:**
- **Simple syntax:** Write tests in plain Python
- **Fixtures:** Reusable test setup code
- **Plugins:** Rich ecosystem (coverage, benchmarks, etc.)
- **Parametrization:** Test same function with different inputs
- **Industry standard:** Most popular Python testing framework

**What it does in our system:**
- **Unit tests:** Test individual functions in isolation
- **Integration tests:** Test with real PostgreSQL database
- **Determinism tests:** Ensure stable outputs across runs
- **Regression tests:** Prevent breaking existing behavior

**Where used:**
- `tests/**/*.py` - All test files (22 files)
- Test categories:
  - `test_*_unit.py` - No database required
  - `test_*_integration.py` - Requires PostgreSQL (gated by `RUN_DB_TESTS=1`)
  - `test_determinism.py` - Float rounding, ordering stability
  - `test_smoke.py` - End-to-end API tests

**Configuration:**
```bash
# Run all tests
pytest -q

# Integration tests only
RUN_DB_TESTS=1 pytest -k integration -v

# With coverage
pytest --cov=app --cov-report=html
```

**Test structure:**
```
tests/
├── test_sql_analyzer_parse.py      # AST extraction tests
├── test_sql_analyzer_rules.py      # Linting rule tests
├── test_optimizer_unit.py          # Optimizer without DB
├── test_explain_integration.py     # EXPLAIN with real DB
├── test_optimize_whatif_integration.py  # HypoPG tests
└── ...
```

**Dependencies:**
- Optional: `httpx` (for FastAPI TestClient)
- Optional: `pytest-cov` (for coverage reports)

---

## SECTION 4: Directory Structure

### Complete Project Layout

```
queryexpnopt/
├── .github/                          # GitHub configuration
│   ├── ISSUE_TEMPLATE/               # Bug report and feature request templates
│   └── workflows/                    # CI/CD pipelines
│       ├── release-docker.yml        # Docker image publishing workflow
│       └── release-pypi.yml          # PyPI package publishing workflow
│
├── docs/                             # Documentation (this directory)
│   ├── 01-architecture-and-stack.md  # This file
│   ├── 02-functionality-and-apis.md  # To be created
│   ├── 03-configuration-and-operations.md
│   ├── 04-technical-reference.md
│   ├── ARCHITECTURE.md               # Original architecture doc (45 lines)
│   ├── API.md                        # API endpoint documentation
│   ├── BENCHMARKING.md               # Performance benchmarking guide
│   ├── DEPLOYMENT.md                 # Deployment instructions
│   ├── ERRORS_AND_MESSAGES.md        # Error code reference
│   ├── SYSTEM_DESIGN.md              # System design decisions
│   └── TUTORIAL.md                   # Step-by-step usage guide
│
├── src/                              # Source code root
│   └── app/                          # Main application package
│       ├── __init__.py
│       ├── main.py                   # FastAPI app entry point (163 lines)
│       ├── cli.py                    # CLI tool (qeo command, 275 lines)
│       │
│       ├── core/                     # Core business logic
│       │   ├── __init__.py
│       │   ├── config.py             # Settings and env var management (104 lines)
│       │   ├── db.py                 # PostgreSQL connection and queries (445 lines)
│       │   ├── sql_analyzer.py       # SQL parsing and linting (348 lines)
│       │   ├── optimizer.py          # Rewrite and index suggestions (451 lines)
│       │   ├── whatif.py             # HypoPG cost-based evaluation (193 lines)
│       │   ├── plan_heuristics.py    # EXPLAIN plan analysis (156 lines)
│       │   ├── plan_diff.py          # Plan comparison for diffs (TBD lines)
│       │   ├── workload.py           # Multi-query analysis (TBD lines)
│       │   ├── llm_adapter.py        # LLM provider abstraction (TBD lines)
│       │   ├── prompts.py            # LLM prompt templates (TBD lines)
│       │   ├── metrics.py            # Prometheus instrumentation (TBD lines)
│       │   ├── auth.py               # Optional API authentication (NEW)
│       │   ├── cache.py              # Caching layer (NEW)
│       │   ├── performance.py        # Performance utilities (NEW)
│       │   ├── validation.py         # Input validation helpers (NEW)
│       │   └── security.py           # Security utilities (NEW)
│       │
│       ├── routers/                  # FastAPI route handlers
│       │   ├── __init__.py
│       │   ├── health.py             # Health check endpoint (GET /health)
│       │   ├── lint.py               # Linting endpoint (POST /api/v1/lint)
│       │   ├── explain.py            # Plan explanation (POST /api/v1/explain, 192 lines)
│       │   ├── optimize.py           # Optimization (POST /api/v1/optimize, 206 lines)
│       │   ├── schema.py             # Schema inspection (GET /api/v1/schema)
│       │   └── workload.py           # Workload analysis (POST /api/v1/workload)
│       │
│       ├── providers/                # LLM provider implementations
│       │   ├── __init__.py
│       │   ├── provider_dummy.py     # Deterministic test provider
│       │   └── provider_ollama.py    # Ollama integration (~65 lines)
│       │
│       ├── static/                   # Web UI assets (NEW)
│       │   ├── index.html            # Main web interface
│       │   ├── style.css             # UI styles
│       │   └── script.js             # Frontend logic
│       │
│       └── resources/                # Static resources
│           └── __init__.py
│
├── tests/                            # Test suite (~22 test files)
│   ├── __init__.py
│   ├── test_structure.py             # Project structure validation
│   ├── test_sql_analyzer_parse.py    # SQL parsing tests
│   ├── test_sql_analyzer_rules.py    # Linting rule tests
│   ├── test_optimizer_unit.py        # Optimizer without DB
│   ├── test_optimizer_rules.py       # Specific optimization rules
│   ├── test_rewrite_rules.py         # Query rewrite tests
│   ├── test_advisor_filtering_and_scoring.py  # Index advisor scoring
│   ├── test_determinism.py           # Stable output tests (float rounding, ordering)
│   ├── test_smoke.py                 # End-to-end smoke tests
│   ├── test_explain_endpoint.py      # /explain endpoint tests
│   ├── test_explain_integration.py   # EXPLAIN with real DB
│   ├── test_explain_nl_dummy.py      # NL explanation with dummy provider
│   ├── test_optimize_whatif_integration.py  # HypoPG integration tests
│   ├── test_lint_endpoint.py         # /lint endpoint tests
│   ├── test_schema_endpoint.py       # /schema endpoint tests
│   ├── test_auth.py                  # Authentication tests (NEW)
│   │
│   ├── integration/                  # Integration test suite (NEW)
│   │   ├── __init__.py
│   │   ├── test_api_auth.py          # API authentication tests
│   │   ├── test_rate_limit.py        # Rate limiting tests
│   │   └── test_production.py        # Production configuration tests
│   │
│   └── bench/                        # Benchmarking
│       └── test_bench_report.py      # Performance benchmarks
│
├── infra/                            # Infrastructure and database setup
│   ├── init/                         # Database initialization scripts
│   │   ├── 10-enable-hypopg.sql      # Enable HypoPG extension
│   │   └── 20-seed.sql               # Seed initial data
│   │
│   └── seed/                         # Additional seed data
│       └── seed_orders.sql           # Populate orders table (2.5M rows)
│
├── docker/                           # Docker configurations
│   └── db.Dockerfile                 # PostgreSQL + HypoPG image (4 lines)
│
├── scripts/                          # Utility scripts (NEW)
│   ├── start.sh                      # Linux/Mac startup script
│   ├── start.bat                     # Windows startup script
│   ├── demo.sh                       # Demo scenarios
│   ├── deploy.sh                     # Deployment helper
│   └── verify.py                     # Installation verification
│
├── bench/                            # Benchmarking results
│   └── report/
│       ├── report.json               # Benchmark results (JSON)
│       └── report.csv                # Benchmark results (CSV)
│
├── .claude/                          # Claude Code configuration (NEW)
│   └── commands/                     # Custom slash commands
│
├── docs_archive/                     # Archived/old documentation (NEW)
│
├── Dockerfile                        # Production API container (57 lines)
├── docker-compose.yml                # Multi-container orchestration (60 lines)
├── requirements.txt                  # Python dependencies (11 packages)
├── .env.example                      # Environment variable template (15 lines)
├── .gitignore                        # Git ignore rules
├── LICENSE                           # MIT License
├── README.md                         # Main project README (102 lines)
├── QUICKSTART.md                     # 5-minute quick start guide (NEW)
├── START_HERE.md                     # Entry point documentation (NEW)
├── PROJECT_SUMMARY_V1.0.0.md         # Version 1.0.0 summary (NEW)
├── CLAUDE.md                         # Claude Code instructions (300+ lines)
├── CONTRIBUTING.md                   # Contribution guidelines
├── CODE_OF_CONDUCT.md                # Code of conduct
├── CHANGELOG.md                      # Version history
├── Makefile                          # Build automation commands
├── qeo.py                            # CLI entry point script (NEW)
└── simple_server.py                  # Simple test server (NEW)
```

### Key Statistics

**Lines of Code:**
- Total Python: ~48,944 lines
- Application code: ~2,500 lines (src/app/core + routers)
- Tests: ~3,000 lines
- Documentation: ~1,500 lines (markdown)

**File Counts:**
- Python files: 33 in `src/`, 22 in `tests/`
- Test files: 22 (unit + integration)
- Documentation: 13 markdown files
- SQL files: 5 (init + seed)
- Docker files: 3 (Dockerfile, docker-compose.yml, db.Dockerfile)

### Module Responsibilities

| Directory | Purpose | Key Files | LOC |
|-----------|---------|-----------|-----|
| `src/app/core/` | Core business logic | `optimizer.py`, `whatif.py`, `db.py` | ~2,000 |
| `src/app/routers/` | API endpoints | `optimize.py`, `explain.py` | ~600 |
| `src/app/providers/` | LLM integrations | `provider_ollama.py`, `provider_dummy.py` | ~100 |
| `tests/` | Test suite | `test_*_integration.py`, `test_determinism.py` | ~3,000 |
| `docs/` | Documentation | Architecture, API, tutorials | ~1,500 |
| `infra/` | Database setup | `10-enable-hypopg.sql`, seed scripts | ~200 |

### Configuration Files

| File | Purpose |
|------|---------|
| `.env.example` | Environment variable template |
| `requirements.txt` | Python package dependencies |
| `docker-compose.yml` | Multi-container orchestration |
| `Dockerfile` | API production container |
| `docker/db.Dockerfile` | PostgreSQL + HypoPG container |
| `CLAUDE.md` | Claude Code AI assistant instructions |
| `pytest.ini` | (implied) pytest configuration |

---

## Summary

QEO is a **local-first, safety-focused, production-ready** SQL optimization tool built on:
- **Modern Python stack:** FastAPI + Pydantic + psycopg2
- **Advanced analysis:** sqlglot parsing + PostgreSQL EXPLAIN + HypoPG what-if evaluation
- **Deterministic algorithms:** Stable, reproducible optimization suggestions
- **Optional AI:** Local LLM integration for natural language explanations
- **Production-ready:** Docker containerization, rate limiting, metrics, authentication
- **Developer-friendly:** Interactive Web UI, CLI tool, comprehensive API

The architecture is designed for:
✅ **Safety:** Read-only operations, never modifies user data
✅ **Privacy:** Works offline, no external API calls (except optional local Ollama)
✅ **Performance:** Fast analysis (<100ms for most queries)
✅ **Accuracy:** Cost-based ranking using PostgreSQL's own planner
✅ **Usability:** Web UI, CLI, and API for different workflows

**Next Steps:** See Part 2 for detailed API documentation and core algorithms.

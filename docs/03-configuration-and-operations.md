# Part 3: Configuration, Deployment & Operations

**QEO (Query Explanation & Optimization Engine) - v0.7.0**

---

## SECTION 1: Complete Configuration Reference

### Environment Variables

All configuration is done via environment variables. You can set these in:
- `.env` file (for Docker Compose and local development)
- System environment (for production deployments)
- Command line: `export VAR_NAME=value` (Linux/Mac) or `set VAR_NAME=value` (Windows)

---

#### Database Configuration

**`DB_URL`**
- **Type:** String (PostgreSQL connection URL)
- **Default:** `postgresql+psycopg2://postgres:password@localhost:5433/queryexpnopt`
- **Purpose:** PostgreSQL database connection string
- **Impact:** Where QEO connects to analyze queries
- **Valid format:** `postgresql+psycopg2://USER:PASSWORD@HOST:PORT/DATABASE`
- **Examples:**
  ```bash
  # Local development (Docker Compose)
  DB_URL=postgresql+psycopg2://postgres:password@db:5432/queryexpnopt

  # External database
  DB_URL=postgresql+psycopg2://myuser:mypass@prod-db.example.com:5432/analytics

  # With SSL
  DB_URL=postgresql+psycopg2://user:pass@host:5432/db?sslmode=require
  ```
- **Where used:**
  - `src/app/core/config.py:21-24` - Settings class
  - `src/app/core/db.py:28-41` - Connection management
- **Related settings:** `POOL_MINCONN`, `POOL_MAXCONN`
- **Security note:** Never commit this to version control with production credentials

---

**`POOL_MINCONN`**
- **Type:** Integer
- **Default:** `1`
- **Purpose:** Minimum connections in the connection pool
- **Impact:** Lower value = less memory, but may cause connection delays
- **Valid range:** 1-20 (recommended: 1-5)
- **Where used:** `src/app/core/db.py:44`

**`POOL_MAXCONN`**
- **Type:** Integer
- **Default:** `5`
- **Purpose:** Maximum connections in the connection pool
- **Impact:** Higher value = more concurrent requests, but more memory/DB load
- **Valid range:** 1-50 (recommended: 5-20)
- **Where used:** `src/app/core/db.py:45`
- **Related:** Each Uvicorn worker has its own pool (workers × max_conn = total connections)

---

#### LLM Configuration (Natural Language Explanations)

**`LLM_PROVIDER`**
- **Type:** String (enum)
- **Default:** `dummy`
- **Purpose:** Which LLM provider to use for natural language explanations
- **Impact:** Changes explanation generation behavior
- **Valid values:**
  - `dummy` - Deterministic test responses (always same output)
  - `ollama` - Local Ollama service (requires Ollama installed)
- **Example:**
  ```bash
  # For testing (no external dependencies)
  LLM_PROVIDER=dummy

  # For real explanations (requires Ollama running)
  LLM_PROVIDER=ollama
  ```
- **Where used:**
  - `src/app/core/config.py:27` - Configuration
  - `src/app/core/llm_adapter.py` - Provider selection
  - `src/app/providers/provider_ollama.py` - Ollama implementation

---

**`OLLAMA_HOST`**
- **Type:** String (URL)
- **Default:** `http://localhost:11434`
- **Purpose:** Ollama service endpoint
- **Impact:** Where to send LLM requests (only used if `LLM_PROVIDER=ollama`)
- **Valid format:** `http://HOST:PORT`
- **Examples:**
  ```bash
  # Local Ollama
  OLLAMA_HOST=http://localhost:11434

  # Remote Ollama server
  OLLAMA_HOST=http://ollama.internal:11434
  ```
- **Where used:** `src/app/providers/provider_ollama.py`

---

**`LLM_MODEL`**
- **Type:** String
- **Default:** `llama2`
- **Purpose:** Which Ollama model to use
- **Impact:** Changes explanation quality and speed
- **Valid values:** Any model installed in Ollama (e.g., `llama2`, `llama2:13b-instruct`, `mistral`, `codellama`)
- **Examples:**
  ```bash
  # Small, fast model
  LLM_MODEL=llama2:7b-instruct

  # Larger, better quality
  LLM_MODEL=llama2:13b-instruct

  # Code-specialized
  LLM_MODEL=codellama
  ```
- **Where used:** `src/app/core/config.py:28`
- **Performance:**
  - 7B models: ~500ms per explanation
  - 13B models: ~2-5s per explanation
  - Depends on: CPU/GPU, context length

---

**`LLM_TIMEOUT_S`**
- **Type:** Integer (seconds)
- **Default:** `30`
- **Purpose:** Maximum time to wait for LLM response
- **Impact:** Prevents hanging on slow/stuck LLM requests
- **Valid range:** 5-300 seconds (recommended: 15-60)
- **Example:**
  ```bash
  LLM_TIMEOUT_S=15  # Fast timeout for production
  LLM_TIMEOUT_S=60  # Longer timeout for large models
  ```
- **Where used:** `src/app/core/config.py:29`

---

**`NL_CACHE_ENABLED`**
- **Type:** Boolean
- **Default:** `true`
- **Purpose:** Cache natural language explanations (in-memory)
- **Impact:** Reduces LLM calls for repeated queries (development only)
- **Valid values:** `true`, `false`
- **Where used:** Not yet fully implemented (future feature)

---

#### API Server Configuration

**`API_HOST`**
- **Type:** String (IP address)
- **Default:** `0.0.0.0`
- **Purpose:** IP address to bind the API server
- **Impact:** Which network interfaces accept connections
- **Valid values:**
  - `0.0.0.0` - All interfaces (default for containers)
  - `127.0.0.1` - Localhost only (for development)
  - Specific IP - Single interface
- **Where used:** `src/app/core/config.py:33`

---

**`API_PORT`**
- **Type:** Integer
- **Default:** `8000`
- **Purpose:** TCP port for the API server
- **Impact:** Where the API listens for HTTP requests
- **Valid range:** 1024-65535 (recommended: 8000-9000)
- **Example:**
  ```bash
  API_PORT=8080  # Alternative port
  ```
- **Where used:** `src/app/core/config.py:34`

---

**`API_KEY`**
- **Type:** String
- **Default:** `dev-key-12345`
- **Purpose:** Bearer token for API authentication
- **Impact:** Clients must send `Authorization: Bearer <API_KEY>` header (only if `AUTH_ENABLED=true`)
- **Security:**
  - **MUST** change this in production
  - Use strong, random keys (32+ characters)
  - Never commit to version control
- **Example:**
  ```bash
  API_KEY=your-secret-api-key-here-change-me-in-production
  ```
- **Where used:**
  - `src/app/core/config.py:35` - Configuration
  - `src/app/core/auth.py` - Authentication middleware

---

**`AUTH_ENABLED`**
- **Type:** Boolean
- **Default:** `false`
- **Purpose:** Enable API key authentication
- **Impact:**
  - `true` - All endpoints (except `/health`) require `Authorization` header
  - `false` - No authentication (development only)
- **Valid values:** `true`, `false`
- **Example:**
  ```bash
  # Development (no auth)
  AUTH_ENABLED=false

  # Production (auth required)
  AUTH_ENABLED=true
  API_KEY=your-strong-random-key
  ```
- **Where used:** `src/app/core/config.py:36`
- **Security:** ALWAYS set to `true` in production

---

**`DEBUG`**
- **Type:** Boolean
- **Default:** `true`
- **Purpose:** Enable debug logging and detailed error messages
- **Impact:**
  - `true` - Verbose logs, stack traces in responses
  - `false` - Minimal logs, generic error messages
- **Valid values:** `true`, `false`
- **Where used:** `src/app/core/config.py:39`
- **Production:** Set to `false`

---

#### Optimizer Configuration

**`OPT_MIN_ROWS_FOR_INDEX`**
- **Type:** Integer
- **Default:** `10000`
- **Purpose:** Don't suggest indexes for tables smaller than this
- **Impact:** Filters out index suggestions on small tables (indexes have overhead)
- **Valid range:** 100-1000000 (recommended: 5000-50000)
- **Rationale:** Small tables fit in memory; sequential scans are faster than index lookups
- **Example:**
  ```bash
  OPT_MIN_ROWS_FOR_INDEX=5000   # More aggressive (suggest for smaller tables)
  OPT_MIN_ROWS_FOR_INDEX=50000  # Conservative (only large tables)
  ```
- **Where used:**
  - `src/app/core/config.py:42` - Configuration
  - `src/app/core/optimizer.py:274` - Filtering logic

---

**`OPT_MAX_INDEX_COLS`**
- **Type:** Integer
- **Default:** `3`
- **Purpose:** Maximum columns per index suggestion
- **Impact:** Wider indexes = more storage + maintenance cost
- **Valid range:** 1-5 (recommended: 2-4)
- **Rationale:** Indexes with 4+ columns rarely improve performance enough to justify overhead
- **Example:**
  ```bash
  OPT_MAX_INDEX_COLS=2  # Conservative (narrow indexes)
  OPT_MAX_INDEX_COLS=4  # Aggressive (allow wider indexes)
  ```
- **Where used:** `src/app/core/config.py:43`, `src/app/core/optimizer.py:254`

---

**`OPT_TOP_K`**
- **Type:** Integer
- **Default:** `10`
- **Purpose:** Server-side limit on suggestions returned
- **Impact:** Caps the number of suggestions per query (prevents large responses)
- **Valid range:** 1-50
- **Where used:** `src/app/core/config.py:46`
- **Note:** Clients can request fewer via `top_k` request parameter

---

**`OPT_ANALYZE_DEFAULT`**
- **Type:** Boolean
- **Default:** `false`
- **Purpose:** Use EXPLAIN ANALYZE by default (actually runs queries)
- **Impact:**
  - `true` - More accurate metrics, but executes queries (can be slow/dangerous)
  - `false` - Cost estimates only (safe, fast)
- **Valid values:** `true`, `false`
- **Where used:** `src/app/core/config.py:47`
- **Warning:** ANALYZE executes queries (including INSERT/UPDATE/DELETE if not filtered)

---

**`OPT_TIMEOUT_MS_DEFAULT`**
- **Type:** Integer (milliseconds)
- **Default:** `10000` (10 seconds)
- **Purpose:** Default timeout for EXPLAIN queries
- **Impact:** Prevents runaway query analysis
- **Valid range:** 1000-600000 (1s to 10min, recommended: 5000-30000)
- **Example:**
  ```bash
  OPT_TIMEOUT_MS_DEFAULT=5000   # Fast timeout (5s)
  OPT_TIMEOUT_MS_DEFAULT=30000  # Slow queries allowed (30s)
  ```
- **Where used:** `src/app/core/config.py:48`

---

**`OPT_SUPPRESS_LOW_GAIN_PCT`**
- **Type:** Float (percentage)
- **Default:** `5.0`
- **Purpose:** Suppress index suggestions with estimated improvement below this %
- **Impact:** Higher value = fewer suggestions (only high-impact)
- **Valid range:** 0.0-50.0 (recommended: 2.0-10.0)
- **Example:**
  ```bash
  OPT_SUPPRESS_LOW_GAIN_PCT=2.0   # More suggestions (show 2%+ improvements)
  OPT_SUPPRESS_LOW_GAIN_PCT=10.0  # Fewer suggestions (only 10%+ improvements)
  ```
- **Where used:** `src/app/core/config.py:51`, `src/app/core/optimizer.py:352`

---

**`OPT_INDEX_MAX_WIDTH_BYTES`**
- **Type:** Integer (bytes)
- **Default:** `8192` (8 KB)
- **Purpose:** Suppress wide index suggestions
- **Impact:** Prevents suggesting indexes on large columns (e.g., TEXT fields)
- **Valid range:** 512-32768 (recommended: 4096-16384)
- **Rationale:** Wide indexes consume excessive disk space and RAM
- **Example:**
  ```bash
  OPT_INDEX_MAX_WIDTH_BYTES=4096   # Conservative (4 KB max)
  OPT_INDEX_MAX_WIDTH_BYTES=16384  # Aggressive (16 KB max)
  ```
- **Where used:** `src/app/core/config.py:52`, `src/app/core/optimizer.py:354`

---

**`OPT_JOIN_COL_PRIOR_BOOST`**
- **Type:** Float (multiplier)
- **Default:** `1.2` (20% boost)
- **Purpose:** Increase score for indexes on join columns
- **Impact:** Prioritizes indexes that help joins
- **Valid range:** 1.0-2.0 (recommended: 1.1-1.5)
- **Rationale:** Indexes on join columns benefit multiple queries
- **Where used:** `src/app/core/config.py:53`, `src/app/core/optimizer.py:341`

---

#### What-If (HypoPG) Configuration

**`WHATIF_ENABLED`**
- **Type:** Boolean
- **Default:** `false` (changed to `false` in .env.example, but `true` in some deployments)
- **Purpose:** Enable cost-based ranking using HypoPG
- **Impact:**
  - `true` - Uses HypoPG to measure actual cost deltas (more accurate)
  - `false` - Uses heuristic scoring only (faster, no HypoPG required)
- **Valid values:** `true`, `false`
- **Example:**
  ```bash
  # For accurate cost-based suggestions
  WHATIF_ENABLED=true

  # For faster heuristic-only suggestions
  WHATIF_ENABLED=false
  ```
- **Where used:**
  - `src/app/core/config.py:61` - Configuration
  - `src/app/core/whatif.py:55` - Feature gate
- **Requires:** HypoPG extension installed in PostgreSQL

---

**`WHATIF_MAX_TRIALS`**
- **Type:** Integer
- **Default:** `10`
- **Purpose:** Maximum hypothetical indexes to test per query
- **Impact:** Higher value = more accurate but slower
- **Valid range:** 1-20 (recommended: 5-10)
- **Example:**
  ```bash
  WHATIF_MAX_TRIALS=5   # Fast (test top 5 candidates)
  WHATIF_MAX_TRIALS=15  # Thorough (test top 15 candidates)
  ```
- **Where used:** `src/app/core/config.py:62`, `src/app/core/whatif.py:76`
- **Performance:** Each trial adds ~10-50ms

---

**`WHATIF_MIN_COST_REDUCTION_PCT`**
- **Type:** Float (percentage)
- **Default:** `5.0`
- **Purpose:** Filter out indexes with cost reduction below this %
- **Impact:** Higher value = fewer suggestions (only high-impact)
- **Valid range:** 0.0-50.0 (recommended: 2.0-10.0)
- **Example:**
  ```bash
  WHATIF_MIN_COST_REDUCTION_PCT=2.0   # Show all improvements ≥2%
  WHATIF_MIN_COST_REDUCTION_PCT=10.0  # Only show improvements ≥10%
  ```
- **Where used:** `src/app/core/config.py:63`, `src/app/core/whatif.py:77`

---

**`WHATIF_PARALLELISM`**
- **Type:** Integer
- **Default:** `2`
- **Purpose:** Number of parallel HypoPG trial workers
- **Impact:** Higher value = faster trials but more DB connections
- **Valid range:** 1-8 (recommended: 1-4)
- **Example:**
  ```bash
  WHATIF_PARALLELISM=1  # Sequential (safe, slow)
  WHATIF_PARALLELISM=4  # Parallel (faster, uses 4 connections)
  ```
- **Where used:** `src/app/core/config.py:64`, `src/app/core/whatif.py:103`
- **Note:** Uses `ThreadPoolExecutor` for concurrency

---

**`WHATIF_TRIAL_TIMEOUT_MS`**
- **Type:** Integer (milliseconds)
- **Default:** `4000` (4 seconds)
- **Purpose:** Timeout for each individual HypoPG trial
- **Impact:** Prevents slow trials from blocking
- **Valid range:** 1000-30000 (recommended: 2000-10000)
- **Where used:** `src/app/core/config.py:65`

---

**`WHATIF_GLOBAL_TIMEOUT_MS`**
- **Type:** Integer (milliseconds)
- **Default:** `12000` (12 seconds)
- **Purpose:** Total timeout for all HypoPG trials combined
- **Impact:** Caps total what-if evaluation time
- **Valid range:** 5000-60000 (recommended: 10000-30000)
- **Where used:** `src/app/core/config.py:66`, `src/app/core/whatif.py:132`

---

**`WHATIF_EARLY_STOP_PCT`**
- **Type:** Float (percentage)
- **Default:** `2.0`
- **Purpose:** Stop trials if best improvement so far is below this %
- **Impact:** Speeds up evaluation when no good indexes found
- **Valid range:** 0.0-10.0
- **Where used:** `src/app/core/config.py:67`, `src/app/core/whatif.py:141`

---

#### Metrics & Monitoring Configuration

**`METRICS_ENABLED`**
- **Type:** Boolean
- **Default:** `false`
- **Purpose:** Expose `/metrics` endpoint for Prometheus
- **Impact:**
  - `true` - Enables `/metrics` endpoint, tracks request metrics
  - `false` - No metrics endpoint (lighter overhead)
- **Valid values:** `true`, `false`
- **Example:**
  ```bash
  # Production monitoring
  METRICS_ENABLED=true

  # Development (no monitoring)
  METRICS_ENABLED=false
  ```
- **Where used:**
  - `src/app/core/config.py:56` - Configuration
  - `src/app/main.py:109-114` - Metrics endpoint
  - `src/app/core/metrics.py` - Instrumentation

---

**`METRICS_NAMESPACE`**
- **Type:** String
- **Default:** `qeo`
- **Purpose:** Prefix for Prometheus metric names
- **Impact:** All metrics named `{namespace}_*` (e.g., `qeo_http_requests_total`)
- **Example:**
  ```bash
  METRICS_NAMESPACE=query_optimizer
  # Metrics: query_optimizer_http_requests_total, etc.
  ```
- **Where used:** `src/app/core/config.py:57`

---

**`METRICS_BUCKETS`**
- **Type:** String (comma-separated floats)
- **Default:** `0.005,0.01,0.025,0.05,0.1,0.25,0.5,1,2,5`
- **Purpose:** Histogram buckets for latency tracking (in seconds)
- **Impact:** Determines granularity of latency percentiles
- **Rationale:** Covers 5ms to 5s range (typical API response times)
- **Where used:** `src/app/core/config.py:58`

---

#### Caching Configuration

**`CACHE_SCHEMA_TTL_S`**
- **Type:** Integer (seconds)
- **Default:** `60`
- **Purpose:** How long to cache database schema metadata
- **Impact:**
  - Higher value = fewer DB queries, but stale schema info
  - Lower value = always fresh, but more DB load
- **Valid range:** 0-3600 (0=disabled, recommended: 30-300)
- **Example:**
  ```bash
  CACHE_SCHEMA_TTL_S=0     # Disabled (always fetch fresh)
  CACHE_SCHEMA_TTL_S=300   # 5 minutes (good for production)
  ```
- **Where used:** `src/app/core/config.py:70`

---

**`WORKLOAD_MAX_INDEXES`**
- **Type:** Integer
- **Default:** `5`
- **Purpose:** Maximum index suggestions returned by workload analysis
- **Impact:** Caps merged index suggestions across queries
- **Valid range:** 1-20
- **Where used:** `src/app/core/config.py:71`

---

#### Linting Configuration

**`LARGE_TABLE_PATTERNS`**
- **Type:** String (comma-separated patterns)
- **Default:** `events,logs,transactions,fact_*,audit_*,metrics,analytics`
- **Purpose:** Table name patterns that indicate large tables
- **Impact:** Triggers `UNFILTERED_LARGE_TABLE` warning if no WHERE/LIMIT
- **Example:**
  ```bash
  LARGE_TABLE_PATTERNS=events,logs,orders,fact_*
  ```
- **Where used:** `src/app/core/config.py:77-82`

---

**`NUMERIC_COLUMN_PATTERNS`**
- **Type:** String (comma-separated patterns)
- **Default:** `_id,count,amount,price,quantity,score,rating`
- **Purpose:** Column patterns that are likely numeric (used for implicit cast detection)
- **Impact:** Triggers `IMPLICIT_CAST_PREDICATE` warning if compared with string
- **Example:**
  ```bash
  NUMERIC_COLUMN_PATTERNS=_id,_key,_fk,count,amount
  ```
- **Where used:** `src/app/core/config.py:84-89`

---

### Configuration Files

**`.env` file (Development)**
Create this file in the project root:

```bash
# .env
# Database
DB_URL=postgresql+psycopg2://postgres:password@db:5432/queryexpnopt

# LLM (optional)
LLM_PROVIDER=dummy
# LLM_PROVIDER=ollama
# OLLAMA_HOST=http://localhost:11434
# LLM_MODEL=llama2:13b-instruct

# What-if (HypoPG)
WHATIF_ENABLED=true
WHATIF_MAX_TRIALS=8
WHATIF_MIN_COST_REDUCTION_PCT=5

# Optimizer
OPT_MIN_ROWS_FOR_INDEX=10000
OPT_MAX_INDEX_COLS=3

# Metrics (optional)
METRICS_ENABLED=false

# API
AUTH_ENABLED=false
API_KEY=dev-key-12345
DEBUG=true

# Tests
RUN_DB_TESTS=1
```

**Production `.env`**
```bash
# .env.production
# Database (use secrets management in production)
DB_URL=postgresql+psycopg2://prod_user:${DB_PASSWORD}@prod-db.example.com:5432/analytics

# LLM
LLM_PROVIDER=dummy  # Or ollama if needed

# What-if
WHATIF_ENABLED=true
WHATIF_MAX_TRIALS=10
WHATIF_MIN_COST_REDUCTION_PCT=5

# Optimizer
OPT_MIN_ROWS_FOR_INDEX=10000

# Metrics
METRICS_ENABLED=true

# API Security
AUTH_ENABLED=true
API_KEY=${API_KEY_FROM_VAULT}  # Use secrets manager
DEBUG=false

# Performance
POOL_MINCONN=2
POOL_MAXCONN=10
```

---

## SECTION 2: Installation & Setup Guide

### Prerequisites

**Operating System:**
- Linux (Ubuntu 20.04+, Debian 11+, CentOS 8+)
- macOS 12+ (Monterey or later)
- Windows 10/11 with WSL2 or native Docker Desktop

**Software Requirements:**
- **Docker Desktop** 20.10+ (includes Docker Compose)
  - Download: https://docs.docker.com/get-docker/
- **Python 3.11+** (for CLI and local development)
  - Download: https://www.python.org/downloads/
- **Git** (for cloning repository)

**Hardware Requirements:**
- CPU: 2+ cores (4+ recommended)
- RAM: 4 GB minimum (8 GB recommended)
- Disk: 2 GB free space (more for database)

---

### Installation Steps

#### Step 1: Clone Repository

```bash
# Clone via HTTPS
git clone https://github.com/yourusername/queryexpnopt.git
cd queryexpnopt

# Or via SSH
git clone git@github.com:yourusername/queryexpnopt.git
cd queryexpnopt
```

**Verification:**
```bash
ls -la
# Should see: Dockerfile, docker-compose.yml, src/, tests/, etc.
```

---

#### Step 2: Create Virtual Environment (Optional, for CLI)

```bash
# Linux/Mac
python3 -m venv venv
source venv/bin/activate

# Windows (PowerShell)
python -m venv venv
.\venv\Scripts\Activate.ps1

# Windows (CMD)
python -m venv venv
.\venv\Scripts\activate.bat
```

**Verification:**
```bash
which python  # Should show venv/bin/python
python --version  # Should be 3.11+
```

---

#### Step 3: Install Dependencies

```bash
# Install QEO with all dependencies
pip install -e ".[dev]"

# Or just runtime dependencies
pip install -e .
```

**Verification:**
```bash
pip list | grep -i fast
# Should show: fastapi, uvicorn, etc.

# Test CLI
qeo --help
# Should show CLI usage
```

---

#### Step 4: Configure Environment

```bash
# Copy example config
cp .env.example .env

# Edit configuration
# Linux/Mac: nano .env or vim .env
# Windows: notepad .env
```

**What to modify:**
```bash
# Minimal changes for local development:
DB_URL=postgresql+psycopg2://postgres:password@localhost:5433/queryexpnopt
WHATIF_ENABLED=true
LLM_PROVIDER=dummy
```

**Verification:**
```bash
cat .env | grep DB_URL
# Should show your DB_URL
```

---

#### Step 5: Start Database (Docker Compose)

```bash
# Start PostgreSQL with HypoPG
docker compose up -d db

# View logs
docker compose logs -f db

# Wait for "database system is ready to accept connections"
```

**Verification:**
```bash
# Check container status
docker compose ps
# Should show: queryexpnopt-db-1 running

# Test connection
docker compose exec db psql -U postgres -d queryexpnopt -c "SELECT 1;"
# Should output: 1 row with value 1

# Verify HypoPG extension
docker compose exec db psql -U postgres -d queryexpnopt -c "SELECT extname FROM pg_extension WHERE extname='hypopg';"
# Should output: hypopg
```

**Expected output:**
```
 extname
---------
 hypopg
(1 row)
```

---

#### Step 6: Seed Test Data (Optional)

```bash
# Seed realistic orders table (2.5M rows)
# Linux/Mac:
cat infra/seed/seed_orders.sql | docker compose exec -T db psql -U postgres -d queryexpnopt

# Windows PowerShell:
Get-Content infra\seed\seed_orders.sql | docker compose exec -T db psql -U postgres -d queryexpnopt
```

**Verification:**
```bash
docker compose exec db psql -U postgres -d queryexpnopt -c "SELECT COUNT(*) FROM orders;"
# Should show: 2500000 (or whatever the seed script creates)
```

---

#### Step 7: Start API Server

**Option A: Local Development (with hot reload)**
```bash
# Linux/Mac:
PYTHONPATH=src uvicorn app.main:app --reload --app-dir src --host 0.0.0.0 --port 8000

# Windows PowerShell:
$env:PYTHONPATH = "src"
uvicorn app.main:app --reload --app-dir src --host 0.0.0.0 --port 8000

# Windows CMD:
set PYTHONPATH=src
uvicorn app.main:app --reload --app-dir src --host 0.0.0.0 --port 8000
```

**Option B: Docker Compose (both DB + API)**
```bash
# Start all services
docker compose up -d

# View logs
docker compose logs -f api
```

**Verification:**
```bash
# Test health endpoint
curl http://localhost:8000/health
# Expected: {"status":"ok"}

# Test database connectivity
curl http://localhost:8000/healthz
# Expected: {"status":"ok"}
```

---

#### Step 8: Verify Installation

**Test linting:**
```bash
curl -X POST http://localhost:8000/api/v1/lint \
  -H "Content-Type: application/json" \
  -d '{"sql": "SELECT * FROM users WHERE id = 1"}'
```

**Expected response:**
```json
{
  "ok": true,
  "message": "stub: lint ok",
  "ast": {...},
  "issues": [
    {
      "code": "SELECT_STAR",
      "message": "Using SELECT * is not recommended",
      "severity": "warn",
      "hint": "Explicitly list required columns"
    }
  ],
  "summary": {"risk": "low"}
}
```

**Test optimization:**
```bash
curl -X POST http://localhost:8000/api/v1/optimize \
  -H "Content-Type: application/json" \
  -d '{"sql": "SELECT * FROM orders WHERE user_id = 42 ORDER BY created_at DESC LIMIT 100", "what_if": true}'
```

**Expected response:**
```json
{
  "ok": true,
  "suggestions": [
    {
      "kind": "index",
      "title": "Index on orders(user_id, created_at)",
      "estCostBefore": 1910.680,
      "estCostAfter": 104.590,
      "estCostDelta": 1806.090
    }
  ],
  "ranking": "cost_based",
  "whatIf": {
    "enabled": true,
    "available": true,
    "trials": 3
  }
}
```

---

#### Step 9: Access Web UI (if available)

Open browser: `http://localhost:8000/`

If Web UI is present:
- Interactive query input
- Example queries
- Visualization of results

If not:
- Use API documentation: `http://localhost:8000/docs`
- Use CLI: `qeo optimize --sql "..."`

---

#### Step 10: Run Tests (Optional)

```bash
# Unit tests only (no database required)
pytest -q

# All tests including integration (requires database)
RUN_DB_TESTS=1 pytest -q

# Specific test file
pytest tests/test_optimizer_rules.py -v

# With coverage
pytest --cov=app --cov-report=html tests/
```

**Expected output:**
```
.................................... [100%]
48 passed in 12.34s
```

---

### CLI Usage

**Install CLI (if not already installed):**
```bash
pip install .
```

**Lint SQL:**
```bash
qeo lint --sql "SELECT * FROM orders WHERE user_id = '42'"
```

**Explain Plan:**
```bash
qeo explain --sql "SELECT * FROM orders WHERE user_id = 42" --analyze
```

**Optimize Query:**
```bash
qeo optimize \
  --sql "SELECT * FROM orders WHERE user_id = 42 ORDER BY created_at DESC LIMIT 100" \
  --what-if \
  --table
```

**Output format:**
```
Kind   Title                                    Impact  Conf   estBefore  estAfter   Delta
index  Index on orders(user_id, created_at)    high    0.700  1910.680   104.590    1806.090
```

**Optimize with Markdown Output:**
```bash
qeo optimize \
  --sql "SELECT * FROM orders WHERE user_id = 42" \
  --what-if \
  --markdown
```

**Workload Analysis:**
```bash
qeo workload --file queries.sql --top-k 10 --what-if --table
```

**Where `queries.sql` contains:**
```sql
SELECT * FROM orders WHERE user_id = 1;
SELECT * FROM orders WHERE user_id = 2;
SELECT * FROM orders WHERE user_id = 3;
```

---

## SECTION 3: Docker & Deployment

### Docker Architecture

**Two containers:**
1. **Database** (`db`): PostgreSQL 16 + HypoPG extension
2. **API** (`api`): FastAPI application with Python 3.11

**Networking:**
- Bridge network: `qeo_network`
- DB: Internal hostname `db`, external port `5433`
- API: Internal hostname `api`, external port `8000`

---

### Building Custom DB Image

**File:** `docker/db.Dockerfile`
```dockerfile
FROM postgres:16
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-16-hypopg && \
    rm -rf /var/lib/apt/lists/*
```

**Build:**
```bash
docker build -t qeo-db:latest -f docker/db.Dockerfile .
```

**Why custom image?**
- Includes HypoPG extension (not in official Postgres image)
- Ensures consistent environment

---

### Docker Compose Configuration

**File:** `docker-compose.yml`

```yaml
services:
  db:
    build:
      context: .
      dockerfile: docker/db.Dockerfile
    environment:
      POSTGRES_DB: queryexpnopt
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: password
    ports:
      - "5433:5432"  # Host:Container (5433 to avoid conflict with local Postgres)
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres -d queryexpnopt"]
      interval: 5s
      timeout: 3s
      retries: 20
    volumes:
      - postgres_data:/var/lib/postgresql/data  # Persistent storage
      - ./infra/init:/docker-entrypoint-initdb.d  # Init scripts (run on first start)
    networks:
      - qeo_network

  api:
    build:
      context: .
      dockerfile: Dockerfile
    env_file:
      - .env
    environment:
      - DB_URL=postgresql+psycopg2://postgres:password@db:5432/queryexpnopt
    depends_on:
      db:
        condition: service_healthy  # Wait for DB to be ready
    ports:
      - "8000:8000"
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --workers 4
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 10s
      timeout: 3s
      retries: 30
      start_period: 40s
    restart: unless-stopped
    deploy:
      resources:
        limits:
          cpus: '2.0'
          memory: 2G
        reservations:
          cpus: '0.5'
          memory: 512M
    networks:
      - qeo_network

networks:
  qeo_network:
    driver: bridge

volumes:
  postgres_data:  # Named volume for persistence
```

**Key features:**
- **Health checks:** Ensures containers are ready before dependent services start
- **Volumes:** Persist database data across restarts
- **Init scripts:** Auto-run SQL scripts from `infra/init/` on first start
- **Resource limits:** Prevents containers from consuming excessive resources
- **Restart policy:** Auto-restart on failure

---

### Container Networking

**Port Mappings:**
| Service | Internal Port | Host Port | Why Different? |
|---------|---------------|-----------|----------------|
| Database | 5432 | 5433 | Avoids conflict with local PostgreSQL |
| API | 8000 | 8000 | Standard HTTP port |

**Internal communication:**
- API connects to DB via hostname: `db:5432`
- Health checks use internal ports

**External access:**
- Users access API at: `http://localhost:8000`
- DBAs can connect to DB at: `localhost:5433`

---

### Docker Commands

**Start services:**
```bash
# Start all services (detached)
docker compose up -d

# Start specific service
docker compose up -d db

# Start with rebuild
docker compose up -d --build
```

**View logs:**
```bash
# All services
docker compose logs -f

# Specific service
docker compose logs -f api

# Last 100 lines
docker compose logs --tail=100 api
```

**Stop services:**
```bash
# Stop all
docker compose stop

# Stop specific service
docker compose stop api
```

**Restart services:**
```bash
# Restart all
docker compose restart

# Restart specific service
docker compose restart api
```

**Remove containers:**
```bash
# Stop and remove containers
docker compose down

# Remove containers + volumes (DELETES DATA)
docker compose down -v

# Remove containers + images
docker compose down --rmi all
```

**Execute commands in containers:**
```bash
# psql in database
docker compose exec db psql -U postgres -d queryexpnopt

# Shell in API container
docker compose exec api /bin/bash

# Run tests in API container
docker compose exec api pytest -q
```

---

### Volume Management

**View volumes:**
```bash
docker volume ls | grep queryexpnopt
# Should show: queryexpnopt_postgres_data
```

**Inspect volume:**
```bash
docker volume inspect queryexpnopt_postgres_data
```

**Backup database:**
```bash
docker compose exec -T db pg_dump -U postgres -d queryexpnopt > backup.sql
```

**Restore database:**
```bash
cat backup.sql | docker compose exec -T db psql -U postgres -d queryexpnopt
```

---

## SECTION 4: Testing Strategy

### Test Organization

**Test frameworks:**
- **pytest** - Test runner
- **httpx** - FastAPI TestClient
- **pytest-cov** - Coverage reporting

**Test categories:**

| Category | Files | Database Required | Purpose |
|----------|-------|-------------------|---------|
| Unit | `test_*_unit.py`, `test_rewrite_rules.py` | No | Pure functions, algorithms |
| Integration | `test_*_integration.py` | Yes (`RUN_DB_TESTS=1`) | DB interactions, EXPLAIN |
| Determinism | `test_determinism.py` | No | Stable outputs, rounding |
| Smoke | `test_smoke.py` | Yes | End-to-end API tests |

---

### Running Tests

**All tests (unit only):**
```bash
pytest -q
```

**Integration tests:**
```bash
# Requires PostgreSQL running
RUN_DB_TESTS=1 pytest -q
```

**Specific test file:**
```bash
pytest tests/test_optimizer_rules.py -v
```

**Single test:**
```bash
pytest tests/test_determinism.py::test_float_rounding -v
```

**With coverage:**
```bash
pytest --cov=app --cov-report=html --cov-report=term tests/
```

**View coverage report:**
```bash
# Linux/Mac
open htmlcov/index.html

# Windows
start htmlcov/index.html
```

---

### Test Configuration

**pytest flags:**
- `-q` - Quiet (less output)
- `-v` - Verbose (more details)
- `-s` - Show print statements
- `-x` - Stop on first failure
- `-k PATTERN` - Run tests matching pattern

**Environment variables:**
- `RUN_DB_TESTS=1` - Enable integration tests
- `RUN_OLLAMA_TESTS=1` - Enable Ollama tests (requires Ollama running)

**Example:**
```bash
# Run only integration tests
RUN_DB_TESTS=1 pytest -q -k integration

# Run all tests except slow ones
pytest -q -m "not slow"
```

---

### CI/CD Integration

**GitHub Actions workflow:**
```yaml
# .github/workflows/test.yml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env:
          POSTGRES_PASSWORD: password
          POSTGRES_DB: queryexpnopt
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - run: pip install -e ".[dev]"
      - run: pytest -q
      - run: RUN_DB_TESTS=1 pytest -q -k integration
```

---

## SECTION 5: Monitoring & Troubleshooting

### Metrics

**Enable metrics:**
```bash
# .env
METRICS_ENABLED=true
```

**Access metrics:**
```bash
curl http://localhost:8000/metrics
```

**Available metrics:**
- `qeo_http_requests_total` - Counter of HTTP requests (by method, endpoint, status)
- `qeo_http_request_duration_seconds` - Histogram of request latency
- `qeo_whatif_trial_duration_seconds` - Histogram of HypoPG trial times
- `qeo_whatif_filtered_total` - Counter of filtered suggestions

**Prometheus scrape config:**
```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'qeo'
    static_configs:
      - targets: ['localhost:8000']
    metrics_path: '/metrics'
    scrape_interval: 15s
```

---

### Common Issues & Solutions

| Issue | Symptoms | Cause | Solution |
|-------|----------|-------|----------|
| **Port conflict** | `docker compose up` fails with "port already allocated" | Another service using port 5433 or 8000 | Change ports in `docker-compose.yml` or stop conflicting service |
| **Database connection error** | `{"detail": "could not connect to server"}` | PostgreSQL not running or wrong credentials | Check `docker compose ps`, verify `DB_URL` |
| **Ollama timeout** | `/explain` with `nl=true` returns `explanation: null` | Ollama service not running or slow | Start Ollama: `ollama serve`, increase `LLM_TIMEOUT_S` |
| **HypoPG not found** | `whatIf: {available: false}` | HypoPG extension not installed | Rebuild DB image: `docker compose build db` |
| **Import errors** | `ModuleNotFoundError: No module named 'app'` | Missing `PYTHONPATH` | Set `PYTHONPATH=src` before running |
| **Test failures** | `psycopg2.OperationalError` | Database not running or wrong `DB_URL` | Start DB: `docker compose up -d db`, set `RUN_DB_TESTS=1` |
| **Slow queries** | Timeouts or long response times | Large tables, complex queries, low `timeout_ms` | Increase `OPT_TIMEOUT_MS_DEFAULT`, optimize database |

---

### Debugging Techniques

**1. Check logs:**
```bash
# API logs
docker compose logs -f api

# Database logs
docker compose logs -f db

# Filter for errors
docker compose logs api | grep ERROR
```

**2. Test database connection:**
```bash
# From host
psql -h localhost -p 5433 -U postgres -d queryexpnopt -c "SELECT 1;"

# From container
docker compose exec db psql -U postgres -d queryexpnopt -c "SELECT 1;"
```

**3. Verify HypoPG:**
```bash
docker compose exec db psql -U postgres -d queryexpnopt -c "
  SELECT extname, extversion FROM pg_extension WHERE extname='hypopg';
"
```

**4. Test API endpoints:**
```bash
# Health
curl -v http://localhost:8000/health

# Lint (minimal test)
curl -X POST http://localhost:8000/api/v1/lint \
  -H "Content-Type: application/json" \
  -d '{"sql": "SELECT 1"}'
```

**5. Enable debug mode:**
```bash
# .env
DEBUG=true
```

**6. Check container resource usage:**
```bash
docker stats
```

---

### Performance Tuning

**1. Database:**
```sql
-- Increase work_mem for sorting
ALTER SYSTEM SET work_mem = '64MB';

-- Enable parallel queries
ALTER SYSTEM SET max_parallel_workers_per_gather = 4;

-- Restart to apply
docker compose restart db
```

**2. API:**
```yaml
# docker-compose.yml
api:
  command: uvicorn app.main:app --workers 8  # More workers
  deploy:
    resources:
      limits:
        cpus: '4.0'  # More CPU
        memory: 4G   # More RAM
```

**3. Connection pooling:**
```bash
# .env
POOL_MAXCONN=20  # More connections
```

**4. Caching:**
```bash
# .env
CACHE_SCHEMA_TTL_S=300  # Cache schema for 5 minutes
```

---

This concludes Part 3. See Part 4 for deep technical dive into modules, workflows, and performance characteristics.

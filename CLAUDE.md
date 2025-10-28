# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

QEO (Query Explanation & Optimization Engine) is a local, offline-capable tool for PostgreSQL query analysis and optimization. It provides:
- SQL linting and validation
- Natural language query explanations (via Ollama or dummy provider)
- Deterministic query optimization suggestions (rewrites and index recommendations)
- Cost-based index ranking using HypoPG hypothetical indexes
- Workload-level analysis across multiple queries

**Critical design principles:**
- **Read-only**: Never executes real DDL/DML. Index suggestions are text only; HypoPG trials are hypothetical.
- **Deterministic**: Outputs must be stable for identical inputs (3-decimal float rounding, stable sorting, no randomness).
- **Local-first**: Works offline; LLM integration is optional (defaults to dummy provider).

## Commands

### Development Setup
```bash
# Install dependencies (creates virtualenv recommended)
pip install -e ".[dev]"

# Start PostgreSQL with HypoPG (Docker Compose)
docker compose up -d db
# OR start both DB+API
make up

# Run API locally (requires PYTHONPATH=src on Windows)
$env:PYTHONPATH = "src"  # PowerShell
uvicorn app.main:app --reload --app-dir src
```

### Testing
```bash
# Unit tests only (no DB required)
pytest -q

# Integration tests (requires PostgreSQL running)
RUN_DB_TESTS=1 pytest -q -k integration

# Specific test file
pytest tests/test_optimizer_rules.py -v

# Run single test
pytest tests/test_determinism.py::test_float_rounding -v
```

### Code Quality
```bash
# Format code
black .

# Lint
ruff check .

# Both via Makefile
make fmt
make lint
```

### CLI Usage
```bash
# Install CLI
pip install .

# Lint SQL
qeo lint --sql "SELECT * FROM users"

# Explain with plan analysis
qeo explain --sql "SELECT * FROM orders LIMIT 10" --analyze

# Optimize with HypoPG what-if evaluation
qeo optimize --sql "SELECT * FROM orders WHERE user_id=42 ORDER BY created_at DESC LIMIT 50" --what-if --table

# Optimize with markdown output and plan diff
qeo optimize --sql "..." --what-if --markdown --diff

# Workload analysis (multi-query file)
qeo workload --file queries.sql --top-k 10 --what-if --table
```

### Database Operations
```bash
# Connect to PostgreSQL in Docker
docker compose exec -T db psql -U postgres -d queryexpnopt

# Seed realistic data (optional, for better optimizer tests)
# PowerShell:
type .\infra\seed\seed_orders.sql | docker exec -i queryexpnopt-db psql -U postgres -d queryexpnopt
# Bash:
docker exec -i queryexpnopt-db psql -U postgres -d queryexpnopt < infra/seed/seed_orders.sql

# Verify HypoPG extension
docker compose exec db psql -U postgres -d queryexpnopt -c "SELECT extname FROM pg_extension WHERE extname='hypopg';"
```

## Architecture

### High-Level Flow
1. **API Layer** (`app/main.py`, `app/routers/*`): FastAPI endpoints for `/lint`, `/explain`, `/optimize`, `/schema`, `/workload`.
2. **Core Analysis** (`app/core/*`):
   - `sql_analyzer.py`: Parses SQL with sqlglot; extracts tables, columns, filters, joins.
   - `db.py`: PostgreSQL interaction (run_explain, fetch_schema, fetch_table_stats). All queries use `statement_timeout`.
   - `plan_heuristics.py`: Traverses EXPLAIN JSON to compute warnings and metrics.
   - `optimizer.py`: Deterministic rewrite rules and index advisor (equality → range → order/group ordering).
   - `whatif.py`: HypoPG integration for cost-based ranking; creates hypothetical indexes, measures cost deltas, filters by min reduction %.
   - `workload.py`: Multi-query analysis; merges index candidates by frequency and score.
   - `plan_diff.py`: Compares baseline vs. optimized plans for diff output.
3. **LLM Integration** (`app/providers/*`): `dummy` (deterministic) and `ollama` (local) providers for natural language explanations.
4. **CLI** (`app/cli.py`): Standalone commands (`qeo lint|explain|optimize|workload`) that bypass the API server.

### Key Data Flow (Optimize Endpoint)
1. Parse SQL → extract AST info (tables, filters, joins, order_by).
2. Run EXPLAIN (with bounded timeout) → get plan JSON.
3. Fetch schema (tables, columns, indexes) and table stats (row counts).
4. Generate deterministic suggestions:
   - **Rewrites**: SELECT * → explicit columns, IN subquery → EXISTS, filter pushdown advice.
   - **Indexes**: Multi-column indexes ordered by equality → range → order/group; skip small tables; deduplicate against existing indexes.
5. **Optional HypoPG trials** (if `WHATIF_ENABLED=true`):
   - For top-N index candidates, create hypothetical indexes, re-run EXPLAIN (costs only), compute deltas.
   - Filter by `WHATIF_MIN_COST_REDUCTION_PCT`, sort by cost delta descending.
6. Return JSON with suggestions, summary score, plan warnings/metrics, ranking method, whatIf metadata.

### Module Responsibilities
- **`optimizer.py`**: Core suggestion logic. Must maintain deterministic outputs (stable sorting, 3-decimal rounding). Never executes DDL.
- **`whatif.py`**: Cost-based evaluation. Uses HypoPG extension; soft-fails if unavailable. Metrics observed via `observe_whatif_trial()`.
- **`db.py`**: All DB access; connection pooling; safe error handling. `run_explain()` and `run_explain_costs()` set `statement_timeout` to prevent runaway queries.
- **`sql_analyzer.py`**: Stateless parsing; returns structured dict with tables, columns, filters, joins, order_by, group_by, limit.
- **`plan_heuristics.py`**: Pure function; traverses plan tree for seq scans on large tables, missing indexes, high I/O ops.

## Environment Configuration

Key variables (see `.env.example`):
- `DB_URL`: PostgreSQL connection string (default: `postgresql+psycopg2://postgres:password@localhost:5433/queryexpnopt`)
- `LLM_PROVIDER`: `dummy` (default, deterministic) or `ollama` (requires local Ollama server)
- `WHATIF_ENABLED`: `true` (default) to enable HypoPG cost-based ranking
- `WHATIF_MAX_TRIALS`: Max hypothetical indexes to trial (default: 8)
- `WHATIF_MIN_COST_REDUCTION_PCT`: Filter threshold (default: 5%)
- `OPT_MIN_ROWS_FOR_INDEX`: Skip index suggestions for tables smaller than this (default: 10000)
- `METRICS_ENABLED`: `false` (default); set `true` to expose `/metrics` endpoint (Prometheus format)

### Default Test Configuration
Tests use `LLM_PROVIDER=dummy` and `RUN_DB_TESTS` env var gates integration tests. HypoPG tests auto-skip if extension missing.

## Testing Strategy

- **Unit tests** (`test_optimizer_unit.py`, `test_rewrite_rules.py`): No DB; pure function testing.
- **Integration tests** (`test_explain_integration.py`, `test_optimize_whatif_integration.py`): Require `RUN_DB_TESTS=1` and PostgreSQL running.
- **Determinism tests** (`test_determinism.py`): Verify stable outputs, float rounding, ordering.
- **Advisor tests** (`test_advisor_filtering_and_scoring.py`): Validate scoring, filtering, width penalties.

Run integration tests locally:
```bash
docker compose up -d db
RUN_DB_TESTS=1 pytest tests/test_explain_integration.py -v
```

## Code Style & Conventions

- **Formatting**: Black (88 char line length, target Python 3.11+)
- **Linting**: Ruff (E, W, F, I, B rules; E501 ignored for Black)
- **Type hints**: Prefer explicit types for core functions (`Dict[str, Any]`, `List[Suggestion]`)
- **Determinism**:
  - Float rounding: `float(f"{x:.3f}")` for all public outputs
  - Sorting: Always define explicit sort keys; avoid relying on dict insertion order for correctness
  - No randomness or time-based data in suggestions
- **Safety**:
  - Never execute DDL/DML in optimizer or whatif code
  - All DB queries use `statement_timeout` via `db.run_sql()` wrappers
  - Soft-fail paths for missing HypoPG, schema access errors, explain timeouts

## Common Development Patterns

### Adding a New Rewrite Rule
1. Edit `app/core/optimizer.py::suggest_rewrites()`
2. Add deterministic heuristic (check AST info, schema)
3. Return `Suggestion(kind="rewrite", title="...", rationale="...", impact="...", confidence=..., statements=[], alt_sql="...")`
4. Add unit test in `tests/test_rewrite_rules.py`
5. Ensure stable ordering in `optimizer.analyze()` (rewrites before indexes, sorted by score/title)

### Adding a New Index Advisor Heuristic
1. Edit `app/core/optimizer.py::suggest_indexes()`
2. Extract relevant AST patterns (filters, joins, order_by, group_by)
3. Build candidate columns ordered: equality → range → order/group
4. Deduplicate against existing indexes (`_existing_index_covers()`)
5. Compute score, width, estReductionPct; apply filtering thresholds
6. Return `Suggestion(kind="index", ...)` with `statements=["CREATE INDEX CONCURRENTLY ..."]`
7. Add test in `tests/test_advisor_filtering_and_scoring.py` or `tests/test_optimizer_rules.py`

### Adding a New Configuration Variable
1. Add to `app/core/config.py::Settings` with default value
2. Document in `.env.example`
3. Update README.md if user-facing
4. Use `settings.VAR_NAME` in code (no direct `os.getenv()` calls outside config.py)

### Modifying What-If Logic
1. Edit `app/core/whatif.py::evaluate()`
2. Maintain soft-fail behavior (return `ranking="heuristic"` if HypoPG unavailable)
3. All trials must call `hypopg_reset()` before and after
4. Use `observe_whatif_trial()` for metrics
5. Ensure filtering by `WHATIF_MIN_COST_REDUCTION_PCT` and rounding to 3 decimals
6. Add integration test in `tests/test_optimize_whatif_integration.py` (requires `RUN_DB_TESTS=1`)

## API Endpoints

- `GET /health` - Health check (no DB required)
- `GET /healthz` - Alternative health check
- `POST /api/v1/lint` - Lint SQL (static analysis, no DB)
- `POST /api/v1/explain` - Get EXPLAIN plan + warnings/metrics (requires DB)
  - Params: `sql`, `analyze` (bool), `timeout_ms`, optional NL fields (`nl`, `audience`, `style`, `length`)
- `POST /api/v1/optimize` - Get optimization suggestions (requires DB)
  - Params: `sql`, `analyze` (bool), `timeout_ms`, `top_k`, `what_if` (bool)
- `GET /api/v1/schema` - Fetch schema metadata (query params: `schema`, `table`)
- `POST /api/v1/workload` - Analyze multiple queries
  - Params: `sqls` (list), `top_k`, `what_if` (bool)
- `GET /metrics` - Prometheus metrics (requires `METRICS_ENABLED=true`)

## Project Structure

```
src/app/
├── main.py              # FastAPI app entry point, middleware, metrics endpoint
├── cli.py               # CLI commands (qeo lint|explain|optimize|workload)
├── core/
│   ├── config.py        # Settings (env vars, defaults)
│   ├── db.py            # PostgreSQL helpers (run_explain, fetch_schema, fetch_table_stats)
│   ├── sql_analyzer.py  # sqlglot parsing, lint rules
│   ├── plan_heuristics.py # EXPLAIN plan warnings/metrics
│   ├── optimizer.py     # Deterministic rewrite + index advisor
│   ├── whatif.py        # HypoPG cost-based evaluation
│   ├── workload.py      # Multi-query analysis
│   ├── plan_diff.py     # Plan comparison (for --diff output)
│   ├── metrics.py       # Prometheus wiring
│   ├── prompts.py       # LLM prompt templates
│   └── llm_adapter.py   # LLM provider interface
├── providers/
│   ├── provider_dummy.py   # Deterministic test provider
│   └── provider_ollama.py  # Local Ollama integration
└── routers/
    ├── health.py, lint.py, explain.py, optimize.py, schema.py, workload.py
tests/
├── test_optimizer_rules.py, test_rewrite_rules.py, test_determinism.py, etc.
infra/
├── init/                # DB init scripts (HypoPG extension, seed data)
└── seed/                # Seed SQL scripts (orders table)
docker/
├── db.Dockerfile        # PostgreSQL + HypoPG image
```

## Docker & Deployment

- **DB Image**: Custom Postgres 16 with HypoPG extension pre-installed (`docker/db.Dockerfile`)
- **Init scripts**: Auto-run on first start (`infra/init/10-enable-hypopg.sql`, `20-seed.sql`)
- **Compose**: `docker-compose.yml` defines `db` and `api` services; API builds from root Dockerfile
- **Ports**: DB on `5433` (host) → `5432` (container), API on `8000`

### Building and Running
```bash
# Build and start all services
docker compose up -d --build

# View logs
docker compose logs -f

# Stop and remove volumes
docker compose down -v
```

## Benchmarking

- **Script**: `scripts/bench/run_bench.py` (requires `RUN_DB_TESTS=1`)
- **Output**: `bench/report/report.json` and `report.csv`
- **Usage**: Ephemeral schema `bench_qeo`; dropped at end
- Run: `PYTHONPATH=src python scripts/bench/run_bench.py`

## LLM Integration (Optional)

- **Dummy provider** (default): Returns deterministic explanations for testing
- **Ollama provider**: Requires local Ollama server (`OLLAMA_HOST=http://localhost:11434`, `LLM_MODEL=llama2:13b-instruct`)
- NL explanations are soft-fail: errors return `explanation: null` without breaking the response
- Gate Ollama tests with `RUN_OLLAMA_TESTS=1` env var

## Troubleshooting

### HypoPG Not Available
- Symptom: `whatIf: { available: false }`
- Solution: Ensure DB image has HypoPG extension enabled. Check `SELECT extname FROM pg_extension WHERE extname='hypopg';`

### Tests Failing with DB Errors
- Symptom: `psycopg2.OperationalError: could not connect`
- Solution: Start DB with `docker compose up -d db`; set `RUN_DB_TESTS=1`

### Determinism Tests Failing
- Symptom: Float values or ordering differ across runs
- Solution: Ensure all floats rounded to 3 decimals with `float(f"{x:.3f}")`; verify stable sorting (explicit keys, no reliance on dict order)

### Empty/Wrong Index Suggestions
- Possible causes:
  - Table too small (< `OPT_MIN_ROWS_FOR_INDEX`)
  - Existing index already covers the pattern
  - Estimated reduction below `WHATIF_MIN_COST_REDUCTION_PCT` (what-if filtering)
- Check: Adjust thresholds in `.env`, verify schema/stats available, inspect `actualTopK` in response

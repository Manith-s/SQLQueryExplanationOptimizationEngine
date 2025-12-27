# Query Explanation & Optimization Engine (QEO)

A local, offline-capable tool for PostgreSQL query analysis, explanation, and optimization. Provides deterministic query optimization suggestions, cost-based index recommendations using HypoPG, and optional natural language explanations via local LLMs.

## What This Does

- **SQL Linting & Validation** - Static analysis to catch syntax errors and anti-patterns before execution
- **EXPLAIN Plan Analysis** - Extract warnings and performance metrics from PostgreSQL query execution plans
- **Deterministic Optimization** - Stable, reproducible query rewrites and index suggestions based on AST analysis
- **Cost-Based Index Ranking** - HypoPG-powered "what-if" analysis for evaluating hypothetical index impact
- **Workload Analysis** - Analyze multiple queries to find the most impactful optimizations across a workload
- **Read-Only Safety** - Never executes DDL/DML; all index suggestions are informational

## Architecture

QEO consists of a FastAPI REST API, command-line interface, and core analysis engine. The system parses SQL queries, analyzes execution plans, generates optimization suggestions, and optionally evaluates hypothetical indexes using HypoPG.

```mermaid
graph TB
    A[Client Request] --> B{CLI or API}
    B --> C[SQL Analyzer]
    C --> D[AST Extraction]
    D --> E[Plan Heuristics]
    E --> F[Optimizer]
    F --> G{What-If Enabled?}
    G -->|Yes| H[HypoPG Evaluation]
    G -->|No| I[Heuristic Ranking]
    H --> J[Cost-Based Ranking]
    I --> J
    J --> K[Response]
```

### Core Components

1. **SQL Analyzer** - Parses SQL using sqlglot, extracts tables, columns, filters, joins
2. **Plan Heuristics** - Analyzes EXPLAIN output for warnings and performance metrics
3. **Optimizer** - Deterministic rewrite rules and index advisor based on AST and catalog stats
4. **What-If Engine** - HypoPG-based cost evaluation for index candidates
5. **Workload Analyzer** - Multi-query analysis and index consolidation

## Key Features

- **Local-First Design** - Works completely offline; no cloud dependencies
- **Deterministic Outputs** - Stable results for identical inputs (3-decimal rounding, stable sorting)
- **HypoPG Integration** - Cost-based evaluation of hypothetical indexes without creating them
- **Query Correction** - Auto-detection and correction of SQL syntax errors
- **Web UI** - Visual query builder, plan visualizer, and profiler dashboard
- **REST API** - Programmatic access with rate limiting and optional authentication
- **CLI Tool** - Command-line interface for batch processing and automation
- **Query Profiler** - Background monitoring and performance degradation detection

## Tech Stack

**Backend:**
- Python 3.11+
- FastAPI - REST API framework
- sqlglot - SQL parsing and AST analysis
- psycopg2 - PostgreSQL connectivity
- HypoPG - Hypothetical index extension for PostgreSQL

**Infrastructure:**
- Docker & Docker Compose - Containerized PostgreSQL with HypoPG
- PostgreSQL 16 - Database engine
- Uvicorn - ASGI server

**Optional:**
- Ollama - Local LLM runtime for natural language explanations
- Prometheus - Metrics collection (when enabled)

## Repository Structure

```
queryexpnopt/
├── src/app/                    # Main application code
│   ├── core/                   # Core engine modules
│   │   ├── sql_analyzer.py     # SQL parsing and AST extraction
│   │   ├── optimizer.py        # Query optimization engine
│   │   ├── plan_heuristics.py  # Execution plan analysis
│   │   ├── whatif.py           # HypoPG cost-based evaluation
│   │   ├── workload.py         # Multi-query analysis
│   │   └── ...                 # Other core modules
│   ├── routers/                # FastAPI route handlers
│   │   ├── lint.py             # SQL linting endpoint
│   │   ├── explain.py          # EXPLAIN plan endpoint
│   │   ├── optimize.py         # Optimization endpoint
│   │   └── ...                 # Other endpoints
│   ├── providers/              # LLM providers (dummy, ollama)
│   ├── static/                 # Web UI files
│   ├── cli.py                  # Command-line interface
│   └── main.py                 # FastAPI application entry point
├── tests/                      # Test suite
│   ├── integration/            # Integration tests (require DB)
│   └── load/                   # Load testing scripts
├── docs/                       # Documentation
├── infra/                      # Infrastructure setup
│   ├── init/                   # Database initialization scripts
│   └── seed/                   # Sample data
├── docker/                     # Docker configuration
├── pyproject.toml              # Python project configuration
├── docker-compose.yml          # Docker Compose configuration
└── Makefile                    # Common commands
```

## Quickstart (Local)

### Prerequisites

- **Docker** and **Docker Compose**
- **Python 3.11+**
- **pip**

### Setup

```bash
# 1. Clone the repository
git clone https://github.com/yourusername/queryexpnopt.git
cd queryexpnopt

# 2. Install QEO
pip install -e ".[dev]"

# 3. Start PostgreSQL with HypoPG
docker compose up -d db

# 4. (Optional) Seed sample data
# PowerShell
type .\infra\seed\seed_orders.sql | docker exec -i queryexpnopt-db psql -U postgres -d queryexpnopt
# Bash
docker exec -i queryexpnopt-db psql -U postgres -d queryexpnopt < infra/seed/seed_orders.sql
```

### Run

**CLI Usage:**
```bash
# Lint SQL
qeo lint --sql "SELECT * FROM users WHERE id = 42"

# Explain with analysis
qeo explain --sql "SELECT * FROM orders WHERE user_id=42" --analyze

# Get optimization suggestions with cost-based ranking
qeo optimize \
  --sql "SELECT * FROM orders WHERE user_id=42 ORDER BY created_at DESC LIMIT 50" \
  --what-if \
  --table

# Analyze workload from file
qeo workload --file queries.sql --top-k 10 --what-if
```

**API Server:**
```bash
# Set PYTHONPATH and start server
# PowerShell
$env:PYTHONPATH = "src"
uvicorn app.main:app --reload --app-dir src

# Bash
export PYTHONPATH=src
uvicorn app.main:app --reload --app-dir src
```

The API will be available at `http://localhost:8000`. Visit `/docs` for interactive API documentation.

## Configuration

QEO is configured via environment variables. Create a `.env` file in the project root or set them in your environment.

| Variable | Default | Description |
|----------|---------|-------------|
| `DB_URL` | `postgresql+psycopg2://postgres:password@localhost:5433/queryexpnopt` | PostgreSQL connection string |
| `LLM_PROVIDER` | `dummy` | LLM provider: `dummy` (deterministic) or `ollama` (local LLM) |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama server URL (when using `ollama` provider) |
| `WHATIF_ENABLED` | `false` | Enable HypoPG cost-based ranking |
| `WHATIF_MAX_TRIALS` | `10` | Max hypothetical indexes to trial |
| `WHATIF_MIN_COST_REDUCTION_PCT` | `5` | Minimum cost reduction % to report |
| `OPT_MIN_ROWS_FOR_INDEX` | `10000` | Skip index suggestions for small tables |
| `OPT_MAX_INDEX_COLS` | `3` | Maximum columns per index suggestion |
| `AUTH_ENABLED` | `false` | Enable Bearer token authentication for API |
| `API_KEY` | `dev-key-12345` | API key for authentication (when enabled) |
| `METRICS_ENABLED` | `false` | Enable Prometheus metrics endpoint |
| `PROFILER_ENABLED` | `true` | Enable query profiler background tasks |
| `CORS_ALLOW_ORIGINS` | `*` | CORS allowed origins (comma-separated) |

### Example .env

```bash
DB_URL=postgresql+psycopg2://postgres:password@localhost:5433/queryexpnopt
WHATIF_ENABLED=true
LLM_PROVIDER=ollama
OLLAMA_HOST=http://localhost:11434
AUTH_ENABLED=false
METRICS_ENABLED=false
```

## Usage

### CLI Commands

**Lint SQL:**
```bash
qeo lint --sql "SELECT * FROM users"
qeo lint --file queries.sql
```

**Explain Query:**
```bash
qeo explain --sql "SELECT * FROM orders WHERE user_id=42" --analyze
```

**Optimize Query:**
```bash
qeo optimize \
  --sql "SELECT * FROM orders WHERE user_id=42 ORDER BY created_at DESC" \
  --what-if \
  --table \
  --top-k 5
```

**Workload Analysis:**
```bash
qeo workload --file queries.sql --top-k 10 --what-if --table
```

### API Endpoints

**Core Endpoints:**
- `POST /api/v1/lint` - SQL linting and validation
- `POST /api/v1/correct` - Query error detection and correction
- `POST /api/v1/explain` - Execution plan analysis
- `POST /api/v1/optimize` - Optimization suggestions
- `POST /api/v1/workload` - Multi-query workload analysis
- `GET /api/v1/schema` - Database schema inspection

**Management Endpoints:**
- `POST /api/v1/index/analyze` - Index usage analysis
- `POST /api/v1/index/auto-tune` - Automated index tuning
- `GET /api/v1/cache/stats` - Cache statistics
- `POST /api/v1/cache/warm` - Cache warming
- `GET /api/v1/catalog` - Database catalog information

**Web UI:**
- `GET /` - Main dashboard
- `GET /query-builder` - Visual query builder
- `GET /plan-visualizer` - Execution plan visualizer
- `GET /profiler` - Query profiler dashboard

**Health & Metrics:**
- `GET /health` - Health check
- `GET /metrics` - Prometheus metrics (when enabled)
- `GET /docs` - Interactive API documentation

### Example API Request

```bash
curl -X POST "http://localhost:8000/api/v1/optimize" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -d '{
    "sql": "SELECT * FROM orders WHERE user_id=42 ORDER BY created_at DESC LIMIT 50",
    "what_if": true,
    "top_k": 5
  }'
```

## Testing

QEO uses `pytest` with separate test categories:

- **Unit tests** - No database required; fast, deterministic
- **Integration tests** - Require `RUN_DB_TESTS=1` and PostgreSQL running
- **Determinism tests** - Verify stable outputs and float rounding

```bash
# Run unit tests (no DB required)
pytest -q

# Run integration tests (requires PostgreSQL running)
docker compose up -d db
RUN_DB_TESTS=1 pytest -v

# Run specific test file
pytest tests/test_optimizer_rules.py -v

# Run single test
pytest tests/test_determinism.py::test_float_rounding -v
```

## Deployment

### Docker Compose

```bash
# Start all services (DB + API)
docker compose up -d --build

# View logs
docker compose logs -f

# Stop all services
docker compose down -v
```

The API will be available at `http://localhost:8000` and PostgreSQL at `localhost:5433`.

### Production Considerations

- Set `AUTH_ENABLED=true` and configure a secure `API_KEY`
- Configure `DB_URL` to point to your production database
- Enable `METRICS_ENABLED=true` for monitoring
- Adjust `WHATIF_MAX_TRIALS` and timeouts based on workload
- Set appropriate `CORS_ALLOW_ORIGINS` for your frontend
- Use environment-specific `.env` files or secrets management

See `docs/deployment.md` for detailed production deployment guidance.

## Troubleshooting

**Database Connection Issues:**
- Ensure Docker is running: `docker compose ps`
- Check database logs: `docker compose logs db`
- Verify port 5433 is not in use

**HypoPG Not Available:**
```bash
# Check if HypoPG is installed
docker compose exec db psql -U postgres -d queryexpnopt -c "SELECT extname FROM pg_extension WHERE extname='hypopg';"

# If missing, rebuild the database image
docker compose down -v
docker compose up -d --build db
```

**CLI Not Found:**
- Verify installation: `pip show queryexpnopt`
- Ensure the script is in your PATH
- Try running directly: `python -m app.cli <command>`

**Rate Limiting:**
- Default limit is 100 requests/minute per IP
- `/api/v1/optimize` has a stricter limit of 10 requests/minute
- Check `X-RateLimit-Limit` and `Retry-After` headers

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Credits

- **HypoPG** - Hypothetical index extension for PostgreSQL
- **sqlglot** - Fast SQL parser and transpiler
- **FastAPI** - Modern Python web framework
- **Ollama** - Local LLM runtime

# QEO Project Structure

**Last Updated:** January 2025  
**Version:** 1.0.0

## Overview

This document describes the current structure of the QEO (Query Explanation & Optimization Engine) project, helping developers understand the codebase organization.

## Directory Structure

```
queryexpnopt/
├── src/app/                    # Main application code
│   ├── core/                   # Core engine modules
│   │   ├── sql_analyzer.py     # SQL parsing and AST extraction
│   │   ├── optimizer.py        # Query optimization (rewrites + indexes)
│   │   ├── plan_heuristics.py  # Execution plan analysis
│   │   ├── whatif.py           # HypoPG cost-based evaluation
│   │   ├── query_corrector.py  # Query error detection and correction
│   │   ├── db.py               # Database connectivity
│   │   ├── workload.py         # Multi-query analysis
│   │   └── ...                 # Other core modules
│   ├── routers/                # FastAPI route handlers
│   │   ├── lint.py             # SQL linting endpoint
│   │   ├── correct.py           # Query correction endpoint
│   │   ├── explain.py          # EXPLAIN plan endpoint
│   │   ├── optimize.py         # Optimization endpoint
│   │   ├── workload.py         # Workload analysis endpoint
│   │   └── ...                 # Other endpoints
│   ├── providers/              # LLM providers (dummy, ollama)
│   ├── static/                 # Web UI files
│   ├── cli.py                  # Command-line interface
│   └── main.py                 # FastAPI application entry point
│
├── tests/                      # Test suite
│   ├── test_sql_analyzer_*.py  # SQL parsing tests
│   ├── test_optimizer_*.py     # Optimizer tests
│   ├── test_lint_endpoint.py   # API endpoint tests
│   ├── integration/            # Integration tests (require DB)
│   └── load/                   # Load testing scripts
│
├── docs/                       # Documentation
│   ├── getting-started.md      # Installation and setup guide
│   ├── tutorial.md             # Usage examples
│   ├── api-reference.md        # API documentation
│   ├── architecture.md         # System architecture
│   ├── deployment.md           # Deployment guide
│   └── archive/                # Historical documentation
│
├── infra/                      # Infrastructure setup
│   ├── init/                   # Database initialization scripts
│   └── seed/                   # Sample data
│
├── scripts/                     # Utility scripts
│   ├── local/                  # Local development scripts
│   └── bench/                  # Benchmarking scripts
│
├── docker/                     # Docker configuration
│   └── db.Dockerfile           # PostgreSQL with HypoPG
│
├── README.md                   # Main project documentation
├── CHANGELOG.md                # Version history
├── pyproject.toml              # Python project configuration
├── requirements.txt            # Python dependencies
├── docker-compose.yml          # Docker Compose configuration
└── Makefile                    # Common commands
```

## Key Modules

### Core Engine (`src/app/core/`)

| Module | Purpose |
|--------|---------|
| `sql_analyzer.py` | Parses SQL, extracts AST (tables, columns, filters, joins) |
| `optimizer.py` | Generates rewrite suggestions and index recommendations |
| `query_corrector.py` | Detects and fixes SQL syntax errors |
| `plan_heuristics.py` | Analyzes EXPLAIN output for warnings and metrics |
| `whatif.py` | Uses HypoPG for cost-based index evaluation |
| `db.py` | Database connection management and queries |
| `workload.py` | Multi-query analysis and pattern detection |

### API Endpoints (`src/app/routers/`)

| Endpoint | Path | Purpose |
|----------|------|---------|
| Lint | `/api/v1/lint` | Static SQL analysis and linting |
| Correct | `/api/v1/correct` | Query error detection and correction |
| Explain | `/api/v1/explain` | Execution plan analysis |
| Optimize | `/api/v1/optimize` | Optimization suggestions |
| Workload | `/api/v1/workload` | Multi-query analysis |
| Schema | `/api/v1/schema` | Database schema inspection |

## Data Flow

```
User Query
    ↓
[CLI or API]
    ↓
sql_analyzer.parse_sql() → AST
    ↓
optimizer.analyze() → Suggestions
    ↓
whatif.evaluate() → Cost-based ranking (optional)
    ↓
Response (suggestions + metadata)
```

## Configuration

- **Environment Variables**: See `.env` file or `docs/getting-started.md`
- **Database**: PostgreSQL 16 with HypoPG extension
- **Python**: 3.11+
- **Dependencies**: See `requirements.txt`

## Development Workflow

1. **Local Development**:
   ```bash
   pip install -e ".[dev]"
   docker compose up -d db
   uvicorn app.main:app --reload
   ```

2. **Testing**:
   ```bash
   pytest tests/                    # Unit tests (no DB)
   RUN_DB_TESTS=1 pytest tests/    # Integration tests (requires DB)
   ```

3. **CLI Usage**:
   ```bash
   qeo lint --sql "SELECT * FROM users"
   qeo optimize --sql "SELECT * FROM orders" --what-if
   ```

## Key Features

1. **SQL Linting**: Static analysis for anti-patterns
2. **Query Correction**: Auto-fix syntax errors and typos
3. **Query Optimization**: Rewrite suggestions + index recommendations
4. **Cost-Based Ranking**: HypoPG-powered what-if analysis
5. **Workload Analysis**: Multi-query pattern detection

## Architecture Principles

- **Read-Only**: Never executes DDL/DML
- **Deterministic**: Stable outputs for identical inputs
- **Local-First**: Works offline, no cloud dependencies
- **Safe by Default**: Timeouts, error handling, no destructive operations

## Documentation

- **Getting Started**: `docs/getting-started.md`
- **API Reference**: `docs/api-reference.md`
- **Architecture**: `docs/architecture.md`
- **Tutorial**: `docs/tutorial.md`

## Contributing

See `CONTRIBUTING.md` for guidelines.







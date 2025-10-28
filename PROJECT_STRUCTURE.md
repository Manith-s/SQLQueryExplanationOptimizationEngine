# Project Structure

This document explains the organization of the SQL Query Optimization Engine codebase.

## Directory Layout

```
queryexpnopt/
├── README.md                    # Main project documentation
├── QUICKSTART.md               # 5-minute getting started guide
├── PROJECT_STRUCTURE.md        # This file
│
├── scripts/                    # Startup and utility scripts
│   ├── start.bat              # Windows startup script
│   ├── start.sh               # Linux/Mac startup script
│   ├── verify.py              # System verification script
│   ├── demo.sh                # Demo script
│   └── deploy.sh              # Deployment script
│
├── docs/                      # Documentation
│   ├── SYSTEM_DESIGN.md      # Architecture and system design
│   ├── API.md                # API endpoint documentation
│   ├── TUTORIAL.md           # Step-by-step tutorials
│   ├── DEPLOYMENT.md         # Production deployment guide
│   ├── BENCHMARKING.md       # Performance benchmarks
│   └── ERRORS_AND_MESSAGES.md # Error codes reference
│
├── src/                      # Source code
│   └── app/                  # Main application package
│       ├── main.py           # FastAPI application entry point
│       ├── cli.py            # Command-line interface
│       │
│       ├── routers/          # API route handlers
│       │   ├── health.py     # Health check endpoints
│       │   ├── lint.py       # SQL linting endpoint
│       │   ├── explain.py    # Query plan explanation
│       │   ├── optimize.py   # Main optimization endpoint
│       │   ├── schema.py     # Database schema endpoint
│       │   └── workload.py   # Multi-query analysis
│       │
│       ├── core/             # Core business logic
│       │   ├── config.py     # Configuration and settings
│       │   ├── db.py         # Database operations
│       │   ├── sql_analyzer.py    # SQL parsing and linting
│       │   ├── optimizer.py       # Optimization rules engine
│       │   ├── plan_heuristics.py # EXPLAIN plan analysis
│       │   ├── whatif.py          # HypoPG what-if analysis
│       │   ├── workload.py        # Multi-query optimization
│       │   ├── plan_diff.py       # Plan comparison
│       │   ├── prompts.py         # LLM prompt templates
│       │   ├── auth.py            # Authentication
│       │   ├── security.py        # Security utilities
│       │   ├── validation.py      # Input validation
│       │   ├── cache.py           # Caching layer
│       │   ├── performance.py     # Performance monitoring
│       │   └── metrics.py         # Prometheus metrics
│       │
│       ├── providers/        # LLM providers
│       │   ├── provider_dummy.py  # Deterministic test provider
│       │   └── provider_ollama.py # Ollama local LLM
│       │
│       └── static/           # Static files for web UI
│           └── index.html    # Web interface
│
├── tests/                    # Test suite
│   ├── test_optimizer_rules.py
│   ├── test_rewrite_rules.py
│   ├── test_determinism.py
│   ├── test_explain_integration.py
│   ├── test_optimize_whatif_integration.py
│   ├── test_advisor_filtering_and_scoring.py
│   ├── test_auth.py
│   ├── test_smoke.py
│   └── integration/          # Integration tests
│       ├── test_api_auth.py
│       ├── test_production.py
│       └── test_rate_limit.py
│
├── infra/                    # Infrastructure files
│   ├── init/                 # Database initialization scripts
│   │   ├── 10-enable-hypopg.sql
│   │   └── 20-seed.sql
│   └── seed/                 # Sample data
│       └── seed_orders.sql
│
├── docker/                   # Docker configuration
│   └── db.Dockerfile        # PostgreSQL + HypoPG image
│
├── bench/                    # Benchmarking results
│   └── report/
│       ├── report.json
│       └── report.csv
│
├── simple_server.py         # Standalone server script
├── qeo.py                   # CLI wrapper (optional)
│
├── .env                     # Environment variables (local)
├── .env.example             # Environment template
├── .gitignore               # Git ignore rules
│
├── docker-compose.yml       # Docker Compose configuration
├── Dockerfile               # API server Docker image
│
├── requirements.txt         # Python dependencies
├── pyproject.toml          # Project metadata
│
├── Makefile                # Development commands
├── LICENSE                 # MIT License
├── CHANGELOG.md            # Version history
├── CONTRIBUTING.md         # Contribution guidelines
├── CODE_OF_CONDUCT.md      # Code of conduct
└── CLAUDE.md               # Claude Code assistant instructions
```

## Key Files Explained

### Entry Points

| File | Purpose |
|------|---------|
| `scripts/start.bat` / `scripts/start.sh` | **Main startup script** - Start here! |
| `simple_server.py` | Standalone server (used by start scripts) |
| `src/app/main.py` | FastAPI application definition |
| `src/app/cli.py` | Command-line interface |

### Configuration

| File | Purpose |
|------|---------|
| `.env` | Local environment variables (DB URL, settings) |
| `src/app/core/config.py` | Configuration management |
| `docker-compose.yml` | Docker services definition |

### Core Logic

| File | Purpose |
|------|---------|
| `src/app/core/optimizer.py` | **Main optimization engine** |
| `src/app/core/whatif.py` | HypoPG cost-based analysis |
| `src/app/core/sql_analyzer.py` | SQL parsing and validation |
| `src/app/core/plan_heuristics.py` | EXPLAIN plan analysis |

### API Routes

| File | Endpoint | Purpose |
|------|----------|---------|
| `src/app/routers/optimize.py` | `/api/v1/optimize` | Main optimization |
| `src/app/routers/explain.py` | `/api/v1/explain` | Plan explanation |
| `src/app/routers/lint.py` | `/api/v1/lint` | SQL linting |
| `src/app/routers/schema.py` | `/api/v1/schema` | Schema metadata |
| `src/app/routers/workload.py` | `/api/v1/workload` | Multi-query analysis |

## Common Tasks

### Running the System

```bash
# Start everything
scripts/start.bat      # Windows
./scripts/start.sh     # Linux/Mac

# Verify system health
scripts/verify.py
```

### Development

```bash
# Run tests
pytest

# Format code
black .

# Lint code
ruff check .

# Type check
mypy src/app
```

### Database Operations

```bash
# Connect to database
docker exec -it queryexpnopt-db psql -U postgres -d queryexpnopt

# Run seed script
docker exec -i queryexpnopt-db psql -U postgres -d queryexpnopt < infra/seed/seed_orders.sql
```

## File Naming Conventions

- **Scripts**: `verb.extension` (e.g., `start.bat`, `verify.py`)
- **Modules**: `noun.py` (e.g., `optimizer.py`, `config.py`)
- **Tests**: `test_subject.py` (e.g., `test_optimizer_rules.py`)
- **Docs**: `ALLCAPS.md` for root, `TitleCase.md` for docs folder

## What's in Each Layer?

### Application Layer (`src/app/`)

- **Routers**: HTTP request handling, input validation
- **Core**: Business logic, optimization engine
- **Providers**: External service integrations (LLM)
- **Static**: Web UI assets

### Data Layer

- **PostgreSQL**: Sample database with orders/users tables
- **HypoPG**: Extension for hypothetical index testing
- **Docker**: Containerized for easy setup

### Infrastructure

- **Docker**: Container definitions and orchestration
- **Scripts**: Automation and deployment tools
- **Tests**: Quality assurance and regression testing

## Dependencies

### Runtime Dependencies

- **FastAPI**: Web framework
- **psycopg2-binary**: PostgreSQL driver
- **sqlglot**: SQL parser
- **pydantic**: Data validation
- **uvicorn**: ASGI server

### Development Dependencies

- **pytest**: Testing framework
- **black**: Code formatter
- **ruff**: Linter
- **mypy**: Type checker
- **httpx**: HTTP client (for tests)

## Configuration Files

| File | Purpose |
|------|---------|
| `.env` | Local environment variables (not in git) |
| `.env.example` | Template for environment variables |
| `requirements.txt` | Python dependencies |
| `pyproject.toml` | Project metadata and tool config |
| `docker-compose.yml` | Multi-container setup |
| `.gitignore` | Files to exclude from git |

## Adding New Features

### Adding a New Optimization Rule

1. Edit `src/app/core/optimizer.py`
2. Add rule to `suggest_rewrites()` or `suggest_indexes()`
3. Add test to `tests/test_optimizer_rules.py`
4. Update documentation

### Adding a New API Endpoint

1. Create router in `src/app/routers/new_endpoint.py`
2. Define Pydantic models for request/response
3. Implement handler function
4. Register in `src/app/main.py`
5. Add tests in `tests/`
6. Update `docs/API.md`

### Adding New Documentation

1. Create `.md` file in `docs/`
2. Link from `README.md`
3. Follow existing formatting style
4. Include code examples

## Clean Code Practices

This project follows these principles:

✅ **Separation of Concerns**: Routers handle HTTP, Core handles logic
✅ **Single Responsibility**: Each module has one clear purpose
✅ **Type Hints**: All functions have type annotations
✅ **Documentation**: Docstrings for all public functions
✅ **Testing**: Unit tests for logic, integration tests for API
✅ **Configuration**: All settings in one place (`config.py`)
✅ **Error Handling**: Graceful degradation, helpful messages
✅ **Security**: Input validation, parameterized queries
✅ **Performance**: Caching, connection pooling, async operations

---

**Need help navigating the codebase?** See [QUICKSTART.md](QUICKSTART.md) or [docs/SYSTEM_DESIGN.md](docs/SYSTEM_DESIGN.md).

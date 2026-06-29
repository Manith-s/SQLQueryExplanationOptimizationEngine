<div align="center">

# 🔍 QEO — SQL Query Explanation & Optimization Engine

**A local, offline-first engine that explains, scores, and optimizes your PostgreSQL queries — safely and deterministically.**

[![Python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104%2B-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![HypoPG](https://img.shields.io/badge/HypoPG-what--if%20indexes-336791)](https://github.com/HypoPG/hypopg)
[![Tests](https://img.shields.io/badge/tests-213%20passing-brightgreen)](#-testing)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

</div>

---

## ✨ What is QEO?

QEO is a **read-only** tool for developers and DBAs who want to understand and speed up their SQL — without sending anything to the cloud and without risking accidental schema changes. Point it at a PostgreSQL database and it will:

- **Explain** a query's execution plan and surface the warnings that matter.
- **Lint** SQL statically to catch syntax errors and anti-patterns before they run.
- **Optimize** by proposing deterministic rewrites and index candidates.
- **Prove it** — validate those index candidates with **HypoPG "what-if"** analysis, which measures the real cost change of a *hypothetical* index without ever creating one.

Everything runs locally. The same input always produces the same output. No DDL or DML is ever executed against your database.

> **Why "deterministic"?** QEO sorts results stably and rounds floats to 3 decimals, so identical inputs always yield byte-identical output — making suggestions easy to diff, review, and trust in CI.

---

## 📑 Table of Contents

- [Highlights](#-highlights)
- [How it works](#-how-it-works)
- [Quickstart](#-quickstart)
- [Usage (CLI & API)](#-usage)
- [API reference](#-api-reference)
- [Configuration](#-configuration)
- [Testing](#-testing)
- [Project structure](#-project-structure)
- [Deployment](#-deployment)
- [Troubleshooting](#-troubleshooting)
- [Tech stack](#-tech-stack)
- [License & credits](#-license--credits)

---

## 🚀 Highlights

| Capability | What it gives you |
|---|---|
| 🧠 **EXPLAIN analysis** | Canonical plan JSON plus human-readable warnings and metrics (node counts, costs, timings). |
| 🩺 **SQL linting** | Static validation that flags syntax errors and risky patterns *before* execution. |
| ⚙️ **Deterministic optimizer** | Stable, reproducible query rewrites and composite-index suggestions from AST + catalog stats. |
| 🔬 **HypoPG what-if** | Cost-based ranking of index candidates using hypothetical indexes — measure impact with zero risk. |
| 📦 **Workload analysis** | Analyze many queries at once and consolidate the highest-impact indexes. |
| 🛠️ **Index lifecycle & self-healing** | Detect unused/redundant indexes and propose (optionally auto-approved) healing actions. |
| 📈 **Query profiler** | Background performance tracking with percentiles, trend analysis, and degradation alerts. |
| 🎯 **SLO monitoring** | Error-budget tracking and a "can we deploy?" check, exposed over the API. |
| ⚡ **Caching layer** | Query/plan caching with analytics, invalidation, and warm-up. |
| 🌐 **Web UI** | Visual query builder, plan visualizer, and profiler dashboard. |
| 🔌 **REST API + CLI** | Programmatic access with rate limiting and optional Bearer-token auth, plus a scriptable CLI. |
| 🗣️ **Optional local LLM** | Natural-language plan explanations via [Ollama](https://ollama.com) — fully offline, soft-fails if absent. |

---

## 🧩 How it works

```mermaid
flowchart LR
    U[Client · CLI or API] --> P[SQL Analyzer<br/>sqlglot AST]
    P --> H[Plan Heuristics<br/>warnings + metrics]
    H --> O[Optimizer<br/>rewrites + index advisor]
    O --> W{What-if<br/>enabled?}
    W -- yes --> HP[HypoPG<br/>cost deltas]
    W -- no --> HR[Heuristic<br/>ranking]
    HP --> R[Ranked suggestions]
    HR --> R
    P -. EXPLAIN .-> DB[(PostgreSQL)]
    HP -. hypothetical index .-> DB
    R --> U
```

**Core components**

1. **SQL Analyzer** (`core/sql_analyzer.py`) — parses SQL with `sqlglot`; extracts tables, columns, filters, joins.
2. **Plan Heuristics** (`core/plan_heuristics.py`) — turns `EXPLAIN (FORMAT JSON)` into warnings and metrics.
3. **Optimizer** (`core/optimizer.py`) — deterministic rewrite rules and a composite-index advisor (equality → range → order/group).
4. **What-If Engine** (`core/whatif.py`) — uses HypoPG to cost-rank index candidates without creating them.
5. **Profiler / Index Manager / SLO** — performance tracking, index lifecycle/self-healing, and error-budget monitoring.

The database is only ever **read** (catalog inspection + `EXPLAIN`). The single exception is HypoPG's *hypothetical* index API, which never touches real data.

---

## ⚡ Quickstart

### Prerequisites

- **Docker** & **Docker Compose** (ships PostgreSQL 16 + HypoPG)
- **Python 3.11+**

### Setup

```bash
# 1. Clone
git clone https://github.com/Manith-s/SQL-Query-Explanation-Optimization-Engine-.git
cd SQL-Query-Explanation-Optimization-Engine-

# 2. Install (with dev extras)
pip install -e ".[dev]"

# 3. Start PostgreSQL + HypoPG (auto-seeds sample data on first run)
docker compose up -d db

# 4. Copy the example environment file
cp .env.example .env      # Windows: copy .env.example .env
```

### Run the API

```bash
# Bash
export PYTHONPATH=src
uvicorn app.main:app --reload --app-dir src

# PowerShell
$env:PYTHONPATH = "src"
uvicorn app.main:app --reload --app-dir src
```

Open **http://localhost:8000** for the dashboard and **http://localhost:8000/docs** for interactive API docs.

```bash
# Smoke test
curl http://localhost:8000/health
# -> {"status":"healthy","version":"1.0.0","database":"connected","hypopg":"available"}
```

---

## 🛠️ Usage

### CLI

```bash
# Lint SQL
qeo lint --sql "SELECT * FROM orders WHERE user_id = 42"

# Explain a plan (optionally with ANALYZE)
qeo explain --sql "SELECT * FROM orders WHERE user_id = 42" --analyze

# Optimize with cost-based what-if ranking
qeo optimize \
  --sql "SELECT * FROM orders WHERE user_id = 42 ORDER BY created_at DESC LIMIT 50" \
  --what-if --table

# Analyze a whole workload from a file
qeo workload --file queries.sql --top-k 10 --what-if
```

### API example

```bash
curl -X POST http://localhost:8000/api/v1/optimize \
  -H "Content-Type: application/json" \
  -d '{
    "sql": "SELECT * FROM orders WHERE user_id = 42 ORDER BY created_at DESC LIMIT 50",
    "what_if": true,
    "top_k": 5
  }'
```

---

## 📡 API reference

> All `/api/v1/*` routes accept an optional `Authorization: Bearer <API_KEY>` header (required only when `AUTH_ENABLED=true`). `/health` is always public.

**Analysis**
| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/lint` | Static SQL validation; returns `issues`, `errors`, parsed `ast`. |
| `POST` | `/api/v1/correct` | Detect and correct SQL syntax errors. |
| `POST` | `/api/v1/explain` | Execution-plan analysis with warnings & metrics. |
| `POST` | `/api/v1/optimize` | Rewrite + index suggestions with optional what-if ranking. |
| `POST` | `/api/v1/workload` | Multi-query workload analysis & index consolidation. |
| `GET`  | `/api/v1/schema` | Database schema inspection (`schema` + `schemas`). |
| `GET`  | `/api/v1/catalog` | Catalog metadata and relationships. |

**Operations**
| Method | Path | Description |
|---|---|---|
| `POST` | `/api/v1/index/analyze` · `/auto-tune` | Index usage analysis & automated tuning. |
| `GET`  | `/api/v1/cache/stats` · `POST /cache/warm` | Cache analytics and warm-up. |
| `GET`  | `/api/v1/slo/status` · `/budget` · `/report` · `/can-deploy` | SLO status & error budgets. |

**Web UI & health**
| Method | Path | Description |
|---|---|---|
| `GET` | `/` · `/query-builder` · `/plan-visualizer` · `/profiler` | Dashboards & tools. |
| `GET` | `/health` | Liveness + `database`/`hypopg` status + version. |
| `GET` | `/metrics` | Prometheus metrics (when `METRICS_ENABLED=true`). |
| `GET` | `/docs` | Interactive OpenAPI docs. |

---

## 🔧 Configuration

QEO reads configuration from environment variables (or a `.env` file). Start from [`.env.example`](.env.example).

| Variable | Default | Description |
|---|---|---|
| `DB_URL` | `postgresql+psycopg2://postgres:password@localhost:5433/queryexpnopt` | PostgreSQL connection string |
| `WHATIF_ENABLED` | `false` | Enable HypoPG cost-based ranking |
| `WHATIF_MAX_TRIALS` | `10` | Max hypothetical indexes to trial |
| `WHATIF_MIN_COST_REDUCTION_PCT` | `5` | Minimum cost reduction % to report |
| `OPT_MIN_ROWS_FOR_INDEX` | `10000` | Skip index suggestions for small tables |
| `OPT_MAX_INDEX_COLS` | `3` | Max columns per suggested index |
| `LLM_PROVIDER` | `dummy` | `dummy` (deterministic) or `ollama` (local LLM) |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama URL when `LLM_PROVIDER=ollama` |
| `AUTH_ENABLED` | `false` | Require Bearer-token auth on API routes |
| `API_KEY` | `dev-key-12345` | API key when auth is enabled |
| `METRICS_ENABLED` | `false` | Expose Prometheus `/metrics` |
| `PROFILER_ENABLED` | `true` | Enable the query-profiler routes |

> Auth settings are read **dynamically**, so `AUTH_ENABLED`/`API_KEY` can be toggled without restarting.

---

## 🧪 Testing

The suite is split into fast unit tests (no database) and database-backed integration tests.

```bash
# Unit tests only — no database needed
PYTHONPATH=src pytest -q

# Full suite — needs PostgreSQL + HypoPG (via docker compose)
docker compose up -d db
RUN_DB_TESTS=1 WHATIF_ENABLED=true PYTHONPATH=src pytest -q
```

**Current status:** ✅ **213 passing**, 1 skipped (an optional Ollama LLM test, enabled with `RUN_OLLAMA_TESTS=1`). See [`CHANGELOG.md`](CHANGELOG.md) for the latest fixes.

---

## 🗂️ Project structure

```
queryexpnopt/
├── src/app/
│   ├── core/            # Engine: sql_analyzer, optimizer, plan_heuristics,
│   │                    #   whatif, profiler, index_manager, slo, cache, ...
│   ├── routers/         # FastAPI routes (lint, explain, optimize, schema,
│   │                    #   workload, index, cache, slo, catalog, health, ...)
│   ├── providers/       # LLM providers (dummy, ollama)
│   ├── static/          # Web UI (builder, plan visualizer, profiler)
│   ├── cli.py           # Command-line interface
│   └── main.py          # FastAPI application entry point
├── tests/               # Unit + integration/ tests
├── docs/                # Architecture, API reference, deployment, getting started
├── infra/               # DB init scripts + sample seed data
├── docker/              # HypoPG-enabled PostgreSQL image
├── docker-compose.yml   # PostgreSQL (+ HypoPG) service
├── pyproject.toml       # Project metadata, deps, tooling config
└── Makefile             # Common dev commands
```

---

## 🚢 Deployment

```bash
# Build & run everything
docker compose up -d --build

# Logs / teardown
docker compose logs -f
docker compose down -v
```

API: `http://localhost:8000` · PostgreSQL: `localhost:5433`.

**Production checklist**

- Set `AUTH_ENABLED=true` and a strong `API_KEY`.
- Point `DB_URL` at your managed PostgreSQL (HypoPG optional but recommended).
- Enable `METRICS_ENABLED=true` and scrape `/metrics`.
- Tune `WHATIF_MAX_TRIALS` and timeouts for your workload.

See [`docs/deployment.md`](docs/deployment.md) for details.

---

## 🩹 Troubleshooting

<details>
<summary><strong>Database connection issues</strong></summary>

- `docker compose ps` — is the `db` service up?
- `docker compose logs db` — check for startup errors.
- Ensure host port `5433` is free.
</details>

<details>
<summary><strong>HypoPG not available</strong></summary>

```bash
docker compose exec db psql -U postgres -d queryexpnopt \
  -c "SELECT extname FROM pg_extension WHERE extname='hypopg';"
# If missing, rebuild the DB image:
docker compose down -v && docker compose up -d --build db
```
</details>

<details>
<summary><strong>Rate limiting (HTTP 429)</strong></summary>

- Default: 100 requests/min per IP; `/api/v1/optimize` is stricter at 10/min.
- Check the `Re

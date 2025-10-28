# Contributing to QEO (Query Explanation & Optimization) Engine

Thanks for your interest in contributing! QEO is a local-first, read-only analysis tool for PostgreSQL queries with optional HypoPG-based what-if evaluation. This guide explains how to set up your environment, make changes, and submit a high-quality pull request.

## Project scope
- Local/dev focus; read-only with respect to real DDL/DML (only HypoPG hypothetical indexes are used for cost validation)
- Deterministic outputs: stable ordering and 3-decimal rounding for floats
- Optional features: NL explanations via local providers (dummy or Ollama), Prometheus metrics, HypoPG trials

## Dev setup

### Prerequisites
- Python 3.11+
- Docker Desktop (for Postgres 16 + HypoPG)
- Git

### Create and activate virtualenv
- macOS/Linux:
```bash
python -m venv .venv
source .venv/bin/activate
```
- Windows PowerShell:
```powershell
python -m venv .venv
. .\.venv\Scripts\Activate.ps1
```

### Install
```bash
pip install -e ".[dev]"
```

### Start Postgres locally (Docker Compose)
```bash
# start DB only
docker compose up -d db
# or start DB+API
make up
```

### Run API locally
```bash
uvicorn app.main:app --reload
```

### Running tests
- Unit tests:
```bash
pytest -q
```
- Integration tests (requires DB):
```bash
RUN_DB_TESTS=1 pytest -q -k integration
```
- What-if (HypoPG) tests: ensure the hypopg extension is enabled; tests will auto-skip if missing

### Style & tools
- Code style: Black; lint: Ruff
```bash
black .
ruff check .
```
- Optional pre-commit:
```bash
pip install pre-commit
pre-commit install
```

## Making changes
- Keep outputs deterministic (stable ordering + 3-decimal rounding) and read-only (no real DDL/DML)
- Prefer small, focused PRs with tests
- When adding rules or features, add unit tests and update docs (README and docs/*)
- Ensure new env flags have sensible defaults and are documented in `.env.example` and README

## Commit messages & PRs
- Use clear, concise commit messages (e.g., "optimizer: add selectivity-based ranking")
- Open a PR with:
  - Checklist: updated docs, tests added/updated, determinism preserved
  - Manual test steps (copy/paste runnable)
  - Screenshots or snippets where useful

## Issue triage & labels
- Labels: `bug`, `enhancement`, `documentation`, `good first issue`, `performance`, `question`
- When filing bugs, include environment, steps to reproduce, expected vs actual, logs, and sample SQL

## Code of Conduct
By participating, you agree to abide by our [Code of Conduct](CODE_OF_CONDUCT.md).






# Getting Started with QEO

This guide will help you get QEO up and running in under 5 minutes.

## Prerequisites

- **Docker** and **Docker Compose** (for PostgreSQL with HypoPG)
- **Python 3.11+**
- **pip** (Python package manager)

## Quick Start

### 1. Clone and Install

```bash
# Clone the repository
git clone <your-repo-url>
cd queryexpnopt

# Install QEO and dependencies
pip install -e ".[dev]"
```

### 2. Start PostgreSQL with HypoPG

```bash
# Start the database (includes HypoPG extension)
docker compose up -d db

# Verify it's running
docker compose ps
```

The database will be available at `localhost:5433` with:
- User: `postgres`
- Password: `password`
- Database: `queryexpnopt`

### 3. (Optional) Seed Sample Data

For more realistic optimization testing:

**PowerShell:**
```powershell
type .\infra\seed\seed_orders.sql | docker exec -i queryexpnopt-db psql -U postgres -d queryexpnopt
```

**Bash:**
```bash
docker exec -i queryexpnopt-db psql -U postgres -d queryexpnopt < infra/seed/seed_orders.sql
```

### 4. Run the API (Optional)

If you want to use the web API:

**PowerShell:**
```powershell
$env:PYTHONPATH = "src"
uvicorn app.main:app --reload --app-dir src
```

**Bash:**
```bash
export PYTHONPATH=src
uvicorn app.main:app --reload --app-dir src
```

The API will be available at `http://localhost:8000`. Visit `/docs` for the interactive API documentation.

### 5. Use the CLI

QEO works best via the command-line interface:

```bash
# Lint SQL
qeo lint --sql "SELECT * FROM users"

# Explain a query with analysis
qeo explain --sql "SELECT * FROM orders WHERE user_id=42" --analyze

# Get optimization suggestions with cost-based ranking
qeo optimize \
  --sql "SELECT * FROM orders WHERE user_id=42 ORDER BY created_at DESC LIMIT 50" \
  --what-if \
  --table

# Analyze multiple queries from a file
qeo workload --file queries.sql --top-k 10 --what-if --table
```

## Next Steps

- Read the [Tutorial](tutorial.md) for detailed examples
- Explore the [API Reference](api-reference.md) for programmatic access
- Review [Architecture](architecture.md) to understand how QEO works
- Check [Deployment](deployment.md) for production considerations

## Troubleshooting

### Database Connection Issues

If you see `psycopg2.OperationalError: could not connect`:

1. Ensure Docker is running: `docker compose ps`
2. Check database logs: `docker compose logs db`
3. Verify port 5433 is not in use: `netstat -an | grep 5433`

### HypoPG Not Available

If what-if cost analysis shows `available: false`:

```bash
# Check if HypoPG is installed
docker compose exec db psql -U postgres -d queryexpnopt -c "SELECT extname FROM pg_extension WHERE extname='hypopg';"
```

If missing, rebuild the database image:

```bash
docker compose down -v
docker compose up -d --build db
```

### CLI Not Found

After `pip install -e .`, if `qeo` command is not found:

1. Verify installation: `pip show qeo`
2. Check if the script is in your PATH
3. Try running directly: `python -m app.cli <command>`

## Local Development Script

For convenience, use the provided local development script:

**Windows:**
```bash
scripts/local/start.bat
```

**Linux/macOS:**
```bash
scripts/local/start.sh
```

This will start the database and API together.

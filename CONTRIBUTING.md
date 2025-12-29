# Contributing to QEO

Thank you for your interest in contributing to QEO!

## Development Setup

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd queryexpnopt
   ```

2. **Install dependencies**
   ```bash
   pip install -e ".[dev]"
   ```

3. **Install pre-commit hooks (recommended)**
   ```bash
   pip install pre-commit
   pre-commit install
   ```
   This will automatically format your code before each commit.

## Code Quality

### Before Committing

Always run formatting and linting checks before committing:

```bash
# Auto-fix all issues
make format-all

# Or manually:
black .
ruff check . --fix
```

### Pre-commit Hooks

If you've installed pre-commit hooks, they will automatically:
- Remove trailing whitespace
- Fix end-of-file issues
- Format code with black
- Run ruff linting and auto-fix

### Manual Checks

```bash
# Check formatting (without fixing)
make fmt-check

# Check linting (without fixing)
make lint
```

## Running Tests

```bash
# Unit tests (no database required)
pytest -q

# Integration tests (requires PostgreSQL)
docker compose up -d db
RUN_DB_TESTS=1 pytest -v
```

## CI/CD

The CI pipeline will:
1. Check code formatting with `black --check`
2. Check linting with `ruff check`
3. Run unit tests

If any step fails, fix the issues locally and push again.

## Common Issues

### Formatting Errors

If CI fails with formatting errors:
```bash
make format-all
git add .
git commit --amend --no-edit
git push --force-with-lease
```

### Linting Errors

If CI fails with linting errors:
```bash
make lint-fix
git add .
git commit --amend --no-edit
git push --force-with-lease
```

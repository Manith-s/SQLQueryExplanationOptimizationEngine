# Changelog

## 1.0.0

This release completes unfinished wiring, fixes a set of latent bugs (most of
which only surfaced when the database-backed test suite is run), aligns the API
with its documented contract, and makes the test suite deterministic and
isolated. The full suite now passes: 213 passed, 1 skipped (Ollama, optional).

### Added
- **SLO monitoring router** is now mounted at `/api/v1/slo/*`
  (`status`, `budget`, `report`, `can-deploy`). It was fully implemented but
  never registered and failed to import.
- **Health endpoint** now reports `version`, `database`, and `hypopg` status,
  matching the documented production-ready contract.
- **Schema endpoint** now returns a `schemas` list (each table also exposes a
  `table` alias alongside `name`) in addition to the existing `schema` object.
- **Lint endpoint** now returns a dedicated `errors` array and actually flags
  SQL that cannot be parsed as a valid statement.
- `pytest-asyncio` / `pytest-timeout` added to `requirements.txt`; pytest
  markers (`db`, `integration`, `requires_hypopg`, `asyncio`) registered and
  `asyncio_mode = "auto"` enabled.
- Optional `advanced` extra in `pyproject.toml` for the standalone
  observability/resilience/region-routing modules (OpenTelemetry, aiohttp).

### Fixed
- **SLO router** imported `observe_request` (a metrics helper) and used it as a
  decorator, crashing at import; `ErrorBudgetResponse.time_to_exhaustion_hours`
  was a required `float` but the manager returns `None`.
- **Profiler** window/cleanup queries compared SQLite's space-separated
  `CURRENT_TIMESTAMP` against `datetime.isoformat()` (a `T`-separated string),
  so statistics, trends, summaries and alerts always returned zero rows.
- **Profiler** percentile calculation was off-by-one (p50/p95/p99); replaced
  with a nearest-rank helper. `cleanup_old_data(days=0)` now deletes same-second
  rows.
- **Query history** `get_recent_queries` tied on a second-resolution timestamp
  and returned the oldest row for `LIMIT 1`; `get_shared_query` returned the
  stale pre-increment `access_count`.
- **Index manager / stats collector** queried non-existent `tablename`/
  `indexname` columns on `pg_stat_user_indexes` / `pg_stat_user_tables`
  (correct columns are `relname` / `indexrelname`) with ambiguous join columns.
- **Self-healing** `auto_approve` did not approve dry-run actions.
- **TableStatistics** dataclass was missing `last_autoanalyze`, crashing
  statistics collection.
- **Visual plan endpoint** checked for a `"plan"` key, but `run_explain`
  returns the canonical `{"Plan": {...}}`, so it always returned HTTP 400.
- **Auth** `AUTH_ENABLED` / `API_KEY` were read once at import and could not be
  toggled at runtime; they are now read dynamically (also fixes test isolation).
- **Seed data** `infra/seed/seed_orders.sql` produced `NULL` statuses because
  the array index could round to 5 (out of bounds), violating `NOT NULL`.
- **Optimize** what-if payload now exposes `trialsRun` alongside `trials`.
- Replaced leftover `"stub: ... ok"` messages with `"ok"`.
- API/package version aligned to `1.0.0`.

### Tests
- Flaky cache micro-benchmarks no longer assert a tight throughput floor.
- Added an autouse fixture that clears both rate limiters between tests so
  accumulated request counts no longer cause spurious HTTP 429s.
- Fixed the `mock_connection` fixture (`MagicMock` for context-manager support)
  and removed direct fixture calls.

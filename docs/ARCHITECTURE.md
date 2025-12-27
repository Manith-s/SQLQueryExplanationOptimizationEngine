## Architecture

### Overview

QEO consists of:
- API service (FastAPI) exposing endpoints for lint, explain, optimize, schema, metrics.
- Core analysis modules (`app/core`) for DB access, plan heuristics, optimizer, what-if.
- Optional LLM providers (`app/providers`) used for natural language explanations.
- CLI (`qeo`) to run the same operations without the API.

### Data flow

1) Client calls `/api/v1/explain` or `/api/v1/optimize`.
2) API validates input and calls `db.run_explain()` with a bounded `statement_timeout`.
3) `plan_heuristics.analyze()` computes warnings and simple metrics from the plan tree.
4) `optimizer.analyze()` generates deterministic rewrite/index suggestions using AST, plan, and catalog stats.
5) Optional what-if costs: `whatif.evaluate()` uses HypoPG to synthesize hypothetical indexes, reruns EXPLAIN (costs only), and attaches `estCost*` deltas.
6) Optional NL: `llm_adapter.get_llm()` returns a provider that generates an explanation string; errors soft-fail to explanation=null.

### Modules

- `core/db.py`: psycopg2 helpers; `run_sql`, `run_explain`, `fetch_schema`, `fetch_table_stats`. Enforces `statement_timeout` and safe error handling.
- `core/plan_heuristics.py`: traverses plan JSON; computes warnings and metrics.
- `core/optimizer.py`: deterministic suggestions; merges rewrites and index advisor; rounds floats to 3 decimals.
- `core/whatif.py`: HypoPG integration; optional cost-based ranking; soft-fails when extension missing.
- `core/metrics.py`: Prometheus wiring, gated by `METRICS_ENABLED`.
- `providers/*`: `dummy` and `ollama` implementations behind `LLMProvider` interface.

### Sequence (What-if)

1) Collect baseline plan costs via `run_explain_costs(sql)`.
2) For top-N index candidates: `hypopg_reset()`, `hypopg_create_index()` with the candidate definition, run `run_explain_costs(sql)`.
3) Attach rounded `estCostBefore/After/Delta` to suggestions; filter by `WHATIF_MIN_COST_REDUCTION_PCT`.
4) Sort by cost delta desc then tie-breakers.

### Determinism

- Sorting and rounding are enforced in the optimizer and what-if.
- All random sources avoided; row estimates from catalogs only.
- Stable ordering on suggestions and table outputs.













# Benchmarking QEO

## Run the micro-bench
```bash
PYTHONPATH=src python scripts/bench/run_bench.py
```
Outputs under `bench/report/`:
- `report.json`: JSON with per-case timings and node counts
- `report.csv`: CSV summary

## Tuning knobs
- WHATIF_MAX_TRIALS (default 8)
- WHATIF_PARALLELISM (default 2)
- WHATIF_EARLY_STOP_PCT (default 2)
- OPT_MIN_ROWS_FOR_INDEX (default 10000)
- OPT_SUPPRESS_LOW_GAIN_PCT (default 5)

## Template for comparisons
| Case | planning_time_ms | execution_time_ms | node_count |
|------|------------------:|------------------:|-----------:|
| orders_topn |  |  |  |






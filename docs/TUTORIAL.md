# QEO Tutorial

## Spin up services
```bash
cp .env.example .env
docker compose up -d --build
curl http://localhost:8000/healthz
```

## CLI examples
```bash
qeo explain --sql "SELECT 1"
qeo optimize --sql "SELECT * FROM orders WHERE user_id=42 ORDER BY created_at DESC LIMIT 50" --what-if --diff --markdown
qeo workload --file infra/seed/seed_orders.sql --top-k 5 --table
```

## API examples
```bash
curl -s -X POST http://localhost:8000/api/v1/explain \
  -H 'Content-Type: application/json' \
  -d '{"sql":"SELECT * FROM pg_class LIMIT 5","analyze":true,"timeout_ms":2000}' | jq .

curl -s -X POST http://localhost:8000/api/v1/optimize \
  -H 'Content-Type: application/json' \
  -d '{"sql":"SELECT * FROM orders WHERE user_id=42 ORDER BY created_at DESC LIMIT 50","analyze":false,"timeout_ms":3000}' | jq .
```

## Interpreting outputs
- `plan_metrics`: planning/execution time, node count
- `reason`: why the suggestion is proposed (filters, joins, ordering)
- `impactPct`: estimated cost reduction percent (when what-if ran)
- `planDiff`: compact summary of operator/cost/rows deltas






# Errors and Messages

## Common errors

### SQL parse error
- HTTP 400 `{ ok:false, code:"SQL_SYNTAX", message:"..." }`
- Suggestion: run `qeo lint --sql "..."`

### Timeout during EXPLAIN
- HTTP 400 with message containing "Timeout"
- Increase `timeout_ms` or simplify the query

### NL explanation unavailable
- HTTP 200 `{ explanation:null, message:"NL explanation unavailable (timeout/provider)." }`
- Set `LLM_PROVIDER=dummy` for deterministic fallback

### DB connectivity
- Ensure Postgres is running (Docker) and `DB_URL` is correct
- Verify `curl http://localhost:8000/healthz`











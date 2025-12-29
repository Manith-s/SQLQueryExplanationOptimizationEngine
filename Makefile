.PHONY: up down logs api seed fmt lint test test-db
up:      ## Start DB+API
	docker compose up -d --build
down:    ## Stop all
	docker compose down -v
logs:    ## Tail logs
	docker compose logs -f
api:     ## Run API locally (venv must be active)
	uvicorn app.main:app --reload
seed:    ## Seed DB in compose
	docker compose exec -T db psql -U postgres -d queryexpnopt -f /docker-entrypoint-initdb.d/seed/seed_orders.sql
fmt:
	black .
lint:
	ruff check .
lint-fix:
	ruff check . --fix && ruff check .
test:
	pytest -q
test-db:
	RUN_DB_TESTS=1 pytest -q -k integration













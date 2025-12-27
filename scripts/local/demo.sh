#!/bin/bash
# QEO Demo Script - Showcasing all features
# Version 1.0.0

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

API_URL="http://localhost:8000"
API_KEY="${API_KEY:-dev-key-12345}"

echo -e "${BLUE}╔══════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   QEO - Query Explanation & Optimization Engine Demo   ║${NC}"
echo -e "${BLUE}║                    Version 1.0.0                             ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Function to print section headers
section() {
    echo ""
    echo -e "${GREEN}═══════════════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}  $1${NC}"
    echo -e "${GREEN}═══════════════════════════════════════════════════════════════${NC}"
    echo ""
}

# Function to print step
step() {
    echo -e "${YELLOW}▶ $1${NC}"
}

# Function to check if API is running
check_api() {
    if ! curl -s -f "$API_URL/health" > /dev/null 2>&1; then
        echo -e "${RED}✗ API is not running. Please start it first:${NC}"
        echo "  docker compose up -d"
        echo "  OR"
        echo "  PYTHONPATH=src uvicorn app.main:app --reload --app-dir src"
        exit 1
    fi
    echo -e "${GREEN}✓ API is running${NC}"
}

section "1. Health Check"
step "Checking API health..."
curl -s "$API_URL/health" | python -m json.tool || echo "Failed"

section "2. SQL Linting (Static Analysis)"
step "Linting valid SQL..."
curl -s -X POST "$API_URL/api/v1/lint" \
  -H "Content-Type: application/json" \
  -d '{"sql": "SELECT id, name, email FROM users WHERE active = true ORDER BY created_at DESC LIMIT 10"}' | python -m json.tool

step "Linting SQL with issues..."
curl -s -X POST "$API_URL/api/v1/lint" \
  -H "Content-Type: application/json" \
  -d '{"sql": "SELECT * FROM users"}' | python -m json.tool

section "3. Query Explanation"
step "Getting execution plan..."
curl -s -X POST "$API_URL/api/v1/explain" \
  -H "Content-Type: application/json" \
  -d '{
    "sql": "SELECT * FROM orders WHERE user_id = 42 ORDER BY created_at DESC LIMIT 10",
    "analyze": false,
    "nl": false
  }' | python -m json.tool

section "4. Query Optimization (Basic)"
step "Getting optimization suggestions..."
curl -s -X POST "$API_URL/api/v1/optimize" \
  -H "Content-Type: application/json" \
  -d '{
    "sql": "SELECT * FROM orders WHERE user_id = 42 ORDER BY created_at DESC LIMIT 50",
    "top_k": 5,
    "what_if": false
  }' | python -m json.tool

section "5. Query Optimization (What-If Analysis)"
step "Getting cost-based optimization suggestions..."
curl -s -X POST "$API_URL/api/v1/optimize" \
  -H "Content-Type: application/json" \
  -d '{
    "sql": "SELECT * FROM orders WHERE user_id = 42 AND status = '\''pending'\'' ORDER BY created_at DESC LIMIT 50",
    "top_k": 10,
    "what_if": true
  }' | python -m json.tool

section "6. Schema Inspection"
step "Fetching database schema..."
curl -s "$API_URL/api/v1/schema" | python -m json.tool

step "Fetching schema for specific table..."
curl -s "$API_URL/api/v1/schema?table=orders" | python -m json.tool

section "7. Workload Analysis"
step "Analyzing multiple queries together..."
curl -s -X POST "$API_URL/api/v1/workload" \
  -H "Content-Type: application/json" \
  -d '{
    "sqls": [
      "SELECT * FROM orders WHERE user_id = 1",
      "SELECT * FROM orders WHERE user_id = 2",
      "SELECT * FROM orders WHERE user_id = 3",
      "SELECT COUNT(*) FROM orders",
      "SELECT * FROM orders ORDER BY created_at DESC LIMIT 100"
    ],
    "top_k": 10,
    "what_if": false
  }' | python -m json.tool

section "8. Authentication Demo"
step "Testing without authentication (should fail if AUTH_ENABLED=true)..."
curl -s -X POST "$API_URL/api/v1/lint" \
  -H "Content-Type: application/json" \
  -d '{"sql": "SELECT 1"}' | python -m json.tool

step "Testing with valid API key..."
curl -s -X POST "$API_URL/api/v1/lint" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"sql": "SELECT 1"}' | python -m json.tool

section "9. Rate Limiting Demo"
step "Making rapid requests to test rate limiting..."
for i in {1..5}; do
    echo "Request $i..."
    curl -s -X POST "$API_URL/api/v1/optimize" \
      -H "Content-Type: application/json" \
      -d '{"sql": "SELECT * FROM orders LIMIT 1"}' | python -m json.tool
    sleep 1
done

section "10. Caching Demo"
step "First request (cache miss)..."
time curl -s -X POST "$API_URL/api/v1/workload" \
  -H "Content-Type: application/json" \
  -d '{
    "sqls": ["SELECT * FROM orders WHERE user_id = 123"],
    "top_k": 5
  }' | python -m json.tool

step "Second identical request (cache hit)..."
time curl -s -X POST "$API_URL/api/v1/workload" \
  -H "Content-Type: application/json" \
  -d '{
    "sqls": ["SELECT * FROM orders WHERE user_id = 123"],
    "top_k": 5
  }' | python -m json.tool

section "Demo Complete!"
echo ""
echo -e "${GREEN}All features demonstrated successfully!${NC}"
echo ""
echo "For more information:"
echo "  - API Documentation: http://localhost:8000/docs"
echo "  - Project README: README.md"
echo "  - API Reference: docs/API.md"
echo "  - Deployment Guide: docs/DEPLOYMENT.md"
echo ""

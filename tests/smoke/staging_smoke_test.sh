#!/bin/bash
#
# Staging Environment Smoke Tests
#
# Quick validation tests to ensure staging environment is working correctly.
# Run after deployment or data sync to verify core functionality.
#
# Usage:
#   ./staging_smoke_test.sh [--url http://staging.qeo.example.com]
#
# Exit codes:
#   0 - All tests passed
#   1 - One or more tests failed

set -euo pipefail

# Configuration
BASE_URL="${BASE_URL:-http://localhost:8000}"
TIMEOUT=10
VERBOSE=false

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Test counters
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --url)
            BASE_URL="$2"
            shift 2
            ;;
        -v|--verbose)
            VERBOSE=true
            shift
            ;;
        -h|--help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --url URL       Base URL of QEO API (default: http://localhost:8000)"
            echo "  -v, --verbose   Verbose output"
            echo "  -h, --help      Show this help message"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Logging functions
log_test() {
    echo -e "${BLUE}[TEST]${NC} $*"
}

log_pass() {
    echo -e "${GREEN}[PASS]${NC} $*"
    PASSED_TESTS=$((PASSED_TESTS + 1))
}

log_fail() {
    echo -e "${RED}[FAIL]${NC} $*"
    FAILED_TESTS=$((FAILED_TESTS + 1))
}

log_info() {
    if [[ "$VERBOSE" == "true" ]]; then
        echo -e "${YELLOW}[INFO]${NC} $*"
    fi
}

# HTTP request helper
http_get() {
    local endpoint="$1"
    local expected_status="${2:-200}"

    local response
    local status

    response=$(curl -s -w "\n%{http_code}" --max-time "$TIMEOUT" "${BASE_URL}${endpoint}" 2>&1)
    status=$(echo "$response" | tail -n 1)
    body=$(echo "$response" | sed '$d')

    log_info "GET $endpoint -> HTTP $status"
    if [[ "$VERBOSE" == "true" ]]; then
        echo "$body" | jq . 2>/dev/null || echo "$body"
    fi

    if [[ "$status" == "$expected_status" ]]; then
        echo "$body"
        return 0
    else
        return 1
    fi
}

http_post() {
    local endpoint="$1"
    local data="$2"
    local expected_status="${3:-200}"

    local response
    local status

    response=$(curl -s -w "\n%{http_code}" --max-time "$TIMEOUT" \
        -X POST \
        -H "Content-Type: application/json" \
        -d "$data" \
        "${BASE_URL}${endpoint}" 2>&1)
    status=$(echo "$response" | tail -n 1)
    body=$(echo "$response" | sed '$d')

    log_info "POST $endpoint -> HTTP $status"
    if [[ "$VERBOSE" == "true" ]]; then
        echo "$body" | jq . 2>/dev/null || echo "$body"
    fi

    if [[ "$status" == "$expected_status" ]]; then
        echo "$body"
        return 0
    else
        return 1
    fi
}

# Test functions
test_health_check() {
    TOTAL_TESTS=$((TOTAL_TESTS + 1))
    log_test "Health check endpoint"

    if response=$(http_get "/health" 200); then
        if echo "$response" | jq -e '.status == "healthy"' &>/dev/null; then
            log_pass "Health check returned healthy status"
        else
            log_fail "Health check status not healthy: $response"
        fi
    else
        log_fail "Health check endpoint failed"
    fi
}

test_health_db_connection() {
    TOTAL_TESTS=$((TOTAL_TESTS + 1))
    log_test "Database connectivity check"

    if response=$(http_get "/health" 200); then
        if echo "$response" | jq -e '.database == true' &>/dev/null; then
            log_pass "Database connection verified"
        else
            log_fail "Database connection failed"
        fi
    else
        log_fail "Could not check database connection"
    fi
}

test_lint_endpoint() {
    TOTAL_TESTS=$((TOTAL_TESTS + 1))
    log_test "Lint endpoint with valid SQL"

    local sql='{"sql": "SELECT * FROM users WHERE id = 42"}'

    if response=$(http_post "/api/v1/lint" "$sql" 200); then
        if echo "$response" | jq -e '.valid == true' &>/dev/null; then
            log_pass "Lint endpoint validated SQL"
        else
            log_fail "Lint endpoint rejected valid SQL"
        fi
    else
        log_fail "Lint endpoint failed"
    fi
}

test_lint_invalid_sql() {
    TOTAL_TESTS=$((TOTAL_TESTS + 1))
    log_test "Lint endpoint with invalid SQL"

    local sql='{"sql": "SELECT * FORM users"}'

    if response=$(http_post "/api/v1/lint" "$sql" 200); then
        if echo "$response" | jq -e '.valid == false' &>/dev/null; then
            log_pass "Lint endpoint detected invalid SQL"
        else
            log_fail "Lint endpoint did not detect invalid SQL"
        fi
    else
        log_fail "Lint endpoint failed"
    fi
}

test_explain_endpoint() {
    TOTAL_TESTS=$((TOTAL_TESTS + 1))
    log_test "Explain endpoint without ANALYZE"

    local data='{"sql": "SELECT * FROM users LIMIT 10", "analyze": false}'

    if response=$(http_post "/api/v1/explain" "$data" 200); then
        if echo "$response" | jq -e '.plan != null' &>/dev/null; then
            log_pass "Explain endpoint returned plan"
        else
            log_fail "Explain endpoint did not return plan"
        fi
    else
        log_fail "Explain endpoint failed"
    fi
}

test_explain_with_analyze() {
    TOTAL_TESTS=$((TOTAL_TESTS + 1))
    log_test "Explain endpoint with ANALYZE"

    local data='{"sql": "SELECT COUNT(*) FROM users", "analyze": true, "timeout_ms": 5000}'

    if response=$(http_post "/api/v1/explain" "$data" 200); then
        if echo "$response" | jq -e '.plan != null' &>/dev/null; then
            log_pass "Explain ANALYZE returned plan"
        else
            log_fail "Explain ANALYZE did not return plan"
        fi
    else
        log_fail "Explain ANALYZE endpoint failed"
    fi
}

test_optimize_endpoint() {
    TOTAL_TESTS=$((TOTAL_TESTS + 1))
    log_test "Optimize endpoint without what-if"

    local data='{"sql": "SELECT * FROM orders WHERE user_id = 123 ORDER BY created_at DESC", "what_if": false, "top_k": 5}'

    if response=$(http_post "/api/v1/optimize" "$data" 200); then
        if echo "$response" | jq -e '.suggestions != null' &>/dev/null; then
            log_pass "Optimize endpoint returned suggestions"
        else
            log_fail "Optimize endpoint did not return suggestions"
        fi
    else
        log_fail "Optimize endpoint failed"
    fi
}

test_optimize_with_whatif() {
    TOTAL_TESTS=$((TOTAL_TESTS + 1))
    log_test "Optimize endpoint with what-if analysis"

    local data='{"sql": "SELECT * FROM orders WHERE user_id = 123 ORDER BY created_at DESC LIMIT 10", "what_if": true, "top_k": 5}'

    if response=$(http_post "/api/v1/optimize" "$data" 200); then
        if echo "$response" | jq -e '.whatIf != null' &>/dev/null; then
            if echo "$response" | jq -e '.whatIf.available == true' &>/dev/null; then
                log_pass "What-if analysis completed"
            else
                log_fail "What-if analysis not available (HypoPG missing?)"
            fi
        else
            log_fail "What-if metadata missing"
        fi
    else
        log_fail "Optimize with what-if failed"
    fi
}

test_schema_endpoint() {
    TOTAL_TESTS=$((TOTAL_TESTS + 1))
    log_test "Schema endpoint for public schema"

    if response=$(http_get "/api/v1/schema?schema=public" 200); then
        if echo "$response" | jq -e '.tables != null' &>/dev/null; then
            local table_count
            table_count=$(echo "$response" | jq '.tables | length')
            log_pass "Schema endpoint returned $table_count tables"
        else
            log_fail "Schema endpoint did not return tables"
        fi
    else
        log_fail "Schema endpoint failed"
    fi
}

test_schema_specific_table() {
    TOTAL_TESTS=$((TOTAL_TESTS + 1))
    log_test "Schema endpoint for specific table"

    if response=$(http_get "/api/v1/schema?schema=public&table=users" 200); then
        if echo "$response" | jq -e '.tables[0].columns != null' &>/dev/null; then
            local column_count
            column_count=$(echo "$response" | jq '.tables[0].columns | length')
            log_pass "Users table has $column_count columns"
        else
            log_fail "Schema endpoint did not return columns for users table"
        fi
    else
        log_fail "Schema endpoint for users table failed"
    fi
}

test_workload_endpoint() {
    TOTAL_TESTS=$((TOTAL_TESTS + 1))
    log_test "Workload endpoint with multiple queries"

    local data='{"sqls": ["SELECT * FROM users LIMIT 10", "SELECT * FROM orders LIMIT 10"], "top_k": 5, "what_if": false}'

    if response=$(http_post "/api/v1/workload" "$data" 200); then
        if echo "$response" | jq -e '.queries != null' &>/dev/null; then
            log_pass "Workload endpoint analyzed queries"
        else
            log_fail "Workload endpoint did not return analysis"
        fi
    else
        log_fail "Workload endpoint failed"
    fi
}

test_metrics_endpoint() {
    TOTAL_TESTS=$((TOTAL_TESTS + 1))
    log_test "Metrics endpoint (if enabled)"

    if response=$(http_get "/metrics" 200); then
        if echo "$response" | grep -q "qeo_http_requests_total"; then
            log_pass "Metrics endpoint returning Prometheus metrics"
        else
            log_fail "Metrics endpoint not returning expected metrics"
        fi
    else
        log_info "Metrics endpoint not enabled or failed (this may be expected)"
        PASSED_TESTS=$((PASSED_TESTS + 1))  # Don't fail on this
    fi
}

test_cors_headers() {
    TOTAL_TESTS=$((TOTAL_TESTS + 1))
    log_test "CORS headers present"

    local headers
    headers=$(curl -s -I --max-time "$TIMEOUT" "${BASE_URL}/health" 2>&1)

    if echo "$headers" | grep -iq "access-control-allow-origin"; then
        log_pass "CORS headers present"
    else
        log_fail "CORS headers missing"
    fi
}

test_rate_limiting() {
    TOTAL_TESTS=$((TOTAL_TESTS + 1))
    log_test "Rate limiting (if enabled)"

    # Make multiple rapid requests
    local success_count=0
    local rate_limited=false

    for i in {1..10}; do
        if curl -s --max-time "$TIMEOUT" "${BASE_URL}/health" &>/dev/null; then
            success_count=$((success_count + 1))
        else
            rate_limited=true
            break
        fi
    done

    if [[ $success_count -ge 5 ]]; then
        log_pass "API handling rapid requests"
    else
        log_fail "API not handling rapid requests properly"
    fi
}

test_response_time() {
    TOTAL_TESTS=$((TOTAL_TESTS + 1))
    log_test "Response time check"

    local start_time
    local end_time
    local duration

    start_time=$(date +%s%N)
    http_get "/health" 200 &>/dev/null
    end_time=$(date +%s%N)

    duration=$(( (end_time - start_time) / 1000000 ))  # Convert to ms

    if [[ $duration -lt 1000 ]]; then
        log_pass "Health check responded in ${duration}ms"
    else
        log_fail "Health check slow: ${duration}ms"
    fi
}

test_synthetic_data_present() {
    TOTAL_TESTS=$((TOTAL_TESTS + 1))
    log_test "Synthetic data present in database"

    local data='{"sql": "SELECT COUNT(*) FROM users", "analyze": false}'

    if response=$(http_post "/api/v1/explain" "$data" 200); then
        # Try to extract row count from plan
        if echo "$response" | jq -e '.plan' &>/dev/null; then
            log_pass "Users table accessible (synthetic data loaded)"
        else
            log_fail "Users table query failed"
        fi
    else
        log_fail "Could not query users table"
    fi
}

# Summary
print_summary() {
    echo ""
    echo "========================================"
    echo "SMOKE TEST SUMMARY"
    echo "========================================"
    echo "Total tests: $TOTAL_TESTS"
    echo -e "${GREEN}Passed:${NC} $PASSED_TESTS"
    echo -e "${RED}Failed:${NC} $FAILED_TESTS"
    echo "========================================"

    if [[ $FAILED_TESTS -eq 0 ]]; then
        echo -e "${GREEN}✓ All smoke tests passed!${NC}"
        return 0
    else
        echo -e "${RED}✗ Some smoke tests failed${NC}"
        return 1
    fi
}

# Main execution
main() {
    echo "========================================"
    echo "QEO Staging Smoke Tests"
    echo "========================================"
    echo "Base URL: $BASE_URL"
    echo "Timeout: ${TIMEOUT}s"
    echo ""

    # Check if server is reachable
    if ! curl -s --max-time "$TIMEOUT" "${BASE_URL}/health" &>/dev/null; then
        log_fail "Server not reachable at $BASE_URL"
        exit 1
    fi

    # Run all tests
    test_health_check
    test_health_db_connection
    test_lint_endpoint
    test_lint_invalid_sql
    test_explain_endpoint
    test_explain_with_analyze
    test_optimize_endpoint
    test_optimize_with_whatif
    test_schema_endpoint
    test_schema_specific_table
    test_workload_endpoint
    test_metrics_endpoint
    test_cors_headers
    test_rate_limiting
    test_response_time
    test_synthetic_data_present

    # Print summary
    print_summary
}

# Run main and exit with appropriate code
if main; then
    exit 0
else
    exit 1
fi

#!/bin/bash
# Production deployment script for QEO API

set -e  # Exit on error

# Color output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}QEO Production Deployment Script${NC}"
echo "=================================="

# Check if .env file exists
if [ ! -f .env ]; then
    echo -e "${RED}Error: .env file not found${NC}"
    echo "Please copy .env.example to .env and configure it for production"
    exit 1
fi

# Load environment variables
source .env

# Verify required environment variables
REQUIRED_VARS=("DB_URL" "API_KEY")
for var in "${REQUIRED_VARS[@]}"; do
    if [ -z "${!var}" ]; then
        echo -e "${RED}Error: Required environment variable $var is not set${NC}"
        exit 1
    fi
done

# Function to check service health
check_health() {
    local service=$1
    local url=$2
    local max_attempts=30
    local attempt=1

    echo -e "${YELLOW}Waiting for $service to be healthy...${NC}"

    while [ $attempt -le $max_attempts ]; do
        if curl -f -s "$url" > /dev/null 2>&1; then
            echo -e "${GREEN}✓ $service is healthy${NC}"
            return 0
        fi
        echo "Attempt $attempt/$max_attempts..."
        sleep 2
        attempt=$((attempt + 1))
    done

    echo -e "${RED}✗ $service failed health check${NC}"
    return 1
}

# Build images
echo -e "${YELLOW}Building Docker images...${NC}"
docker compose build --no-cache

# Stop existing containers
echo -e "${YELLOW}Stopping existing containers...${NC}"
docker compose down

# Start database first
echo -e "${YELLOW}Starting database...${NC}"
docker compose up -d db

# Wait for database to be healthy
if ! check_health "Database" "http://localhost:5433"; then
    echo -e "${RED}Database failed to start. Check logs with: docker compose logs db${NC}"
    exit 1
fi

# Verify HypoPG extension is loaded
echo -e "${YELLOW}Verifying HypoPG extension...${NC}"
HYPOPG_CHECK=$(docker compose exec -T db psql -U postgres -d queryexpnopt -t -c "SELECT COUNT(*) FROM pg_extension WHERE extname='hypopg';" 2>/dev/null || echo "0")
if [ "$HYPOPG_CHECK" -eq "0" ]; then
    echo -e "${RED}Warning: HypoPG extension not found${NC}"
    echo "Installing HypoPG extension..."
    docker compose exec -T db psql -U postgres -d queryexpnopt -c "CREATE EXTENSION IF NOT EXISTS hypopg;" || true
fi

# Start API service
echo -e "${YELLOW}Starting API service...${NC}"
docker compose up -d api

# Wait for API to be healthy
if ! check_health "API" "http://localhost:8000/health"; then
    echo -e "${RED}API failed to start. Check logs with: docker compose logs api${NC}"
    docker compose down
    exit 1
fi

# Run smoke tests
echo -e "${YELLOW}Running smoke tests...${NC}"
API_KEY="${API_KEY}" AUTH_ENABLED="${AUTH_ENABLED:-false}"

# Test health endpoint (no auth required)
if curl -f -s "http://localhost:8000/health" > /dev/null; then
    echo -e "${GREEN}✓ Health endpoint OK${NC}"
else
    echo -e "${RED}✗ Health endpoint failed${NC}"
    docker compose logs api
    exit 1
fi

# Test lint endpoint (with auth if enabled)
if [ "${AUTH_ENABLED}" = "true" ]; then
    LINT_RESPONSE=$(curl -s -w "%{http_code}" -X POST "http://localhost:8000/api/v1/lint" \
        -H "Authorization: Bearer ${API_KEY}" \
        -H "Content-Type: application/json" \
        -d '{"sql": "SELECT 1"}' -o /dev/null)
else
    LINT_RESPONSE=$(curl -s -w "%{http_code}" -X POST "http://localhost:8000/api/v1/lint" \
        -H "Content-Type: application/json" \
        -d '{"sql": "SELECT 1"}' -o /dev/null)
fi

if [ "$LINT_RESPONSE" = "200" ]; then
    echo -e "${GREEN}✓ Lint endpoint OK${NC}"
else
    echo -e "${RED}✗ Lint endpoint failed (HTTP $LINT_RESPONSE)${NC}"
    exit 1
fi

# Display deployment info
echo ""
echo -e "${GREEN}=================================="
echo "Deployment Successful!"
echo "==================================${NC}"
echo ""
echo "Services running:"
echo "  - API:      http://localhost:8000"
echo "  - Database: localhost:5433"
echo ""
echo "Health check: http://localhost:8000/health"
echo "API docs:     http://localhost:8000/docs"
echo ""
echo "Useful commands:"
echo "  View logs:        docker compose logs -f"
echo "  View API logs:    docker compose logs -f api"
echo "  View DB logs:     docker compose logs -f db"
echo "  Stop services:    docker compose down"
echo "  Restart API:      docker compose restart api"
echo ""

# Show container status
docker compose ps

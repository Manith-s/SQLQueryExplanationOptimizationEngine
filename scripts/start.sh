#!/bin/bash
# ============================================================================
# SQL Query Optimizer - Main Startup Script (Unix/Mac/Linux)
#
# This script starts the complete system:
# - PostgreSQL database with HypoPG extension
# - FastAPI web server with optimization engine
#
# Usage: ./start.sh [port]
# Default port: 9000
# ============================================================================

set -e

# Parse port argument (default: 9000)
PORT=${1:-9000}

clear

echo ""
echo "========================================================================"
echo "  SQL Query Optimizer - Starting System"
echo "========================================================================"
echo ""
echo "  Port: $PORT"
echo "  Database: PostgreSQL (port 5433)"
echo "  UI: http://localhost:$PORT"
echo ""
echo "========================================================================"
echo ""

# Step 1: Verify Docker is running
echo "[1/5] Verifying Docker..."
if ! docker ps > /dev/null 2>&1; then
    echo ""
    echo "[ERROR] Docker is not running!"
    echo ""
    echo "Please start Docker and wait for it to be ready, then try again."
    echo ""
    exit 1
fi
echo "      [OK] Docker is running"
echo ""

# Step 2: Clean up any old servers on this port
echo "[2/5] Cleaning up existing processes on port $PORT..."
lsof -ti:$PORT | xargs kill -9 2>/dev/null || true
echo "      [OK] Port $PORT is clean"
echo ""

# Step 3: Start PostgreSQL database
echo "[3/5] Starting PostgreSQL database..."
docker compose up -d db > /dev/null 2>&1
if [ $? -ne 0 ]; then
    echo "      [ERROR] Failed to start database"
    echo "      Check docker-compose.yml and .env file"
    exit 1
fi
sleep 3
echo "      [OK] Database started"
echo ""

# Step 4: Activate virtual environment (if exists)
echo "[4/5] Setting up Python environment..."
if [ -f .venv/bin/activate ]; then
    source .venv/bin/activate
    echo "      [OK] Virtual environment activated"
else
    echo "      [WARN] Virtual environment not found, using system Python"
fi

# Set environment variables
export PYTHONPATH=src
export DB_URL=postgresql+psycopg2://postgres:password@localhost:5433/queryexpnopt
echo "      [OK] Environment configured"
echo ""

# Step 5: Start the web server
echo "[5/5] Starting web server..."
echo ""
echo "========================================================================"
echo "  SYSTEM READY!"
echo "========================================================================"
echo ""
echo "  Open your browser to: http://localhost:$PORT"
echo ""
echo "  Features:"
echo "  - Web UI for query optimization"
echo "  - API documentation at http://localhost:$PORT/docs"
echo "  - Health check at http://localhost:$PORT/health"
echo ""
echo "  Press Ctrl+C to stop the server"
echo "========================================================================"
echo ""

# Start the server
python simple_server.py $PORT

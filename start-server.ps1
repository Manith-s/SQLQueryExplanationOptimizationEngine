# QEO Server Startup Script
# This script starts the server with the correct database configuration

Write-Host "Starting QEO Server..." -ForegroundColor Green
Write-Host ""

# Set database URL for local development
$env:DB_URL = "postgresql+psycopg2://postgres:password@localhost:5433/queryexpnopt"
Write-Host "DB_URL set to: $env:DB_URL" -ForegroundColor Cyan
Write-Host ""

# Check if PostgreSQL is running (optional)
Write-Host "Note: Make sure PostgreSQL is running on localhost:5433" -ForegroundColor Yellow
Write-Host "To start PostgreSQL: docker compose up -d db" -ForegroundColor Yellow
Write-Host ""

# Start the server
Write-Host "Starting server on http://127.0.0.1:8000..." -ForegroundColor Green
Write-Host "Press Ctrl+C to stop the server" -ForegroundColor Yellow
Write-Host ""

python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload







@echo off
REM ============================================================================
REM  SQL Query Optimizer - Main Startup Script (Windows)
REM
REM  This script starts the complete system:
REM  - PostgreSQL database with HypoPG extension
REM  - FastAPI web server with optimization engine
REM
REM  Usage: start.bat [port]
REM  Default port: 9000
REM ============================================================================

cls
setlocal

REM Parse port argument (default: 9000)
set PORT=9000
if not "%1"=="" set PORT=%1

echo.
echo ========================================================================
echo   SQL Query Optimizer - Starting System
echo ========================================================================
echo.
echo   Port: %PORT%
echo   Database: PostgreSQL (port 5433)
echo   UI: http://localhost:%PORT%
echo.
echo ========================================================================
echo.

REM Step 1: Verify Docker is running
echo [1/5] Verifying Docker...
docker ps >nul 2>&1
if errorlevel 1 (
    echo.
    echo [ERROR] Docker is not running!
    echo.
    echo Please start Docker Desktop and wait for it to be ready, then try again.
    echo.
    pause
    exit /b 1
)
echo       [OK] Docker is running
echo.

REM Step 2: Clean up any old servers on this port
echo [2/5] Cleaning up existing processes on port %PORT%...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%PORT% " ^| findstr LISTENING') do (
    echo       Stopping process %%a
    taskkill /PID %%a /F >nul 2>&1
)
echo       [OK] Port %PORT% is clean
echo.

REM Step 3: Start PostgreSQL database
echo [3/5] Starting PostgreSQL database...
docker compose up -d db >nul 2>&1
if errorlevel 1 (
    echo       [ERROR] Failed to start database
    echo       Check docker-compose.yml and .env file
    pause
    exit /b 1
)
timeout /t 3 /nobreak >nul
echo       [OK] Database started
echo.

REM Step 4: Activate virtual environment (if exists)
echo [4/5] Setting up Python environment...
if exist .venv\Scripts\activate.bat (
    call .venv\Scripts\activate.bat
    echo       [OK] Virtual environment activated
) else (
    echo       [WARN] Virtual environment not found, using system Python
)

REM Set environment variables
set PYTHONPATH=src
set DB_URL=postgresql+psycopg2://postgres:password@localhost:5433/queryexpnopt
echo       [OK] Environment configured
echo.

REM Step 5: Start the web server
echo [5/5] Starting web server...
echo.
echo ========================================================================
echo   SYSTEM READY!
echo ========================================================================
echo.
echo   Open your browser to: http://localhost:%PORT%
echo.
echo   Features:
echo   - Web UI for query optimization
echo   - API documentation at http://localhost:%PORT%/docs
echo   - Health check at http://localhost:%PORT%/health
echo.
echo   Press Ctrl+C to stop the server
echo ========================================================================
echo.

REM Start the server
python simple_server.py %PORT%

REM Cleanup on exit
if errorlevel 1 (
    echo.
    echo [ERROR] Server failed to start
    echo Check the error messages above
    pause
)

endlocal

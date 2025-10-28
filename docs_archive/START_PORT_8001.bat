@echo off
cls
echo.
echo ========================================================================
echo   SQL QUERY OPTIMIZER - STARTING ON PORT 8001
echo ========================================================================
echo.

REM Check Docker
docker ps >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Docker not running! Please start Docker Desktop.
    pause
    exit /b 1
)

REM Start database
echo Starting database...
docker compose up -d db >nul 2>&1
timeout /t 3 /nobreak >nul

REM Activate venv if exists
if exist .venv\Scripts\activate.bat call .venv\Scripts\activate.bat

REM Set environment
set PYTHONPATH=src
set DB_URL=postgresql+psycopg2://postgres:password@localhost:5433/queryexpnopt

echo.
echo ========================================================================
echo   READY! Opening http://localhost:8001  <<<< NOTE: PORT 8001
echo ========================================================================
echo.
echo   Open your browser to: http://localhost:8001
echo.
echo   Press Ctrl+C to stop
echo ========================================================================
echo.

REM Start server on port 8001
python simple_server.py 8001

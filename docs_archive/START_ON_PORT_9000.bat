@echo off
cls

echo.
echo ====================================================================
echo   SQL Query Optimizer - Starting on PORT 9000
echo   (Using different port to avoid conflicts)
echo ====================================================================
echo.

REM Check Docker
docker ps >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Docker is not running!
    echo Please start Docker Desktop and run this script again.
    pause
    exit /b 1
)
echo [OK] Docker is running

REM Start database
echo Starting database...
docker compose up -d db >nul 2>&1
timeout /t 3 /nobreak >nul
echo [OK] Database started

REM Activate venv
if exist .venv\Scripts\activate.bat (
    call .venv\Scripts\activate.bat
)

REM Set environment
set PYTHONPATH=src
set DB_URL=postgresql+psycopg2://postgres:password@localhost:5433/queryexpnopt

echo.
echo ====================================================================
echo   Starting Web Server on PORT 9000
echo ====================================================================
echo.
echo   OPEN YOUR BROWSER TO: http://localhost:9000
echo.
echo   Press Ctrl+C to stop the server
echo ====================================================================
echo.

REM Start the server on port 9000
python simple_server.py 9000

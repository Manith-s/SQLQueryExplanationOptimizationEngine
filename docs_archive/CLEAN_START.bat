@echo off
cls

echo.
echo ====================================================================
echo   SQL Query Optimizer - Clean Start
echo ====================================================================
echo.

REM Kill any existing processes on port 8000
echo Step 1: Cleaning up old servers...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000 ^| findstr LISTENING') do (
    taskkill /PID %%a /F >nul 2>&1
)

REM Check Docker
echo Step 2: Checking Docker...
docker ps >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Docker is not running!
    echo Please start Docker Desktop and run this script again.
    pause
    exit /b 1
)
echo [OK] Docker is running

REM Start database
echo Step 3: Starting database...
docker compose up -d db >nul 2>&1
timeout /t 5 /nobreak >nul
echo [OK] Database started

REM Activate venv
if exist .venv\Scripts\activate.bat (
    call .venv\Scripts\activate.bat
    echo [OK] Virtual environment activated
)

REM Set environment
set PYTHONPATH=src
set DB_URL=postgresql+psycopg2://postgres:password@localhost:5433/queryexpnopt

echo.
echo ====================================================================
echo   Starting Web Server...
echo ====================================================================
echo.
echo   IMPORTANT: Open your browser to http://localhost:8000
echo.
echo   You should see a purple web interface with SQL query box
echo.
echo   Press Ctrl+C to stop the server
echo ====================================================================
echo.

REM Start the server
python simple_server.py

pause

@echo off
cls
echo.
echo ========================================================================
echo   SQL QUERY OPTIMIZER - EASY STARTUP
echo ========================================================================
echo.
echo This will start the optimizer with the web interface
echo.
echo Step 1: Checking Docker...

docker ps >nul 2>&1
if errorlevel 1 (
    echo.
    echo [X] Docker is not running!
    echo.
    echo Please:
    echo   1. Start Docker Desktop
    echo   2. Wait for it to be ready
    echo   3. Run this script again
    echo.
    pause
    exit /b 1
)

echo [OK] Docker is running
echo.
echo Step 2: Starting database...

docker compose up -d db >nul 2>&1

echo [OK] Database started
echo.
echo Step 3: Waiting for database to be ready...

timeout /t 5 /nobreak >nul

echo [OK] Database is ready
echo.
echo Step 4: Starting web server...
echo.

REM Activate virtual environment if it exists
if exist .venv\Scripts\activate.bat (
    call .venv\Scripts\activate.bat
)

REM Set environment
set PYTHONPATH=src
set DB_URL=postgresql+psycopg2://postgres:password@localhost:5433/queryexpnopt

echo ========================================================================
echo   SUCCESS! System is starting...
echo ========================================================================
echo.
echo   OPEN YOUR BROWSER TO: http://localhost:8000
echo.
echo   You should see a purple web interface with:
echo   - SQL query text box
echo   - Example queries to click
echo   - Optimize button
echo.
echo   If you see JSON instead of a web page:
echo   - Wait 5 seconds and refresh your browser
echo   - The server is loading...
echo.
echo ========================================================================
echo   Press Ctrl+C to stop (then close this window)
echo ========================================================================
echo.

REM Start server
python -m uvicorn app.main:app --reload --app-dir src --host 0.0.0.0 --port 8000

pause

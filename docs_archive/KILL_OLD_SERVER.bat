@echo off
echo Killing any process using port 8000...

for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000') do (
    echo Found process %%a on port 8000
    taskkill /PID %%a /F
)

echo Done!
timeout /t 2

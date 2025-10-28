# PowerShell script to forcefully kill anything on port 8000
Write-Host "Killing all processes using port 8000..." -ForegroundColor Yellow

$connections = netstat -ano | Select-String ":8000" | Select-String "LISTENING"

if ($connections) {
    foreach ($connection in $connections) {
        $parts = $connection -split '\s+' | Where-Object { $_ -ne '' }
        $pid = $parts[-1]

        if ($pid -match '^\d+$') {
            Write-Host "Found process $pid using port 8000" -ForegroundColor Cyan
            try {
                Stop-Process -Id $pid -Force
                Write-Host "Killed process $pid" -ForegroundColor Green
            } catch {
                Write-Host "Could not kill process $pid - may need admin rights" -ForegroundColor Red
            }
        }
    }
    Write-Host "`nAll processes killed. Wait 2 seconds..." -ForegroundColor Yellow
    Start-Sleep -Seconds 2
} else {
    Write-Host "No process found on port 8000" -ForegroundColor Green
}

Write-Host "`nDone! Now run CLEAN_START.bat" -ForegroundColor Green

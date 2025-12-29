# Auto-fix linting issues with ruff and black (PowerShell)

Write-Host "🔍 Running ruff check with auto-fix..." -ForegroundColor Cyan
ruff check . --fix

Write-Host "✅ Running ruff check (verification)..." -ForegroundColor Green
ruff check .

Write-Host "🎨 Running black formatter..." -ForegroundColor Cyan
black .

Write-Host "✨ All linting issues fixed!" -ForegroundColor Green


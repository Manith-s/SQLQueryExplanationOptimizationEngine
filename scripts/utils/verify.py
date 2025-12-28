"""
Quick verification script to check if everything is set up correctly.
Run this before starting the server: python verify.py
"""

import subprocess
import sys
from pathlib import Path

print("=" * 70)
print("  SQL Query Optimizer - System Verification")
print("=" * 70)
print()

errors = []
warnings = []

# Check 1: Python version
print("✓ Checking Python version...")
if sys.version_info < (3, 8):
    errors.append("Python 3.8+ required")
else:
    print(f"  Python {sys.version_info.major}.{sys.version_info.minor} OK")

# Check 2: Required directories
print("\n✓ Checking directories...")
dirs_to_check = [
    "src",
    "src/app",
    "src/app/static",
    "src/app/routers",
    "src/app/core"
]
for d in dirs_to_check:
    if not Path(d).exists():
        errors.append(f"Missing directory: {d}")
    else:
        print(f"  {d}/ exists")

# Check 3: Critical files
print("\n✓ Checking critical files...")
files_to_check = [
    "src/app/static/index.html",
    "src/app/main.py",
    "simple_server.py",
    "docker-compose.yml",
    ".env"
]
for f in files_to_check:
    path = Path(f)
    if not path.exists():
        errors.append(f"Missing file: {f}")
    else:
        size = path.stat().st_size
        print(f"  {f} exists ({size:,} bytes)")

# Check 4: Web UI file content
print("\n✓ Checking web UI...")
index_path = Path("src/app/static/index.html")
if index_path.exists():
    content = index_path.read_text(encoding='utf-8')
    if "SQL Query Optimizer" in content:
        print("  Web UI HTML looks good")
    else:
        errors.append("Web UI HTML file seems corrupted")
    if len(content) < 1000:
        warnings.append("Web UI HTML file seems too small")

# Check 5: Required Python packages
print("\n✓ Checking Python packages...")
required_packages = [
    "fastapi",
    "uvicorn",
    "sqlglot",
    "psycopg2"
]
for pkg in required_packages:
    try:
        __import__(pkg)
        print(f"  {pkg} installed")
    except ImportError:
        errors.append(f"Missing package: {pkg} (run: pip install {pkg})")

# Check 6: Docker
print("\n✓ Checking Docker...")

try:
    result = subprocess.run(["docker", "ps"], capture_output=True, timeout=5)
    if result.returncode == 0:
        print("  Docker is running")
    else:
        warnings.append("Docker not responding - start Docker Desktop")
except Exception as e:
    warnings.append(f"Cannot check Docker: {e}")

# Summary
print("\n" + "=" * 70)
if errors:
    print("❌ ERRORS FOUND:")
    for e in errors:
        print(f"  - {e}")
    print("\nFix these errors before starting the server!")
elif warnings:
    print("⚠️  WARNINGS:")
    for w in warnings:
        print(f"  - {w}")
    print("\nYou can try starting the server, but fix warnings if issues occur.")
else:
    print("✅ ALL CHECKS PASSED!")
    print("\nYou're ready to start the server:")
    print("  Run: CLEAN_START.bat")
    print("  Then open: http://localhost:8000")

print("=" * 70)

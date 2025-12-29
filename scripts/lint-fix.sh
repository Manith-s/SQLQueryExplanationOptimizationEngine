#!/bin/bash
# Auto-fix linting issues with ruff and black

set -e

echo "🔍 Running ruff check with auto-fix..."
ruff check . --fix

echo "✅ Running ruff check (verification)..."
ruff check .

echo "🎨 Running black formatter..."
black .

echo "✅ Verifying black formatting..."
black --check .

echo "✨ All linting issues fixed!"

#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/.."

# Activate virtual environment if present
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

echo "== Rebuilding demo git repositories (tests run against them) =="
python3 scripts/setup_demo_repos.py

echo "== Running backend test suite (unittest; pytest used automatically if installed) =="
cd backend
if python3 -c "import pytest" 2>/dev/null; then
    python3 -m pytest tests/ -v
else
    echo "(pytest not installed in this environment — using stdlib unittest instead)"
    python3 -m unittest discover -s tests -v
fi

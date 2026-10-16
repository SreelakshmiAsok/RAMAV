#!/usr/bin/env bash
# Builds demo repos (idempotent) and starts the RAMAV backend, which also
# serves the frontend dashboard from the same origin.
set -e
cd "$(dirname "$0")/.."

# Activate virtual environment if present
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

export PATH="$HOME/.local/bin:$PATH"

# Start Ollama service if installed and not yet running
if command -v ollama >/dev/null 2>&1; then
    if ! curl -s --max-time 1 http://localhost:11434/api/tags >/dev/null 2>&1; then
        echo "== RAMAV: starting Ollama service in background =="
        ollama serve >/dev/null 2>&1 &
        sleep 1
    fi
fi

echo "== RAMAV: setting up demo repositories =="
python3 scripts/setup_demo_repos.py

echo "== RAMAV: installing backend dependencies =="
python3 -m pip install -r backend/requirements.txt --quiet || python3 -m pip install -r backend/requirements.txt --break-system-packages --quiet

echo "== RAMAV: starting backend (serves API + dashboard on http://localhost:8000) =="
cd backend
export RAMAV_PORT="${RAMAV_PORT:-8000}"
python3 -m app.main

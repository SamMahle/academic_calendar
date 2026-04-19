#!/usr/bin/env bash
set -e

echo "CadetCal Launcher"
echo "-----------------"

# Check Python
if ! command -v python3 &>/dev/null; then
    echo "ERROR: python3 not found."
    echo "Install Python 3.11+ from https://www.python.org/downloads/"
    exit 1
fi

# Create venv on first run
if [ ! -d ".venv" ]; then
    echo "Setting up for first use — this takes about a minute..."
    python3 -m venv .venv
    source .venv/bin/activate
    pip install --quiet --upgrade pip
    pip install --quiet -r requirements.txt
    echo "Setup complete."
else
    source .venv/bin/activate
fi

echo "Starting CadetCal..."
# Open browser after a short delay so the server has time to start
(sleep 2 && open "http://localhost:8501" 2>/dev/null || xdg-open "http://localhost:8501" 2>/dev/null || true) &
streamlit run app.py --server.headless true --server.port 8501

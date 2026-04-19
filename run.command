#!/usr/bin/env bash
# Double-click this file in Finder to launch CadetCal.
set -e

# Always run from the folder this file lives in
cd "$(dirname "$0")"

echo "CadetCal Launcher"
echo "-----------------"

# Check Python
if ! command -v python3 &>/dev/null; then
    echo "ERROR: python3 not found."
    echo "Install Python 3.11+ from https://www.python.org/downloads/"
    read -p "Press Enter to close..."
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

echo "Starting CadetCal — browser will open automatically..."
(sleep 2 && open "http://localhost:8501") &
streamlit run app.py --server.headless true --server.port 8501

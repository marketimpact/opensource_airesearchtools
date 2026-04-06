#!/bin/bash
# Entry point for launchd. Activates venv and runs the research agent.
# Update PROJECT_DIR to match your installation path.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

# Ensure Ollama is running
if ! pgrep -q ollama; then
    echo "Starting Ollama..."
    brew services start ollama
    sleep 5
fi

source .venv/bin/activate
python3 -m research.agent 2>&1

#!/bin/bash
# One-time setup for the research agent.
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"

echo "=== Research Agent Setup ==="

# 1. Create venv if needed
if [ ! -d ".venv" ]; then
    echo "Creating Python virtual environment..."
    python3 -m venv .venv
fi

echo "Installing dependencies..."
.venv/bin/pip install --quiet ollama duckduckgo-search pyyaml

# 2. Create directories
mkdir -p data/logs

# 3. Pull Gemma 4 31B
echo "Pulling Gemma 4 31B (this may take a while)..."
ollama pull gemma4:31b

echo ""
echo "=== Setup Complete ==="
echo "Edit configs/research-agent.yaml to customize your queries."
echo "Test with: source .venv/bin/activate && python3 -m research.agent"

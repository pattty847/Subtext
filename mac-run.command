#!/usr/bin/env bash
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "Subtext"
echo ""

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is not installed."
  echo "Install it from: https://docs.astral.sh/uv/getting-started/installation/"
  read -r -n 1 -p "Press any key to close..."
  exit 1
fi

if [ ! -d ".venv" ]; then
  echo "Setting up environment with uv sync..."
  if ! uv sync; then
    echo "Setup failed."
    read -r -n 1 -p "Press any key to close..."
    exit 1
  fi
fi

echo "  [1] Desktop app         - full local workflow with AI analysis"
echo "  [2] Private web service - localhost service for browser/Tailscale use"
echo ""
read -r -p "Choose 1 or 2: " pick
echo ""

case "${pick:-1}" in
  2)
    echo "Starting private web service..."
    echo "Local check: http://127.0.0.1:8000"
    echo "For iPhone access, pair it with Tailscale Serve."
    echo ""
    uv run python run_web.py
    ;;
  *)
    echo "Launching Subtext Desktop app..."
    uv run python run.py
    ;;
esac

if [ $? -ne 0 ]; then
  echo ""
  echo "Application exited with an error."
  read -r -n 1 -p "Press any key to close..."
  exit 1
fi

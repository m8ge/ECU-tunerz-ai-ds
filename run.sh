#!/bin/bash
# APEX CAL // AI ECU Calibration Optimizer & Web Dashboard Launcher

set -e

# Change directory to script directory
cd "$(dirname "$0")"

# Locate best python interpreter
if [ -f "./venv/bin/python" ]; then
  PYTHON="./venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON="python3"
elif command -v python >/dev/null 2>&1; then
  PYTHON="python"
else
  echo "❌ Error: Python 3 was not found on your system."
  echo "Please install Python 3 or ensure it is in your PATH."
  exit 1
fi

ACTION="${1:-server}"

case "$ACTION" in
  server|web|start)
    echo "🚀 Starting APEX CAL Web Dashboard..."
    exec "$PYTHON" server.py "${2:-8080}"
    ;;
  optimize|pipeline|train)
    echo "🏁 Running Calibration Optimization Pipeline..."
    exec "$PYTHON" main.py
    ;;
  all|full)
    echo "🏁 Running Optimization & Launching Web Dashboard..."
    exec "$PYTHON" main.py --serve
    ;;
  build|package|bundle|zip)
    echo "📦 Building netlify_deploy.zip and dist/..."
    exec "$PYTHON" build.py
    ;;
  *)
    echo "Usage: ./run.sh [server | optimize | all | build]"
    echo "  ./run.sh         -> Start the local web dashboard"
    echo "  ./run.sh optimize -> Run the 30-cell optimization pipeline"
    echo "  ./run.sh all      -> Run optimization, then launch dashboard"
    echo "  ./run.sh build    -> Package netlify_deploy.zip for Netlify deployment"
    exit 1
    ;;
esac

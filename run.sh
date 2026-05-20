#!/usr/bin/env bash
# run.sh — Start the Tenthline development server
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Create and activate virtual environment if it doesn't exist
if [ ! -d ".venv" ]; then
  echo "🔧 Creating Python virtual environment..."
  python3 -m venv .venv
fi

source .venv/bin/activate

# Install / upgrade dependencies
echo "📦 Installing dependencies..."
pip install --quiet --upgrade pip
pip install --quiet -r backend/requirements.txt

echo ""
echo "⚖  Tenthline is starting..."
echo "   Open http://localhost:8000 in your browser"
echo "   Press Ctrl+C to stop"
echo ""

uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload

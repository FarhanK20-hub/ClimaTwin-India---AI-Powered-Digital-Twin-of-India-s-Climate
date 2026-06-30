#!/bin/bash
echo "==================================================="
echo "  ClimaTwin India - AI Digital Twin of Climate"
echo "  ISRO Hack2Skill 2026 - Maharashtra Pilot"
echo "==================================================="

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 not found."
    exit 1
fi

# Create venv if missing
if [ ! -d ".venv" ]; then
    echo "[1/3] Creating virtual environment..."
    python3 -m venv .venv
fi

echo "[2/3] Installing dependencies..."
source .venv/bin/activate
pip install -r requirements.txt -q

echo "[3/3] Starting ClimaTwin India server..."
echo ""
echo " Dashboard: http://127.0.0.1:8000"
echo " Press Ctrl+C to stop."
echo ""

python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload

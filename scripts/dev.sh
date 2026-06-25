#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
source .venv/bin/activate

pip install -q -r api/requirements.txt
pip install -q -r requirements.txt 2>/dev/null || \
  echo "Note: skipped core requirements (alphasift needs Python 3.10+; API/web still runs)"

if [[ ! -d frontend/node_modules ]]; then
  (cd frontend && npm install)
fi

echo "API:  http://127.0.0.1:8000  (LAN: add --host 0.0.0.0 for iPhone)"
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000 &
API_PID=$!

cleanup() {
  kill "$API_PID" 2>/dev/null || true
}
trap cleanup EXIT

sleep 2
echo "Starting web on http://127.0.0.1:5173"
(cd frontend && npm run dev -- --host 127.0.0.1)

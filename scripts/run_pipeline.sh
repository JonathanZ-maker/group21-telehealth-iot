#!/usr/bin/env bash
# run_pipeline.sh — start the full defended pipeline locally.
#
# Prerequisites
#   - Python venv activated
#   - pip install -r requirements.txt
#   - .env file populated (see .env.example)
#   - MongoDB Atlas cluster reachable
#
# Opens three terminals' worth of background processes. Ctrl-C kills them all.

set -e
set -o pipefail

if [ -f .env ]; then
  set -a; source .env; set +a
fi

cleanup() {
  echo "Stopping services..."
  kill $CLOUD_PID $GATEWAY_PID 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "[1/3] Starting cloud service on :5000"
python cloud/cloud.py &
CLOUD_PID=$!
sleep 2

echo "[2/3] Starting edge gateway on :8000"
python edge/gateway.py &
GATEWAY_PID=$!
sleep 2

echo "[3/3] Starting wearable simulator"
python edge/wearable.py --speed 5

wait

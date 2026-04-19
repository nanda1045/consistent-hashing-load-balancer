#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"

echo "Starting cluster..."
docker compose up -d --build

echo "Waiting for load balancer health..."
until curl -fsS "$BASE_URL/health" >/dev/null; do
  sleep 1
done

echo "Ring status before failure:"
curl -s "$BASE_URL/ring/status" | python -m json.tool

echo "Stopping worker-2 to simulate node failure..."
docker compose stop worker-2

echo "Waiting 7 seconds for heartbeat TTL + watcher interval..."
sleep 7

echo "Ring status after failure (worker-2 should be gone):"
curl -s "$BASE_URL/ring/status" | python -m json.tool

echo "Demo complete."

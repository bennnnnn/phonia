#!/usr/bin/env bash
# Stop stale Expo/Metro dev servers (ports 8081–8090).
set -euo pipefail

PIDS=$(lsof -tiTCP:8081-8090 -sTCP:LISTEN 2>/dev/null || true)
if [[ -z "$PIDS" ]]; then
  echo "No Metro servers running."
  exit 0
fi

echo "Stopping Metro PIDs: $PIDS"
kill $PIDS 2>/dev/null || kill -9 $PIDS 2>/dev/null || true
echo "Done."

#!/usr/bin/env bash
# Set EXPO_PUBLIC_API_URL for iOS Simulator / localhost testing.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$ROOT/apps/mobile/.env"
API_URL="http://127.0.0.1:8000"

if [[ ! -f "$ENV_FILE" ]]; then
  cp "$ROOT/apps/mobile/.env.example" "$ENV_FILE"
fi

if grep -q "^EXPO_PUBLIC_API_URL=" "$ENV_FILE"; then
  if [[ "$OSTYPE" == "darwin"* ]]; then
    sed -i '' "s|^EXPO_PUBLIC_API_URL=.*|EXPO_PUBLIC_API_URL=${API_URL}|" "$ENV_FILE"
  else
    sed -i "s|^EXPO_PUBLIC_API_URL=.*|EXPO_PUBLIC_API_URL=${API_URL}|" "$ENV_FILE"
  fi
else
  echo "EXPO_PUBLIC_API_URL=${API_URL}" >> "$ENV_FILE"
fi

echo "Set EXPO_PUBLIC_API_URL=${API_URL} (iOS Simulator / localhost)"

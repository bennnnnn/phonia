#!/usr/bin/env bash
# Set EXPO_PUBLIC_API_URL to this Mac's LAN IP (for physical device testing).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$ROOT/apps/mobile/.env"

IP="$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || true)"
if [[ -z "$IP" ]]; then
  echo "Could not detect LAN IP. Connect to Wi‑Fi and retry." >&2
  exit 1
fi

API_URL="http://${IP}:8000"

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

echo "Set EXPO_PUBLIC_API_URL=${API_URL}"
echo ""
echo "Restart Expo with cache clear:"
echo "  cd apps/mobile && pnpm start -- --clear"

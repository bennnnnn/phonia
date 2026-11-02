#!/usr/bin/env bash
# Print the debug keystore SHA-1 for Google Cloud Console → Android OAuth client.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
KEYSTORE="$ROOT/apps/mobile/android/app/debug.keystore"

if [[ ! -f "$KEYSTORE" ]]; then
  echo "No debug keystore yet. Run: cd apps/mobile && pnpm expo prebuild --platform android" >&2
  exit 1
fi

echo "Add an Android OAuth client in Google Cloud (APIs & Services → Credentials):"
echo "  Package name: com.recall.app"
echo ""
echo "SHA-1 fingerprint (debug build):"
keytool -list -v -keystore "$KEYSTORE" -alias androiddebugkey -storepass android -keypass android 2>/dev/null | grep "SHA1:"
echo ""
echo "Use the same Web client ID in:"
echo "  apps/mobile/.env  → EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID"
echo "  apps/api/.env     → GOOGLE_CLIENT_ID"

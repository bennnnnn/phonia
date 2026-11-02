#!/usr/bin/env bash
# Print cryptographically strong values for production secrets.
# Paste into apps/api/.env.production — never commit that file.
set -euo pipefail

echo "=== Recall production secret generators ==="
echo
echo "JWT_SECRET=$(openssl rand -base64 32 | tr -d '\n')"
echo "REVENUECAT_WEBHOOK_AUTH=$(openssl rand -hex 32)"
echo
echo "Copy the lines above into apps/api/.env.production"
echo "Then fill DATABASE_URL, REDIS_URL, GOOGLE_CLIENT_ID, OPENROUTER_API_KEY, R2_*, CORS_ORIGINS."

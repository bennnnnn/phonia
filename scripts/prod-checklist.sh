#!/usr/bin/env bash
# Pre-launch checklist — verifies repo config; ops secrets are manual (see docs/PRODUCTION.md).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
API_URL="${API_URL:-http://localhost:8000}"
cd "$ROOT"

echo "== Recall production checklist =="
echo

fail=0
warn=0

check() {
  if eval "$2"; then
    echo "  OK  $1"
  else
    echo "  FAIL  $1"
    fail=$((fail + 1))
  fi
}

warn_if() {
  if eval "$2"; then
    echo "  OK  $1"
  else
    echo "  WARN  $1"
    warn=$((warn + 1))
  fi
}

echo "Code gate"
if ./scripts/dev.sh check; then
  echo "  OK  ./scripts/dev.sh check"
else
  echo "  FAIL  ./scripts/dev.sh check"
  fail=$((fail + 1))
fi
echo

echo "API .env.example"
check "JWT access TTL documented as 60m" "grep -q 'JWT_EXPIRE_MINUTES=60' apps/api/.env.example"
check "JWT refresh TTL documented" "grep -q 'JWT_REFRESH_EXPIRE_DAYS' apps/api/.env.example"
check "Sentry DSN documented" "grep -q 'SENTRY_DSN' apps/api/.env.example"
echo

echo "Legal routes ($API_URL)"
warn_if "GET /legal/privacy" "curl -sf '$API_URL/legal/privacy' >/dev/null 2>&1"
warn_if "GET /legal/terms" "curl -sf '$API_URL/legal/terms' >/dev/null 2>&1"
echo

echo "Production env scripts (run on your machine with real secrets):"
warn_if "apps/api/.env.production.example exists" "test -f apps/api/.env.production.example"
warn_if "validate-prod-env.sh executable" "test -x scripts/validate-prod-env.sh"
echo "  Flow: cp .env.production.example → .env.production"
echo "        ./scripts/generate-prod-secrets.sh"
echo "        ./scripts/validate-prod-env.sh"
echo "        ./scripts/fly-secrets-import.sh && ./scripts/deploy-api.sh"
echo

echo "Manual ops (cannot auto-verify — see docs/PRODUCTION.md):"
echo "  - Fly secrets filled per apps/api/.env.production.example"
echo "  - Neon: vector + pg_trgm, alembic upgrade head"
echo "  - EAS: EXPO_PUBLIC_API_URL, production builds, store listings"
echo "  - Hosted legal URLs: https://<api-host>/legal/privacy and /legal/terms"
echo

if [[ "$fail" -gt 0 ]]; then
  echo "FAILED ($fail hard failures, $warn warnings)"
  exit 1
fi

echo "PASSED ($warn warnings — review manual ops above)"
exit 0

#!/usr/bin/env bash
#
# Automated smoke checks — backend health, migration head, local gate optional.
# Does not replace on-device QA (see docs/QA_MATRIX.md). The live checks cover
# the API only; scripts/verify-production.sh --live adds the worker and the
# database's migration state.
#
# Usage:
#   ./scripts/qa-smoke.sh              # static checks only
#   ./scripts/qa-smoke.sh --live       # also hit API health (API must be running)
#   ./scripts/qa-smoke.sh --live-only  # only the API checks (after a deploy)
#   API_URL=https://api.example.com ./scripts/qa-smoke.sh --live
#
# Needs curl, grep and python3 (and uv for the alembic head check).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
API_URL="${API_URL:-http://127.0.0.1:8000}"
LIVE=0
STATIC=1
case "${1:-}" in
  --live) LIVE=1 ;;
  --live-only) LIVE=1 STATIC=0 ;;
esac

fail=0

if [[ "$STATIC" -eq 1 ]]; then
  echo "==> Alembic has a single head"
  if command -v uv >/dev/null 2>&1; then
    HEADS_OUT="$(
      cd "$ROOT/apps/api" && uv run alembic heads 2>/dev/null || true
    )"
    HEAD_COUNT="$(printf '%s\n' "$HEADS_OUT" | grep -c '(head)' || true)"
    if [[ "${HEAD_COUNT:-0}" == "1" ]]; then
      echo "    OK: $(printf '%s\n' "$HEADS_OUT" | head -1)"
    else
      echo "    FAIL: expected exactly one alembic head, got:"
      printf '%s\n' "${HEADS_OUT:-<empty>}" | sed 's/^/      /'
      fail=1
    fi
  else
    echo "    WARN: uv not found — skipped"
  fi

  echo "==> Production env template covers required keys"
  REQUIRED_KEYS=(
    ENVIRONMENT
    DATABASE_URL
    REDIS_URL
    JWT_SECRET
    GOOGLE_CLIENT_ID
    OPENROUTER_API_KEY
    CORS_ORIGINS
    REVENUECAT_WEBHOOK_AUTH
    REVENUECAT_SECRET_KEY
    DAILY_GLOBAL_SPEND_USD
    STORAGE_BACKEND
    R2_ACCOUNT_ID
    R2_ACCESS_KEY_ID
    R2_SECRET_ACCESS_KEY
    R2_BUCKET
  )
  env_fail=0
  for key in "${REQUIRED_KEYS[@]}"; do
    if ! grep -q "^${key}=" "$ROOT/apps/api/.env.production.example"; then
      echo "    FAIL: missing $key in apps/api/.env.production.example"
      env_fail=1
    fi
  done
  if [[ "$env_fail" -eq 0 ]]; then
    echo "    OK"
  else
    fail=1
  fi
fi

if [[ "$LIVE" -eq 1 ]]; then
  echo "==> Live health: $API_URL/health"
  if curl -sf --max-time 10 "$API_URL/health" | grep -q '"status": *"ok"'; then
    echo "    OK"
  else
    echo "    FAIL: GET /health"
    fail=1
  fi

  # Fly routes on /health/ready, which answers 200 with "redis": "degraded" on purpose (a
  # Redis blip must not drain the fleet). /health/dependencies, what the phone's connection
  # check reads, answers 503 while Postgres or Redis is down: sign-in, chat and quota need
  # both, so the smoke check reads that.
  echo "==> Live readiness: $API_URL/health/ready (Fly's routing check)"
  if curl -sf --max-time 10 "$API_URL/health/ready" | grep -q '"status": *"ok"'; then
    echo "    OK"
  else
    echo "    FAIL: GET /health/ready"
    fail=1
  fi

  echo "==> Live dependencies: $API_URL/health/dependencies (Postgres and Redis)"
  DEPS_STATUS="$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$API_URL/health/dependencies" || true)"
  if [[ "$DEPS_STATUS" == "200" ]]; then
    echo "    OK"
  else
    echo "    FAIL: GET /health/dependencies answered ${DEPS_STATUS:-nothing}"
    echo "          (503: the API cannot reach Postgres or REDIS_URL)"
    fail=1
  fi

  for page in privacy terms; do
    echo "==> Live legal page: $API_URL/legal/$page"
    if curl -sf --max-time 10 "$API_URL/legal/$page" | grep -qi '<h1>'; then
      echo "    OK"
    else
      echo "    FAIL: GET /legal/$page"
      fail=1
    fi
  done
fi

if [[ "$fail" -ne 0 ]]; then
  echo ""
  echo "FAIL: smoke checks failed"
  exit 1
fi

echo ""
echo "OK: smoke checks passed"
if [[ "$LIVE" -eq 0 ]]; then
  echo "Tip: start API and run ./scripts/qa-smoke.sh --live"
fi

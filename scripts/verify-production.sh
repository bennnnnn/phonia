#!/usr/bin/env bash
#
# Production readiness report — static validation + optional live checks.
# Does not provision cloud resources; see docs/PRODUCTION.md.
#
# Usage:
#   ./scripts/verify-production.sh
#   API_URL=https://recall-api.fly.dev ./scripts/verify-production.sh --live
#
# --live also checks, through flyctl (`fly auth login` first; FLY_APP, default
# recall-api), that the worker answers its health check and that the database
# is at the repository's migration head. A check that cannot run is not a pass:
# with --live it fails the run, and the report lists it.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
API_URL="${API_URL:-}"
FLY_APP="${FLY_APP:-recall-api}"
LIVE=0
[[ "${1:-}" == "--live" ]] && LIVE=1

fail=0
not_checked=()

echo "=== Recall production verification ==="
echo ""

# Reuse smoke checks (static, plus API health and readiness with --live)
if [[ "$LIVE" -eq 1 && -z "$API_URL" ]]; then
  echo "FAIL: --live needs API_URL=https://<api-host>"
  exit 1
fi
smoke_args=()
[[ "$LIVE" -eq 1 ]] && smoke_args+=(--live)
# The ${a[@]+...} form keeps an empty array safe under set -u in macOS's bash 3.2.
if ! "$ROOT/scripts/qa-smoke.sh" ${smoke_args[@]+"${smoke_args[@]}"}; then
  fail=1
fi

echo ""
echo "==> Fly.toml process split"
if grep -q 'PROCESS_ROLE = "api"' "$ROOT/fly.toml" && grep -q 'worker' "$ROOT/fly.toml"; then
  echo "    OK: app + worker processes defined"
else
  echo "    WARN: review fly.toml process configuration"
fi

echo ""
echo "==> Production settings validator exists"
if grep -q 'def validate_production_settings' "$ROOT/apps/api/app/core/config.py"; then
  echo "    OK"
else
  echo "    FAIL: validate_production_settings not found"
  fail=1
fi

echo ""
echo "==> Production secrets (apps/api/.env.production, the file imported to Fly)"
if [[ -f "$ROOT/apps/api/.env.production" ]]; then
  if "$ROOT/scripts/validate-prod-env.sh" "$ROOT/apps/api/.env.production"; then
    echo "    OK"
  else
    fail=1
  fi
else
  echo "    NOT CHECKED: no apps/api/.env.production here (Fly secrets cannot be read back;"
  echo "    validate the file you import: ./scripts/validate-prod-env.sh <file>)"
  not_checked+=("production secrets")
fi

echo ""
echo "==> Mobile EAS production profile"
if [[ -f "$ROOT/apps/mobile/eas.json" ]] && grep -q '"production"' "$ROOT/apps/mobile/eas.json"; then
  echo "    OK"
else
  echo "    WARN: review apps/mobile/eas.json"
fi

fly_cli() {
  if command -v flyctl >/dev/null 2>&1; then
    echo flyctl
  elif command -v fly >/dev/null 2>&1; then
    echo fly
  fi
}

# Runs one command on a Machine of the given process group; prints its output.
fly_exec() {
  local group="$1" command="$2"
  "$FLY" ssh console --app "$FLY_APP" --process-group "$group" --quiet -C "$command" 2>&1
}

if [[ "$LIVE" -eq 1 ]]; then
  FLY="$(fly_cli)"

  echo ""
  echo "==> Worker health (process group worker, http://127.0.0.1:8001/health/ready)"
  if [[ -z "$FLY" ]]; then
    echo "    NOT CHECKED: flyctl not installed"
    not_checked+=("worker health")
  elif WORKER_OUT="$(fly_exec worker 'curl -sf --max-time 5 http://127.0.0.1:8001/health/ready')" &&
    [[ "$WORKER_OUT" == *'"status":"ok"'* ]]; then
    echo "    OK"
  else
    echo "    FAIL: worker not ready: ${WORKER_OUT:-no answer}"
    echo "          (fly status --app $FLY_APP; fly logs --app $FLY_APP --process-group worker)"
    fail=1
  fi

  echo ""
  echo "==> Database migrations (alembic current on Fly == alembic heads here)"
  if [[ -z "$FLY" ]]; then
    echo "    NOT CHECKED: flyctl not installed"
    not_checked+=("migration state")
  elif ! command -v uv >/dev/null 2>&1; then
    echo "    NOT CHECKED: uv not installed (needed for alembic heads)"
    not_checked+=("migration state")
  else
    HEADS="$(cd "$ROOT/apps/api" && uv run --frozen alembic heads 2>/dev/null | awk '/\(head\)/ {print $1}' | sort | tr '\n' ' ')"
    CURRENT_OUT="$(fly_exec app "sh -c 'cd /app && /opt/venv/bin/alembic current'" || true)"
    # Revision ids here start with four digits (0111_web_search_setting).
    CURRENT="$(printf '%s\n' "$CURRENT_OUT" | awk '/^[0-9][0-9][0-9][0-9][0-9A-Za-z_]*( |$)/ {print $1}' | sort | tr '\n' ' ')"
    if [[ -n "$HEADS" && "$CURRENT" == "$HEADS" ]]; then
      echo "    OK: $HEADS"
    else
      echo "    FAIL: database at '${CURRENT:-unknown}', repository head '${HEADS:-unknown}'"
      printf '%s\n' "$CURRENT_OUT" | tail -5 | sed 's/^/          /'
      fail=1
    fi
  fi

  echo ""
  echo "==> CORS preflight (OPTIONS) — informational"
  ORIGIN="${CORS_TEST_ORIGIN:-https://app.recall.app}"
  STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X OPTIONS \
    -H "Origin: $ORIGIN" \
    -H "Access-Control-Request-Method: GET" \
    "$API_URL/health" || echo "000")
  echo "    OPTIONS /health from Origin $ORIGIN → HTTP $STATUS"
else
  not_checked+=("live API, worker health and migration state (run with --live)")
fi

echo ""
echo "=== Manual steps remaining ==="
echo "  • Install flyctl and authenticate: https://fly.io/docs/hands-on/install-flyctl/"
echo "  • Set Fly secrets (see docs/PRODUCTION.md §4) — app name: $FLY_APP"
echo "  • fly scale count app=1 worker=1 && deploy (GitHub Actions → Deploy, from main)"
echo "  • Provision R2 and set STORAGE_BACKEND=r2 (+ R2_* secrets)"
echo "  • Confirm Neon's restore window and test one restore (docs/PRODUCTION.md §1)"
echo "  • EAS production builds + store submission"
echo "  • Complete docs/QA_MATRIX.md on physical devices"
echo "  • Publish the Google OAuth consent screen (sign-in only)"
echo ""

if [[ "${#not_checked[@]}" -gt 0 ]]; then
  echo "Not checked:"
  printf '  - %s\n' "${not_checked[@]}"
fi
if [[ "$fail" -ne 0 ]]; then
  echo "FAIL: production verification failed"
  exit 1
fi
if [[ "$LIVE" -eq 1 && "${#not_checked[@]}" -gt 0 ]]; then
  echo "FAIL: live verification is incomplete (see Not checked)"
  exit 1
fi
if [[ "$LIVE" -eq 1 ]]; then
  echo "OK: live verification passed"
else
  echo "OK: static verification passed (live checks not run)"
fi

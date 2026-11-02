#!/usr/bin/env bash
# Import apps/api/.env.production into Fly secrets for app recall-api.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${1:-$ROOT/apps/api/.env.production}"
FLY_APP="${FLY_APP:-recall-api}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE — copy from apps/api/.env.production.example" >&2
  exit 1
fi

if ! command -v flyctl >/dev/null 2>&1 && ! command -v fly >/dev/null 2>&1; then
  echo "flyctl not found. Install: https://fly.io/docs/hands-on/install-flyctl/" >&2
  exit 1
fi

FLY="${FLYCTL:-flyctl}"
command -v "$FLY" >/dev/null 2>&1 || FLY=fly

echo "==> Validating production env locally"
"$ROOT/scripts/validate-prod-env.sh" "$ENV_FILE"

echo "==> Importing secrets to Fly app '$FLY_APP'"
# Strip comments/blank lines; fly secrets import expects KEY=VALUE lines.
grep -v '^\s*#' "$ENV_FILE" | grep -v '^\s*$' | "$FLY" secrets import --app "$FLY_APP"

echo "OK: secrets imported. Deploy with: ./scripts/deploy-api.sh"

#!/usr/bin/env bash
# Deploy Recall API to Fly.io (recall-api) from this checkout. Requires flyctl auth
# and secrets set. The normal path is GitHub Actions → Deploy (from main, after CI);
# this script is the break-glass path and builds exactly the local tree, so it
# refuses uncommitted changes and any branch but main unless you pass --force.
#
# Usage: ./scripts/deploy-api.sh [--force]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FLY_APP="${FLY_APP:-recall-api}"
FORCE=0
if [[ "${1:-}" == "--force" ]]; then
  FORCE=1
elif [[ $# -gt 0 ]]; then
  echo "usage: $0 [--force]" >&2
  exit 2
fi

if ! command -v flyctl >/dev/null 2>&1 && ! command -v fly >/dev/null 2>&1; then
  echo "flyctl not found. Install: https://fly.io/docs/hands-on/install-flyctl/" >&2
  exit 1
fi

FLY="${FLYCTL:-flyctl}"
command -v "$FLY" >/dev/null 2>&1 || FLY=fly

cd "$ROOT"
BRANCH="$(git rev-parse --abbrev-ref HEAD)"
SHA="$(git rev-parse HEAD)"
problems=()
if [[ -n "$(git status --porcelain)" ]]; then
  problems+=("the working tree has uncommitted or untracked changes (git status)")
fi
if [[ "$BRANCH" != "main" ]]; then
  problems+=("the checkout is on '$BRANCH', not main")
elif git rev-parse --verify --quiet origin/main >/dev/null &&
  [[ "$(git rev-parse origin/main)" != "$SHA" ]]; then
  problems+=("main is not origin/main (git fetch && git status)")
fi
if [[ "${#problems[@]}" -gt 0 ]]; then
  echo "Refusing to deploy: the image is built from this tree and"
  printf '  - %s\n' "${problems[@]}"
  if [[ "$FORCE" -eq 0 ]]; then
    echo "Deploy from a clean, up-to-date main (or GitHub Actions → Deploy), or pass --force."
    exit 1
  fi
  echo "--force: deploying anyway."
fi

if [[ -f "$ROOT/apps/api/.env.production" ]]; then
  echo "==> Validating apps/api/.env.production"
  "$ROOT/scripts/validate-prod-env.sh"
else
  echo "WARN: apps/api/.env.production not found — assuming Fly secrets already set"
fi

LABEL="git-$SHA"
[[ -n "$(git status --porcelain)" ]] && LABEL="$LABEL-dirty"
echo "==> Deploying $FLY_APP from $BRANCH @ ${SHA:0:12} (remote build, image label $LABEL)"
"$FLY" deploy --app "$FLY_APP" --remote-only --image-label "$LABEL"

echo
echo "==> Smoke checks"
API_URL="https://${FLY_APP}.fly.dev" "$ROOT/scripts/qa-smoke.sh" --live-only
echo
echo "API URL: https://${FLY_APP}.fly.dev"
echo "Full check: API_URL=https://${FLY_APP}.fly.dev ./scripts/verify-production.sh --live"

#!/usr/bin/env bash
#
# One-command local gate — mirrors CI exactly so "is it green?" is a single run.
# API order matches .github/workflows/api-ci.yml: ruff -> format -> mypy -> migrate -> pytest.
# Skips a side cleanly if its toolchain isn't installed.
#
# Usage: ./scripts/check.sh            (also: ./scripts/dev.sh check)
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
fail=0

echo "==> API: ruff check + format + mypy + pytest (coverage >= 80%)"
if command -v uv >/dev/null 2>&1; then
  (
    cd "$ROOT/apps/api" &&
      uv run ruff check . &&
      uv run ruff format --check . &&
      uv run mypy &&
      uv run python ../../scripts/check_mypy_strict.py &&
      if uv run python -c "from app.core.config import Settings; Settings().database_url" >/dev/null 2>&1; then
        echo "    Migrating database (alembic upgrade head)..."
        uv run alembic upgrade head
      else
        echo "    WARN: DATABASE_URL not configured - skipping alembic migrate"
      fi &&
      uv run pytest --cov=app --cov-report=term-missing --cov-fail-under=80
  ) || fail=1
else
  echo "    WARN: uv not found - skipping API checks"
fi

echo "==> Mobile: typecheck + lint + jest"
if command -v pnpm >/dev/null 2>&1; then
  (cd "$ROOT/apps/mobile" && pnpm typecheck && pnpm lint && pnpm test) || fail=1
else
  echo "    WARN: pnpm not found - skipping mobile checks"
fi

echo "==> File sizes: production files over 500 lines need a recorded reason and may not grow"
python3 "$ROOT/scripts/check_file_sizes.py" || fail=1

echo "==> Web: typecheck + lint"
if command -v pnpm >/dev/null 2>&1; then
  (cd "$ROOT/apps/web" && pnpm typecheck && pnpm lint) || fail=1
else
  echo "    WARN: pnpm not found - skipping web checks"
fi

if [ "$fail" -ne 0 ]; then
  echo "FAIL: gate is red - fix the above before committing"
  exit 1
fi
echo "OK: gate is green"

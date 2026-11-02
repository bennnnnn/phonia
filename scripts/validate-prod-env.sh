#!/usr/bin/env bash
# Validate apps/api/.env.production against production boot rules (no deploy).
#
# Only the file counts. Settings normally also reads apps/api/.env (the dev
# file) and the shell's environment, which quietly filled in any key the
# production file was missing, so a file without REDIS_URL passed here.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${1:-$ROOT/apps/api/.env.production}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE"
  echo "Copy apps/api/.env.production.example → apps/api/.env.production and fill values."
  exit 1
fi
ENV_FILE="$(cd "$(dirname "$ENV_FILE")" && pwd)/$(basename "$ENV_FILE")"

echo "Validating $ENV_FILE ..."
cd "$ROOT/apps/api"
LITELLM_MODE=PRODUCTION uv run --frozen python - "$ENV_FILE" <<'PY'
import os
import sys

from app.core.config import Settings, validate_production_settings

# Drop every inherited variable Settings would read (names match case-insensitively),
# and read the given file instead of apps/api/.env.
fields = {name.upper() for name in Settings.model_fields}
for key in list(os.environ):
    if key.upper() in fields:
        del os.environ[key]

settings = Settings(_env_file=sys.argv[1])
if settings.environment != "production":
    sys.exit(f"FAIL: ENVIRONMENT={settings.environment!r} in {sys.argv[1]}; it must be production")
try:
    validate_production_settings(settings)
except RuntimeError as exc:
    sys.exit(f"FAIL: {exc}")
print("OK: production configuration passes validate_production_settings()")
PY

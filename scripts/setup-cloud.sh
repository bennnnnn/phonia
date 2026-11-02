#!/usr/bin/env bash
# Provision Neon + Upstash for Recall (no Docker).
#
# Option A — paste URLs manually:
#   ./scripts/setup-cloud.sh
#
# Option B — automate with API keys:
#   NEON_API_KEY=... UPSTASH_EMAIL=... UPSTASH_API_KEY=... ./scripts/setup-cloud.sh

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$ROOT/apps/api/.env"

to_asyncpg_url() {
  local url="$1"
  url="${url/postgresql:\/\//postgresql+asyncpg:\/\/}"
  url="${url/postgres:\/\//postgresql+asyncpg:\/\/}"
  if [[ "$url" != *"sslmode="* ]]; then
    if [[ "$url" == *"?"* ]]; then
      url="${url}&sslmode=require"
    else
      url="${url}?sslmode=require"
    fi
  fi
  echo "$url"
}

set_env_var() {
  local key="$1"
  local value="$2"
  if grep -q "^${key}=" "$ENV_FILE" 2>/dev/null; then
    if [[ "$OSTYPE" == "darwin"* ]]; then
      sed -i '' "s|^${key}=.*|${key}=${value}|" "$ENV_FILE"
    else
      sed -i "s|^${key}=.*|${key}=${value}|" "$ENV_FILE"
    fi
  else
    echo "${key}=${value}" >> "$ENV_FILE"
  fi
}

ensure_env_file() {
  if [[ ! -f "$ENV_FILE" ]]; then
    cp "$ROOT/apps/api/.env.example" "$ENV_FILE"
  fi
  if ! grep -q "^JWT_SECRET=" "$ENV_FILE" || grep -q "change-me-in-production" "$ENV_FILE"; then
    set_env_var "JWT_SECRET" "$(openssl rand -base64 32 | tr -d '\n')"
    echo "Generated JWT_SECRET"
  fi
}

provision_neon() {
  echo "Creating Neon project 'recall'..."
  npx --yes neonctl@latest projects create --name recall --output json > /tmp/recall-neon.json
  local project_id
  project_id=$(python3 -c "import json; print(json.load(open('/tmp/recall-neon.json'))['project']['id'])")
  local conn
  conn=$(npx --yes neonctl@latest connection-string --project-id "$project_id" --pooled)
  conn=$(to_asyncpg_url "$conn")
  set_env_var "DATABASE_URL" "$conn"
  echo "Neon project created."
}

provision_upstash() {
  echo "Creating Upstash Redis 'recall'..."
  local result
  result=$(curl -s -X POST "https://api.upstash.com/v2/redis/database" \
    -u "${UPSTASH_EMAIL}:${UPSTASH_API_KEY}" \
    -H "Content-Type: application/json" \
    -d '{"name":"recall","region":"us-east-1","tls":true}')
  local redis_url
  redis_url=$(python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('endpoint','') or d.get('redis_url',''))" <<< "$result")
  if [[ -z "$redis_url" ]]; then
    echo "Upstash create failed: $result" >&2
    exit 1
  fi
  if [[ "$redis_url" != rediss://* && "$redis_url" != redis://* ]]; then
    redis_url="rediss://${redis_url}"
  fi
  set_env_var "REDIS_URL" "$redis_url"
  echo "Upstash Redis created."
}

prompt_manual() {
  echo ""
  echo "=== Recall cloud setup (manual) ==="
  echo ""
  echo "1. Neon:  https://console.neon.tech → New Project → name it 'recall'"
  echo "   Copy the connection string (pooled is fine)."
  echo ""
  read -r -p "Paste DATABASE_URL (postgresql://...): " db_url
  db_url=$(to_asyncpg_url "$db_url")
  set_env_var "DATABASE_URL" "$db_url"
  echo ""
  echo "2. Upstash: https://console.upstash.com/redis → Create Database → name 'recall'"
  echo "   Copy the Redis URL (rediss://...)."
  echo ""
  read -r -p "Paste REDIS_URL (rediss://...): " redis_url
  set_env_var "REDIS_URL" "$redis_url"
}

run_migrate() {
  echo ""
  echo "Running migrations..."
  cd "$ROOT/apps/api"
  uv sync
  uv run alembic upgrade head
  echo ""
  echo "Done. Start backend: ./scripts/dev.sh api"
}

ensure_env_file

if [[ -n "${NEON_API_KEY:-}" && -n "${UPSTASH_EMAIL:-}" && -n "${UPSTASH_API_KEY:-}" ]]; then
  export NEON_API_KEY
  provision_neon
  provision_upstash
elif [[ -n "${DATABASE_URL:-}" && -n "${REDIS_URL:-}" ]]; then
  set_env_var "DATABASE_URL" "$(to_asyncpg_url "$DATABASE_URL")"
  set_env_var "REDIS_URL" "$REDIS_URL"
else
  prompt_manual
fi

run_migrate

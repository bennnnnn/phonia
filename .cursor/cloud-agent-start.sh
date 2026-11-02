#!/usr/bin/env bash
# Per-boot services: Postgres, Redis, migrations, API, and the web client.
# Stays in the foreground so the API and Vite processes keep running.
set -euo pipefail

if [[ -d /workspace/apps/api ]]; then
  ROOT="/workspace"
else
  ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fi
export PATH="/usr/local/bin:${HOME}/.local/bin:${PATH}"

sudo service postgresql start
sudo service redis-server start

# Password login for asyncpg over TCP. Local sockets stay peer auth.
sudo -u postgres psql -v ON_ERROR_STOP=1 -c "ALTER USER postgres PASSWORD 'dev';"
if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='recall'" | grep -q 1; then
  sudo -u postgres createdb recall
fi

for _ in $(seq 1 30); do
  if sudo -u postgres pg_isready -q && redis-cli ping | grep -q PONG; then
    break
  fi
  sleep 1
done
sudo -u postgres pg_isready -q
redis-cli ping | grep -q PONG

API_ENV="${ROOT}/apps/api/.env"
if [[ ! -f "${API_ENV}" ]]; then
  cat > "${API_ENV}" <<'EOF'
DATABASE_URL=postgresql+asyncpg://postgres:dev@127.0.0.1:5432/recall
REDIS_URL=redis://127.0.0.1:6379
JWT_SECRET=cloud-agent-dev-secret-not-for-production-32
DEV_AUTH_ENABLED=true
MOCK_LLM_ENABLED=true
ENVIRONMENT=development
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
STORAGE_BACKEND=local
WEB_SEARCH_ENABLED=true
EOF
fi

WEB_ENV="${ROOT}/apps/web/.env"
if [[ ! -f "${WEB_ENV}" ]]; then
  cat > "${WEB_ENV}" <<'EOF'
VITE_API_URL=http://127.0.0.1:8000
VITE_GOOGLE_CLIENT_ID=
EOF
fi

MOBILE_ENV="${ROOT}/apps/mobile/.env"
if [[ ! -f "${MOBILE_ENV}" ]]; then
  cat > "${MOBILE_ENV}" <<'EOF'
EXPO_PUBLIC_API_URL=http://127.0.0.1:8000
EXPO_PUBLIC_DEV_AUTH_ENABLED=true
EOF
fi

cd "${ROOT}/apps/api"
uv run alembic upgrade head

if curl -sf http://127.0.0.1:8000/health >/dev/null && curl -sf http://127.0.0.1:5173/ >/dev/null; then
  echo "API and web already running"
  exit 0
fi

# Bind all interfaces inside the VM. Stay in the foreground with the servers.
cd "${ROOT}/apps/api"
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 &
API_PID=$!

cd "${ROOT}/apps/web"
pnpm dev --host 0.0.0.0 --port 5173 &
WEB_PID=$!

cleanup() {
  kill "${API_PID}" "${WEB_PID}" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

# Stay attached until one of the servers exits.
wait -n "${API_PID}" "${WEB_PID}"

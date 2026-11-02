#!/usr/bin/env bash
# Idempotent Cloud Agent bootstrap. Safe to run more than once.
# Installs toolchains and dependencies. Does not start dev servers or migrate.
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive
if [[ -d /workspace/apps/api ]]; then
  ROOT="/workspace"
else
  ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
fi

sudo apt-get update
sudo apt-get install -y \
  postgresql \
  postgresql-contrib \
  postgresql-16-pgvector \
  redis-server \
  build-essential \
  libpq-dev \
  curl \
  ca-certificates

if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
fi
if [[ -x "${HOME}/.local/bin/uv" ]]; then
  sudo ln -sfn "${HOME}/.local/bin/uv" /usr/local/bin/uv
  sudo ln -sfn "${HOME}/.local/bin/uvx" /usr/local/bin/uvx
fi
export PATH="/usr/local/bin:${HOME}/.local/bin:${PATH}"

# System Python on this image is 3.12.3, which segfaults compiling the API tests.
uv python install 3.12

cd "${ROOT}/apps/api"
uv sync --all-groups --frozen

# packageManager pins pnpm@9.15.9. corepack honors that pin.
corepack enable
corepack prepare pnpm@9.15.9 --activate

cd "${ROOT}/apps/web"
pnpm install --frozen-lockfile

cd "${ROOT}/apps/mobile"
pnpm install --frozen-lockfile

echo "cloud-agent install complete"

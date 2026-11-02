#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

kill_metro() {
  "$ROOT/scripts/kill-metro.sh" || true
}

# The API processes: whatever listens on :8000 (the reloader and its server
# with --reload), and uv/uvicorn running app.main. Finding none is not an
# error: under `set -euo pipefail` it made `up` exit when no API was running.
api_pids() {
  {
    lsof -tiTCP:8000 -sTCP:LISTEN 2>/dev/null || true
    pgrep -f "uvicorn app.main" 2>/dev/null || true
  } | sort -u
}

# Running, and not a zombie that only waits for its parent to reap it.
is_running() {
  local stat
  stat="$(ps -o stat= -p "$1" 2>/dev/null)" || return 1
  [[ -n "$stat" && "$stat" != Z* ]]
}

# SIGTERM first, so the API runs its shutdown: it stops its SymPy workers
# (about 250 MB each), finishes saving replies and closes its connections.
# `kill -9` skipped all of that. SIGKILL only what is still there after 15s.
stop_api() {
  local pids alive pid i
  pids="$(api_pids)"
  [[ -z "$pids" ]] && return 0
  kill $pids 2>/dev/null || true
  for i in $(seq 1 30); do
    alive=""
    for pid in $pids; do
      is_running "$pid" && alive="$alive $pid"
    done
    [[ -z "$alive" ]] && return 0
    sleep 0.5
  done
  echo "API still running after 15s; killing it."
  kill -9 $alive 2>/dev/null || true
}

kill_all_dev() {
  echo "Stopping API, Metro, and Expo…"
  stop_api
  kill_metro
  pkill -9 -f "expo start" 2>/dev/null || true
  pkill -9 -f "expo/bin/cli" 2>/dev/null || true
  xcrun simctl terminate booted host.exp.Exponent 2>/dev/null || true
  echo "All dev servers stopped."
}

# The API logs to tmp/api.log, so a failed start would show nothing here: the
# app just could not connect. Say so in the terminal, with the log's last lines.
report_api_start() {
  local i
  for i in $(seq 1 45); do
    if curl -sf -m 2 http://127.0.0.1:8000/health >/dev/null 2>&1; then
      echo "API is up on :8000."
      return 0
    fi
    sleep 1
  done
  printf '\033[31mThe API did not start. Last lines of tmp/api.log:\033[0m\n'
  tail -n 25 "$ROOT/tmp/api.log"
  printf '\033[31mFix the error above; the API reloads when its files change.\033[0m\n'
}

# Past API_LOG_MAX_MB (default 20), a log moves to <log>.1, replacing the one
# before, and starts again empty.
rotate_if_big() {
  local log="$1" size
  size=$(wc -c <"$log" 2>/dev/null || echo 0)
  if (( size > ${API_LOG_MAX_MB:-20} * 1024 * 1024 )); then
    cp "$log" "$log.1" && : >"$log"
  fi
}

# The API writes tmp/api.log for as long as `up` runs, which is days when
# follow-main keeps it current, and the log grew without limit. The API
# appends, so after a rotation its next line lands at the start of the file.
cap_api_log() {
  while sleep 30; do
    rotate_if_big "$ROOT/tmp/api.log"
  done
}

# One terminal for everything: the API in the background (log in tmp/api.log),
# the app in the foreground, and the checkout kept on origin/main so a merged
# pull request reaches the running app by itself. Ctrl+C stops it all.
up() {
  local target="${1:-sim}" mobile_cmd
  case "$target" in
    sim) mobile_cmd=mobile-sim ;;
    phone) mobile_cmd=mobile ;;
    *) echo "Usage: scripts/dev.sh up [sim|phone]"; exit 1 ;;
  esac
  kill_all_dev
  RECALL_DEV_UP=starting "$ROOT/scripts/follow-main.sh" --once
  mkdir -p "$ROOT/tmp"
  : >"$ROOT/tmp/api.log"
  (cd "$ROOT/apps/api" && exec uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000) \
    >>"$ROOT/tmp/api.log" 2>&1 &
  local api_pid=$!
  cap_api_log &
  local cap_pid=$!
  report_api_start &
  RECALL_DEV_UP=running "$ROOT/scripts/follow-main.sh" &
  local follow_pid=$!
  trap 'kill '"$follow_pid"' '"$cap_pid"' '"$api_pid"' 2>/dev/null; lsof -tiTCP:8000 -sTCP:LISTEN 2>/dev/null | xargs kill 2>/dev/null || true' EXIT
  echo "API on :8000 (log: tmp/api.log). Pulling merged changes from main every minute."
  # follow-main stops Metro (and leaves this flag) when a merge changed the
  # app's packages; start it again with them, then reload the app.
  rm -f "$ROOT/tmp/restart-metro"
  while true; do
    "$ROOT/scripts/dev.sh" "$mobile_cmd" || true
    [[ -f "$ROOT/tmp/restart-metro" ]] || break
    rm -f "$ROOT/tmp/restart-metro"
    echo "Restarting Metro with the new packages…"
    reload_when_metro_is_back &
  done
}

# Metro answers /status once it can serve the app again.
reload_when_metro_is_back() {
  local i
  for i in $(seq 1 120); do
    if curl -sf -m 2 http://127.0.0.1:8081/status >/dev/null 2>&1; then
      sleep 3
      node "$ROOT/scripts/reload-app.mjs"
      return 0
    fi
    sleep 1
  done
}

case "${1:-}" in
  up)
    up "${2:-sim}"
    ;;
  infra)
    echo "Optional: starts local Postgres + Redis via Docker."
    docker compose -f "$ROOT/docker-compose.yml" up -d
    ;;
  api)
    cd "$ROOT/apps/api"
    uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
    ;;
  watch-errors)
    mkdir -p "$ROOT/tmp"
    SAVE="$ROOT/tmp/http-errors.log"
    rotate_if_big "$SAVE"
    echo "API on :8000 — 4xx/5xx highlighted on stderr, copied to $SAVE"
    echo "Success responses (200/201/204) stay in the normal log. Ctrl+C stops the API."
    cd "$ROOT/apps/api"
    uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 2>&1 |
      python3 "$ROOT/scripts/watch-http-errors.py" --passthrough --save "$SAVE"
    ;;
  mobile)
    kill_metro
    # A phone reaches the API at this Mac's LAN address, not the 127.0.0.1 mobile-sim leaves.
    "$ROOT/scripts/set-lan-ip.sh"
    cd "$ROOT/apps/mobile"
    echo "LAN mode — phone and Mac must be on the same Wi‑Fi."
    echo "Unplug USB or authorize USB debugging if Android is connected."
    pnpm exec expo start --lan --clear
    ;;
  mobile-sim)
    kill_metro
    "$ROOT/scripts/set-sim-ip.sh"
    cd "$ROOT/apps/mobile"
    echo "iOS Simulator — Expo Go on virtual device (API at 127.0.0.1:8000)."
    # --lan binds 0.0.0.0 so Expo Go can reach Metro via 127.0.0.1 (not IPv6-only ::1).
    pnpm exec expo start --lan --clear --go --ios
    ;;
  mobile-tunnel)
    kill_metro
    cd "$ROOT/apps/mobile"
    echo "Tunnel mode — scan QR in Expo Go (Wi‑Fi or cellular on phone)."
    echo "Tip: UNPLUG USB cable if adb reverse errors appear."
    adb kill-server 2>/dev/null || true
    pnpm exec expo start --tunnel --clear
    ;;
  web)
    cd "$ROOT/apps/web"
    echo "Web client — http://localhost:5173 (API at \$VITE_API_URL)"
    pnpm dev
    ;;
  kill-metro)
    kill_metro
    ;;
  kill-all)
    kill_all_dev
    ;;
  migrate)
    cd "$ROOT/apps/api"
    uv run alembic upgrade head
    ;;
  test-api)
    cd "$ROOT/apps/api"
    uv run pytest
    ;;
  check)
    "$ROOT/scripts/check.sh"
    ;;
  qa-smoke)
    shift
    "$ROOT/scripts/qa-smoke.sh" "$@"
    ;;
  battery)
    shift
    (cd "$ROOT/apps/api" && uv run python "$ROOT/scripts/battery.py" "$@")
    ;;
  verify-production)
    shift
    "$ROOT/scripts/verify-production.sh" "$@"
    ;;
  setup)
    cp -n "$ROOT/apps/api/.env.example" "$ROOT/apps/api/.env" 2>/dev/null || true
    cp -n "$ROOT/apps/mobile/.env.example" "$ROOT/apps/mobile/.env" 2>/dev/null || true
    cp -n "$ROOT/apps/web/.env.example" "$ROOT/apps/web/.env" 2>/dev/null || true
    cd "$ROOT/apps/api" && uv sync
    cd "$ROOT/apps/mobile" && pnpm install
    cd "$ROOT/apps/web" && pnpm install
    echo ""
    echo "Setup complete (no Docker)."
    echo ""
    echo "Next:"
    echo "  1. Add Neon + Upstash URLs to apps/api/.env"
    echo "  2. ./scripts/dev.sh migrate"
    echo "  3. ./scripts/dev.sh api   OR   ./scripts/dev.sh mobile"
    echo ""
    echo "Optional local DB: ./scripts/dev.sh infra  (requires Docker)"
    ;;
  *)
    echo "Usage: scripts/dev.sh {up|setup|migrate|api|watch-errors|mobile|mobile-sim|mobile-tunnel|web|kill-metro|kill-all|test-api|check|battery|qa-smoke|verify-production|infra}"
    echo ""
    echo "  up [sim|phone] API + app in one terminal, kept on the latest main (default: sim)"
    echo "  setup          Install deps, copy .env (no Docker)"
    echo "  migrate        Apply DB migrations (needs DATABASE_URL in .env)"
    echo "  api            Run FastAPI on :8000"
    echo "  watch-errors   Run API and highlight 4xx/5xx (saves to tmp/http-errors.log)"
    echo "  check          Run the full local gate (API ruff+format+mypy+pytest, mobile+web typecheck+lint)"
    echo "  battery        Send the behavior battery to the running API; report in tmp/battery/"
    echo "                 (--category teaching, --only map-where-is,search-ai-news, --pro)"
    echo "  qa-smoke       Backend smoke checks (add --live when API running)"
    echo "  verify-production  Production readiness report (add --live for deployed API)"
    echo "  api            Run FastAPI on :8000"
    echo "  web            Run the web client (Vite) on :5173"
    echo "  mobile         Run Expo (LAN — same Wi‑Fi, unplug USB if adb errors)"
    echo "  mobile-sim     Run Expo Go on iOS Simulator (localhost)"
    echo "  mobile-tunnel  Run Expo (tunnel — unplug USB, scan QR in Expo Go)"
    echo "  kill-metro     Stop stale Metro servers on ports 8081–8090"
    echo "  kill-all       Stop API (:8000), Metro, Expo, and Expo Go on simulator"
    echo "  infra          Optional: Docker Postgres + Redis"
    exit 1
    ;;
esac

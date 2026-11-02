#!/usr/bin/env bash
# Keep this checkout on origin/main while the dev servers run, so a merged
# pull request reaches the running app without anyone pulling by hand.
#
# The API (uvicorn --reload) reloads changed files on its own. After a pull
# that changed the app, this reloads every app connected to Metro (Fast Refresh
# alone misses a phone that was asleep); when the app's packages changed, it
# installs them and, under dev.sh up, restarts Metro with them. It also runs
# new migrations and API dependency installs.
#
# It never touches work. It pulls only as a fast-forward, and git refuses
# one that would overwrite a file you edited. On a branch whose commits are
# all in main (a merged pull request, "Rebase and merge" included) with no
# edits, it switches to main. Otherwise it says why (in the terminal and, on
# macOS, as a notification) and waits.
#
#   follow-main.sh          check every FOLLOW_MAIN_INTERVAL seconds (60)
#   follow-main.sh --once   check once and exit
#
# Written for the bash 3.2 that macOS ships.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
INTERVAL="${FOLLOW_MAIN_INTERVAL:-60}"
ONCE=0
for arg in "$@"; do
  case "$arg" in
    --once) ONCE=1 ;;
    --switch) ;; # Switching off a merged branch is now always on.
    *) echo "usage: follow-main.sh [--once]" >&2; exit 2 ;;
  esac
done

cd "$ROOT" || exit 1

say() { printf '\033[36m[follow-main]\033[0m %s\n' "$*"; }

# Metro's output buries a terminal line; a macOS notification does not.
notify() {
  command -v osascript >/dev/null 2>&1 || return 0
  local text="${1//\"/\'}"
  osascript -e "display notification \"$text\" with title \"Recall dev\"" >/dev/null 2>&1 || true
}

LAST_NOTICE=""
notice_once() {
  if [[ "$1" != "$LAST_NOTICE" ]]; then
    say "$1"
    notify "$1"
    LAST_NOTICE="$1"
  fi
}

has_local_changes() {
  [[ -n "$(git status --porcelain --untracked-files=no)" ]]
}

# Every commit on this branch is already in main. "Rebase and merge" puts
# copies with new ids on main, so ancestry alone misses it; git cherry
# compares the changes themselves ("-" = already upstream).
merged_into_main() {
  git merge-base --is-ancestor HEAD origin/main && return 0
  ! git cherry origin/main HEAD 2>/dev/null | grep -q '^+'
}

# dev.sh up sets RECALL_DEV_UP: "starting" before Metro runs, "running" after.
restart_metro() {
  case "${RECALL_DEV_UP:-}" in
    starting) ;; # Metro starts next, with the new packages.
    running)
      say "Restarting Metro with them; the app reloads when it is back."
      mkdir -p "$ROOT/tmp"
      touch "$ROOT/tmp/restart-metro"
      pkill -TERM -f "expo start" 2>/dev/null || true
      ;;
    *) say "Restart the app (Ctrl+C, then ./scripts/dev.sh up) to load them." ;;
  esac
}

reload_app() {
  [[ "${RECALL_DEV_UP:-}" == "starting" ]] && return
  sleep 2 # Let Metro see the pulled files first.
  node "$ROOT/scripts/reload-app.mjs" && say "Reloaded the app."
}

after_pull() {
  local before="$1" changed
  changed="$(git diff --name-only "$before" HEAD)"
  say "Updated to $(git log -1 --format='%h %s')"
  notify "Updated to $(git log -1 --format='%s')"
  if grep -qE '^apps/api/(pyproject\.toml|uv\.lock)$' <<<"$changed"; then
    say "API dependencies changed: uv sync"
    (cd apps/api && uv sync -q)
  fi
  if grep -q '^apps/api/alembic/versions/' <<<"$changed"; then
    say "New database migration: alembic upgrade head"
    (cd apps/api && uv run alembic upgrade head)
  fi
  if grep -qE '^apps/mobile/(package\.json|pnpm-lock\.yaml)$' <<<"$changed"; then
    say "Mobile dependencies changed: pnpm install"
    (cd apps/mobile && pnpm install --silent)
    restart_metro
  elif grep -q '^apps/mobile/' <<<"$changed"; then
    reload_app
  fi
  if grep -qE '^apps/mobile/(app\.config\.ts|plugins/)' <<<"$changed"; then
    say "The app's native config changed: restart the app to load it."
  fi
}

sync_once() {
  local branch behind before
  if ! git fetch -q origin main 2>/dev/null; then
    notice_once "Could not reach GitHub; will try again."
    return
  fi
  branch="$(git symbolic-ref --short -q HEAD || true)"
  if [[ "$branch" != "main" ]]; then
    behind="$(git rev-list --count HEAD..origin/main)"
    [[ "$behind" -eq 0 ]] && return
    if ! merged_into_main; then
      notice_once "main has new commits; ${branch:-a detached HEAD} has work not in main, so staying on it."
      return
    fi
    if has_local_changes; then
      notice_once "${branch:-This branch} is merged into main, but has unsaved edits; staying on it."
      return
    fi
    # A branch whose commits are all in main holds nothing main lacks.
    say "Leaving ${branch:-a detached HEAD} (merged into main) for main."
    git switch -q main || { notice_once "Could not switch to main."; return; }
  fi
  behind="$(git rev-list --count HEAD..origin/main)"
  [[ "$behind" -eq 0 ]] && return
  before="$(git rev-parse HEAD)"
  # Git refuses a fast-forward that would overwrite an edited file, so edits
  # elsewhere no longer hold back every merged change.
  if git merge --ff-only -q origin/main 2>/dev/null; then
    LAST_NOTICE=""
    after_pull "$before"
  elif has_local_changes; then
    notice_once "main changed files you have edited; not pulling over them."
  else
    notice_once "Could not fast-forward main (it has commits origin/main lacks)."
  fi
}

sync_once
[[ "$ONCE" -eq 1 ]] && exit 0
while sleep "$INTERVAL"; do
  sync_once
done

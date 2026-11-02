#!/usr/bin/env bash
#
# Succeed only when a CI workflow passed for the code at a commit.
#
# Usage: scripts/require-green-ci.sh <workflow file> <sha> <path>...
#   e.g. scripts/require-green-ci.sh api-ci.yml "$GITHUB_SHA" apps/api scripts/check_file_sizes.py
#
# CI runs on push only when the push touched the workflow's paths, so the
# commit being deployed may have no run of its own. Walk back its first-parent
# history to the newest commit that has a push run, and accept that run only
# when none of <path>... changed between that commit and <sha> (the code it
# tested is the code being shipped). The run must have completed with success:
# queued, running, failed or cancelled all refuse.
#
# Needs: git history (actions/checkout fetch-depth), gh, GH_TOKEN with
# actions: read, and GITHUB_REPOSITORY (owner/repo).
set -euo pipefail

if [[ $# -lt 3 ]]; then
  echo "usage: $0 <workflow file> <sha> <path>..." >&2
  exit 2
fi
workflow="$1"
sha="$2"
shift 2
repo="${GITHUB_REPOSITORY:?set GITHUB_REPOSITORY=owner/repo}"
max_commits="${MAX_COMMITS:-50}"

refuse() {
  echo "::error title=CI not green::$*"
  exit 1
}

for commit in $(git rev-list --first-parent --max-count="$max_commits" "$sha"); do
  if ! git diff --quiet "$commit" "$sha" -- "$@"; then
    refuse "$workflow has not run on the code at ${sha:0:12}: no commit since $* last" \
      "changed has a push run. Wait for CI on main, then deploy again."
  fi
  run="$(gh api -X GET "repos/$repo/actions/workflows/$workflow/runs" \
    -f head_sha="$commit" -f event=push -f per_page=20 \
    --jq '.workflow_runs | sort_by(.run_number) | last
          | if . == null then "" else "\(.status) \(.conclusion // "none") \(.html_url)" end')"
  if [[ -z "$run" ]]; then
    continue
  fi
  read -r status conclusion url <<<"$run"
  if [[ "$status" != "completed" ]]; then
    refuse "$workflow is still $status for ${commit:0:12} ($url). Deploy again once it passes."
  fi
  if [[ "$conclusion" != "success" ]]; then
    refuse "$workflow ended $conclusion for ${commit:0:12} ($url)."
  fi
  echo "OK: $workflow passed for ${commit:0:12} ($url); $* unchanged since then"
  exit 0
done

refuse "no $workflow push run in the last $max_commits commits of ${sha:0:12}."

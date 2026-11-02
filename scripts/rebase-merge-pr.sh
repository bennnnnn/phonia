#!/usr/bin/env bash
# Rebase a grade-up PR onto origin/main, resolve FEATURES conflicts, renumber
# colliding alembic 0044_* revisions, then merge.
set -euo pipefail
PR="${1:?pr number}"
BRANCH="${2:?branch}"
ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

git fetch origin main "$BRANCH"
git checkout -B "$BRANCH" "origin/$BRANCH"

resolve_features() {
  if [ -f FEATURES.md ] && grep -q '<<<<<<' FEATURES.md; then
    python3 - <<'PY'
from pathlib import Path
import re
text = Path("FEATURES.md").read_text()
def pick(m):
    head, incoming = m.group(1), m.group(2)
    return incoming if incoming.count("✅") >= head.count("✅") else head
new = re.sub(
    r"<<<<<<< HEAD\n(.*?)=======\n(.*?)>>>>>>> [^\n]+\n",
    pick,
    text,
    flags=re.S,
)
if "<<<<<<" in new:
    raise SystemExit("unresolved FEATURES conflict")
Path("FEATURES.md").write_text(new)
print("FEATURES resolved")
PY
    git add FEATURES.md
  fi
}

renumber_alembic() {
  # If our branch adds a 0044_* that already exists on main under a different name,
  # or conflicts on add, pick next free revision after head on main.
  python3 - <<'PY'
from pathlib import Path
import re, sys

versions = Path("apps/api/alembic/versions")
files = sorted(versions.glob("*.py"))
# Find max numeric prefix in use
nums = []
for f in files:
    m = re.match(r"^(\d{4})_", f.name)
    if m:
        nums.append(int(m.group(1)))
if not nums:
    sys.exit(0)
# Detect unmerged conflicted alembic files
import subprocess
u = subprocess.check_output(["git", "diff", "--name-only", "--diff-filter=U"], text=True)
conflicted = [p for p in u.splitlines() if "alembic/versions" in p]
if not conflicted:
    # Also handle "both added" after rebase stopped — check for duplicate revision ids
    revs = {}
    for f in files:
        text = f.read_text()
        m = re.search(r'^revision:\s*str\s*=\s*["\']([^"\']+)["\']', text, re.M)
        if m:
            revs.setdefault(m.group(1), []).append(f)
    dups = {k: v for k, v in revs.items() if len(v) > 1}
    if not dups:
        sys.exit(0)
    print("duplicate revisions", dups)
    sys.exit(1)

print("conflicted alembic:", conflicted)
# For each conflicted file: take ours (the incoming branch version during rebase is the working tree
# for "both added" — use --ours/--theirs carefully). During rebase, --ours = upstream (main),
# --theirs = commit being applied.
for path in conflicted:
    # Keep both: main's file (ours) stays; rename theirs to next number.
    # First checkout --ours to keep main version of conflicting path if same name,
    # but usually different filenames both-added.
    pass

# Simpler approach for both-added different files: just `git add` all and fix down_revision
# to chain after current head.
head_rev = None
# Find tip: revision that nothing points to as down_revision among main files
# After conflict, unmerged files need resolution.
for path in conflicted:
    # During rebase both-added: keep the incoming file content (theirs) under a new name
    # if filename already exists on HEAD.
    p = Path(path)
    # Get theirs content
    try:
        theirs = subprocess.check_output(["git", "show", f":3:{path}"], text=True)
    except subprocess.CalledProcessError:
        # maybe only one stage
        theirs = p.read_text() if p.exists() else ""
    try:
        ours = subprocess.check_output(["git", "show", f":2:{path}"], text=True)
    except subprocess.CalledProcessError:
        ours = ""

    if ours and theirs and path.endswith(".py"):
        # Same path both modified/added — prefer chaining: keep ours on this path,
        # write theirs as next free number.
        git_rm = False
        subprocess.check_call(["git", "checkout", "--ours", "--", path])
        # find next number
        nums = []
        for f in versions.glob("*.py"):
            m = re.match(r"^(\d{4})_", f.name)
            if m:
                nums.append(int(m.group(1)))
        nxt = max(nums) + 1 if nums else 44
        # parse revision id and down from theirs
        rev_m = re.search(r'^revision:\s*str\s*=\s*["\']([^"\']+)["\']', theirs, re.M)
        down_m = re.search(r'^down_revision:\s*.*?=\s*["\']([^"\']+)["\']', theirs, re.M)
        old_rev = rev_m.group(1) if rev_m else f"{nxt:04d}_new"
        # find current head revision among non-conflict files: a revision not used as down_revision
        all_revs = {}
        downs = set()
        for f in versions.glob("*.py"):
            if str(f) in conflicted:
                continue
            t = f.read_text()
            rm = re.search(r'^revision:\s*str\s*=\s*["\']([^"\']+)["\']', t, re.M)
            dm = re.search(r'^down_revision:\s*.*?=\s*["\']([^"\']+)["\']', t, re.M)
            if rm:
                all_revs[rm.group(1)] = f
            if dm:
                downs.add(dm.group(1))
        # also include ours content revision
        om = re.search(r'^revision:\s*str\s*=\s*["\']([^"\']+)["\']', ours, re.M)
        if om:
            all_revs[om.group(1)] = Path(path)
            dm = re.search(r'^down_revision:\s*.*?=\s*["\']([^"\']+)["\']', ours, re.M)
            if dm:
                downs.add(dm.group(1))
        tips = [r for r in all_revs if r not in downs]
        tip = tips[0] if tips else (om.group(1) if om else None)
        new_rev = f"{nxt:04d}_" + re.sub(r"^\d{4}_", "", old_rev)
        # slug from filename
        base = re.sub(r"^\d{4}_", "", p.name)
        new_path = versions / f"{nxt:04d}_{base}"
        new_text = theirs
        new_text = re.sub(
            r'^revision:\s*str\s*=\s*["\'][^"\']+["\']',
            f'revision: str = "{new_rev}"',
            new_text,
            count=1,
            flags=re.M,
        )
        if tip:
            new_text = re.sub(
                r'^down_revision:\s*.*$',
                f'down_revision: str | None = "{tip}"',
                new_text,
                count=1,
                flags=re.M,
            )
        new_path.write_text(new_text)
        subprocess.check_call(["git", "add", path, str(new_path)])
        print(f"kept ours {path}; wrote theirs as {new_path} rev={new_rev} down={tip}")
    elif theirs and not ours:
        # only theirs — just add, but fix down_revision to tip
        p.write_text(theirs)
        subprocess.check_call(["git", "add", path])
        print(f"added theirs {path}")
    else:
        subprocess.check_call(["git", "checkout", "--ours", "--", path])
        subprocess.check_call(["git", "add", path])
        print(f"kept ours {path}")
PY
}

if ! git rebase origin/main; then
  while [ -d .git/rebase-merge ] || [ -d .git/rebase-apply ]; do
    resolve_features || true
    conflicts=$(git diff --name-only --diff-filter=U || true)
    echo "Conflicts: $conflicts"
    if echo "$conflicts" | grep -q 'alembic/versions'; then
      renumber_alembic
    fi
    # take theirs for i18n if needed? prefer merge with union via checkout --theirs for json? 
    remaining=$(git diff --name-only --diff-filter=U || true)
    if [ -n "$remaining" ]; then
      # For leftover non-alembic/non-FEATURES: prefer incoming (theirs) during rebase
      while IFS= read -r f; do
        [ -z "$f" ] && continue
        if [ "$f" = "FEATURES.md" ]; then resolve_features; continue; fi
        git checkout --theirs -- "$f" || true
        git add "$f"
        echo "took theirs for $f"
      done <<< "$remaining"
    fi
    remaining=$(git diff --name-only --diff-filter=U || true)
    if [ -n "$remaining" ]; then
      echo "Still unresolved: $remaining"
      exit 4
    fi
    GIT_EDITOR=true git rebase --continue
  done
fi

# Fix alembic chain if duplicate revision ids after clean rebase
python3 - <<'PY'
from pathlib import Path
import re, subprocess
versions = Path("apps/api/alembic/versions")
by_rev = {}
for f in versions.glob("*.py"):
    t = f.read_text()
    m = re.search(r'^revision:\s*str\s*=\s*["\']([^"\']+)["\']', t, re.M)
    if m:
        by_rev.setdefault(m.group(1), []).append(f)
dups = {k:v for k,v in by_rev.items() if len(v)>1}
if dups:
    print("ERROR duplicate revisions", {k:[str(x) for x in v] for k,v in dups.items()})
    raise SystemExit(1)
# ensure single tip
downs=set(); revs={}
for f in versions.glob("*.py"):
    t=f.read_text()
    rm=re.search(r'^revision:\s*str\s*=\s*["\']([^"\']+)["\']', t, re.M)
    dm=re.search(r'^down_revision:\s*.*?=\s*["\']([^"\']+)["\']', t, re.M)
    if rm: revs[rm.group(1)]=f
    if dm: downs.add(dm.group(1))
tips=[r for r in revs if r not in downs]
print("alembic tips:", tips)
if len(tips)!=1:
    print("WARNING: expected 1 tip")
PY

git push --force-with-lease origin "$BRANCH"

for i in 1 2 3 4 5 6 7 8; do
  state=$(gh pr view "$PR" --json state,mergeable --jq '"\(.state) \(.mergeable)"')
  echo "merge state: $state"
  case "$state" in
    MERGED*) echo already merged; exit 0 ;;
    *" MERGEABLE") gh pr merge "$PR" --merge --delete-branch; exit 0 ;;
  esac
  sleep 4
done
gh pr merge "$PR" --merge --delete-branch

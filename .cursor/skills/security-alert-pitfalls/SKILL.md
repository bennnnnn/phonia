---
name: security-alert-pitfalls
description: >-
  Common pitfalls fixing CodeQL polynomial-ReDoS and Dependabot npm alerts in
  Recall. Use when clearing CodeQL py/polynomial-redos, workflow permissions,
  or Dependabot alerts on apps/mobile lockfile / transitive deps.
---

# Security alert pitfalls (Recall)

Hard-won from clearing CodeQL High ReDoS + Dependabot npm alerts. Fix the sink; don't paper over it.

## CodeQL `py/polynomial-redos`

**Symptom:** High alert on `re.search` / `finditer` / `.sub` of user chat / OCR / caption text — often `\s+`, ` ?`, `.+?`, nested optionals.

**Pitfalls (what does NOT clear the alert):**
- `collapse_ws` / `" ".join(text.split())` before the regex — CodeQL does **not** treat this as a sanitizer.
- A const length guard (`if len(text) > 1000: return`) alone — same; sinks stay flagged.
- Tweaking `\s+` → single space in the pattern while leaving `.+` / nested `?` pumps.

**What works:** rewrite the sink to **linear** matching — `str.find` / prefix strips / digit parsers / char-set walks. Keep only simple digit-only regexes if needed (`-?\d+(?:\.\d+)?` on a short slice is usually fine; optional-space LaTeX patterns are not).

**Also:** moving the same poly regex into a helper module does not help — CodeQL follows the call. Fix or delete the pattern.

**Workflow permissions (`actions/missing-workflow-permissions`):** add top-level `permissions: contents: read`. Elevate per-job only when required (e.g. docker `cache-to: type=gha` needs `actions: write` on that job).

## Dependabot (npm / `apps/mobile`)

**Symptom:** alerts on packages you don't depend on directly.

**Pitfalls:**
- Bumping only the direct pin (e.g. `markdown-it@^14`) while `react-native-markdown-display` still locks `markdown-it@10` + `linkify-it@2` in the lockfile — Dependabot keeps filing.
- `uuid@7` via Expo → `xcode` — not fixed by app code changes; needs a **pnpm override**.
- Regenerating the lock with **pnpm 11** while CI pins **pnpm 9** → `ERR_PNPM_LOCKFILE_CONFIG_MISMATCH` / dropped `patchedDependencies`. Always: `npx pnpm@9.15.9 install`.

**What works:** `package.json` → `pnpm.overrides` to patched versions, then regenerate lock with pnpm 9. Confirm with `pnpm why <pkg>` that only patched versions remain.

## GitHub Security UI

**Pitfall:** after merge, the Security tab can still list alerts (old line numbers / “opened N minutes ago”) while the API already has `state: fixed` and `open=0`. Trust `gh api .../code-scanning/alerts?state=open` (and Dependabot equivalents) over a stale UI refresh mid-scan — don't open a duplicate fix PR.

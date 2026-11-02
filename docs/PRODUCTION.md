# Recall — Production Provisioning Checklist

Step-by-step guide to provision production infrastructure. Pair with [`README.md`](../README.md) §Production deployment and run [`scripts/verify-production.sh`](../scripts/verify-production.sh) after each stage.

---

## 0. Accounts, plans and regions (decided 2026-10-22)

Development runs on free tiers. **When we deploy, every account below moves to a paid
plan first, then the sections that follow are worked through in order.** Everything
sits in or beside Fly's `iad` (Ashburn, Virginia), so no request pays a cross-region
hop: the database in Ohio cost about 10 ms per round trip, and a chat turn makes
several. Check each provider's current pricing when buying, and set a spending limit
or alert on every usage-billed account.

| Service | What it runs | Production plan | Region | Today |
|---------|--------------|-----------------|--------|-------|
| Neon | Postgres + pgvector | Paid, usage-based, for the whole org | AWS `us-east-1` | No production database. Development uses a throwaway free database in `us-east-1`; its data does not matter. The paid one is created fresh on deploy day, and it is the first data we keep. |
| Upstash | Redis (jobs, quota, rate limits, sign-out) | Pay as you go | `us-east-1` | No production database yet; local dev uses Homebrew Redis. |
| Fly.io | API and worker machines | Pay as you go (card on file) | `iad` | Not deployed. `recall-api.fly.dev` answers as an unrelated app, so the name `recall-api` may be taken: pick a free name and update `fly.toml` and the app's `EXPO_PUBLIC_API_URL`. |
| Cloudflare R2 | Attachments | Pay as you go | Location hint: Eastern North America | Not created. |
| OpenRouter | Chat models | Prepaid credits with auto top-up | — | Dev key in `apps/api/.env`. |
| OpenAI | Speech to text, read aloud, live talk | Pay as you go with a monthly limit | — | |
| Tavily | Web search, reference photos | A plan sized to search volume | — | |
| Resend | Transactional email | Free tier until volume needs more; verify the sending domain | — | |
| RevenueCat | Plus and Pro subscriptions | Free until its revenue threshold | — | |
| Sentry | Errors (optional) | Free tier to start | — | |
| Expo EAS | Store builds, over-the-air updates | Paid only if build or update volume needs it | — | |
| Apple Developer, Google Play | Store accounts | Apple yearly, Google once | — | |

**Lessons that set these rules:**

- **Production never shares a free allowance with dev.** On 2026-10-21 the dev API's
  schedulers kept the old Neon project's compute awake about 430 hours, spent the free
  plan's compute allowance, and Neon suspended every branch of the project, production
  included, until the month reset. On the paid plan, keep `dev` as a branch only with a
  spending limit set; otherwise give dev its own project or the local Postgres.
- **A Neon project's region cannot change.** Moving means a new project and a data copy
  (done once, 2026-10-22). The old project `recall` (red-salad-87226210, us-east-2) is
  kept until its quota resets on 2026-11-01 and can then be deleted.
- **Neon, Upstash and Fly move together.** If the Fly region changes, recreate the
  database and Redis beside it.

**Order at deploy time:**

1. Neon: on a paid plan with a spending limit, create the production project in
   `us-east-1`, run the migrations and confirm it shows `alembic heads` (§1).
2. Upstash: create the production database in `us-east-1`; take its `rediss://` URL (§2).
3. R2: bucket and token (§3).
4. Fly: install `flyctl`, choose the app name, deploy, set every secret (§4).
5. Then §4b to §8, and the owner actions at the end.

---

## 1. Database (Neon Postgres + pgvector)

- [ ] Create the paid Neon project in AWS `us-east-1`, beside Fly `iad` (§0)
- [ ] Enable `vector` extension: `CREATE EXTENSION IF NOT EXISTS vector;`
- [ ] Set `DATABASE_URL` as `postgresql+asyncpg://...?sslmode=require`, the
      project's **direct** endpoint (the app switches itself to the `-pooler`
      host; migrations stay on the direct one). Production boot refuses a
      `DATABASE_URL` that points at localhost, the default when it is unset.
- [ ] Run migrations: `cd apps/api && uv run alembic upgrade head`
- [ ] Confirm `uv run alembic current` matches `uv run alembic heads`

```bash
cd apps/api
uv run alembic heads
uv run alembic current
# The same single revision should be shown by both commands.
```

Every migration transaction runs with `lock_timeout = 5s` and
`statement_timeout = 4min` (`MIGRATION_LOCK_TIMEOUT`,
`MIGRATION_STATEMENT_TIMEOUT`): an `ALTER TABLE users` stuck behind a long
query fails the release command instead of queueing every request on `users`.
Rerun the deploy when the database is quieter. Schema changes are
expand/contract ([ROLLBACK.md](ROLLBACK.md#schema-changes-expand-then-contract)).

### Backups and restore (owner, before launch)

The rollback runbook and the `0103` downgrade both assume a restorable copy of
the database. Neon keeps one through its restore window (point-in-time restore
from the write-ahead log); nothing in this repository takes backups.

- [ ] In the Neon console, find the project's restore window (project
      settings, "Instant restore" / "history retention"; the name depends on
      the console version) and note how far back it reaches on your plan (it
      differs by plan, from hours on Free to days on paid plans). Raise it to
      at least 7 days for launch: a problem found on Monday must still be
      restorable to Friday.
- [ ] Rehearse one restore before launch, never onto production: create a
      branch from a past point in time (console: Branches → create a branch
      from past data at a chosen timestamp; `neonctl branches create` can do
      the same, see Neon's docs for the flag), point a local API at it
      (`DATABASE_URL=<branch URL> uv run alembic current`), check a known row,
      then delete the branch.
- [ ] Write down who can restore and where the connection strings live. To
      recover production, restore to a branch at the last good time, verify
      it, then either repoint `DATABASE_URL` (`fly secrets set`) or use
      Neon's restore of the root branch (it keeps a backup branch of the state
      it replaced). Both lose the writes made after that time.
- [ ] Optional: a nightly `pg_dump` of the direct endpoint to storage outside
      Neon, for a window longer than the plan's or an account-level disaster.

---

## 2. Redis (Upstash)

- [ ] Create Upstash Redis database
- [ ] Set `REDIS_URL=rediss://...` (TLS URL). Production boot refuses a
      `REDIS_URL` without TLS or pointing at localhost (the default when the
      secret is missing): before this, the API booted, `/health/ready` said
      `"redis": "degraded"` with a 200, and every signed-in request got 503.
- [ ] Verify connectivity from Fly region (latency to Upstash region)
- [ ] After deploy, `API_URL=https://<api> ./scripts/qa-smoke.sh --live` must show
      readiness OK, which needs `"redis": "ok"`
- [ ] Redis holds the job stream, quota counters, rate limits and sign-out
      state. Nothing here backs it up; if Redis is lost or flushed, the worker
      recreates its consumer group by itself and queued jobs are gone

**Cached user rows.** Each API machine keeps the user rows it has read for up to
5 minutes and checks each one, on every request and chat frame, against the
user's generation in Redis (`usergen:<user id>`, `core/user_cache.py`). Every
change the app commits to a user row (settings, consent, memory switches, the
RevenueCat plan) stores a new generation, so all machines read the row again on
their next request.

- A change made to `users` outside the app (SQL by hand, a restore) is not
  seen until each machine's copy expires: after it, run
  `DEL usergen:<user id>` for each user changed (after a restore,
  `redis-cli --scan --pattern 'usergen:*' | xargs redis-cli del`). The next
  request starts a fresh generation and reads the row.
- If Redis refuses a change's new generation (after three tries), the request
  answers `503` + `Retry-After` although the change is saved. While Redis is
  down every request is refused anyway. Once it is back, other machines can
  serve the old row until the change is made again (the phone does not retry a
  503 by itself, so the user does, after the error; a RevenueCat redelivery; a
  retried job) or for at most 5 minutes.

---

## 3. Object storage (Cloudflare R2)

Required for production attachments (`STORAGE_BACKEND=r2`).

- [ ] Create R2 bucket (e.g. `recall-attachments`)
- [ ] Create API token with R2 read/write on bucket
- [ ] Set secrets:
  - `STORAGE_BACKEND=r2`
  - `R2_ACCOUNT_ID`
  - `R2_ACCESS_KEY_ID`
  - `R2_SECRET_ACCESS_KEY`
  - `R2_BUCKET`
- [ ] Smoke-test: upload image in app → confirm object in R2 → download in chat
- [ ] Bucket lifecycle: abort incomplete multipart after 7 days. Account delete
  purges known keys then enqueues a `storage_sweep` job that `list`+`delete`s
  leftover objects under `{user_id}/` (covers Redis reaper never running). Do
  not weaken `reap_orphan_attachments`. Unconfirmed original uploads are reaped
  after `attachment_pending_orphan_hours` (default 1h). Hidden clones stay until
  `attachment_orphan_grace_hours` (default 24h) — that billed window is
  intentional. Optionally add an R2 lifecycle rule
  that expires unprefixed leftovers as a last resort.
- [ ] Recovery (owner): R2 keeps no earlier version of an object unless the
  bucket has versioning or a bucket lock rule (check what the Cloudflare
  dashboard offers for the bucket; the code assumes neither). A delete is final,
  which is what account deletion needs. Decide whether that is acceptable, and
  never add a lifecycle rule that expires `{user_id}/` objects (live
  attachments). After a Neon restore to an earlier time (§1), rows can name
  objects deleted since; those attachments show as missing, and objects
  uploaded after the restore point become orphans for the reaper.

Native iOS/Android uploads are not subject to browser CORS. Before enabling the
planned web client, add an R2 bucket CORS policy that allows `PUT`/`GET` from the
exact production web origin and only the headers used by presigned uploads.

---

## 4. Fly.io API

- [ ] `fly launch` (or connect existing app to repo root; uses `apps/api/Dockerfile`)
- [ ] Scale processes: `fly scale count app=1 worker=1` (worker is not
      covered by `min_machines_running`; pin it or jobs stop silently)
- [ ] Confirm worker health:
  `fly ssh console --process-group worker -C 'curl -sf http://127.0.0.1:8001/health/ready'`
  (or check worker logs show the jobs consumer started). The worker retries
  Redis forever at boot and exits non-zero (so `[[restart]]` brings it back)
  when its jobs loop or a scheduler dies; a failing health check alone never
  restarts a Machine on Fly.
- [ ] Set **all** secrets (enforced by `validate_production_settings`):

| Secret | Required | Notes |
|--------|----------|-------|
| `ENVIRONMENT` | yes | `production` |
| `DEV_AUTH_ENABLED` | yes | `false` |
| `MOCK_LLM_ENABLED` | yes | `false` |
| `JWT_SECRET` | yes | ≥32 random chars |
| `DATABASE_URL` | yes | asyncpg URL, direct Neon endpoint; not localhost |
| `REDIS_URL` | yes | `rediss://`; not localhost |
| `GOOGLE_CLIENT_ID` | yes | Google Sign-In (ID-token audience) |
| `APPLE_TEAM_ID`, `APPLE_KEY_ID`, `APPLE_PRIVATE_KEY` | for App Review 5.1.1(v) | A Sign in with Apple key (Apple Developer → Keys); `APPLE_PRIVATE_KEY` is the `.p8` contents. Account delete revokes the user's Apple grant with it. Unset: delete still works, boot logs a warning |
| `OPENROUTER_API_KEY` | yes | Chat + composer STT (`gpt-transcribe`) |
| `OPENAI_API_KEY` | Live Talk only | WebRTC Realtime; OpenRouter has no Realtime API |
| `CORS_ORIGINS` | yes | Explicit origins, never `*` |
| `REVENUECAT_WEBHOOK_AUTH` | yes | Shared secret for the webhook |
| `REVENUECAT_SECRET_KEY` | yes | REST API; every access change, TRANSFER, plan sync, hourly reconcile |
| `REVENUECAT_ENTITLEMENT_ID` | no (default `pro`) | Top plan's entitlement; keep `pro` so earlier subscribers stay on Pro |
| `REVENUECAT_PLUS_ENTITLEMENT_ID` | no (default `plus`) | Lower paid plan's entitlement |
| `TAVILY_API_KEY` | if web search | |
| `TRUST_X_FORWARDED_FOR` | yes (set in `fly.toml` `[env]`) | `true` behind Fly. Unset, every per-IP rate limit keys on Fly's proxy address and becomes one global bucket; production boot logs a warning. |
| `DAILY_GLOBAL_SPEND_USD` | yes | UTC-day provider $ cap (every model call, images, voice, live talk); must be > 0. At the cap new chat turns are refused: see [Load and abuse limits](#load-and-abuse-limits) |
| R2 vars | yes | See §3 |
| `RESEND_API_KEY` | if email | Without it nothing is emailed (§8) |

Validate the file you import before `fly secrets import`:
`./scripts/validate-prod-env.sh apps/api/.env.production`. It reads only that
file (not `apps/api/.env` or your shell), and fails when `ENVIRONMENT` is not
`production`.

### Deploying

Deploy with GitHub **Actions → Deploy**, run on `main`. A gate job (no secrets)
refuses any other branch and any commit whose API CI (or Mobile CI, for the
EAS build) push run has not passed for that commit's code; then the deploy job
runs in the GitHub environment `production`. `scripts/deploy-api.sh` is the
break-glass path from a laptop: it refuses a dirty tree or a branch other than
an up-to-date `main` unless `--force`.

- [ ] **Owner:** Settings → Environments → `production`: add yourself (and
      anyone else) as **required reviewers**, set **deployment branches** to
      `main` only, and move `FLY_API_TOKEN` and `EXPO_TOKEN` there as
      environment secrets (delete the repository-level copies) so no other
      job can read them. `FLY_API_TOKEN` should be a deploy token for this app
      (`fly tokens create deploy --app recall-api`), not a personal token.
      GitHub offers environments in private repositories on Pro, Team and
      Enterprise plans, and required reviewers there only on Enterprise; on a
      plan without them the gate job and the main-only checks still apply,
      but nobody has to approve.
- [ ] **Owner:** the `preview` environment (EAS Update to the preview channel)
      needs `EXPO_TOKEN` too, if it is moved off the repository.
- [ ] Bumping a pinned action or CLI (`setup-flyctl` commit and flyctl
      version, `expo-github-action` commit and eas-cli version,
      `pnpm/action-setup` commit) is a reviewed change to the workflow.

What one deploy does (`fly.toml`):

1. `release_command` runs `alembic upgrade head` once, with the bounded lock
   and statement timeouts (§1). If it fails, nothing is replaced.
2. `strategy = "bluegreen"`: a new Machine boots next to each old one (app and
   worker), traffic moves only after the new Machines pass their health checks,
   then the old ones are stopped. The org needs room for one extra Machine per
   group during the deploy. For a moment two workers run; job leases, dedupe
   keys and scheduler locks make that safe.
3. An old Machine gets Fly's stop signal (SIGINT), then `kill_timeout = 45`
   seconds: uvicorn's `--timeout-graceful-shutdown 30` lets in-flight requests
   and chat turns finish or stop and save, and lifespan shutdown drains
   background work for up to 10s. The worker leaves unfinished jobs pending for
   the new worker. Keep these numbers in step in `fly.toml` and
   `apps/api/Dockerfile` (`app/tests/test_deploy_config.py` checks them).
4. The workflow smoke-checks `https://recall-api.fly.dev` (readiness must
   report `"redis": "ok"`). The image is labelled `git-<sha>`
   (`fly releases --image` maps a release back to its commit).

```bash
# Full check after a deploy (needs flyctl auth and uv): API readiness with
# Redis, worker health, alembic current on Fly == alembic heads here.
API_URL=https://<your-api> ./scripts/verify-production.sh --live
```

- [ ] Health monitor: `GET /health` (liveness) and `GET /health/ready` (Postgres;
      Redis may report `degraded` without 503 — alert on that too, §8).
      `GET /health/dependencies` answers 503 (with `Retry-After`) when either
      Postgres or Redis is down: the phone's connection check reads it, and Fly's
      checks never do
- [ ] **Measure before launch:** `[http_service.concurrency]` is `type =
      "requests"`, `soft_limit = 150`, `hard_limit = 200` per Machine. Whether
      Fly's proxy counts each open chat WebSocket as one in-flight request for
      its whole life (so 200 idle sockets would fill the Machine and queue
      every REST call) was not confirmed from Fly's docs here. Load-test one
      Machine with ~200 open `/ws/chat` sockets plus REST traffic and watch
      Fly's proxy concurrency metrics and any 503s or queueing. If sockets count, use
      `type = "connections"` with limits sized to sockets plus REST
      connections, or scale out on `soft_limit`; do not leave it to launch day.
- [ ] RevenueCat webhook → `https://<api>/webhooks/revenuecat` with `Authorization` header
- [ ] Plans and store products set up per [§4b](#4b-plans-and-revenuecat-free-plus-pro)

---

## 4b. Plans and RevenueCat (Free, Plus, Pro)

Three plans. "Plus" and "Pro" are working names: the app shows them from i18n
(`plans.plus`, `plans.pro` in all nine locale files), so renaming them is a
copy change. The server only knows the ids `free`, `plus`, `pro`.

| | Free | Plus (lower paid) | Pro (top) |
|---|---|---|---|
| Models | free pool | all | all |
| Tokens / day | 100k | 500k | 500k |
| Voice input / day | — | 200 | 200 |
| Natural read-aloud / day | — (phone voice only) | 100 | 100 |
| AI images / day | 3 | 10 | 15 |
| Live talk | — | — | 60 min / UTC calendar month |

Every number is a setting in `core/settings/plans.py` (`<NAME>`, `<NAME>_PLUS`,
`<NAME>_PRO`; see `apps/api/.env.example`). A metered feature belongs to a plan
when its number is above zero, so moving a feature between plans is a secret
change, not a release. `modules/billing/entitlements.py` is the one place that
decides; the server refuses (403) anything a plan lacks, whatever the app shows.

**Prices are never in code.** Set them in App Store Connect and Play Console;
the app shows the store's localized price from the RevenueCat offering.

### What to create (owner)

1. **App Store Connect** — one subscription group (e.g. "Recall") holding two
   auto-renewable monthly subscriptions, e.g. `recall_plus_monthly` ($7.99) and
   `recall_pro_monthly` ($13.99). Rank Pro **above** Plus in the group (level 1),
   so Plus → Pro is an immediate upgrade and Pro → Plus takes effect at renewal.
   If a Pro product already exists, keep it as the Pro product in that group.
2. **Play Console** — two subscriptions (e.g. `recall_plus`, `recall_pro`), each
   with a monthly base plan. The app replaces the Plus subscription when someone
   buys Pro (prorated, immediate), so nobody pays for both.
3. **RevenueCat → Entitlements** — keep `pro` (the single-plan id; existing
   subscribers stay on Pro with nothing lost) and add `plus`. Attach the Plus
   products to `plus` and the Pro products to `pro` (attaching Pro to both is
   fine; the server takes the higher plan).
4. **RevenueCat → Offerings** — the current offering holds two packages with the
   custom identifiers **`plus_monthly`** and **`pro_monthly`**. (An offering with
   only the old monthly package is shown as Pro, so the switch can be staged.)
5. **RevenueCat → Project settings** — keep restore behavior **Transfer to new
   App User ID** (the default). Two accounts on one Apple ID: the account that
   restores gets the plan and the other drops to Free on the TRANSFER webhook.
6. **Webhook** — unchanged URL and auth. The server re-reads the subscriber on
   every event that can change access; BILLING_ISSUE (grace period),
   SUBSCRIPTION_PAUSED and auto-renew-off CANCELLATION keep access until
   EXPIRATION. The worker re-checks every paid row hourly
   (`BILLING_RECONCILE_INTERVAL_SECONDS`).
7. **Deploy order** — migrate (`0107_plus_plan` only widens `ck_users_plan`;
   no rows change), deploy the API, then ship the app build with the new
   offering. An older app build still sees Pro correctly; it does not offer Plus.

### Live talk minutes

The phone talks to OpenAI over WebRTC after the server mints a session, so the
server meters at its own edges: a mint reserves `min(minutes left,
LIVE_TALK_MAX_SESSION_SECONDS)` (refused under `LIVE_TALK_MIN_SESSION_SECONDS`),
the session may save turns and use voice tools only for that reservation, the
phone hangs up when it ends, and `POST /speech/live/end` settles it to the time
the server measured (never refunding more than was reserved). A phone that
never reports keeps the whole reservation charged. The global spend counter
follows the same reservation: a mint adds the reserved minutes at
`LIVE_TALK_SPEND_USD_PER_MINUTE` ($0.20, `services/quota/spend.py`) and the
end report gives back the unused part, so saved turns add no spend. A session
may save one turn per 5 reserved seconds (at least 12) and a user 20 turns a
minute; past either, `POST /speech/live/persist` answers 429. Known limit: the
server cannot hang up the OpenAI call itself, so a modified client could keep
talking past its reservation (nothing is saved, no tools); that time is not
on the spend counter.

### QA (sandbox / test track)

- [ ] Free: mic and live talk open the plans; read-aloud uses the phone voice;
      3 AI images, then the limit message
- [ ] Buy Plus: voice input and read-aloud work, live talk opens the plans,
      Settings shows Plus and "Upgrade to Pro"
- [ ] Plus → Pro: one subscription in the store afterwards; live talk works and
      Settings shows minutes left; a 2-minute call takes about 2 minutes
- [ ] Pro → Plus (store downgrade): Pro until renewal, then Plus
- [ ] Cancel, let it expire: back to Free on the next request
- [ ] Refund (support): back to Free; restore on a second device; sign in as a
      second account on the same Apple ID and restore (TRANSFER)

---

## 5. Mobile (EAS)

- [ ] Configure EAS project ID in `apps/mobile/.env` / EAS secrets
- [ ] Set `EXPO_PUBLIC_API_URL=https://<api-host>`
- [ ] Set Google client IDs (iOS + web) in EAS secrets
- [ ] Set RevenueCat API keys per platform
- [ ] Register **both** Android release SHA-1s with Google Cloud, not only the EAS
      one: see [§6](#6-google-sign-in)
- [ ] Release builds pass the config guard for API URL, EAS project ID, Google
      client IDs, and the platform's RevenueCat SDK key
- [ ] Optional crash reporting: `EXPO_PUBLIC_SENTRY_DSN` turns on Sentry. A
      release build then uploads source maps and debug symbols, and Sentry's
      Xcode and Gradle steps fail the build at its end when that upload fails. So
      when the DSN is set, the config guard stops the build on the EAS worker
      unless all three are set:
  - `SENTRY_ORG` and `SENTRY_PROJECT` (the slugs; Plain text)
  - `SENTRY_AUTH_TOKEN` (a Sentry organization auth token; **Secret**)

  To ship without uploads (crash stacks stay minified), set
  `SENTRY_DISABLE_AUTO_UPLOAD=true` instead. The check runs only on the build
  worker (`EAS_BUILD`): EAS keeps Secret variables out of the config that
  `eas build` and `eas update` resolve locally, and updates upload nothing.
- [ ] Build:
  ```bash
  cd apps/mobile
  eas build --platform ios --profile production
  eas build --platform android --profile production
  ```
- [ ] Submit to App Store / Play Console (see [Store submission](#store-submission-owner))
- [ ] On-device QA per [`docs/QA_MATRIX.md`](QA_MATRIX.md), including the iPad
      and store-build passes

### What the store build declares

`app.json` asks only for what the app uses, so review sees no unexplained
permission. Changing any of it is a native change (bump `version`, new build).

- **iOS purpose strings** live in `ios.infoPlist`, and every config plugin that
  writes the same key carries the same text (`lib/__tests__/appStoreConfig.test.ts`
  checks this), because the plugins' order decides which text wins. One
  microphone string covers dictation and Live Talk; one camera string covers
  photo attachments and the maths scanner.
- **No background audio.** Read-aloud stops and Live Talk hangs up when the app
  leaves the foreground, so `expo-audio` has `enableBackgroundPlayback: false`:
  no `UIBackgroundModes` on iOS, no foreground service on Android.
- **Not declared:** Face ID, Always location and Android media read access
  (`READ_MEDIA_*`; saving to the gallery is write-only and the photo picker needs
  none), plus WebRTC's `SYSTEM_ALERT_WINDOW` and `BLUETOOTH`
  (`android.blockedPermissions`). `NSMotionUsageDescription` stays, saying the
  app does not use motion: `expo-location` links Core Motion, and App Store
  Connect rejects an upload whose binary uses an API without its purpose string
  (ITMS-90683).
- **Export compliance:** `ios.config.usesNonExemptEncryption: false` (HTTPS
  only), so App Store Connect does not ask on every build.
- **Privacy manifest:** `ios.privacyManifests` in `app.json`, which `expo prebuild`
  writes to `ios/Recall/PrivacyInfo.xcprivacy`. It lists the data the app
  collects (the [App Privacy answers](#app-privacy-answers-draft) below) with
  `NSPrivacyTracking: false`, and the one required-reason API the app's own code
  reaches: file timestamps, `C617.1`, for the modification times and sizes of its
  own cache and document files, read through `expo-file-system` (whose manifest
  gives only the SDK wrapper reason, `0A2A.1`). Each SDK declares its own
  required-reason APIs (user defaults, system boot time, disk space) in its
  manifest, and `pod install` copies them into the app's (React Native's privacy
  manifest aggregation, on unless `apple.privacyManifestAggregationEnabled` is
  `false`). `lib/__tests__/appStoreConfig.test.ts` holds both lists.
- Expo's dev launcher adds a local-network prompt to Info.plist; its own Release
  build phase ("Strip Local Network Keys for Release") removes it from store builds.

### Store submission (owner)

- [ ] **Subscriptions ship with the first build.** Submit both products from
      [§4b](#4b-plans-and-revenuecat-free-plus-pro) (Plus and Pro) for review
      together with the first app version (App Store Connect: add them on the
      version page under In-App Purchases and Subscriptions; Play: activate both
      base plans). A product that is not approved does not load.
- [ ] **RevenueCat offering first.** The current offering must hold the
      `plus_monthly` and `pro_monthly` packages before review. Without them the
      plan sheet's buy buttons stay disabled (`features/billing/components/UpgradeSheet.tsx`),
      and a paywall that cannot buy is rejected.
- [ ] **App Review notes:** sign in with Apple (or Google). The line under the
      sign-in buttons says that continuing agrees to the Terms, the Privacy
      Policy and third-party AI processing of chats and voice, with both links
      beside it; that tap is the user's permission for guideline 5.1.2(i), and
      the server records it with the sign-in. Chat, memory, to-dos
      and the maths scanner work on Free. Voice input and read-aloud need Plus
      and Live Talk needs Pro: buy them with the sandbox account (no charge)
      to test the microphone features.
- [ ] **After the first upload**, watch App Store Connect email for
      **ITMS-91053** (the binary uses a required-reason API that no privacy
      manifest declares). If it names an API category, add it with the right
      reason under `ios.privacyManifests.NSPrivacyAccessedAPITypes` in `app.json`
      (and in the test's list) and rebuild.
- [ ] **App Privacy (App Store) and Data safety (Play):** answer from the
      [draft below](#app-privacy-answers-draft). None of it is used for tracking
      or sold. Play's Data safety form asks for the same data in its own
      categories.
- [ ] Play Console → App content: the build declares no `READ_MEDIA_*` or
      foreground-service permission, so the photo and video permissions and
      foreground service declarations do not apply

#### App Privacy answers (draft)

The same rows as the privacy manifest (`ios.privacyManifests` in `app.json`) and
the hosted privacy policy (`apps/api/app/content/privacy_policy.py`). "Linked"
means tied to the account. Tracking (Apple's sense: combining with other
companies' data for advertising, or sharing with data brokers) is **No** for
every row, and the manifest says `NSPrivacyTracking: false`.

| App Store Connect data type | Linked | Tracking | Purposes | What the app collects |
|---|---|---|---|---|
| Contact Info → Email Address | Yes | No | App Functionality | Google or Apple sign-in; reminder, welcome and receipt emails |
| Contact Info → Name | Yes | No | App Functionality, Product Personalization | Sign-in and profile name; the greeting and the model's answers use it |
| Location → Precise Location | Yes | No | App Functionality | A nearby or "where am I" message carries the phone's coordinates; when the phone finds no place name, the label sent is the coordinates to four decimals, which reaches the model and the web search |
| Location → Coarse Location | Yes | No | App Functionality | The city, region and country saved while Use current location is on |
| User Content → Photos or Videos | Yes | No | App Functionality | Attached photos, maths scans, the profile photo |
| User Content → Audio Data | Yes | No | App Functionality | Voice input and Live Talk (sent to OpenAI; Recall keeps the text, not the audio) |
| User Content → Other User Content | Yes | No | App Functionality, Product Personalization | Messages, chats, memory, to-dos, attached files, custom instructions, thumbs-up/down feedback |
| Identifiers → User ID | Yes | No | App Functionality, Analytics | The account id, also RevenueCat's app user id; product events are stored under it |
| Identifiers → Device ID | Yes | No | App Functionality, Analytics | This install's id (`lib/installationId.ts`), sent with the push token and product events; the push token |
| Purchases → Purchase History | Yes | No | App Functionality, Analytics | Plan and subscription status (RevenueCat); purchase started, succeeded and failed events |
| Usage Data → Product Interaction | Yes | No | Analytics | Metadata-only product events: paywall views, purchase outcomes, notification permission, how a chat turn ended |
| Diagnostics → Performance Data | Yes | No | Analytics, App Functionality | How quickly replies start (bucketed product events); Sentry traces when the DSN is set |
| Diagnostics → Crash Data | No | No | App Functionality | Sentry crash reports when the DSN is set: no user id, no message text (`lib/sentry.ts`) |
| Diagnostics → Other Diagnostic Data | No | No | App Functionality | Sentry error reports (a screen or message that failed to draw, store and push failures), same rules; a chat that could not be created or read, a failed upload or purchase, and a reply block the app would not draw or that crashed carry ids and codes only, never message text |
| Other Data → Other Data Types | Yes | No | App Functionality, Product Personalization | Optional profile fields (age, country, job); each signed-in session's device name or model |

Not collected: phone number, physical address, contacts, health or fitness,
financial info (Apple or Google take payment), browsing history, search history
(the drawer's search reads saved chats and keeps no query) and advertising data.
Sensitive Info is not a row of its own: memory keeps a sensitive fact only when
the user asks it to or turns on sensitive memory, and it is then the user's own
words (Other User Content); owner to confirm. The Crash Data and Other Diagnostic
Data rows, and Sentry's share of Performance Data, apply only when the store
build sets `EXPO_PUBLIC_SENTRY_DSN`; the Sentry SDK's own manifest declares them
in every build.

### Over-the-air updates (EAS Update)

JavaScript and asset changes reach installed apps without a store release.
Builds made with the `production` profile listen on the `production` channel
(`preview` builds on `preview`). The app checks on launch, downloads in the
background, and runs the new code from the next launch.

- [ ] In EAS environment variables, keep every `EXPO_PUBLIC_*` value as
      **Plain text** or **Sensitive** (not **Secret**) in the `production` and
      `preview` environments, so `eas update` can bundle them
- [ ] Publish: GitHub **Actions → Publish app update** (channel + message), or
  ```bash
  cd apps/mobile
  RECALL_UPDATE_PROFILE=production eas update --channel production \
    --environment production --message "what changed"
  ```
- [ ] A build takes only updates for its own runtime version, which is the
      `version` in `apps/mobile/app.json`. **Bump that version and ship a store
      build** for any native change: a new native module, an Expo SDK upgrade, or
      a config plugin or permission change. An update sent to an older binary
      without that native code would crash it.
- [ ] Builds made before `expo-updates` was added cannot receive updates; install
      a new build once
- [ ] **Deploy the API before the app** (store build or update) whenever the app
      starts sending something new. An older API refuses fields it does not know:
      the chat analytics fields `paint_bucket` (on `chat_ttft`) and
      `send_ready_bucket` (on `chat_turn_outcome`), and the newer `error_code` values
      on `chat_turn_outcome` (`failed`, `not_found`, `consent_required`, …), get a 422
      there. The API refuses the whole batch for one unknown value, and the app drops
      a refused post without retrying and stops that flush, so every event queued
      with it (other chat timings, a paywall or purchase event) is lost too, until the
      API is out. An older API also sends a picture turn's spend-cap frame without
      `feature`, so a new app words it as the chat-wide cap line.
- [ ] Review [`docs/ROLLBACK.md`](ROLLBACK.md) before the first store submission

---

## 6. Google Sign-In

- [ ] OAuth consent screen published (sign-in scopes only: openid, email, profile)
- [ ] Client IDs match the mobile bundle IDs and `GOOGLE_CLIENT_ID`
- [ ] **Android: one Android OAuth client per signing certificate**, all with
      package `com.recall.app` (the app signs in with the web client ID; these
      clients only vouch for the certificate). Google is the only sign-in on
      Android, so a missing one fails every sign-in with `DEVELOPER_ERROR`:
  - **Play app signing key**: Play Console → Test and release → App integrity
    → App signing → *App signing key certificate* SHA-1. Play re-signs the
    bundle with this key, so every install from Play (production and testing
    tracks) carries it. Registering only the EAS key breaks every Play user.
  - **EAS upload key**: `eas credentials --platform android` → production
    keystore SHA-1 (Play lists it as *Upload key certificate*). Covers preview
    and other builds installed outside Play.
  - **Debug key**: `./scripts/android-debug-sha1.sh`, for local dev builds only.
- [ ] Old deployments: unset `GOOGLE_CLIENT_SECRET` and `OAUTH_TOKEN_ENCRYPTION_KEY`
      (`fly secrets unset ...`); Calendar/Gmail were removed in migration `0106`

---

## 7. Landing & support

- [ ] Landing page live
- [ ] Support URL for store listings
- [ ] `SUPPORT_EMAIL` (Fly secret) set to `support@recall.com`, a mailbox you read. The privacy
      policy, terms and account-deletion pages show it as the contact; production boot logs a
      warning while it is empty
- [ ] `EXPO_PUBLIC_SUPPORT_EMAIL` (EAS environment variable) set to `support@recall.com` too.
      Settings → Help's Contact support, Report a problem and Send feedback email it; a build
      without it hides those rows and says support is not set up
- [ ] Privacy policy + terms URLs for both stores: `https://<api-host>/legal/privacy` and
      `https://<api-host>/legal/terms`
- [ ] Play Console → App content → Data safety → **Delete account URL**:
      `https://<api-host>/legal/delete-account` (public, no sign-in: deleting in the app,
      asking by email from the account's address, what is deleted and what is kept for how long)
- [ ] Owner review of the legal copy in `apps/api/app/content/` (`privacy_policy.py`,
      `terms.py`, `account_deletion.py`); bump `LEGAL_EFFECTIVE_DATE` in `legal.py` with any
      change. App Store App Privacy and Play Data safety answers must match it, including
      third-party AI (OpenRouter and the model providers, OpenAI for voice, Mathpix, Tavily
      and its public-search backup)
- [ ] Every account agrees once, before anything goes to outside AI services
      (`users.ai_data_consent_at`, migration `0112`). On the phone it is recorded with
      the sign-in: the sign-in page's line under its buttons (`login.consent_line`, "By
      continuing, you agree to the Terms and Privacy Policy, and that your chats and voice
      are processed by third-party AI providers.") with the Terms and Privacy links, and
      every sign-in sends `ai_data_consent: true`. An account without it (from before,
      withdrawn in Data controls, or a client that sends no flag: an older phone, web
      slice 1) is asked on the consent screen (phone `/consent`, the web's own) and agrees
      with `PATCH /auth/me`. Change that line, the consent screen and the policy together.
      The server refuses chat, speech and scan reads until then (`consent_required`)

---

## 8. Observability and email

- [ ] `SENTRY_DSN` on the API; mobile: `EXPO_PUBLIC_SENTRY_DSN` plus the upload
      variables in [§5](#5-mobile-eas)
- [ ] External uptime on the API's `/health/dependencies`, alerting on anything
      but 200. It answers 503 when Postgres or Redis is down, which sign-in, chat
      and quota all need. (`/health/ready`, Fly's routing check, answers 200 with
      `"redis": "degraded"` on purpose so a Redis blip does not drain the fleet.)
      `scripts/qa-smoke.sh --live` checks both.
- [ ] Alert on the worker's `worker-health` check (Fly metrics / Grafana). A
      failing check never restarts a Machine; the worker exits by itself (and
      `[[restart]]` brings it back) only when its jobs loop or a scheduler dies.
- [ ] Email (Resend). `EMAIL_ENABLED` and `EMAIL_REMINDERS_SCHEDULER_ENABLED`
      default to on. Set `RESEND_API_KEY` and `EMAIL_FROM` (an address on a
      domain verified in Resend) for welcome, receipt and to-do reminder emails.
      Without a key outside development and test nothing is sent: each send
      reports "not sent", the reminder scheduler does not start, both processes
      log `EMAIL_ENABLED=true but RESEND_API_KEY is not set` at boot, and
      `/auth/me` returns `email_reminders_available: false` so the app hides the
      email-reminder switch. To launch without email, set `EMAIL_ENABLED=false`.

---

## Verification commands

```bash
# Static checks (migration file, env template)
./scripts/qa-smoke.sh

# Against running local or deployed API
API_URL=https://your-api.fly.dev ./scripts/qa-smoke.sh --live

# Full provisioning report
./scripts/verify-production.sh
API_URL=https://your-api.fly.dev ./scripts/verify-production.sh --live
```

---

## Load and abuse limits

Defaults are sized for one shared-CPU `app` machine. Override with Fly secrets
or `[env]` only when you have a measured reason.

**Memory:** the API warms `SYMPY_MAX_WORKERS` (3) SymPy workers at boot, each
its own process. Measured PSS: the API about 270 MB at boot and 400 MB under
load; each worker 90–150 MB (150 once a chemistry fence loads RDKit). That is
550–850 MB, more than a 512 MB machine without swap, so `fly.toml` gives the
`app` machine 1 GB. On 512 MB, run `SYMPY_MAX_WORKERS=1` and accept that a
second maths turn inside the 2 s slot wait gets an unverified answer.
Documents parse and PDF pages render in their own processes
(`DOCUMENT_POOL_WORKERS`, 2), each about 70 MB, started on a machine's first
document and killed at the parse timeout; the `worker` machine runs no more
index jobs at once than it has of them.

| Setting | Default | What it protects |
|---------|---------|------------------|
| `MAX_REQUEST_BODY_BYTES` | `1048576` (1 MiB) | Every HTTP body. A declared `Content-Length` over the cap gets 413 before a byte is read; a chunked body is cut off one chunk past it. `0` disables. |
| `MAX_UPLOAD_REQUEST_BODY_BYTES` | `12582912` (12 MiB) | Photo/audio routes only: `/speech/transcribe`, `/{math,physics,chemistry}/scan/read`, `/attachments/{id}/upload`. Each route still checks its exact limit. |
| `ATTACHMENT_OCR_MAX_PAGE_PIXELS` | `4000000` | Pixel budget per rendered PDF page (scanned-PDF OCR, chat path and index job). The page size comes from the file: a 435-byte PDF with one 14400x14400 pt page peaked at 5.1 GB RSS before; now 259 MB. A letter page at the default 1.5x scale (~1.1 MP) is unaffected. |
| `ATTACHMENT_IMAGE_MAX_DECODE_PIXELS` | `16000000` | Largest decode for a gallery thumbnail (`GET /attachments/{id}/file?w=`), which now runs off the event loop. JPEG decodes at a reduced scale first, so phone photos work; a lossless image past the budget gets 422. A 505 KiB 13000x13000 PNG used to add ~650 MB RSS and block the loop 1.4s. `0` disables. |
| `JOBS_STREAM_MAX_LEN` | `50000` | Hard ceiling on the `recall:jobs` Redis Stream, applied on every `XADD`. The worker trims only entries that were delivered and acked, so the ceiling bites only when no worker has read for a long time; past it the oldest jobs are dropped, and the queue metrics warn at 90%. `0` disables. |
| uvicorn `--ws-max-size` (in `fly.toml` and `apps/api/Dockerfile`) | `1048576` (1 MiB) | Largest WebSocket frame (uvicorn default 16 MiB). A chat frame is at most ~130 KB. Change both files together. |
| WebSocket frame budget (`modules/chat/ws_limits.py`) | 120 frames/min per socket | Every frame after auth counts, including pings, cancels and invalid JSON (only message/regenerate were limited). A ping is answered with a pong; the phone pings once per socket and when a send goes unanswered. Over budget the server sends `{"code": "rate_limited"}` and closes with 1008; a reply in progress is still saved. |
| `WS_MAX_SOCKETS_PER_USER` | `5` | Open chat WebSockets per user on one machine (the phone holds one per open chat screen, and closes it in the background). Past it a new socket is closed with code 4429 and the phone sends over SSE instead. Counted in-process, so with N `app` machines a user can hold up to N×5. `0` disables. |
| `WS_IDLE_TIMEOUT_SECONDS` | `300` | A chat socket that sends no frame between turns for this long is closed with code 4408 (never during a turn). The phone opens a new socket when the user starts to write (keyboard up, first character) or on its next send, with no error shown; it never pings to keep an idle socket open. Sockets used to stay open indefinitely, so idle authenticated sockets could fill Fly's `hard_limit` of 200 per machine. `0` disables. |
| `WS_AUTH_TIMEOUT_SECONDS` | `10` | A new chat socket that has not sent its auth frame by then gets an `Auth timeout` error and is closed, so a connect that never authenticates cannot hold a socket open. |
| `R2_CONNECT_TIMEOUT_SECONDS` / `R2_READ_TIMEOUT_SECONDS` / `R2_MAX_ATTEMPTS` | `5` / `20` / `3` | boto3 calls to R2 (attachment reads on the chat path, deletes, sweeps). botocore's defaults were 60s + 60s with 5 attempts, each holding a default-executor thread (5 on one CPU). Retries use botocore's `standard` mode (jittered backoff). |
| `GOOGLE_AUTH_TIMEOUT_SECONDS` | `10` | Google cert fetch during sign-in (google-auth defaulted to 120s). A failed or slow fetch answers 503 + `Retry-After`, not 500 or 401. |
| Link preview (`modules/link_preview/service.py`) | 8s per fetch, 3 open per user, 20/min | `fetch_safely` takes an overall deadline (DNS, every redirect hop, the body): a server dripping one byte per read used to hold a request open for minutes. A fourth uncached preview while three are open answers 429 + `Retry-After` (Redis sorted set; a crashed fetch ages out after 30s). |
| `DB_CONNECT_TIMEOUT_SECONDS` / `DB_COMMAND_TIMEOUT_SECONDS` | `10` / `120` | asyncpg connect (default was 60s) and every statement (default was unbounded), the idle ping included (`DB_IDLE_PING_SECONDS` below), so a half-open pooled connection can no longer hang a request. Client-side, so it works through Neon's pooler. Generous because account delete is one cascading `DELETE`. Migrations are not affected. A pool, connect or statement timeout, or a dropped connection, now answers `503` + `Retry-After: 5` instead of a bare 500. |
| `DB_IDLE_PING_SECONDS` | `10` | A pooled Postgres connection idle this long is pinged on checkout: one simple `SELECT 1`, outside any transaction, so PgBouncer's transaction mode is fine with it. One used more recently is trusted, and one the server already closed (Neon suspend, a restart) is replaced without a round trip (`core/pool_liveness.py`). This replaced `pool_pre_ping`, which pinged on every checkout with three round trips (BEGIN, `;`, ROLLBACK: about 36 ms to Neon) before each session's first query. A connection that died within the window and that asyncpg has not yet seen close fails its first statement, and the pool recycles every older connection. A chat turn's reads, the save of its message and the save of its reply then run once more on a new connection (`pool_liveness.run_unit`, only when none of their statements had succeeded, so nothing is written twice). Any other request answers `503` + `Retry-After`, which the phone does not retry by itself: the user sees the error and tries again. `0` pings every checkout again. |
| `DAILY_DOCUMENT_LIMIT` / `_PLUS` / `_PRO` | `10` / `50` / `100` | Document (PDF, Word, text) uploads per user per UTC day, reserved at presign like images (`DAILY_IMAGE_LIMIT*`). Each is read and parsed on the API machine; a turn reads its files two at a time and drops a document's bytes once its excerpt is taken. |
| `CHAT_HISTORY_RAG_SEARCH_WINDOW` / `ATTACHMENT_RAG_SEARCH_WINDOW` | `2000` / `2000` | Chunks one recall search ranks: the user's (or the chat's) newest. Exact distances over a bounded set; older chunks stay with their chat. |
| `ANALYTICS_EVENT_RETENTION_DAYS` | `90` | Product events older than this are counted into `product_event_daily` and deleted by an hourly worker cycle (`ANALYTICS_RETENTION_DELETE_BATCH` 5,000 rows a statement, `ANALYTICS_RETENTION_MAX_DELETES_PER_CYCLE` 200,000 a run). `0` keeps them. |
| `JOB_TIMEOUT_SECONDS` | `900` | Deadline for one attempt of one background job. An attempt that runs out goes to the DLQ without retry. Any other failure retries later (15 s, 1 min, 4 min, 16 min, 30 min, ±20%) and goes to the DLQ after the sixth attempt. An entry delivered more than 5 times without an ack (it keeps killing the worker) also goes to the DLQ on reclaim. |

**Deploys and in-flight replies.** On SIGINT/SIGTERM the API stops every chat
turn still running the way the user's Stop does, before uvicorn's graceful wait
(`core/shutdown.py` chains uvicorn's signal handlers; uvicorn itself runs the
app's shutdown only after that wait). Each partial reply is saved (`completion:
"interrupted"`) and its chat's prepare lock and finalize marker are released in
a second or two, well inside `--timeout-graceful-shutdown` (30s) and Fly's
`kill_timeout` (45s). A turn sent during the stop is refused with "The server is
restarting" (`user_message_saved: false`, so the phone offers Retry). WebSockets
close with 1012; the phone reconnects to the new machine and reloads the chat
to pick up the saved reply. If a machine dies without the signal (OOM, host
failure), the prepare lock (`chatprep:{chat}`, TTL 30s, refreshed every 10s)
and the finalize marker (`chatfinal:{chat}`, TTL 30s) expire on their own: the
chat answers `busy` for at most 30 seconds.

Readiness answers inside Fly's 5s check timeout: `/health/ready` gives Postgres 3s
(then 503) and Redis 1s (then `"redis": "degraded"`, still 200); the worker's
probe gives Redis 3s. A stalled Redis used to time out readiness on every
machine at once. `/health/dependencies`, the phone's connection check, asks
both at once under the same limits and answers 503 when either fails. Each
process keeps that answer 5s and runs one probe at a time, so however many
phones ask, a machine probes Postgres and Redis at most once per 5s.

### Spend and daily tokens

**`DAILY_GLOBAL_SPEND_USD`** is a kill-switch on estimated provider dollars per
UTC day (Redis `spend_musd:<date>`, `core/spend_counter.py`). What adds to it:

- a chat turn: catalog price x its tokens, at finalize (`modules/chat/turn_settle.py`);
- every other model call, priced from its tokens by the gateway that makes it
  (`gateways/llm_spend.py`): memory extraction and consolidation, titles,
  compression, follow-up questions, attachment OCR, embeddings,
  the reference resolver, maths extraction;
- a fixed price per call for images, photo lookup, scan reads, voice input and
  read-aloud (`services/quota/spend.py`);
- live talk by time: the reserved minutes at mint, settled at
  `POST /speech/live/end` ([§4b](#live-talk-minutes)).

Once the day's total reaches the cap, until 00:00 UTC:

- a new chat message or regenerate is refused before any model call. Both
  transports send `{"type": "error", "message": "Recall is at capacity for
  today, so new messages are paused for everyone. Try again after midnight
  UTC."}`. It has no `quota_exceeded` code, so the phone shows that text and
  not its upgrade prompt (the user's own allowance is not used up);
- image generation, photo lookup, voice, live talk and scan reads answer 429
  "… temporarily unavailable";
- background model jobs, the tool loop and follow-up questions are skipped.

A Redis error counts as over the cap (fail closed). Known gap: the tool rounds
of a turn that ends in a generated image are not charged (the image is).

**Daily tokens.** A turn reserves its estimate (the message plus
`MAX_OUTPUT_TOKENS`, x the model's quota multiplier) before it runs, or
whatever is left of the day when less is, and finalize settles to the actual
usage; a failed or cancelled turn gives the reservation back. Turns in
different chats share that one remaining budget, so opening many chats at once
cannot multiply the day's allowance. A turn that starts is not cut short to
fit: past the limit its extra tokens are forfeit (the counter is clipped), so
one turn is the most a user can go over. While a turn runs, the usage shown in
Settings includes its reservation.

**Scanned PDFs.** A PDF with no text layer is read with up to
`ATTACHMENT_OCR_INDEX_MAX_PAGES` vision calls by the index job, which first
takes one of the owner's daily image-upload slots (`DAILY_IMAGE_LIMIT*`). At
the cap the file stays attached but is not searchable that day; a PDF read
from its text layer gets the slot back.

---

## Cost telemetry dashboard queries

Each finalized chat turn logs `turn_cost … est_cost_usd=…` and accumulates
`usage_daily.est_cost_usd` from catalog prices × **raw** input/output tokens
(not quota-weighted). Apply migration `0061_usage_daily_est_cost_usd` before
relying on the column. It holds chat turns only: background model calls,
images, voice and live talk count on the Redis spend counter
([Spend and daily tokens](#spend-and-daily-tokens)), not here.

**Spend for one user in the current UTC month:**

```sql
SELECT
  user_id,
  SUM(est_cost_usd) AS est_cost_usd,
  SUM(input_tokens + output_tokens) AS weighted_tokens
FROM usage_daily
WHERE user_id = :user_id
  AND date >= date_trunc('month', timezone('UTC', now()))::date
GROUP BY user_id;
```

**Top spenders yesterday (UTC):**

```sql
SELECT user_id, est_cost_usd, input_tokens, output_tokens
FROM usage_daily
WHERE date = (timezone('UTC', now())::date - 1)
ORDER BY est_cost_usd DESC
LIMIT 50;
```

**Daily platform spend (last 14 days):**

```sql
SELECT date, SUM(est_cost_usd) AS est_cost_usd
FROM usage_daily
WHERE date >= (timezone('UTC', now())::date - 14)
GROUP BY date
ORDER BY date;
```

Note: `input_tokens` / `output_tokens` on `usage_daily` are **quota-weighted**;
`est_cost_usd` is independent of the quota multiplier. Compare log lines
(`turn_cost`) to catalog prices when validating the 3.5× R1 weight.

---

## Owner actions (you — not code)

These cannot be finished in a PR. Track them in the app under Lists → **Launch**
(created for the local Dev User), or follow [`docs/PRODUCTION.md`](./docs/PRODUCTION.md).

0. Move every account in §0 to its paid plan, with spending limits
1. Install `flyctl` + `fly auth login`
2. Confirm Neon `DATABASE_URL` + `uv run alembic current` matches `uv run alembic heads`
3. Confirm Upstash `REDIS_URL` (`rediss://`) from the Fly region
4. Cloudflare R2 bucket + Fly secrets: `STORAGE_BACKEND=r2` + `R2_*`
5. Remaining Fly secrets (JWT, OpenRouter, Google, CORS, OAuth encryption key, RevenueCat,
   `ENVIRONMENT=production`, `DEV_AUTH_ENABLED=false`, `MOCK_LLM_ENABLED=false`)
6. `fly scale count app=1 worker=1` → `fly deploy` → `GET /health/ready`
7. EAS production builds (iOS + Android) with `EXPO_PUBLIC_API_URL=https://<api>`
8. On-device QA — [`docs/QA_MATRIX.md`](./docs/QA_MATRIX.md)
9. Google OAuth consent screen published (sign-in only)
10. Landing page + support URL + privacy/terms for store listings
11. Optional: `SENTRY_DSN` on API + mobile EAS secrets

---

## Launch blockers (from FEATURES.md)

1. Cost guards (speech, Tavily, R1 weight) — done in code
2. Provision Neon, Redis, R2, Fly, EAS
3. Landing page + support URL
4. On-device QA matrix (iOS + Android)
5. R2 production attachments end-to-end

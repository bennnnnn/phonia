# Recall

Personal AI mobile chat that remembers who you are, what you prefer, and what you're working on.

**Stack:** Expo React Native · FastAPI · Neon Postgres · Upstash Redis · LiteLLM

## One-time setup (no Docker)

From the repo root (where this README lives):

```bash
./scripts/dev.sh setup
```

### 1. Neon (Postgres)

1. Create a free project at [neon.tech](https://neon.tech)
2. Copy the connection string
3. Convert to async SQLAlchemy format in `apps/api/.env`:

```bash
DATABASE_URL=postgresql+asyncpg://user:pass@ep-xxx.region.aws.neon.tech/neondb?sslmode=require
```

### 2. Upstash (Redis)

1. Create a free Redis database at [upstash.com](https://upstash.com)
2. Copy the **Redis URL** (starts with `rediss://`) into `apps/api/.env`:

```bash
REDIS_URL=rediss://default:xxx@xxx.upstash.io:6379
```

### 3. Migrate

```bash
./scripts/dev.sh migrate
```

## Start developing

**Backend:**
```bash
./scripts/dev.sh api          # http://localhost:8000/health
./scripts/dev.sh watch-errors # same API, 4xx/5xx highlighted (+ tmp/http-errors.log)
```

**Mobile:**

| Where you test | Start commands | `EXPO_PUBLIC_API_URL` |
|----------------|----------------|------------------------|
| **iOS Simulator (default here)** | `./scripts/dev.sh api` then `./scripts/dev.sh mobile-sim` | `http://127.0.0.1:8000` (set automatically) |
| Physical device + Expo Go | `./scripts/dev.sh api` then `./scripts/set-lan-ip.sh` then `./scripts/dev.sh mobile` | `http://<your-lan-ip>:8000` |

```bash
./scripts/dev.sh api          # backend → http://localhost:8000/health
./scripts/dev.sh mobile-sim   # iOS Simulator + Expo Go (not QR on a real phone)
./scripts/dev.sh mobile       # LAN + QR for a physical device on same Wi‑Fi
./scripts/dev.sh kill-metro   # stop Metro if ports are stuck
```

**Mobile app notes:** use **Continue as Dev User** in Expo Go (Google Sign-In needs a dev build). Theme: **Settings → Personalization → Appearance** (System / Light / Dark). After pulling mobile changes, restart Expo with `--clear` if the bundle looks stale.

On a physical device only, run `./scripts/set-lan-ip.sh` before Expo — do **not** use the LAN IP in the simulator (use `127.0.0.1` instead).

## Dev without Google or API keys

1. Start backend
2. In the app → **Continue as Dev User**
3. Mock LLM replies work until you add `OPENROUTER_API_KEY` ([openrouter.ai/keys](https://openrouter.ai/keys))

## Optional: Docker

Only if you want local Postgres/Redis instead of Neon/Upstash:

```bash
./scripts/dev.sh infra
# then set DATABASE_URL=postgresql+asyncpg://postgres:dev@localhost:5432/recall
# and REDIS_URL=redis://localhost:6379
```

The compose file uses `pgvector/pgvector:pg16` so migrations that need the
`vector` extension (0027/0033) run locally.

## Production deployment (Fly.io)

The API needs a long-running process (WebSockets + background jobs), so deploy to a
host that keeps the process alive — not a serverless function platform. A Dockerfile
+ `fly.toml` are included with **two Fly processes**: `app` (HTTP/WebSocket,
`PROCESS_ROLE=api`) and `worker` (Redis-stream jobs + schedulers,
`PROCESS_ROLE=worker`). Scale them independently (`fly scale count app=1 worker=1`).

1. **Provision:** `fly launch` (uses `apps/api/Dockerfile`), or point an
   existing Fly app at this directory. Provision a Fly Postgres cluster **with
   pgvector** (`fly pg create --image-ref flyio/postgres-flex:16` then
   `CREATE EXTENSION vector`), or keep using Neon.
2. **Set secrets** — copy `apps/api/.env.production.example` → `.env.production`,
   run `./scripts/generate-prod-secrets.sh`, `./scripts/validate-prod-env.sh`, then
   `./scripts/fly-secrets-import.sh`. Every key is enforced at startup by
   `validate_production_settings`:
   - `ENVIRONMENT=production`
   - `DEV_AUTH_ENABLED=false` · `MOCK_LLM_ENABLED=false`
   - `JWT_SECRET=` (≥32 random chars)
   - `DATABASE_URL=` · `REDIS_URL=`
   - `GOOGLE_CLIENT_ID=` (Google Sign-In only)
   - `OPENROUTER_API_KEY=`
   - `CORS_ORIGINS=https://app.recall.app` (explicit; never `*` in prod)
   - `REVENUECAT_WEBHOOK_AUTH=` · `REVENUECAT_SECRET_KEY=`
   - `STORAGE_BACKEND=r2` · `R2_ACCOUNT_ID` · `R2_ACCESS_KEY_ID` ·
     `R2_SECRET_ACCESS_KEY` · `R2_BUCKET`
   - `TAVILY_API_KEY=` (if web search is on)
3. **Migrate + deploy:** `./scripts/deploy-api.sh` (or `fly deploy`) runs
   `alembic upgrade head` first (see `fly.toml`). Confirm `uv run alembic current`
   matches `uv run alembic heads`.
4. **Health:** `GET /health` is liveness. `GET /health/ready` is Postgres
   (Redis may be `degraded` without 503 — do not drain the fleet on an Upstash blip).
   `GET /health/dependencies` is 503 when Postgres or Redis is down; the phone's
   connection check reads it, Fly's checks do not.
5. **RevenueCat:** set the webhook URL to `https://<api>/webhooks/revenuecat`
   with the `Authorization` header = your `REVENUECAT_WEBHOOK_AUTH`.
6. **Process split:** `fly.toml` runs migrations + uvicorn on the `app` process and
   `python -m app.worker_main` on `worker`. Local dev defaults to `PROCESS_ROLE=all`
   (both in one process). Set `PROCESS_ROLE=api` or `worker` when splitting locally.

### Mobile production build

```bash
cd apps/mobile
# set EXPO_PUBLIC_API_URL=https://<api-host> in apps/mobile/.env (or EAS secrets)
eas build --platform ios --profile production
eas build --platform android --profile production
```

Native features require a dev/production build, **not** Expo Go: Google
Sign-In, the HTML/chart preview WebView, push notifications, and RevenueCat
purchases. Configure your EAS `projectId`.

## Launch readiness

- **On-device QA:** [`docs/QA_MATRIX.md`](docs/QA_MATRIX.md)
- **Production provisioning:** [`docs/PRODUCTION.md`](docs/PRODUCTION.md)
- **Rollback:** [`docs/ROLLBACK.md`](docs/ROLLBACK.md)
- **Engineering map:** [`CLAUDE.md`](CLAUDE.md) · product [`FEATURES.md`](FEATURES.md) · [`SECURITY.md`](SECURITY.md)
- **Subject pipelines:** [`docs/math.md`](docs/math.md) · [`docs/chemistry.md`](docs/chemistry.md)
- **Automated smoke:** `./scripts/qa-smoke.sh` (add `--live` when API is running)
- **Local gate:** `./scripts/dev.sh check`
- **Production verify:** `./scripts/verify-production.sh`

## Remote

https://github.com/bennnnnn/recall

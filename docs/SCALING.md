# Scaling the API

What it takes to run more than one `app` machine and more than one `worker` on Fly
(`fly.toml`), what already works across machines, what is per machine on purpose, and
the changes to make, in order, when traffic needs them. Load limits and their defaults
are in [PRODUCTION.md](./PRODUCTION.md#load-and-abuse-limits); where code lives is
[ARCHITECTURE.md](./ARCHITECTURE.md).

Today: one `app` machine (shared CPU, 1 GB, one uvicorn process, one event loop) and one
`worker` (512 MB). Both talk to the same Neon Postgres (through its `-pooler` host),
Upstash Redis and R2. Scale out by adding machines (`fly scale count app=N worker=M`),
not uvicorn `--workers`: every per-process item below would multiply inside one machine
(three more SymPy processes per uvicorn worker, a socket cap per process, one more
signal hook) and the 1 GB budget is sized for one.

## Already safe on N app machines and M workers

Everything a turn or a request must agree on across machines lives in Redis or Postgres.

| What | Where it lives | Notes |
|---|---|---|
| Sign-in and every request's token check | JWT + Redis (`revoked:jti:`, `revoked:sid:`, `revoked_since:`, read with the user's `usergen:` in one MGET) | `core/access_tokens.py`; account delete revokes every session as soon as its rows commit (its worker sweep revokes them again if that failed), so a cached user row elsewhere is not served to a deleted account |
| Rate limits: REST, Google and Apple sign-in (10/min per verified identity, with a 600/min per-IP backstop checked before the token is verified, as refresh's; the REST limit skips it; dev login stays 30/min per IP), token refresh (10/min per account, read from the refresh token, with a 600/min per-IP backstop so a carrier NAT address is not one bucket; the REST limit skips it), chat messages (30/min across WS and SSE), WS connect and handshake, voice, scan reads, link previews | Redis counters (`core/rate_limit.py`, `core/rest_rate_limit.py`, `core/chat_rate_limit.py`, `modules/account/refresh_limit.py`, `modules/account/signin_limit.py`) | Fail closed when Redis is down. Per-IP limits need `TRUST_X_FORWARDED_FOR=true` behind Fly |
| Daily tokens, image, voice, search and live-talk allowances, Tavily budget | Redis (`services/quota/`) | One budget per user whichever machine serves the turn |
| Global daily spend cap | Redis `spend_musd:<date>` (`core/spend_counter.py`) | Every machine adds to and reads the same counter |
| One turn per chat at a time | Redis lock `chatprep:{chat}` (TTL 30 s, refreshed every 10 s) | A second send on another machine gets `busy` |
| "Wait for the last reply to be saved" | Redis marker `chatfinal:{chat}` (`modules/chat/finalize_registry.py`) | Same machine awaits the task; another machine polls the marker (50 ms, up to 10 s) |
| Memory, home, link-preview, web-search, query-embedding and follow-up caches; model health | Redis, keyed by user or query, with TTLs | Where a write must invalidate one, it bumps a Redis generation key (`core/cache_generation.py`), so every machine sees it |
| Memory writes | Redis lock per user (`modules/memory/locks.py`) plus Postgres row locks (user row first) | A busy lock re-enqueues the job with a backoff |
| Background jobs | One Redis Stream `recall:jobs`, consumer group `workers` (`core/jobs/`) | Each worker has its own consumer name; entries are leased and reclaimed after 60 s idle; `jobdone:<key>` dedupe keeps a job from running twice; a failure retries later from `recall:jobs:delayed` (six attempts over about 50 minutes) before the DLQ; poison entries and timeouts go to the DLQ; the worker trims only delivered, acked entries, and `JOBS_STREAM_MAX_LEN` drops the oldest only when no worker reads for long (the queue metrics warn first) |
| Periodic schedulers (push, reminder email, orphan reaper, billing reconcile, retention) | Every worker runs every loop; a Redis lock per cycle lets one run it (`background/periodic.py`) | Adding workers adds lock attempts, not duplicate sends |
| Files | R2 presigned URLs | Production refuses local storage (`validate_production_settings`) |
| Deploys | Blue-green, then SIGINT: in-flight turns stop and save, locks release | Two workers overlap for a moment; leases, dedupe and scheduler locks cover it |

## Per machine on purpose, and what that means

| State | Where | Effect with N app machines |
|---|---|---|
| Last loaded user row, 5 min, checked against Redis | `core/user_cache.py` | Every committed write to a user row (plan change from the RevenueCat webhook, a settings or memory change, consent) stores a new `usergen:{user}`; every request and chat frame reads it with its token check and loads the row again when its copy is older. A write whose generation Redis refuses answers 503 (it is saved; making it again publishes, and the phone does not retry a 503 by itself); a missing key starts a fresh generation, never one an old copy was stored under. A SQL edit to `users` needs `DEL usergen:<id>` (PRODUCTION.md §2); otherwise, and after a machine dies between a commit and its publish, a copy can lag for up to 5 min. Consent is re-read from the row before a turn is refused. |
| A chat created here, 120 s | `modules/conversation/chats_repository.py` (`_chat_cache`) | The send right after "new chat" skips a query. If the chat is deleted through another machine, this machine still starts a turn for it for up to 120 s, which then fails when it saves. |
| Open chat sockets per user (5) | `modules/chat/ws_limits.py` | A user can hold 5 per machine, N×5 in all. The frame budget and idle timeout are per socket, so they are exact. |
| SymPy process pool (3 workers, 2 s slot wait, one slot per user) | `core/sympy_executor.py` | Capacity grows with machines (3 per machine); a maths turn that waits more than 2 s for a slot on its machine is answered unverified. A user holds at most one slot per machine, so one account's pathological expressions cannot take all three. A worker is killed only when a solve overruns; a Stop lets the solve finish first. Every turn also reads its message there once (`core/readings.py`, a few milliseconds; `subject_read_timeout_seconds` 3 s, after which the turn reads no subject and the model answers unverified). |
| In-flight turns, their Stop, the finalize task that saves the reply, the post-turn enqueue, follow-up questions | `modules/chat/` background tasks (`core/background_tasks.py`) | A machine that dies without the stop signal (OOM, host loss) loses the replies it had not saved yet; its `chatprep` lock and `chatfinal` marker expire within 30 s. |
| Spend record and invalid-output counter after each model call | `gateways/llm_spend.py`, `gateways/structured_completion.py` | Written on a background task; lost only if the machine dies in that instant. |
| The connection check's answer (Postgres and Redis both answer), 5 s | `routers/health.py` (`DependencyCheck`) | Each machine probes them at most once per 5 s however many phones ask `/health/dependencies`, so a phone sees an outage, or its end, up to 5 s late. Each machine answers for itself. |
| Outbound HTTP pools, Google request session, Apple signing keys (1 h), storage client | `gateways/` | Each machine warms its own; no shared state. |
| Pure-function LRU caches (maths and physics readers, routing) | `modules/*` | Inputs only; any machine computes the same answer. The readings a turn read in the pool are kept for that turn only (`core/readings.py`). |
| Jobs a worker runs at once (`JOBS_WORKER_CONCURRENCY` 8) and per-type caps (`memory_history_scan` 3) | `core/jobs/worker.py`, `background/handlers.py` | Caps are per worker: M workers run 8×M jobs and 3×M history scans at once. |

## Resource budgets per process

- **Postgres connections.** Every process has one SQLAlchemy pool of `DB_POOL_SIZE` 20 +
  `DB_MAX_OVERFLOW` 10 = up to 30 (`core/db.py`), the worker included, which needs far
  fewer (8 jobs plus five schedulers). A connection is pinged only after 10 s idle
  (`core/pool_liveness.py`), not on every checkout, and no session is held open across a slow
  call (`tests/architecture/test_session_awaits.py`). (N + M) × 30 client connections must fit Neon's
  pooler; the real limit is the compute's server pool (about 0.9 × its `max_connections`),
  which queues transactions beyond it. Set a smaller `DB_POOL_SIZE` on the worker (inline in
  its `fly.toml` process command, as `PROCESS_ROLE` is) before adding many.
- **Redis connections.** Two clients per process (`core/redis.py`: request path, and the
  jobs consumer with a longer socket timeout), each with redis-py's default unbounded
  pool: a burst opens a connection per concurrent command. Upstash limits concurrent
  connections per plan and bills per command.
- **Redis commands per request.** An authenticated REST request costs the rate-limit
  pipeline (INCR + EXPIRE) and one MGET for the token check. A finished chat turn
  enqueues up to seven jobs, one XADD each; the worker trims the stream on its own cadence.
- **CPU.** One event loop per machine on a shared CPU. SymPy and the maths, physics and
  chemistry readers run in the pool's processes: a turn reads its message there once and
  keeps the answers (`core/readings.py`, `modules/chat/turn_prep/reading.py`), and the
  test suite fails when production code reads a message or runs SymPy on the loop
  (`app/tests/loop_guard.py`). Documents parse and PDF pages render in their own
  killable processes (`core/document_executor.py`, 2 per machine). Blocking calls run on
  a small thread pool per kind, never the shared default executor (`core/blocking.py`:
  R2 8, images 2, sign-in 2, DuckDuckGo 2, which refuses rather than queues); the
  saturation report logs each pool's fill. Prompt building and the finalize passes' text
  work still run on the loop.
- **Memory.** About 270–400 MB for the API plus 90–150 MB per SymPy worker and about
  70 MB per document worker once one starts (PRODUCTION.md); hence 1 GB per `app`
  machine.

## Changes for scaling out, most useful first

Each is a change of behavior or of resource use, so none is made yet. The seam is where it
plugs in.

1. **Decide how Fly counts WebSockets** (owner, PRODUCTION.md §4): with
   `[http_service.concurrency] type = "requests"`, 200 open chat sockets may fill a machine.
   Seam: `fly.toml`. Do this first; it decides when a second `app` machine is needed.
2. **Bound Redis connections.** Give both clients a `max_connections` (a blocking pool)
   sized to Upstash's limit ÷ machines. Seam: `core/redis.py`.
3. **Size the Postgres pool per role** (smaller on workers) and per Neon compute, so
   (N + M) × pool stays under the server pool. Seam: `DB_POOL_SIZE` / `DB_MAX_OVERFLOW`
   (`core/settings/infrastructure.py`), set per process group.
4. **Share or invalidate the chat cache** once 120 s of a deleted chat on another machine
   matters: check a Redis generation per chat on read, as `core/user_cache.py` does for
   user rows (the `core/cache_generation.py` pattern). Seam:
   `modules/conversation/chats_repository.py` (`peek_recent_chat` / `forget_chat`).
5. **Count chat sockets per user in Redis** if N×5 is too many: an expiring counter or set
   per user, refreshed while the socket lives. Seam: `modules/chat/ws_limits.py`
   (`user_socket_slot`).
6. **Make the account-delete sweep independent of total size.** `purge_user_redis_keys`
   SCANs the whole keyspace and `purge_user_jobs` walks both job streams on every delete.
   Keep a per-user index of keys (or put the user id in a fixed prefix) and let the stream
   bound age job payloads out. Seams: `modules/account/lifecycle.py`,
   `core/jobs/admin.py`.
7. **Shard the billing reconcile.** It checks every paid user one by one (a RevenueCat call
   plus a 0.2 s gap: at most 18,000 users an hour, about half that with the call's own
   latency), so past that it no longer finishes within its hour. Split by user-id range
   across workers, or check only users without a recent webhook. Seam: `background/billing_reconcile_scheduler.py`.
8. **Separate job classes if one starves another.** All job types share one stream and
   worker slots; `max_running` limits a slow type per worker. A second stream (or a second
   consumer group) for slow jobs would keep titles and memory quick under a burst. Seams:
   `core/jobs/queue.py` (`JOBS_STREAM`, `register`), `core/jobs/worker.py`.
9. **Move the finalize passes off the event loop when measurements say so**: they are text
   processing over the reply, so the SymPy pool could take them as it takes the readers. Seams:
   `core/sympy_executor.py` (the bounded, injectable pool), `core/readings.py`,
   `modules/chat/finalize_passes.py`.
   A remote SymPy service would implement `BoundedSympyExecutor` and plug in through
   `set_sympy_executor`.
10. **Save replies durably** if losing an unsaved reply on a machine crash matters: hand the
    finalize to a job instead of an in-process task. Seams: `modules/chat/stream_pipeline.py`,
    `core/jobs/`.
11. **Raise the orphan reaper batches** if uploads outpace it: an hourly cycle runs
    batches of `ATTACHMENT_ORPHAN_REAP_LIMIT` (100) while they come back full, up to
    `ATTACHMENT_ORPHAN_REAP_BATCHES_PER_CYCLE` (20), so 2,000 rows an hour. Seam:
    `core/settings/attachments.py`.

Provider limits (OpenRouter, Tavily, Expo, Resend, RevenueCat) are per API key and do not
grow with machines; raise them with the provider.

## Data that grows with use

| Table | Kept | Read |
|---|---|---|
| `message_chunks` (chat-history recall) | The user's newest `CHAT_HISTORY_RAG_SEARCH_WINDOW` (2,000); older ones are deleted as a turn stores new ones (`chunks_repository.prune_beyond_window`) | A search ranks the user's newest `CHAT_HISTORY_RAG_SEARCH_WINDOW` (2,000) chunks exactly; no vector index (a global HNSW filters by user only after its scan and found nothing for most users) |
| `attachment_chunks` (document questions) | As long as the attachment | A search ranks the chat's newest `ATTACHMENT_RAG_SEARCH_WINDOW` (2,000) chunks exactly |
| `memories` | 150 active facts a user | Similarity is computed in SQL; no vector leaves Postgres |
| `chats` with no message | `ABANDONED_DRAFT_CHAT_HOURS` (168) | Never listed; the hourly data-retention cycle (`background/data_retention_scheduler.py`) deletes them in batches |
| `usage_daily` | `USAGE_DAILY_RETENTION_DAYS` (400) | Quota reads today's row; the same cycle deletes older ones |
| `product_events` | `ANALYTICS_EVENT_RETENTION_DAYS` (90) | An hourly worker cycle counts each older day into `product_event_daily` (events and distinct accounts per bucket, no user ids), then deletes it in batches |
| `messages` search | Kept | Substring match through a trigram index that leads with `user_id`; three characters at least; "has more" from one extra row, never a count |

# Production rollback

Use this runbook when a release passes deployment but causes production errors.
Rollback is an incident action, not a substitute for the pre-launch gate.

## Before every deploy

1. Merge to `main` and let API CI (and Mobile CI) pass on that commit. The
   Deploy workflow refuses any other branch and any commit whose CI has not
   passed ([PRODUCTION.md §4](PRODUCTION.md#deploying)).
2. Confirm `cd apps/api && uv run alembic current` (against production) matches
   `uv run alembic heads`, and read the migrations this deploy adds: each must
   follow [expand, then contract](#schema-changes-expand-then-contract).
3. Record the current Git SHA, Fly image reference, mobile build numbers, and any
   secret or `fly.toml` changes in the release notes. Deploys label the image
   `git-<sha>`, so `fly releases --image` shows which commit each release ran.
4. Keep the previous production environment file in secure storage. Never commit it.
5. Know the database restore window and that a restore was rehearsed
   ([PRODUCTION.md §1](PRODUCTION.md#backups-and-restore-owner-before-launch)).

## Schema changes: expand, then contract

The release command migrates before any Machine is replaced, blue-green keeps
the old release serving until the new one passes its checks, the old worker
keeps running jobs until it is stopped, and a rollback redeploys an older image
on the newer schema. So every schema change must work with the code before and
after it:

1. **Expand** (release N): add tables, nullable columns or columns with a
   default, new indexes (`CREATE INDEX CONCURRENTLY` in an `autocommit_block`
   on large tables). Code in release N may write both shapes and must not need
   the new one to exist yet in other processes.
2. **Migrate readers** (release N or N+1): code stops reading and writing the
   old column or table. Backfills run as their own migration or job.
3. **Contract** (a later release, once no deployed or rollback-candidate image
   reads the old shape): drop, rename or retype. In `upgrade()`, say why it is
   safe with a comment the CI guard looks for:
   `# expand-contract: release <sha/PR> stopped reading users.legacy_flag`.

Contracts waiting for a later release:

- `memories.embedding_json`, `message_chunks.embedding_json`,
  `attachment_chunks.embedding_json`: no longer read; new writes store NULL (the
  release that ranks memory in SQL, migration `0118`). Drop once no image that ranks
  memory from the JSON copy is a rollback candidate.
- `users.response_style`: no longer read, returned or accepted by `/auth/me` (the
  release that removed the account-wide reply length). Drop once that release is the
  oldest rollback candidate.

`app/tests/architecture/test_migration_safety.py` fails on a migration after
`0111` whose `upgrade()` drops, renames or retypes without that comment, and on
more than one alembic head. `0099` and `0106` dropped columns in the same
release as the code; those cannot be undone by redeploying an earlier image
(see below). Never rewrite a migration that has run in production.

Background jobs follow the same rule. A worker that has no handler for an entry's type
(the old worker during a blue-green deploy, or the restored one after a rollback) holds the
entry and looks again every 10 minutes for a day before dead-lettering it, so the release
that knows the type runs it. Add a job type in one release and enqueue it only after it is
deployed everywhere when possible. A new payload field is optional for one release: the
handler reads it with `payload.get(...)` and a default, so entries the previous release
queued still run, and only a later release may require it.

Every migration transaction has `lock_timeout = 5s` and `statement_timeout =
4min` (`alembic/env.py`). A migration that cannot get its lock fails the
release command and the old release keeps serving: rerun the deploy later. A
long data migration belongs in a job, not in one statement.

## API rollback

Fly rollback means redeploying a known-good image; it does not revert secrets,
configuration, or database data.

```bash
fly releases --app recall-api --image
# --skip-release-command: the database is already at the newer release's head,
# which the older image's alembic does not know ("Can't locate revision"), so
# its `alembic upgrade head` would fail the rollback.
fly deploy --app recall-api --image <known-good-image-reference> --skip-release-command
```

Before redeploying an image, check that it runs on the current schema: it must
not read a column or table a later migration dropped or renamed. With
expand/contract that holds for the previous release; it does not hold across
`0099` (learning tables) or `0106` (Google integration columns), so do not roll
back past either. The redeploy uses the blue-green strategy in the current
`fly.toml`, so the old image must pass the health checks before it takes
traffic. Leave the release command on only when the newer release added no
migration.

After redeploy:

```bash
API_URL=https://<api-host> ./scripts/verify-production.sh --live
fly status --app recall-api
fly logs --app recall-api
```

`verify-production.sh --live` fails unless API readiness reports Redis `ok`,
the worker answers its health check and `alembic current` on Fly equals the
repository's head; it lists anything it could not check. If configuration
changed, restore the prior reviewed `fly.toml` and secrets separately, then
deploy the known-good image again.

## Database migration failure

The Fly release command runs `alembic upgrade head` before new machines start. If it
fails, the application image does not replace the healthy release.

- `canceling statement due to lock timeout`: another query held the table. Find
  it (`SELECT pid, now() - xact_start, query FROM pg_stat_activity WHERE state
  <> 'idle' ORDER BY 2 DESC;`) and rerun the deploy when it is gone.
- Do not run an automatic downgrade against production data.
- Inspect the failed migration and database state.
- Prefer a forward fix that is compatible with the currently running application.
- Test the repair against a Neon branch of production (a branch from "now", or
  from a past timestamp to reproduce the state before the failure).
- Run `uv run alembic current` and `uv run alembic heads` after recovery.

If a migration completed but the new application is unhealthy, verify the prior image
is schema-compatible before redeploying it. Otherwise ship a forward-compatible fix.

## Restoring data

For lost or corrupted rows (a bad migration, a bad job, an operator mistake):

1. Note the last good time (UTC) from logs or the release list.
2. In Neon, create a branch from that point in time, inside the restore window.
3. Point a local API or `psql` at the branch and confirm the data is right.
4. Either copy the needed rows back into production, or, for a wider loss,
   restore the production branch to that time with Neon's restore (it keeps a
   backup branch of the state it replaced) or repoint `DATABASE_URL` at the
   restored branch (`fly secrets set`, which restarts the Machines). Writes after
   that time are lost; say so to affected users.
5. Run `alembic current` against the restored database: a restore to before a
   migration needs the matching image (or `alembic upgrade head`) next.

R2 attachments are not versioned: deleted objects do not come back with a
database restore ([PRODUCTION.md §3](PRODUCTION.md#3-object-storage-cloudflare-r2)).

## Worker and job recovery

Confirm the worker is present and healthy:

```bash
fly scale count app=1 worker=1 --app recall-api
fly ssh console --app recall-api --process-group worker -C 'curl -sf http://127.0.0.1:8001/health/ready'
```

The worker restarts itself: it exits with status 1 when its jobs consumer or a
scheduler dies, and Fly's `[[restart]] policy = "always"` starts it again. A
failing health check alone never restarts a Machine, so a worker that is up but
not ready (Redis unreachable: it keeps retrying) shows only in `fly checks list`
and the logs.

A failed job retries by itself for about 50 minutes before it is dead-lettered, and once
an hour the worker re-enqueues dead letters of types that are safe to run twice
(`storage_sweep`, `account_sweep_backstop`, `attachment_index`, `transactional_email`), each
at most three times.
Dead letters older than seven days are trimmed. Inspect the queue before replaying
anything else:

```bash
cd apps/api
uv run python ../../scripts/replay_dlq.py --list
```

Replay only after the failing handler or dependency is fixed. Do not repeatedly replay
poison jobs into the same failure.

## Mobile release recovery

A bad JavaScript update (EAS Update) is undone over the air: republish the previous
update group to the same channel from the EAS dashboard (Updates → `production`), or
run `eas update:republish --group <previous-group-id>`. Installed apps pick it up on
their next two launches, as with any update.

A bad native release must be replaced through App Store Connect and Play Console.

1. Stop the staged rollout or pause the release.
2. Keep the prior approved version available where the store allows it.
3. Build the fix from a reviewed commit with the production EAS profile.
4. Re-run the physical-device sections in `docs/QA_MATRIX.md`.
5. Submit an expedited review only when user impact justifies it.

Never rotate `JWT_SECRET` as a rollback shortcut; rotation signs every user out. Never
force a database downgrade solely to match a mobile version.

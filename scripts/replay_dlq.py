#!/usr/bin/env -S uv run python
"""Replay failed background jobs from the DLQ back onto the jobs stream.

Production ops tool. Reads up to `--count` entries from the `recall:jobs:dlq`
Redis Stream, re-enqueues each one's (type, payload) onto `recall:jobs`, and
deletes the replayed DLQ entries so they aren't processed twice. The worker
picks them up like any freshly enqueued job.

Usage (from apps/api):
    uv run python ../../scripts/replay_dlq.py [--count N] [--list]

Env: requires REDIS_URL (loaded from apps/api/.env via pydantic-settings).
"""

import argparse
import asyncio
import json
import os
import sys

# Ensure the api package is importable when run from the repo root.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "apps", "api"))

from app.core.config import Settings  # noqa: E402
from app.core import jobs  # noqa: E402
from app.core.redis import get_redis_client  # noqa: E402


async def main() -> int:
    parser = argparse.ArgumentParser(description="Replay Recall job DLQ entries.")
    parser.add_argument("--count", type=int, default=50, help="max entries to replay/list")
    parser.add_argument("--list", action="store_true", help="list DLQ entries without replaying")
    args = parser.parse_args()

    settings = Settings()
    redis = get_redis_client()
    try:
        if args.list:
            entries = await jobs.list_dlq(redis, count=args.count)
            if not entries:
                print("DLQ is empty.")
                return 0
            for e in entries:
                print(
                    json.dumps(
                        {
                            "id": e["id"],
                            "type": e["type"],
                            "failed_at": e["failed_at"],
                            "error": e["error"][:160],
                        },
                        ensure_ascii=False,
                    )
                )
            print(f"\n{len(entries)} entr{'y' if len(entries) == 1 else 'ies'} (showing up to {args.count}).")
            return 0

        replayed = await jobs.replay_dlq(redis, count=args.count, delete=True)
        print(f"Replayed {replayed} DLQ entr{'y' if replayed == 1 else 'ies'} back onto the jobs stream.")
        return 0
    finally:
        await redis.aclose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))

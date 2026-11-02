"""The background jobs worker: concurrency, stream bound, deadlines, health port."""

from pydantic import BaseModel


class WorkerSettings(BaseModel):
    # Max jobs one worker process runs at once; it keeps reading while a slot
    # is free, so a slow LLM job never holds back compress/topic/todo jobs.
    jobs_worker_concurrency: int = 8
    # Hard ceiling on the Redis jobs stream (entries). The soft 10k trim only
    # runs while nothing is pending; one entry left pending by a dead worker
    # used to disable trimming entirely. Past this, the oldest jobs are
    # dropped so Redis (quota, auth revocation, rate limits) stays healthy.
    # Never lower than the soft cap; 0 disables the ceiling.
    jobs_stream_max_len: int = 50_000
    # Deadline for one attempt of one background job. A batch is awaited as a
    # whole, so a hung handler used to stop the worker reading new jobs. An
    # attempt that runs this long goes to the DLQ (not retried). Generous: the
    # memory history scan reads 20 chats and resumes where it stopped.
    job_timeout_seconds: float = 900.0
    # Port of the worker's tiny /health/ready (deploy checks, uptime monitors;
    # Fly never restarts on a failing check, worker_main exits instead). 0
    # disables the worker health server (e.g. process_role=all dev).
    worker_health_port: int = 8001
    # Product events are kept this many days, then folded into per-day counts
    # (``product_event_daily``) and deleted: two rows a chat turn kept forever.
    analytics_event_retention_days: int = 90
    analytics_retention_interval_seconds: int = 3600
    # Rows deleted per statement, and per cycle, so a backlog drains in steps.
    analytics_retention_delete_batch: int = 5_000
    analytics_retention_max_deletes_per_cycle: int = 200_000
    # Hourly data retention: drafts never sent to, and daily usage rows past a year.
    data_retention_interval_seconds: int = 3600
    abandoned_draft_chat_hours: int = 168
    usage_daily_retention_days: int = 400
    data_retention_delete_batch: int = 1_000
    data_retention_max_deletes_per_cycle: int = 50_000

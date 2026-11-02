"""Durable background jobs on a Redis Stream.

Title generation, memory extraction, and history compression are enqueued to a
Redis Stream and processed by a consumer in the worker process (``worker_main``).
Because the stream is persisted in Redis, jobs survive a process restart, and a
crash mid-processing leaves the entry in the consumer group's pending list —
reclaimed via XAUTOCLAIM by a live worker. At-least-once. The worker trims only
entries that were delivered and acked; the stream's hard ceiling
(``jobs_stream_max_len``) drops the oldest only when no worker reads for long,
and the queue metrics warn before that.

``queue`` registers handlers, enqueues and bounds the stream, ``dedupe`` keeps
a logical job from running twice, ``delayed`` holds retries and entries of a type
this worker cannot run yet (``outcomes`` decides which), ``worker`` consumes,
``inflight`` runs the held entries under the concurrency limits and leases them,
``pending`` handles trimmed and poison entries, and ``admin`` holds queue metrics,
the DLQ (with an hourly replay of types safe to run twice) and the per-user purge.
Every submodule logs as ``app.core.jobs``.
"""

from app.core.jobs.admin import (
    list_dlq,
    purge_user_jobs,
    replay_dlq,
    report_queue_metrics,
)
from app.core.jobs.dedupe import job_done_key, unique_dedupe_key
from app.core.jobs.delayed import (
    LOCK_RETRY_ATTEMPTS,
    LOCK_RETRY_BACKOFF_S,
    enqueue_later,
    retry_delay_s,
    schedule_job,
)
from app.core.jobs.pending import MAX_JOB_DELIVERIES
from app.core.jobs.queue import (
    JOBS_DLQ_STREAM,
    JOBS_GROUP,
    JOBS_STREAM,
    JobDiscardError,
    JobSkipped,
    enqueue,
    register,
)
from app.core.jobs.worker import is_worker_alive, start_worker, stop_worker

__all__ = [
    "JOBS_DLQ_STREAM",
    "JOBS_GROUP",
    "JOBS_STREAM",
    "LOCK_RETRY_ATTEMPTS",
    "LOCK_RETRY_BACKOFF_S",
    "MAX_JOB_DELIVERIES",
    "JobDiscardError",
    "JobSkipped",
    "enqueue",
    "enqueue_later",
    "is_worker_alive",
    "job_done_key",
    "list_dlq",
    "purge_user_jobs",
    "register",
    "replay_dlq",
    "report_queue_metrics",
    "retry_delay_s",
    "schedule_job",
    "start_worker",
    "stop_worker",
    "unique_dedupe_key",
]

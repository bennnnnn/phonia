"""What one turn's model stream tells model health: a sample for each model it tried
(recorded once the reply ends, over every model call it made), and the probe it claims
before it tries a recovering model."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field

from redis.asyncio import Redis

from app.core.config import Settings
from app.gateways.stream_signals import StreamAttempt
from app.services import model_health as model_health_service
from app.services.model_health import HealthSample


@dataclass(frozen=True)
class StreamEnd:
    """How the turn's stream ended, as the pipeline saw it."""

    # The model the turn ended on (the one that answered, or the last one tried).
    model: str
    # A model sent at least one token.
    answered: bool
    # The model call itself failed (no model answered, or one failed partway).
    failed: bool
    # The user stopped the turn.
    stopped: bool
    elapsed_ms: float
    first_token_ms: float | None


def health_samples(attempts: Sequence[StreamAttempt], end: StreamEnd) -> list[HealthSample]:
    """A failed try is its own model's failure, whatever ended the turn; the model
    that answered is a success. A try the provider refused over the request (a
    4xx: too large, a policy) says nothing about the model, nor does a Stop:
    neither leaves a sample.

    A model call that reports no tries (the mock model, a test double) counts as
    one try by the turn's model.
    """
    if not attempts:
        failed = end.failed or (not end.answered and not end.stopped)
        attempts = [StreamAttempt(end.model, failed=failed)]
    samples: list[HealthSample] = []
    for attempt in attempts:
        if attempt.failed:
            if not attempt.model_failed:
                continue
            latency = _first(attempt.elapsed_ms, end.elapsed_ms)
            samples.append(
                HealthSample(attempt.alias, latency_ms=latency, success=False, cause=attempt.cause)
            )
        elif not end.stopped:
            latency = _first(attempt.first_delta_ms, end.first_token_ms, end.elapsed_ms)
            samples.append(HealthSample(attempt.alias, latency_ms=latency, success=True))
    return samples


def _first(*values: float | None) -> float:
    """The first measured value (the last one is always measured)."""
    return next((value for value in values if value is not None), 0.0)


def probe_gate(
    redis: Redis, settings: Settings, probe_models: frozenset[str]
) -> Callable[[str], Awaitable[bool]] | None:
    """Before a recovering model is tried, claim its probe: one turn at a time
    tries it, and only a turn that does uses the probe up. A probe this turn holds
    stays its own for the reply's next model call."""
    if not isinstance(probe_models, frozenset) or not probe_models:
        return None
    claimed: set[str] = set()

    async def may_try(alias: str) -> bool:
        if alias not in probe_models or alias in claimed:
            return True
        if not await model_health_service.claim_probe(redis, settings, alias):
            return False
        claimed.add(alias)
        return True

    return may_try


@dataclass
class ReplyHealth:
    """What the reply's model calls tell model health, recorded once when it ends."""

    started: float = field(default_factory=time.perf_counter)
    first_token_ms: float | None = None
    attempts: list[StreamAttempt] = field(default_factory=list)
    failed: bool = False

    def first_token(self) -> None:
        if self.first_token_ms is None:
            self.first_token_ms = (time.perf_counter() - self.started) * 1000

    async def record(self, redis: Redis, model: str, *, stopped: bool) -> None:
        end = StreamEnd(
            model=model,
            answered=self.first_token_ms is not None,
            failed=self.failed,
            stopped=stopped,
            elapsed_ms=(time.perf_counter() - self.started) * 1000,
            first_token_ms=self.first_token_ms,
        )
        if samples := health_samples(self.attempts, end):
            await model_health_service.record_samples(redis, samples)

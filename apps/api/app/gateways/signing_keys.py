"""The keys a sign-in provider signs its tokens with, kept per process.

google-auth's ``verify_token`` fetched Google's certs on every call and kept none, so each
Google sign-in made an HTTPS round trip to Google on sign-in's two threads per machine
(``core/blocking.py``). Measured with the HTTP mocked: 100 sign-ins made 100 fetches, one
after another or all at once; now 1. Apple's keys were kept for an hour, but a token
naming a key id they lack forced a fetch every time: 100 junk tokens made 101; now 1.

* **Kept as long as the provider says.** Google's ``Cache-Control: max-age``, less any
  ``Age`` (about six hours); a minute when it names none. Apple's for an hour, as before.
* **A key rotation still works.** A token naming a key id the kept keys lack fetches them
  again, at most once per ``REFETCH_INTERVAL_SECONDS``: a stream of made-up key ids costs
  one fetch, not one each.
* **Concurrent sign-ins share one fetch**, and its failure.
* **A failed fetch is not kept.** The gateway answers it as unavailable (503: retry,
  don't sign the user out), and the next sign-in fetches again.
"""

from __future__ import annotations

import re
import threading
import time
from collections.abc import Callable, Mapping
from concurrent.futures import Future
from dataclasses import dataclass

REFETCH_INTERVAL_SECONDS = 30.0
# Kept this long when the reply names no max-age, and never longer than a day.
_DEFAULT_MAX_AGE_SECONDS = 60.0
_LONGEST_MAX_AGE_SECONDS = 86_400.0
_MAX_AGE = re.compile(r"(?:^|,)\s*max-age\s*=\s*(\d+)\s*(?:,|$)", re.IGNORECASE)


@dataclass(frozen=True)
class KeySet:
    """A provider's keys as fetched: the body, the key ids it holds, how long it is fresh."""

    body: bytes
    key_ids: frozenset[str]
    max_age_seconds: float


@dataclass(frozen=True)
class _Kept:
    keys: KeySet
    fetched_at: float

    def serves(self, key_id: str | None, now: float) -> bool:
        """Fresh, and it holds ``key_id``, or it was fetched too lately to fetch again."""
        if now - self.fetched_at >= self.keys.max_age_seconds:
            return False
        if key_id is None or key_id in self.keys.key_ids:
            return True
        return now - self.fetched_at < REFETCH_INTERVAL_SECONDS


def _header(headers: Mapping[str, str], name: str) -> str:
    return next((value for key, value in headers.items() if key.lower() == name), "")


def max_age_seconds(headers: Mapping[str, str]) -> float:
    """How long a reply stays fresh: its ``max-age`` less its ``Age``, else a minute."""
    match = _MAX_AGE.search(_header(headers, "cache-control"))
    if match is None:
        return _DEFAULT_MAX_AGE_SECONDS
    age = _header(headers, "age").strip()
    fresh = int(match.group(1)) - (int(age) if age.isdigit() else 0)
    return float(min(max(fresh, 0), _LONGEST_MAX_AGE_SECONDS))


class KeyCache:
    """One provider's keys for this process, shared by the threads that verify tokens."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._kept: _Kept | None = None
        self._fetching: Future[KeySet] | None = None

    def get(
        self, fetch: Callable[[], KeySet], *, key_id: str | None, wait_seconds: float
    ) -> KeySet:
        """The kept keys while they serve ``key_id``, else the ones ``fetch`` returns.

        One fetch at a time: a thread that needs one while another runs waits up to
        ``wait_seconds`` for its keys, or its error. Raises ``TimeoutError`` past that.
        """
        with self._lock:
            kept = self._kept
            if kept is not None and kept.serves(key_id, self._clock()):
                return kept.keys
            fetching = self._fetching
            leads = fetching is None
            if fetching is None:
                fetching = self._fetching = Future()
        if leads:
            self._fetch(fetch, fetching)
        return fetching.result(timeout=wait_seconds)

    def _fetch(self, fetch: Callable[[], KeySet], fetching: Future[KeySet]) -> None:
        try:
            keys = fetch()
        except BaseException as exc:  # handed to every waiter, this thread included
            with self._lock:
                self._fetching = None
            fetching.set_exception(exc)
            return
        with self._lock:
            self._kept = _Kept(keys, fetched_at=self._clock())
            self._fetching = None
        fetching.set_result(keys)

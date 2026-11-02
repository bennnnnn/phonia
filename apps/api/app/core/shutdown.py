"""The moment this process is told to stop, ahead of uvicorn's graceful wait.

On SIGINT/SIGTERM uvicorn closes every WebSocket (1012), waits up to
``--timeout-graceful-shutdown`` for the handlers, and only then runs the app's
lifespan shutdown. Work that has to end cleanly inside that window, such as a
chat reply that must be saved and its lock released, must start at the signal.
``install_signal_hook`` chains uvicorn's handlers so the callbacks registered
with ``on_stop`` run then, once, on the event loop.
"""

from __future__ import annotations

import asyncio
import logging
import signal
import threading
from collections.abc import Callable
from types import FrameType

logger = logging.getLogger(__name__)

_SIGNALS = (signal.SIGINT, signal.SIGTERM)

_callbacks: list[Callable[[], object]] = []
_stopping = False


def stopping() -> bool:
    """True once a stop signal arrived; work that ends early because of it says so."""
    return _stopping


def on_stop(callback: Callable[[], object]) -> None:
    """Run ``callback`` on the event loop when the process is told to stop."""
    if callback not in _callbacks:
        _callbacks.append(callback)


def begin_stop() -> None:
    """Mark the process stopping and run each callback once; one failure skips no other."""
    global _stopping
    if _stopping:
        return
    _stopping = True
    logger.info("Stop signal: ending %d in-flight hook(s)", len(_callbacks))
    for callback in list(_callbacks):
        try:
            callback()
        except Exception:
            logger.exception("Stop hook failed")


def install_signal_hook(loop: asyncio.AbstractEventLoop) -> bool:
    """Chain the server's SIGINT/SIGTERM handlers so ``begin_stop`` runs first.

    Only a Python handler is chained (uvicorn's ``handle_exit``); with the
    default handler there is no graceful window to work in, and signal handlers
    can only be set from the main thread (tests run the lifespan elsewhere).
    """
    if threading.current_thread() is not threading.main_thread():
        return False
    installed = False
    for sig in _SIGNALS:
        previous = signal.getsignal(sig)
        if not callable(previous) or previous is signal.default_int_handler:
            continue
        signal.signal(sig, _chained(loop, previous))
        installed = True
    return installed


def _chained(
    loop: asyncio.AbstractEventLoop,
    previous: Callable[[int, FrameType | None], object],
) -> Callable[[int, FrameType | None], None]:
    def handler(signum: int, frame: FrameType | None) -> None:
        loop.call_soon_threadsafe(begin_stop)
        previous(signum, frame)

    return handler

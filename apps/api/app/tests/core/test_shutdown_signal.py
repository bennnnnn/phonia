"""The stop signal reaches the app before uvicorn's graceful wait (core/shutdown.py)."""

from __future__ import annotations

import asyncio
import signal

import pytest

from app.core import shutdown


@pytest.fixture(autouse=True)
def _fresh_stop_state(monkeypatch):
    monkeypatch.setattr(shutdown, "_stopping", False)
    monkeypatch.setattr(shutdown, "_callbacks", [])


@pytest.fixture
def _restore_signal_handlers():
    saved = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)}
    yield
    for sig, handler in saved.items():
        signal.signal(sig, handler)


def test_begin_stop_runs_each_callback_once_and_survives_a_failing_one():
    calls: list[str] = []

    def broken() -> None:
        calls.append("broken")
        raise RuntimeError("boom")

    shutdown.on_stop(broken)
    shutdown.on_stop(lambda: calls.append("second"))
    assert shutdown.stopping() is False

    shutdown.begin_stop()
    shutdown.begin_stop()

    assert shutdown.stopping() is True
    assert calls == ["broken", "second"]


@pytest.mark.asyncio
@pytest.mark.usefixtures("_restore_signal_handlers")
async def test_signal_hook_runs_the_stop_then_the_servers_own_handler():
    server_exits: list[int] = []
    stopped: list[bool] = []

    def server_exit(signum: int, _frame: object) -> None:  # uvicorn's handle_exit
        server_exits.append(signum)

    signal.signal(signal.SIGTERM, server_exit)
    shutdown.on_stop(lambda: stopped.append(shutdown.stopping()))

    assert shutdown.install_signal_hook(asyncio.get_running_loop()) is True
    signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)
    assert server_exits == [signal.SIGTERM]
    await asyncio.sleep(0)

    assert stopped == [True]


@pytest.mark.asyncio
@pytest.mark.usefixtures("_restore_signal_handlers")
async def test_signal_hook_leaves_default_handlers_alone():
    signal.signal(signal.SIGTERM, signal.SIG_DFL)
    signal.signal(signal.SIGINT, signal.default_int_handler)

    assert shutdown.install_signal_hook(asyncio.get_running_loop()) is False
    assert signal.getsignal(signal.SIGTERM) is signal.SIG_DFL
    assert signal.getsignal(signal.SIGINT) is signal.default_int_handler


def test_signal_hook_needs_the_main_thread():
    import threading

    results: list[bool] = []
    loop = asyncio.new_event_loop()
    try:
        worker = threading.Thread(target=lambda: results.append(shutdown.install_signal_hook(loop)))
        worker.start()
        worker.join()
    finally:
        loop.close()
    assert results == [False]

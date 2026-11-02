"""Every route's dependencies resolve on the event loop, never in a worker thread.

FastAPI runs a plain ``def`` dependency in the threadpool. ``core/deps.py`` kept a sync
``get_redis`` beside an async ``get_redis_dep`` that did the same job, and three routes
took the sync ``get_settings``: 22 routes (sign-in, refresh, the chat history page, both
SSE chat streams) paid a thread hop per request for a function that only returns an
object, about 100 µs alone and 175 µs with 50 requests in flight, and each hop held one
of the threadpool's 40 slots. A dependency that must block says why here.
"""

from __future__ import annotations

import inspect
from collections.abc import Iterator
from typing import Any

from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute, APIWebSocketRoute

# Dependency qualname -> why it may run in a worker thread.
_MAY_BLOCK: dict[str, str] = {}


def _is_async(call: object) -> bool:
    dunder = getattr(call, "__call__", None)  # noqa: B004
    return any(
        inspect.iscoroutinefunction(fn) or inspect.isasyncgenfunction(fn) for fn in (call, dunder)
    )


def _routes(routes: list[Any]) -> Iterator[APIRoute | APIWebSocketRoute]:
    for route in routes:
        inner = getattr(route, "original_router", None)
        if inner is not None:
            yield from _routes(inner.routes)
        elif isinstance(route, APIRoute | APIWebSocketRoute):
            yield route


def _sync_calls(dependant: Dependant) -> Iterator[str]:
    for dep in dependant.dependencies:
        if dep.call is not None and not _is_async(dep.call):
            yield getattr(dep.call, "__qualname__", repr(dep.call))
        yield from _sync_calls(dep)


def test_no_route_resolves_a_dependency_in_a_worker_thread() -> None:
    from app.main import create_app

    routes = list(_routes(create_app().routes))
    assert len(routes) > 50, "the walk no longer finds the app's routes"
    blocking = sorted(
        f"{route.path}: {name}"
        for route in routes
        for name in _sync_calls(route.dependant)
        if name not in _MAY_BLOCK
    )
    assert blocking == [], "make these dependencies async, or say why here"

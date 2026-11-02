"""Stop a request's work when its client hangs up.

Starlette does not cancel a plain route when the client goes away: the phone's Cancel aborts
its request, and the handler ran on, paying for a picture nobody would see and counting it
against the user's day. Work worth stopping runs through ``until_client_leaves``: it polls
the connection, and once the client has gone it cancels the work and waits for the work's
own cleanup (a slot given back, stored bytes deleted) before raising ``ClientLeft``.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable

from starlette.requests import Request

# How often a running request checks that its client is still there.
DISCONNECT_POLL_SECONDS = 0.5


class ClientLeft(Exception):
    """The client closed the connection before the work finished: nobody reads a reply."""


async def until_client_leaves[T](
    request: Request, work: Awaitable[T], *, poll_seconds: float = DISCONNECT_POLL_SECONDS
) -> T:
    """``work``'s result, or ``ClientLeft`` once the client has gone and the work is cancelled.

    Work that finishes in the same moment the client leaves keeps what it did (its own code
    decides what a late cancel may still undo). A failure of the work is raised as it is.
    """
    task = asyncio.ensure_future(work)
    try:
        while True:
            done, _ = await asyncio.wait({task}, timeout=poll_seconds)
            if done:
                return task.result()
            if await request.is_disconnected():
                task.cancel()
                await asyncio.wait({task})
                if task.cancelled():
                    raise ClientLeft
                return task.result()
    finally:
        # This handler itself was cancelled (a shutdown): the work stops with it.
        if not task.done():
            task.cancel()

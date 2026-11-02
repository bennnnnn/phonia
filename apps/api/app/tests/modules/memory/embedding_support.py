"""Fake ``embed_many`` for tests whose embedding fake answers one text at a time."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from app.core.config import Settings

EMBED_MANY = "app.gateways.embedding_gateway.embed_many"


def embed_each(
    embed_text: Callable[[Settings, str], Awaitable[Any]],
) -> Callable[..., Awaitable[list[Any]]]:
    """``embed_many`` as one ``embed_text`` call per input, in order.

    Patch it over ``EMBED_MANY``: the memory writes embed through ``embed_many``,
    whose batched request (mocked in CI) never reaches a patched ``embed_text``.
    """

    async def _embed_many(settings: Settings, texts: list[str], *, concurrency: int) -> list[Any]:
        return [await embed_text(settings, text) for text in texts]

    return _embed_many

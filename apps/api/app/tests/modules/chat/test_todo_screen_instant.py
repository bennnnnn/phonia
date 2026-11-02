"""A to-do change asked in another language is answered before any model runs."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.modules.chat.turn_prep.instant import resolve_instant_reply

_ES_BUTTON = "Puedes añadirlo o cambiarlo en **Tareas**.\n\n```todo_link\n```"


async def _instant(content: str, recent: list[tuple[str, str]], locale: str = "en") -> str | None:
    rows = [SimpleNamespace(role=role, content=text) for role, text in recent]
    request: Any = SimpleNamespace(
        content=content,
        has_image_attachment=False,
        recent_messages=[*rows, SimpleNamespace(role="user", content=content)],
    )
    identity: Any = SimpleNamespace(
        user=SimpleNamespace(id=uuid4(), locale=locale, plan="free"),
        local_tz="UTC",
        geo=SimpleNamespace(user_location=None),
    )
    return await resolve_instant_reply(request, identity, Settings(), AsyncMock())


@pytest.mark.asyncio
async def test_a_spanish_ask_to_add_a_to_do_gets_the_button_without_a_model() -> None:
    # Live, the model asked "¿cuándo?" and then wrote "He añadido…" for nothing saved.
    assert await _instant("añade comprar leche a mis tareas", []) == _ES_BUTTON


@pytest.mark.asyncio
async def test_a_time_after_the_button_gets_it_again() -> None:
    recent = [("user", "añade comprar leche a mis tareas"), ("assistant", _ES_BUTTON)]
    assert await _instant("mañana a las 5", recent) == _ES_BUTTON


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("content", "locale"),
    [
        # English writes in chat: the model answers and offers a card to tap.
        ("remind me to call mom tomorrow at 9", "es"),
        # A question in Spanish is answered from the list by the model.
        ("¿qué tengo hoy?", "en"),
        ("ayúdame con mi tarea de matemáticas", "es"),
    ],
)
async def test_everything_else_goes_to_the_model(content: str, locale: str) -> None:
    assert await _instant(content, [], locale) is None

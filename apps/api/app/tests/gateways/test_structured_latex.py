"""LaTeX a model writes inside structured JSON survives decoding."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

from app.core.config import Settings
from app.gateways import litellm_gateway

_SETTINGS = Settings(mock_llm_enabled=False, openrouter_api_key="sk-or-test")


class _Questions(BaseModel):
    questions: list[str]


async def _decode(raw: str) -> list[str] | None:
    choice = MagicMock()
    choice.message.content = raw
    response = MagicMock(choices=[choice], usage=None)
    with patch.object(litellm_gateway, "acompletion", AsyncMock(return_value=response)):
        result = await litellm_gateway.complete_structured(
            settings=_SETTINGS,
            model_alias="memory-model",
            messages=[{"role": "user", "content": "x"}],
            schema=_Questions,
            allow_fallback=False,
        )
    return None if result is None else result.questions


@pytest.mark.parametrize(
    ("written", "read"),
    [
        # One backslash: \t, \f, \b, \r and \n would decode as control characters.
        (r"What if $f = 15\text{ cm}$?", r"What if $f = 15\text{ cm}$?"),
        (r"Why is $\frac{1}{2}$ half?", r"Why is $\frac{1}{2}$ half?"),
        (r"What if $\beta = 30^\circ$?", r"What if $\beta = 30^\circ$?"),
        (r"Is $\rho$ the density?", r"Is $\rho$ the density?"),
        (r"What if $a \neq b$?", r"What if $a \neq b$?"),
        # No JSON escape at all: this failed the whole parse.
        (r"What if $\alpha = 2$?", r"What if $\alpha = 2$?"),
        (r"Why $\Delta x$?", r"Why $\Delta x$?"),
        # Escaped properly, it reads the same.
        (r"What if $f = 15\\text{ cm}$?", r"What if $f = 15\text{ cm}$?"),
        # Real escapes keep their meaning.
        (r"Line one\nline two", "Line one\nline two"),
        (r"A \"quoted\" word", 'A "quoted" word'),
        (r"café", "café"),
        (r"Tab\there", "Tab\there"),
    ],
)
@pytest.mark.asyncio
async def test_structured_latex_survives_decoding(written: str, read: str) -> None:
    assert await _decode(f'{{"questions": ["{written}"]}}') == [read]

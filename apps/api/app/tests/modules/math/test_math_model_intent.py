"""The two model helpers behind a maths turn run side by side, with the same outcome."""

from __future__ import annotations

import asyncio
import time
from typing import Any

import pytest

from app.core.config import Settings
from app.modules.math.schemas import MathIntent
from app.modules.math.tools import prompt as math_prompt
from app.modules.math.tools import word_problem

_WORD = MathIntent(kind="word_problem", operation="solve")
_EQUATION = MathIntent(kind="equation", lhs="2*x+3", rhs="7", operation="solve", variable="x")


def _settings(**overrides: Any) -> Settings:
    return Settings(**{"math_tools_enabled": True, **overrides})


def _helpers(
    monkeypatch: pytest.MonkeyPatch,
    *,
    translated: MathIntent | None,
    extracted: MathIntent | None,
    translate_seconds: float = 0.0,
    extract_seconds: float = 0.0,
) -> dict[str, Any]:
    calls: dict[str, Any] = {"translate": 0, "extract": 0, "extract_cancelled": False}

    async def translate(_text: str, _settings: Settings) -> MathIntent | None:
        calls["translate"] += 1
        await asyncio.sleep(translate_seconds)
        return translated

    async def extract(_text: str, _settings: Settings) -> MathIntent | None:
        calls["extract"] += 1
        try:
            await asyncio.sleep(extract_seconds)
        except asyncio.CancelledError:
            calls["extract_cancelled"] = True
            raise
        return extracted

    monkeypatch.setattr(word_problem, "word_problem_intent", translate)
    monkeypatch.setattr(math_prompt, "llm_extract_math_intent", extract)
    monkeypatch.setattr(math_prompt, "_model_intent_is_users", lambda _text, _intent: True)
    return calls


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "translated, extracted, expected",
    [
        (_WORD, _EQUATION, _WORD),  # a translated word problem wins
        (_WORD, None, _WORD),
        (None, _EQUATION, _EQUATION),  # otherwise the extraction
        (None, None, None),
    ],
)
async def test_the_outcome_is_todays(
    monkeypatch: pytest.MonkeyPatch,
    translated: MathIntent | None,
    extracted: MathIntent | None,
    expected: MathIntent | None,
) -> None:
    _helpers(monkeypatch, translated=translated, extracted=extracted)
    got = await math_prompt._model_math_intent("text", _settings(), word_problem=True)
    assert got is expected


@pytest.mark.wall_clock
@pytest.mark.asyncio
async def test_a_word_problem_does_not_wait_for_the_extraction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _helpers(
        monkeypatch, translated=_WORD, extracted=_EQUATION, translate_seconds=0.1, extract_seconds=5
    )
    started = time.monotonic()
    assert await math_prompt._model_math_intent("text", _settings(), word_problem=True) is _WORD
    assert time.monotonic() - started < 1.0
    assert calls["extract_cancelled"] is True


@pytest.mark.wall_clock
@pytest.mark.asyncio
async def test_the_extraction_no_longer_waits_out_the_translation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _helpers(
        monkeypatch,
        translated=None,
        extracted=_EQUATION,
        translate_seconds=0.4,
        extract_seconds=0.4,
    )
    started = time.monotonic()
    assert await math_prompt._model_math_intent("text", _settings(), word_problem=True) is _EQUATION
    # Side by side: about one helper's time, not the two of them in a row.
    assert time.monotonic() - started < 0.7


@pytest.mark.wall_clock
@pytest.mark.asyncio
async def test_both_helpers_share_one_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = _helpers(
        monkeypatch, translated=None, extracted=_EQUATION, translate_seconds=5, extract_seconds=5
    )
    started = time.monotonic()
    settings = _settings(math_model_intent_budget_seconds=0.2)
    assert await math_prompt._model_math_intent("text", settings, word_problem=True) is None
    assert time.monotonic() - started < 1.0
    assert calls["extract_cancelled"] is True


@pytest.mark.asyncio
async def test_a_finished_extraction_is_kept_when_the_translation_runs_long(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: the budget threw away an extraction that had finished, because
    the translation beside it (two slow routes) was still running."""
    _helpers(
        monkeypatch,
        translated=None,
        extracted=_EQUATION,
        translate_seconds=0.5,
        extract_seconds=0.05,
    )
    settings = _settings(math_model_intent_budget_seconds=0.3)
    assert await math_prompt._model_math_intent("text", settings, word_problem=True) is _EQUATION


def test_the_budget_outlasts_two_translation_attempts() -> None:
    settings = Settings()
    two_tries = 2 * settings.math_word_problem_timeout_seconds
    assert two_tries < settings.math_model_intent_budget_seconds <= two_tries + 1.5


@pytest.mark.asyncio
async def test_a_photographed_problem_skips_the_translation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _helpers(monkeypatch, translated=_WORD, extracted=_EQUATION)
    got = await math_prompt._model_math_intent("text", _settings(), word_problem=False)
    assert got is _EQUATION
    assert calls["translate"] == 0


@pytest.mark.asyncio
async def test_an_extraction_that_drops_part_of_the_request_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _helpers(monkeypatch, translated=None, extracted=_EQUATION)
    monkeypatch.setattr(math_prompt, "_model_intent_is_users", lambda _text, _intent: False)
    assert await math_prompt._model_math_intent("text", _settings(), word_problem=True) is None


@pytest.mark.asyncio
async def test_a_turn_that_is_not_maths_calls_neither_helper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _helpers(monkeypatch, translated=_WORD, extracted=_EQUATION)
    note, verified = await math_prompt.build_math_augmentation(
        "What's a good name for a cat?", _settings()
    )
    assert (note, verified) == (None, None)
    assert calls["translate"] == calls["extract"] == 0


@pytest.mark.asyncio
async def test_a_plain_equation_the_regex_reads_calls_neither_helper(
    monkeypatch: pytest.MonkeyPatch, thread_sympy_executor: None
) -> None:
    calls = _helpers(monkeypatch, translated=_WORD, extracted=_EQUATION)
    _note, verified = await math_prompt.build_math_augmentation("Solve 2x + 3 = 7", _settings())
    assert verified is not None and verified.canonical_answer is not None
    assert calls["translate"] == calls["extract"] == 0

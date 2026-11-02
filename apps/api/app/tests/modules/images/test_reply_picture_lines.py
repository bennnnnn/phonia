"""The line under a reply whose picture was not drawn: by code, in the app's language."""

from __future__ import annotations

import ast
import inspect
from typing import get_args

import pytest

from app.core.validation import LOCALE_NAMES
from app.exceptions import _STATUS_CODES
from app.modules.images import generation
from app.modules.images import reply_picture_lines as lines
from app.services.quota import messages
from app.tests.architecture.boundary_support import MOBILE_ROOT

_GENERATION_SOURCE = inspect.getsource(generation)


def _codes_generation_raises() -> set[str]:
    """Every ``ImageGenerationError`` code in ``generation.py``: named, or its status's."""
    codes: set[str] = set()
    for node in ast.walk(ast.parse(_GENERATION_SOURCE)):
        if not (
            isinstance(node, ast.Call) and getattr(node.func, "id", "") == "ImageGenerationError"
        ):
            continue
        named = {kw.arg: kw.value for kw in node.keywords}
        if "code" in named:
            value = named["code"]
            assert isinstance(value, ast.Constant) and isinstance(value.value, str), ast.unparse(
                node
            )
            codes.add(value.value)
            continue
        status = named.get("status_code")
        assert isinstance(status, ast.Constant) and isinstance(status.value, int), ast.unparse(node)
        codes.add(_STATUS_CODES[status.value])
    return codes


def test_every_code_generation_raises_has_a_line_of_its_own_choosing() -> None:
    """A new refusal in ``generation`` fails here until someone picks the line it gets."""
    raised = _codes_generation_raises()
    assert {
        "spend_cap",
        "daily_limit",
        "content_blocked",
        "not_in_plan",
        "upstream_failed",
    } <= raised
    missing = raised - set(lines.REASON_BY_CODE)
    assert not missing, f"pick a reason in REASON_BY_CODE for {sorted(missing)}"
    for code in raised:
        assert lines.reason_for_code(code) in get_args(lines.Reason)


@pytest.mark.parametrize(
    ("code", "reason"),
    [
        ("spend_cap", "paused"),
        ("not_available", "paused"),
        ("not_in_plan", "not_in_plan"),
        ("daily_limit", "daily_limit"),
        ("content_blocked", "content_blocked"),
        ("upstream_failed", "failed"),
        ("unavailable", "failed"),
        ("not_found", "failed"),
        ("rate_limited", "failed"),
        ("anything_new", "failed"),
        ("", "failed"),
    ],
)
def test_reason_for_code(code: str, reason: str) -> None:
    assert lines.reason_for_code(code) == reason


def test_every_reason_is_in_every_language_the_phone_has() -> None:
    phone = {path.stem for path in (MOBILE_ROOT / "lib" / "i18n").glob("*.json")}
    assert phone == set(LOCALE_NAMES) == set(lines._NOT_DRAWN)
    keys = {"daily_limit_free", "daily_limit_paid"} | set(get_args(lines.Reason)) - {"daily_limit"}
    assert set(lines._REASONS) == keys
    for key, by_locale in lines._REASONS.items():
        assert set(by_locale) == phone, key
        for locale, text in by_locale.items():
            # A real translation: English left in a locale is a missed line.
            assert locale == "en" or text != by_locale["en"], (key, locale)
            assert "{" not in text and "}" not in text, (key, locale)
    for locale, template in lines._NOT_DRAWN.items():
        assert template.count("{subject}") == 1 and template.count("{reason}") == 1, locale
        assert locale == "en" or template != lines._NOT_DRAWN["en"]


def _old_line(reason: str) -> str:
    """The English line before it was translated: ``_NOT_MADE`` with the refusal's text."""
    return "I couldn't draw the picture ({subject}) this time: {reason}".format(
        subject="a fox", reason=reason.rstrip(".") + "."
    )


@pytest.mark.parametrize(
    ("reason", "paid", "old_text"),
    [
        ("paused", False, messages.IMAGE_GENERATION_SPEND_CAP_MESSAGE),
        ("not_in_plan", False, messages.IMAGE_GENERATION_NOT_IN_PLAN_MESSAGE),
        ("daily_limit", False, messages.IMAGE_GENERATION_LIMIT_EXCEEDED_MESSAGE_FREE),
        ("daily_limit", True, messages.IMAGE_GENERATION_LIMIT_EXCEEDED_MESSAGE_PAID),
        (
            "content_blocked",
            False,
            "That picture can't be made: it breaks the image service's content rules.",
        ),
        ("too_slow", False, "the picture took too long. Ask for it again on its own."),
        ("failed", False, "something went wrong. Ask for it again on its own."),
    ],
)
def test_english_is_unchanged(reason: lines.Reason, paid: bool, old_text: str) -> None:
    assert lines.not_drawn_line(reason, "a fox", "en", paid=paid) == _old_line(old_text)


def test_the_content_rules_line_is_generations_own_english() -> None:
    assert lines._REASONS["content_blocked"]["en"] in _GENERATION_SOURCE


@pytest.mark.parametrize(
    ("locale", "start"),
    [
        (None, "I couldn't draw"),
        ("", "I couldn't draw"),
        ("en-GB", "I couldn't draw"),
        ("xx", "I couldn't draw"),
        ("zh-Hans", "I couldn't draw"),
        ("pt-BR", "Desta vez não consegui"),
        ("PT", "Desta vez não consegui"),
        ("es", "Esta vez no pude"),
        ("fr", "Je n'ai pas pu"),
        ("it", "Questa volta non sono riuscito"),
        ("tr", "Bu sefer resmi"),
        ("ru", "В этот раз"),
        ("am", "ምስሉን"),
        ("de-CH", "Das Bild"),
    ],
)
def test_locale_codes(locale: str | None, start: str) -> None:
    assert lines.not_drawn_line("failed", "a fox", locale).startswith(start)


@pytest.mark.parametrize("subject", ["a {fox}", "{subject} and {reason}", "{0} {}", "50% {x!r}"])
@pytest.mark.parametrize("locale", sorted(LOCALE_NAMES))
def test_braces_in_the_subject_are_kept(subject: str, locale: str) -> None:
    line = lines.not_drawn_line("daily_limit", subject, locale)
    assert f"({subject})" in line
    assert line.count(subject) == 1

"""The server's part of a multi-part reply: a settings card and a picture beside the answer.

"Switch to dark mode and tell me a joke" used to lose the switch, and "switch to dark
mode, and also what is the capital of France?" the question. "Draw a cat wearing a
hat and also explain what a black hole is" drew nothing (I4).
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from app.core.config import Settings
from app.models.orm import User
from app.modules.chat.finalize_parts import add_settings_card, attach_reply_picture
from app.modules.chat.finalize_passes import FinalizeState
from app.modules.chat.reply_language import line_language
from app.modules.chat.turn_intercepts import start_reply_picture
from app.modules.chat.turn_outcome import TurnOutcome
from app.modules.chat.turn_prep import StreamContext
from app.modules.chat.turn_prep.instant import resolve_instant_reply, settings_card
from app.modules.chat.turn_prep.intents import plan_turn
from app.modules.images import reply_picture
from app.modules.images.generation import ImageGenerationError
from app.modules.images.reply_picture import ReplyPicture

_CARD = 'I can switch that for you: Appearance → Dark.\n\n```settings_proposal\n{"proposal_id": "p"}\n```'


def _state(text: str, **ctx_fields: Any) -> FinalizeState:
    ctx = StreamContext(
        user_id=uuid4(),
        chat_id=uuid4(),
        model="free-chat",
        prompt_messages=[{"role": "user", "content": "x"}],
        run_title=False,
        user_message_content="x",
        reserved_tokens=0,
        max_output_tokens=0,
        **ctx_fields,
    )
    return FinalizeState(
        deps=MagicMock(),
        settings=Settings(),
        ctx=ctx,
        raw=text,
        text=text,
        usage={},
        outcome=TurnOutcome(),
        was_cancelled=False,
        assistant_parts=[text],
        should_cancel=None,
    )


def test_the_settings_card_goes_under_the_answer() -> None:
    state = _state("Why did the scarecrow win an award? He was outstanding in his field.")
    state.ctx.settings_card = _CARD
    text = add_settings_card(state)
    assert text.startswith("Why did the scarecrow")
    assert text.endswith("```")
    assert "```settings_proposal" in text
    assert state.committed == text


def test_a_card_the_model_wrote_is_dropped_for_the_servers() -> None:
    forged = 'Sure!\n\n```settings_proposal\n{"proposal_id": "made-up"}\n```\n\nA joke.'
    state = _state(forged, settings_card=_CARD)
    text = add_settings_card(state)
    assert "made-up" not in text
    assert text.count("```settings_proposal") == 1


def test_no_card_leaves_the_reply_alone() -> None:
    state = _state("Just an answer.")
    assert add_settings_card(state) == "Just an answer."
    assert state.committed is None


async def _drawn(picture_id: UUID) -> UUID:
    return picture_id


@pytest.mark.asyncio
async def test_the_picture_goes_above_the_answer_and_is_linked() -> None:
    picture_id, photo_id = uuid4(), uuid4()
    task = asyncio.ensure_future(_drawn(picture_id))
    state = _state(
        "A black hole is a region where gravity...",
        reply_picture=ReplyPicture("cat wearing a hat", task=task),
        answer_photo_ids=[photo_id],
    )
    text = await attach_reply_picture(state)
    assert text.startswith(f"[Image: /attachments/{picture_id}/file]\n\nA black hole")
    assert state.ctx.answer_photo_ids == [photo_id, picture_id]
    assert state.committed == text


_EN = "I couldn't draw the picture (a fox) this time: "
_DE = "Das Bild (a fox) konnte ich diesmal nicht zeichnen: "
# Each reason the line can give, how a picture comes to it, and its German and English.
_NOT_DRAWN = {
    "not_in_plan": (
        "Die Bilderstellung ist in deinem Tarif nicht enthalten. Mit einem Upgrade bekommst du sie.",
        "Image generation isn't part of your plan. Upgrade for it.",
    ),
    "daily_limit_free": (
        "Du hast das heutige Limit für Bilderstellung erreicht. Upgrade für mehr, "
        "oder versuche es nach Mitternacht UTC erneut.",
        "You've reached today's image generation limit. "
        "Upgrade for more — or try again after midnight UTC.",
    ),
    "daily_limit_paid": (
        "Du hast das heutige Limit für Bilderstellung erreicht. "
        "Versuche es nach Mitternacht UTC erneut.",
        "You've reached today's image generation limit. Try again after midnight UTC.",
    ),
    "content_blocked": (
        "Dieses Bild kann nicht erstellt werden: "
        "Es verstößt gegen die Inhaltsregeln des Bilddienstes.",
        "That picture can't be made: it breaks the image service's content rules.",
    ),
    "too_slow": (
        "Das Bild hat zu lange gedauert. Bitte frag in einer eigenen Nachricht noch einmal danach.",
        "the picture took too long. Ask for it again on its own.",
    ),
    "failed": (
        "Etwas ist schiefgelaufen. Bitte frag in einer eigenen Nachricht noch einmal danach.",
        "something went wrong. Ask for it again on its own.",
    ),
    "upstream_failed": (
        "Etwas ist schiefgelaufen. Bitte frag in einer eigenen Nachricht noch einmal danach.",
        "something went wrong. Ask for it again on its own.",
    ),
    "unknown_code": (
        "Etwas ist schiefgelaufen. Bitte frag in einer eigenen Nachricht noch einmal danach.",
        "something went wrong. Ask for it again on its own.",
    ),
}


async def _never() -> UUID:
    await asyncio.sleep(60)
    return uuid4()


def _picture(case: str, locale: str | None) -> ReplyPicture:
    """The picture for ``case`` as the turn makes it: refused up front, or failing to draw."""
    if case == "not_in_plan":
        return ReplyPicture.refused("a fox", "not_in_plan", locale)
    errors: dict[str, BaseException] = {
        # Each with the English (or provider text) that must not reach the reply.
        "daily_limit_free": ImageGenerationError("Daily cap!", status_code=429, code="daily_limit"),
        "daily_limit_paid": ImageGenerationError("Daily cap!", status_code=429, code="daily_limit"),
        "content_blocked": ImageGenerationError(
            "Blocked!", status_code=422, code="content_blocked"
        ),
        "failed": RuntimeError("provider said: 500 Internal Server Error"),
        "upstream_failed": ImageGenerationError("Could not generate image", status_code=502),
        "unknown_code": ImageGenerationError("raw provider text {x}", code="some_new_code"),
    }

    async def draw() -> UUID:
        if case == "too_slow":
            return await _never()
        raise errors[case]

    task = asyncio.ensure_future(draw())
    if case == "daily_limit_paid":
        return ReplyPicture("a fox", task=task, locale=locale, paid=True)
    return ReplyPicture("a fox", task=task, locale=locale)


@pytest.mark.asyncio
@pytest.mark.parametrize("case", list(_NOT_DRAWN))
@pytest.mark.parametrize("locale", ["de", "de-AT", "en", None, ""])
async def test_a_picture_not_drawn_says_why_in_the_apps_language(
    case: str, locale: str | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only the spend cap's line was in the app's language; the rest showed English."""
    german, english = _NOT_DRAWN[case]
    line = _DE + german if locale and locale.startswith("de") else _EN + english
    picture = _picture(case, locale)
    monkeypatch.setattr(reply_picture, "_WAIT_SECONDS", 0.01)
    text = await attach_reply_picture(_state_with(picture))
    picture.cancel()
    assert text == f"Antwort.\n\n{line}"
    assert "!" not in text and "provider" not in text and "Could not" not in text


def _state_with(picture: ReplyPicture) -> FinalizeState:
    return _state("Antwort.", reply_picture=picture)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("locale", "line"),
    [
        (
            "de",
            "Das Bild (a fox) konnte ich diesmal nicht zeichnen: Die Bilderstellung ist "
            "vorübergehend nicht verfügbar. Versuche es später erneut.",
        ),
        (
            "en",
            "I couldn't draw the picture (a fox) this time: Image generation is "
            "temporarily unavailable. Try again later.",
        ),
        (
            None,
            "I couldn't draw the picture (a fox) this time: Image generation is "
            "temporarily unavailable. Try again later.",
        ),
    ],
)
async def test_a_picture_the_spend_cap_stopped_says_so_in_the_apps_language(
    locale: str | None, line: str
) -> None:
    """The cap's English showed under a German reply."""

    async def capped() -> UUID:
        raise ImageGenerationError("Image generation is paused.", status_code=429, code="spend_cap")

    picture = ReplyPicture("a fox", task=asyncio.ensure_future(capped()), locale=locale)
    state = _state("Antwort.", reply_picture=picture)
    text = await attach_reply_picture(state)
    assert text == f"Antwort.\n\n{line}"
    assert state.ctx.answer_photo_ids == []


def test_a_picture_with_drawing_off_says_the_caps_line_in_the_replys_language() -> None:
    """A German app asked in English gets an English reply, so the line is English too;
    it was German under the English answer."""
    picture = start_reply_picture(
        _deps(can_use=True),
        Settings(image_generation_enabled=False),
        user=User(id=uuid4(), plan="pro", locale="de"),
        chat_id=uuid4(),
        content="draw a cat wearing a hat and also explain what a black hole is",
    )
    assert picture is not None
    text, ids = asyncio.run(picture.attach("Answer."))
    assert text == (
        "Answer.\n\nI couldn't draw the picture (cat wearing a hat) this time: "
        "Image generation is temporarily unavailable. Try again later."
    )
    assert ids == []


@pytest.mark.parametrize(
    ("message", "locale", "language"),
    [
        ("Draw a cat and also explain what a black hole is", "de", "en"),
        ("Zeichne eine Katze und erkläre mir bitte, was ein schwarzes Loch ist", "en", "de"),
        ("Нарисуй кошку и объясни чёрную дыру", "en", "ru"),
        # Nothing plainly one language: the app's.
        ("cat + black hole", "de", "de"),
        ("cat + black hole", "pt-BR", "pt"),
        ("cat + black hole", None, "en"),
    ],
)
def test_line_language_follows_the_message_then_the_app(
    message: str, locale: str | None, language: str
) -> None:
    assert line_language(message, locale) == language


@pytest.mark.asyncio
async def test_a_stopped_reply_cancels_its_picture() -> None:
    started = asyncio.Event()

    async def slow() -> UUID:
        started.set()
        await asyncio.sleep(60)
        return uuid4()

    task = asyncio.ensure_future(slow())
    await started.wait()
    state = _state("Partial", reply_picture=ReplyPicture("a fox", task=task))
    state.was_cancelled = True
    assert await attach_reply_picture(state) == "Partial"
    await asyncio.sleep(0)
    assert task.cancelled()


def _deps(*, can_use: bool) -> Any:
    return SimpleNamespace(plan=SimpleNamespace(can_use=lambda *_a: can_use))


def test_start_reply_picture_only_for_a_picture_part() -> None:
    user = User(id=uuid4(), plan="pro")
    settings = Settings()
    for text in ("draw a cat wearing a hat", "explain what a black hole is"):
        assert (
            start_reply_picture(
                _deps(can_use=True), settings, user=user, chat_id=uuid4(), content=text
            )
            is None
        )


def test_start_reply_picture_refuses_without_the_plan() -> None:
    picture = start_reply_picture(
        _deps(can_use=False),
        Settings(),
        user=User(id=uuid4(), plan="pro", locale="de"),
        chat_id=uuid4(),
        content="draw a cat wearing a hat and also explain what a black hole is",
    )
    assert picture is not None and picture.subject == "cat wearing a hat"
    text, ids = asyncio.run(picture.attach("Answer."))
    assert text == (
        "Answer.\n\nI couldn't draw the picture (cat wearing a hat) this time: "
        "Image generation isn't part of your plan. Upgrade for it."
    )
    assert ids == []


@pytest.mark.asyncio
@pytest.mark.parametrize(("plan", "paid"), [("free", False), ("pro", True)])
async def test_a_started_picture_knows_the_plan_for_the_daily_limit_line(
    plan: str, paid: bool
) -> None:
    """Only a free plan is offered an upgrade, as ``quota.plan_message`` words it."""
    drawn = AsyncMock(side_effect=ImageGenerationError("x", status_code=429, code="daily_limit"))
    with patch("app.modules.images.reply_picture.draw_unlinked", drawn):
        picture = ReplyPicture.start(
            Settings(),
            user=User(id=uuid4(), plan=plan, locale="en"),
            chat_id=uuid4(),
            prompt="a fox",
        )
        text, _ids = await picture.attach("Answer.")
    assert text.lower().endswith("try again after midnight utc.")
    assert ("Upgrade for more" in text) is not paid


@pytest.mark.asyncio
async def test_start_reply_picture_draws_the_picture_part() -> None:
    drawn = AsyncMock(return_value=uuid4())
    with patch("app.modules.images.reply_picture.draw_unlinked", drawn):
        picture = start_reply_picture(
            _deps(can_use=True),
            Settings(),
            user=User(id=uuid4(), plan="pro"),
            chat_id=uuid4(),
            content="draw a cat wearing a hat and also explain what a black hole is",
        )
        assert picture is not None
        text, ids = await picture.attach("A black hole...")
    call = drawn.await_args
    assert call is not None and call.kwargs["prompt"] == "cat wearing a hat"
    assert len(ids) == 1 and text.startswith("[Image:")


def _identity() -> Any:
    user = SimpleNamespace(id=uuid4(), locale="en", plan="free")
    return SimpleNamespace(user=user, local_tz="UTC", geo=SimpleNamespace(user_location=None))


@pytest.mark.asyncio
async def test_settings_card_for_the_settings_part() -> None:
    plan = plan_turn("switch to dark mode, and also what is the capital of France?")
    materialize = AsyncMock(return_value=_CARD)
    with patch(
        "app.modules.chat.turn_prep.instant.settings_proposal_service.materialize_settings_reply",
        materialize,
    ):
        card = await settings_card(_identity(), Settings(), AsyncMock(), plan)
    assert card == _CARD
    call = materialize.await_args
    assert call is not None
    changes = call.args[2]
    assert [(change.field, change.value) for change in changes] == [("appearance", "dark")]


@pytest.mark.asyncio
async def test_a_multi_part_message_gets_no_instant_reply() -> None:
    """The settings card used to be the whole reply and drop "what is the capital"."""
    text = "switch to dark mode, and also what is the capital of France?"
    request = SimpleNamespace(content=text, has_image_attachment=False, recent_messages=[])
    reply = await resolve_instant_reply(
        request,  # type: ignore[arg-type]
        _identity(),
        Settings(),
        AsyncMock(),
        plan_turn(text),
    )
    assert reply is None


@pytest.mark.asyncio
async def test_settings_card_is_none_for_one_request() -> None:
    assert (
        await settings_card(_identity(), Settings(), AsyncMock(), plan_turn("switch to dark mode"))
        is None
    )

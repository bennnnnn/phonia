"""The clarify card a reply asks with: read, checked, and kept at most once, last."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.modules.chat.clarify_card import option_value, read_card, settle_clarify_cards
from app.modules.chat.finalize_passes import FinalizeState, run_finalize_passes
from app.modules.chat.finalize_text import settle_clarify
from app.modules.chat.turn_outcome import TurnOutcome
from app.modules.chat.turn_prep import StreamContext
from app.services.md_fence_scan import iter_fences
from app.tests.modules.chat.chat_test_support import turn_deps

_ASK = "But let me ask you one thing. What do you mean by *best*?"
# The lead-in fitted to a two-question card, with no options before it.
_ASK_FITTED_TWO = "**Let me ask you a couple of things.** What do you mean by *best*?"
_PRIORITY = {
    "id": "priority",
    "label": "Main priority",
    "question": "What matters most to you?",
    "options": ["💰 Making money", "🌿 Quality of life", "🛡️ Safety", "🎓 Education"],
}
_PRIORITY_VALUES = ["Making money", "Quality of life", "Safety", "Education"]
_LEVEL = {
    "id": "level",
    "label": "Studied it before",
    "question": "Have you studied integrals before?",
    "options": ["No, never", "A little", "Yes, I'm revising"],
}
_GOAL = {
    "id": "goal",
    "label": "What it's for",
    "question": "What do you need it for?",
    "options": ["An exam", "A class", "Curiosity"],
}
_ANSWER = " ".join(["An integral adds up tiny slices of an area under a curve."] * 5)


def _fence(card: dict[str, Any] | str) -> str:
    body = card if isinstance(card, str) else json.dumps(card)
    return f"```clarify\n{body}\n```"


def _card(text: str) -> dict[str, Any] | None:
    for fence in iter_fences(text):
        if fence.lang == "clarify":
            return json.loads(text[fence.body_start : fence.body_end])
    return None


def _values(question: dict[str, Any]) -> dict[str, Any]:
    return {**question, "values": question["options"]}


def test_a_valid_card_is_kept_last_in_its_normal_shape() -> None:
    card = {
        "request": "Recommend the best country for me.",
        "questions": [_PRIORITY, _LEVEL],
        "closing": "Compare the strongest options with practical pros and cons.",
        "submit": "Find my best country",
    }
    settled = settle_clarify_cards(f"{_ASK}\n\n{_fence(card)}", allowed=True)
    assert settled.startswith(_ASK_FITTED_TWO)
    assert settled.rstrip().endswith("```")
    assert _card(settled) == {
        "questions": [{**_PRIORITY, "values": _PRIORITY_VALUES}, _values(_LEVEL)],
        "request": "Recommend the best country for me.",
        "closing": "Compare the strongest options with practical pros and cons.",
        "submit": "Find my best country",
    }


def test_an_older_card_reads_without_its_when_and_multi() -> None:
    card = read_card(json.dumps({"when": "after", "questions": [{**_GOAL, "multi": True}]}))
    assert card is not None
    assert card.model_dump(exclude_defaults=True) == {"questions": [_values(_GOAL)]}


@pytest.mark.parametrize(
    ("question", "normal"),
    [
        # Trimmed, repeats dropped whatever their case, blanks dropped.
        (
            {**_LEVEL, "options": [" No, never ", "A little", "a little", "", "Yes"]},
            _values({**_LEVEL, "options": ["No, never", "A little", "Yes"]}),
        ),
        # The same choice with and without its emoji is one choice.
        (
            {**_GOAL, "options": ["📝 An exam", "An exam", "A class"]},
            {**_GOAL, "options": ["📝 An exam", "A class"], "values": ["An exam", "A class"]},
        ),
        # Flags, joined emoji and variation selectors leave the words; an emoji alone stays.
        (
            {**_GOAL, "options": ["🇨🇭 Switzerland", "👨‍👩‍👧 Family", "🛡️Safety", "🌍"]},
            {
                **_GOAL,
                "options": ["🇨🇭 Switzerland", "👨‍👩‍👧 Family", "🛡️Safety", "🌍"],
                "values": ["Switzerland", "Family", "Safety", "🌍"],
            },
        ),
        # No id or label: the place and the question name it.
        (
            {"question": "Which do you prefer?", "options": ["Video", "Text"]},
            {
                "id": "q1",
                "label": "Which do you prefer",
                "question": "Which do you prefer?",
                "options": ["Video", "Text"],
                "values": ["Video", "Text"],
            },
        ),
    ],
)
def test_read_card_normalises_a_question(question: dict[str, Any], normal: dict[str, Any]) -> None:
    card = read_card(json.dumps({"questions": [question]}))
    assert card is not None
    assert card.model_dump()["questions"] == [normal]


@pytest.mark.parametrize(
    ("option", "value"),
    [
        ("🇨🇭 Switzerland", "Switzerland"),
        ("👨‍👩‍👧 Family", "Family"),
        ("👍🏽 Yes", "Yes"),
        ("💰Making money", "Making money"),
        ("★ Top rated", "Top rated"),
        # A keycap is a digit, # or * with its mark: the emoji goes, not just the mark.
        ("1️⃣ Beginner", "Beginner"),
        ("#️⃣ Hashtags", "Hashtags"),
        # A symbol that is part of the words stays: the message says "°C", not "C".
        ("°C", "°C"),
        ("°F (Fahrenheit)", "°F (Fahrenheit)"),
        ("№1 choice", "№1 choice"),
        ("#1 pick", "#1 pick"),
        ("$500 or less", "$500 or less"),
    ],
)
def test_option_value_takes_off_a_leading_emoji_only(option: str, value: str) -> None:
    assert option_value(option) == value


def test_read_card_keeps_the_first_three_questions() -> None:
    questions = [{**_GOAL, "id": f"q{i}"} for i in range(5)]
    card = read_card(json.dumps({"questions": questions}))
    assert card is not None and [q.id for q in card.questions] == ["q0", "q1", "q2"]


def test_text_too_long_to_show_is_dropped_not_the_card() -> None:
    card = read_card(
        json.dumps(
            {"request": "x" * 201, "closing": "Short.", "submit": "y" * 41, "questions": [_GOAL]}
        )
    )
    assert card is not None
    assert (card.request, card.closing, card.submit) == ("", "Short.", "")


@pytest.mark.parametrize(
    "body",
    [
        "not json",
        "[]",
        json.dumps({"submit": "Go"}),
        json.dumps({"questions": []}),
        json.dumps({"questions": ["a question"]}),
        # One choice is not a choice, even after a repeat is dropped.
        json.dumps({"questions": [{**_LEVEL, "options": ["Yes", "yes"]}]}),
        json.dumps({"questions": [{**_LEVEL, "question": " "}]}),
        json.dumps({"questions": [{**_LEVEL, "options": ["x" * 81, "y"]}]}),
        json.dumps({"questions": [{**_LEVEL, "label": "x" * 61}]}),
    ],
)
def test_read_card_refuses_a_card_that_breaks_the_rules(body: str) -> None:
    assert read_card(body) is None


@pytest.mark.parametrize(
    ("options", "kept"),
    [
        # Ten choices keep the first eight.
        ([f"Choice {i}" for i in range(10)], [f"Choice {i}" for i in range(8)]),
        # A choice too long to tap is dropped, not the whole card.
        (["x" * 81, "Yes", "No"], ["Yes", "No"]),
    ],
)
def test_read_card_trims_choices_instead_of_dropping_the_card(
    options: list[str], kept: list[str]
) -> None:
    card = read_card(json.dumps({"questions": [{**_LEVEL, "options": options}]}))
    assert card is not None and card.questions[0].options == kept


def test_a_dropped_card_logs_its_reason_not_its_text(caplog: pytest.LogCaptureFixture) -> None:
    secret = "my salary is 4000"
    with caplog.at_level("INFO", logger="app.modules.chat.clarify_card"):
        assert (
            read_card(json.dumps({"questions": [{**_LEVEL, "question": " ", "label": secret}]}))
            is None
        )
    assert "clarify card dropped" in caplog.text and secret not in caplog.text


def test_one_card_only_and_it_moves_under_the_answer() -> None:
    second = {"questions": [_GOAL]}
    text = f"{_fence({'questions': [_LEVEL]})}\n\n{_ANSWER}\n\n{_fence(second)}"
    settled = settle_clarify_cards(text, allowed=True)
    assert settled.count("```clarify") == 1
    assert settled.startswith(_ANSWER)
    assert _card(settled)["questions"][0]["id"] == "level"  # type: ignore[index]


def test_a_broken_card_on_an_ask_keeps_its_questions_as_prose() -> None:
    broken = {"questions": [{**_LEVEL, "options": ["Only one"]}, _GOAL]}
    settled = settle_clarify_cards(f"{_ASK}\n\n{_fence(broken)}", allowed=True)
    assert "```clarify" not in settled
    assert settled == (
        f"{_ASK}\n\n- Have you studied integrals before? (Only one)\n"
        "- What do you need it for? (An exam / A class / Curiosity)"
    )


def test_unreadable_json_leaves_the_sentence() -> None:
    assert settle_clarify_cards(f"{_ASK}\n\n{_fence('{oops')}", allowed=True) == _ASK


def test_a_card_under_an_answer_that_cannot_be_shown_leaves_the_answer() -> None:
    broken = {"questions": [{**_GOAL, "options": ["Only"]}]}
    assert settle_clarify_cards(f"{_ANSWER}\n\n{_fence(broken)}", allowed=False) == _ANSWER


def test_a_turn_that_may_not_ask_keeps_the_questions_as_prose() -> None:
    text = f"{_ASK}\n\n{_fence({'questions': [_LEVEL]})}"
    settled = settle_clarify_cards(text, allowed=False)
    assert "```clarify" not in settled
    assert "- Have you studied integrals before? (No, never / A little" in settled


def test_a_reply_without_a_card_is_untouched() -> None:
    assert settle_clarify_cards(_ANSWER, allowed=True) == _ANSWER


def _state(raw: str, **ctx: Any) -> FinalizeState:
    context = StreamContext(
        user_id=uuid4(),
        chat_id=uuid4(),
        model="free-chat",
        prompt_messages=[{"role": "user", "content": "how can I understand integrals"}],
        run_title=False,
        user_message_content="how can I understand integrals",
        reserved_tokens=0,
        max_output_tokens=0,
        **ctx,
    )
    return FinalizeState(
        deps=turn_deps(),
        settings=Settings(),
        ctx=context,
        raw=raw,
        text=raw,
        usage={},
        outcome=TurnOutcome(),
        was_cancelled=False,
        assistant_parts=[raw],
        should_cancel=None,
    )


_ASKED = f"{_ASK}\n\n{_fence({'questions': [_PRIORITY, _GOAL]})}"


@pytest.mark.parametrize(
    "ctx",
    [
        {"verified_subject": MagicMock()},
        {"solver_unverified": True},
        {"instant_reply": "It's 9:00."},
        {"settings_card": "```settings_proposal\n{}\n```"},
        {"reply_picture": MagicMock()},
        {"answer_photo_ids": [uuid4()]},
    ],
)
def test_the_pass_drops_the_card_on_a_turn_that_never_asks(ctx: dict[str, Any]) -> None:
    assert "```clarify" not in settle_clarify(_state(_ASKED, **ctx))


@pytest.mark.parametrize("lang", ["answer", "reminder", "reminder_proposal", "photo"])
def test_the_pass_drops_the_card_beside_a_card_that_never_asks(lang: str) -> None:
    text = f"```{lang}\n12\n```\n\n{_ASKED}"
    assert "```clarify" not in settle_clarify(_state(text))


def test_the_turn_after_a_card_keeps_no_card_and_no_questions() -> None:
    # Live: "plan my week", the picks sent, and a second card came back.
    again = f"Got it! A couple more questions so the plan is realistic:\n\n{_ASKED}"
    settled = settle_clarify(_state(again, after_card=True))
    assert "```clarify" not in settled
    assert "?" not in settled


def test_after_a_card_the_prose_answer_stays_and_a_card_intro_goes() -> None:
    text = (
        f"{_ANSWER}\nOne more thing to tune it:\n\n"
        f"{_fence({'when': 'after', 'questions': [_GOAL]})}"
    )
    assert settle_clarify_cards(text, allowed=False, after_card=True) == _ANSWER


def test_after_a_card_the_ask_before_a_second_card_goes_with_it() -> None:
    plan = "Here is your week, built around finishing the thesis.\n\n1. Monday: outline."
    text = f"{plan}\n\n**But let me ask you one thing.**\n\nHow many hours a day?\n\n"
    text += _fence({"questions": [_GOAL]})
    assert settle_clarify_cards(text, allowed=False, after_card=True) == plan


def test_after_a_card_a_lone_intro_line_is_kept_so_the_reply_is_not_empty() -> None:
    text = f"A few more questions:\n\n{_fence({'when': 'first', 'questions': [_GOAL]})}"
    assert settle_clarify_cards(text, allowed=False, after_card=True) == "A few more questions:"


def test_the_pass_keeps_a_card_on_an_open_question() -> None:
    state = _state(_ASKED)
    assert _card(settle_clarify(state)) is not None
    assert state.committed is not None


async def test_every_finalize_pass_leaves_a_valid_card_whole() -> None:
    state = _state(_ASKED)
    assert await run_finalize_passes(state)
    card = _card(state.text)
    assert card is not None and [q["id"] for q in card["questions"]] == ["priority", "goal"]
    assert state.text.startswith(_ASK_FITTED_TWO)


async def test_an_unclosed_card_is_closed_then_read() -> None:
    state = _state(_ASKED.removesuffix("\n```"))
    assert await run_finalize_passes(state)
    assert _card(state.text) is not None


def _card_body(*questions: dict[str, Any]) -> str:
    return json.dumps(
        {
            "questions": list(questions),
            "request": "Recommend a laptop for me.",
            "closing": "Compare the options.",
            "submit": "Find my laptop",
        }
    )


@pytest.mark.parametrize(
    ("before", "questions", "lead_in"),
    [
        # Live: no options before it and two questions, yet "But … one thing".
        ("To recommend the best laptop, I need to know more.", 2, "**Let me ask you a couple of things.**"),
        ("To plan your week, I need one detail.", 1, "**Let me ask you one thing.**"),
        # After the strongest options, the "But" reads right.
        ("🇨🇭 **Switzerland — quality of life**\n\n🇸🇬 **Singapore — safety**", 1, "**But let me ask you one thing.**"),
        ("🇨🇭 **Switzerland — quality of life**", 3, "**But let me ask you a few things.**"),
    ],
)  # fmt: skip
def test_the_lead_in_fits_the_start_and_the_card(before: str, questions: int, lead_in: str) -> None:
    asked = [_PRIORITY, _LEVEL, _GOAL][:questions]
    text = f"{before}\n\n**But let me ask you one thing.**\n\nWhat matters most?\n\n"
    text += f"```clarify\n{_card_body(*asked)}\n```"
    settled = settle_clarify_cards(text, allowed=True)
    assert lead_in in settled
    assert settled.lower().count("let me ask you") == 1


def test_a_lead_in_that_opens_its_line_fits_too() -> None:
    # Live: the model went on after the bold lead-in on the same line.
    text = "I need more detail.\n\n**But let me ask you one thing.** Your use and budget?\n\n"
    text += f"```clarify\n{_card_body(_PRIORITY, _LEVEL)}\n```"
    settled = settle_clarify_cards(text, allowed=True)
    assert "**Let me ask you a couple of things.** Your use and budget?" in settled


def test_a_card_written_in_a_json_fence_is_shown_as_the_card() -> None:
    # Live: the model fenced the card as ```json and the user would have seen raw JSON.
    text = f"It depends.\n\n**Let me ask you one thing.**\n\n```json\n{_card_body(_PRIORITY)}\n```"
    settled = settle_clarify_cards(text, allowed=True)
    assert "```json" not in settled
    assert "```clarify" in settled


def test_a_json_answer_the_user_asked_for_stays_code() -> None:
    quiz = json.dumps({"questions": [{"question": "2 + 2?", "options": ["3", "4"]}]})
    text = f"Here is your quiz:\n\n```json\n{quiz}\n```"
    assert settle_clarify_cards(text, allowed=True) == text


@pytest.mark.parametrize(
    ("start", "kept"),
    [
        (
            "A $400,000 house is a big purchase, Dev. Before I run numbers, I need a few "
            "details, so let me ask.",
            "A $400,000 house is a big purchase, Dev.",
        ),
        # The whole start stays: the lead-in never opens a reply on its own.
        ("I have a couple of quick questions first.", None),
        ("To find you the best laptop under 800 dollars, I need a few details.", None),
        ("Rates are high.\nI need some details.", "Rates are high."),
        ("It depends on you.\n\nSo let me ask.", "It depends on you."),
        # Anything more than the ask stays.
        ("To plan your week, I need one detail.", None),
        ("Let me know what matters most. It depends.", None),
        ("At 6.5% over 30 years, $400,000 is about $2,528 a month, but let me ask a few "
         "things to refine it.", None),
        ("I can estimate it now, but I'll need some details to be exact: your rate.", None),
        ("Let me ask: do you already own a home? It changes the math.", None),
        ('Your lender may say "let me ask underwriting." That can take a week.', None),
        ("Dr. Smith said rates are 6.5%. E.g. let me ask about taxes first.", None),
        ("+ Rent: let me ask about cost.", None),
        ("a | let me ask | b", None),
        ("```python\n    print('let me ask.  ok')\n```", None),
        (
            "🇨🇭 **Switzerland — quality of life**\nHigh pay, so let me ask where you'd live.",
            None,
        ),
    ],
)  # fmt: skip
def test_a_start_that_only_says_it_will_ask_says_it_once(start: str, kept: str | None) -> None:
    text = f"{start}\n\n**Let me ask you one thing.**\n\nWhat matters most?\n\n"
    text += f"```clarify\n{_card_body(_PRIORITY)}\n```"

    settled = settle_clarify_cards(text, allowed=True)

    before = settled.split("**Let me ask")[0].split("**But let me ask")[0]
    assert before.rstrip("\n") == (start if kept is None else kept)
    assert not before.startswith("\n")


def test_but_follows_options_left_after_the_ask_goes() -> None:
    text = "A house is a **big** purchase, so let me ask.\n\n**Let me ask you one thing.**\n\n"
    text += f"```clarify\n{_card_body(_PRIORITY)}\n```"

    settled = settle_clarify_cards(text, allowed=True)

    assert settled.startswith("A house is a **big** purchase, so let me ask.\n\n**But let me")


def test_a_bare_json_card_is_put_in_its_fence() -> None:
    body = _card_body(_PRIORITY)
    text = f"It depends on your goal.\n\n🎯 **What's the main goal?**\n\n{body}"

    settled = settle_clarify_cards(text, allowed=True)

    assert settled.endswith("```")
    assert "\n```clarify\n" in settled
    assert settled.count('"questions"') == 1
    assert read_card(settled.split("```clarify\n")[1].rsplit("```", 1)[0]) is not None


@pytest.mark.parametrize(
    "text",
    [
        # JSON the user asked for, and a card already in code, stay as they are.
        'Here is the object:\n\n{"questions": [1, 2], "answer": 3}',
        '```python\nx = {"request": 1, "questions": [], "submit": 2}\n```',
        "Plain prose only.",
    ],
)
def test_other_json_is_not_a_card(text: str) -> None:
    assert settle_clarify_cards(text, allowed=True) == text


def test_the_finalize_pass_fences_a_bare_card() -> None:
    raw = f"It depends on your goal.\n\n🎯 **What's the main goal?**\n\n{_card_body(_PRIORITY)}"

    settled = settle_clarify(_state(raw))

    assert _card(settled) is not None
    assert not settled.rstrip().endswith("}")


def test_a_bare_card_with_blank_lines_inside_is_one_card() -> None:
    body = json.dumps(json.loads(_card_body(_PRIORITY)), indent=2).replace("],\n", "],\n\n")
    text = f"It depends.\n\n{body}\n\nThanks!"

    settled = settle_clarify_cards(text, allowed=True)

    assert '"questions"' in settled and settled.count("```clarify") == 1
    assert "Thanks!" in settled


def test_a_plain_lead_in_is_fitted_and_bolded() -> None:
    # Live (2026-10-29): plain "Let me ask you one thing." over a two-question card.
    text = "I can help with that!\n\nLet me ask you one thing.\n\nWhat matters most?\n\n"
    text += f"```clarify\n{_card_body(_PRIORITY, _LEVEL)}\n```"
    settled = settle_clarify_cards(text, allowed=True)
    assert "**Let me ask you a couple of things.**" in settled
    assert settled.lower().count("let me ask you") == 1


@pytest.mark.parametrize(
    "line",
    [
        "Let me ask you one thing about your budget before I pick.",
        "Let me ask you one thing, then I will draft it.",
    ],
)
def test_a_plain_sentence_that_goes_on_is_left_as_prose(line: str) -> None:
    text = f"I can help with that!\n\n{line}\n\n```clarify\n{_card_body(_PRIORITY, _LEVEL)}\n```"
    settled = settle_clarify_cards(text, allowed=True)
    assert line in settled
    assert "**" not in settled.split("```")[0]

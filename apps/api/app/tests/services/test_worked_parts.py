"""One layout for every worked answer in parts (``services/worked_parts``).

"A ball is dropped from 20 m. What's its speed after 1 s? How long to reach the ground?"
came back as two whole replies: the givens under each part, the part above its givens and
no card under either answer (2026-11-01). It now reads Given and Required once, then
Solution and each part closed by its own card, and the cards reach the saved reply.
"""

from __future__ import annotations

import re
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.modules.chat.finalize_passes import FinalizeState
from app.modules.chat.finalize_subjects import (
    check_chemistry_fences,
    check_math_fences,
    check_physics_fences,
    mark_server_cards,
)
from app.modules.chat.turn_outcome import TurnOutcome
from app.modules.chat.turn_prep import StreamContext
from app.services.answer_fence import VERIFIED_ANSWER_MARKER
from app.services.subjects.dispatch import build_subject_augmentation
from app.services.subjects.registry import subject_adapter
from app.services.worked_parts import (
    WorkedPart,
    merged_given,
    parts_in_one_layout,
    read_worked_reply,
    render_parts,
)
from app.services.workout import Workout, math_line, render_workout
from app.tests.modules.chat.chat_test_support import turn_deps

_SETTINGS = Settings.model_validate({})
_SETUP = "A ball is dropped from 20 m."
_QUESTIONS = ("What's its speed after 1 s?", "How long to reach the ground?")
_PARTS = tuple(f"{_SETUP} {question}" for question in _QUESTIONS)
_WHOLE = " ".join([_SETUP, *_QUESTIONS])


def _headings(text: str) -> list[str]:
    return re.findall(r"^\*\*([^*\n]+)\*\*", text, re.M)


def test_merged_given_names_each_value_and_symbol_once() -> None:
    lines = merged_given(
        [
            "$g = 9.81$",
            "$h_0 = 20$",
            "where $g$ = gravity, $h_0$ = starting height",
            "$g = 9.81$",
            "$t = 1$",
            "where $g$ = gravity, $t$ = time",
        ]
    )
    assert lines == [
        "$g = 9.81$",
        "$h_0 = 20$",
        "$t = 1$",
        "where $g$ = gravity, $h_0$ = starting height, $t$ = time",
    ]


def test_merged_given_keeps_a_group_of_symbols_together() -> None:
    lines = merged_given(["where $m_1$, $m_2$ = masses; $r$ = distance", "where $r$ = distance"])
    assert lines == ["where $m_1$, $m_2$ = masses; $r$ = distance"]


def test_render_parts_is_one_layout() -> None:
    working = render_workout(
        Workout(formula=(math_line("v = gt"),), formula_heading="Constant acceleration formula"),
        answer_heading=None,
    )
    text = render_parts(
        [
            WorkedPart(
                "What's its speed after 1 s?",
                working,
                "9.81",
                required=("$v$ — speed",),
                given=("$g = 9.81$",),
            ),
            WorkedPart(
                "How long to reach the ground?",
                working,
                "2.02",
                required=("$t$ — time",),
                given=("$g = 9.81$",),
            ),
        ]
    )
    assert _headings(text) == [
        "Given",
        "Required",
        "Solution",
        "(a) What's its speed after 1 s?",
        "Constant acceleration formula",
        "Answer (a)",
        "(b) How long to reach the ground?",
        "Constant acceleration formula",
        "Answer (b)",
    ]
    assert "(a) $v$ (speed)  \n(b) $t$ (time)" in text
    assert re.findall(r"```answer\n(.*?)\n```", text) == ["9.81", "2.02"]


def test_a_reply_with_a_lead_is_not_read_as_the_layout() -> None:
    assert (
        read_worked_reply("Here it is.\n\n**Given**  \n$x$\n\n**Answer**\n\n```answer\n1\n```")
        is None
    )
    assert read_worked_reply("**Given**  \n$x$\n\n**Required**  \n$y$\n\n**Answer**") is None


async def test_the_ball_dropped_from_20_m_is_one_layout() -> None:
    found = await build_subject_augmentation(_WHOLE, _SETTINGS, parts=_PARTS, parts_answer_all=True)

    text = found.direct_text or ""
    # The part is the student's own question; what it finds is named by the solver.
    assert _headings(text)[:4] == [
        "Given",
        "Required",
        "Solution",
        "(a) What's its speed after 1 s?",
    ]
    assert text.split("**Solution**")[0].count("**Given**") == 1
    assert text.count("**Required**") == 1
    assert "(a) $v$ (speed)  \n(b) $t$ (time)" in text
    assert text.split("**Solution**")[0].count("where ") == 1
    # Every part ends with its own card, in the reply the phone streams.
    assert re.findall(r"\*\*Answer \(([ab])\)\*\*\n\n```answer\n", text) == ["a", "b"]


async def test_each_part_keeps_its_card_in_the_saved_reply() -> None:
    found = await build_subject_augmentation(_WHOLE, _SETTINGS, parts=_PARTS, parts_answer_all=True)
    assert found.direct_text is not None
    state = FinalizeState(
        deps=turn_deps(math_fence=subject_adapter("math").fence),
        settings=_SETTINGS,
        ctx=StreamContext(
            user_id=uuid4(),
            chat_id=uuid4(),
            model="free-chat",
            prompt_messages=[{"role": "user", "content": _WHOLE}],
            run_title=False,
            user_message_content=_WHOLE,
            reserved_tokens=0,
            max_output_tokens=0,
            verified_subject=found.verified,
            instant_reply=found.direct_text,
        ),
        raw=found.direct_text,
        text=found.direct_text,
        usage={},
        outcome=TurnOutcome(),
        was_cancelled=False,
        assistant_parts=[found.direct_text],
        should_cancel=None,
    )

    # The subject passes the saved reply goes through, in order (``finalize_passes``).
    state.text = check_chemistry_fences(state)
    state.text = check_physics_fences(state)
    state.text = await check_math_fences(state)
    saved = mark_server_cards(state)

    cards = re.findall(r"^```answer\n(.*?)\n```", saved, re.S | re.M)
    assert len(cards) == 2
    assert all(card.startswith(VERIFIED_ANSWER_MARKER) for card in cards)
    assert "9.81" in cards[0] and "2.02" in cards[1]


def test_render_parts_drops_no_part_past_h() -> None:
    parts = [WorkedPart(f"Part {n}", "$x = 1$", str(n), required=("$x$",)) for n in range(10)]
    text = render_parts(parts)
    assert len(re.findall(r"```answer\n", text)) == 10
    assert "**Answer (j)**" in text and "(j) $x$" in text


@pytest.mark.parametrize(
    "question",
    ["What's its speed after 1 s?", "How far does it travel in 3 s?", "How long is the rope?"],
)
def test_a_part_is_labelled_by_its_question_as_written(question: str) -> None:
    reply = (
        "**Given**  \n$x = 1$\n\n**Required**  \n$y$\n\n**Solution**\n\n"
        "**Formula**  \n$y = x$\n\n**Answer**\n\n```answer\n1\n```\n"
    )
    text = parts_in_one_layout([question, "What is x?"], [reply, reply]) or ""
    assert f"**(a) {question}**" in text
    assert "(a) $y$  \n(b) $y$" in text


def _sections_of(text: str) -> tuple[str, list[str]]:
    """The opening (up to Solution) and each part's text."""
    opening, _, parts = text.partition("**Solution**")
    return opening, parts.split("\n\n---\n\n")


async def test_a_given_only_one_part_uses_is_listed_at_that_part() -> None:
    found = await build_subject_augmentation(_WHOLE, _SETTINGS, parts=_PARTS, parts_answer_all=True)

    opening, (first, second) = _sections_of(found.direct_text or "")
    # t = 1 s is (a)'s alone: never in the shared Given beside Required (b) $t$.
    assert "$t = 1" not in opening and "$h_0 = 20" in opening
    assert first.index("**Given**  \n$t = 1") < first.index("**Constant acceleration formula**")
    assert "where $t$ = time" in first
    assert "**Given**" not in second


async def test_separate_problems_keep_their_own_givens() -> None:
    parts = (
        "A car goes 100 m in 5 s; find its speed.",
        "A train goes 300 m in 10 s; find its speed.",
    )
    found = await build_subject_augmentation(
        " ".join(parts), _SETTINGS, parts=parts, parts_answer_all=True
    )

    opening, (car, train) = _sections_of(found.direct_text or "")
    assert "**Given**" not in opening  # nothing is shared
    assert "$d = 100" in car and "$t = 5" in car and "$d = 300" not in car
    assert "$d = 300" in train and "$t = 10" in train and "$d = 100" not in train
    assert re.findall(r"\*\*Answer \(([ab])\)\*\*\n\n```answer\n", found.direct_text or "") == [
        "a",
        "b",
    ]


async def test_three_parts_share_their_setup() -> None:
    setup = "A ball is dropped from 45 m."
    questions = (
        "How long to reach the ground?",
        "What's its speed after 1 s?",
        "What's its speed after 2 s?",
    )
    parts = tuple(f"{setup} {question}" for question in questions)
    found = await build_subject_augmentation(
        " ".join([setup, *questions]), _SETTINGS, parts=parts, parts_answer_all=True
    )

    text = found.direct_text or ""
    opening, sections = _sections_of(text)
    assert "$h_0 = 45" in opening and "$t = " not in opening
    assert "(a) $t$ (time)  \n(b) $v$ (speed)  \n(c) $v$ (speed)" in opening
    assert "**Given**" not in sections[0]
    assert "$t = 1" in sections[1] and "$t = 2" in sections[2]
    assert len(re.findall(r"^```answer\n", text, re.M)) == 3

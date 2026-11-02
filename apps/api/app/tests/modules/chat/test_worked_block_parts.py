"""A ```worked block in parts goes through the one parts layout the server's own parts use.

"A car goes 100 m in 5 s; find its speed. A train goes 300 m in 10 s; find its speed."
came back from the model (2026-11-01) with both cars' givens in one Given (d twice, t
twice), an empty "(b) speed of the car" and the train as (c): the car was worked before
its ``part`` label, which then opened a part of its own. Now a part's givens are its own,
a part that holds nothing is left out, a letter named again is that part, and the parts
are lettered in the order shown.
"""

from __future__ import annotations

import itertools
import re

import pytest

from app.modules.chat.stream_accum import StreamAccum
from app.modules.chat.worked_render import WorkedLayout, render_worked
from app.modules.chat.worked_solution import assemble, read_record
from app.modules.chat.worked_stream import ReplyFilter
from app.services.workout import asked_line

PHYSICS = WorkedLayout(law_heading=True)

_CAR = (
    "formula: Average speed | v = \\frac{d}{t}\nsubstitution: v = \\frac{100}{5}\n"
    "substitution: v = 20\\,\\mathrm{m/s}\nanswer: v | 20 | m/s"
)
_TRAIN = (
    "formula: Average speed | v = \\frac{d}{t}\nsubstitution: v = \\frac{300}{10}\n"
    "substitution: v = 30\\,\\mathrm{m/s}\nanswer: v | 30 | m/s"
)
_ASKED = "required: v | speed of the car\nrequired: v | speed of the train"
_CAR_GIVEN = "given: d | 100 | m | distance\ngiven: t | 5 | s | time"
_TRAIN_GIVEN = "given: d | 300 | m | distance\ngiven: t | 10 | s | time"

# The contract: what is asked first, then each part with its own givens.
CONTRACT = (
    f"{_ASKED}\npart: a | speed of the car\n{_CAR_GIVEN}\n{_CAR}\n"
    f"part: b | speed of the train\n{_TRAIN_GIVEN}\n{_TRAIN}"
)
# Every given first, as the contract asked before November 2026.
GIVENS_FIRST = (
    f"{_CAR_GIVEN}\n{_TRAIN_GIVEN}\n{_ASKED}\npart: a | speed of the car\n{_CAR}\n"
    f"part: b | speed of the train\n{_TRAIN}"
)
# The live reply: the car worked before its label, then "part: a" and "part: b".
LIVE = (
    f"{_CAR_GIVEN}\n{_ASKED}\n{_CAR}\npart: a | speed of the car\n"
    f"part: b | speed of the train\n{_TRAIN_GIVEN}\n{_TRAIN}"
)


def _laid_out(block: str) -> str:
    records = [read_record(line) for line in block.split("\n")]
    return render_worked(assemble([r for r in records if r is not None]), PHYSICS)


def _opening_and_parts(text: str) -> tuple[str, list[str]]:
    opening, _, parts = text.partition("**Solution**")
    return opening, parts.split("\n\n---\n\n")


@pytest.mark.parametrize("block", [CONTRACT, GIVENS_FIRST, LIVE])
def test_two_questions_are_two_parts_each_with_its_own_givens(block: str) -> None:
    text = _laid_out(block)
    opening, (car, train) = _opening_and_parts(text)
    assert "**Given**" not in opening  # nothing is shared
    assert "**Required**  \n(a) $v$ (speed of the car)  \n(b) $v$ (speed of the train)" in opening
    assert car.strip().startswith("**(a) speed of the car**\n\n**Given**  \n$d = 100")
    assert "$t = 5" in car and "where $d$ = distance, $t$ = time" in car
    assert "$d = 300" not in car
    assert train.startswith("**(b) speed of the train**\n\n**Given**  \n$d = 300")
    assert "$t = 10" in train and "$d = 100" not in train
    assert re.findall(r"\*\*Answer \(([a-z])\)\*\*", text) == ["a", "b"]


def test_every_shape_is_the_same_layout() -> None:
    assert _laid_out(CONTRACT) == _laid_out(GIVENS_FIRST) == _laid_out(LIVE)


def test_a_given_every_part_uses_is_given_once() -> None:
    block = (
        "given: h | 20 | m | height\nrequired: v | speed after 1 s\nrequired: t | time to fall\n"
        "part: a | speed after 1 s\ngiven: g | 9.8 | m/s^2 | gravity\ngiven: t | 1 | s | time\n"
        "formula: Free fall | v = g t\nanswer: v | 9.8 | m/s\n"
        "part: b | time to fall\ngiven: g | 9.8 | m/s^2 | gravity\n"
        "formula: Free fall | t = \\sqrt{2h/g}\nanswer: t | 2.02 | s"
    )
    opening, (first, second) = _opening_and_parts(_laid_out(block))
    assert "$h = 20" in opening and "$g = 9.8" in opening
    assert "where $h$ = height, $g$ = gravity" in opening
    assert "$t = 1" not in opening and "$g = " not in first + second
    assert "**Given**  \n$t = 1\\,\\mathrm{s}$  \nwhere $t$ = time" in first
    assert "**Given**" not in second


def test_a_letter_named_again_is_that_part_and_an_empty_part_is_left_out() -> None:
    block = (
        "part: a | speed\nformula: Speed | v = d/t\npart: b | time\npart: c | nothing\n"
        "part: a\nanswer: v | 20 | m/s\npart: d | distance\nformula: Distance | d = v t\n"
        "answer: d | 100 | m"
    )
    text = _laid_out(block)
    assert re.findall(r"^\*\*\(([a-z])\) ([^*]+)\*\*$", text, re.M) == [
        ("a", "speed"),
        ("b", "distance"),
    ]
    assert re.findall(r"\*\*Answer \(([a-z])\)\*\*", text) == ["a", "b"]


@pytest.mark.parametrize("size", [1, 5, 10_000])
def test_parts_with_their_own_givens_stream_without_a_rewrite(size: int) -> None:
    reply = f"```worked\n{CONTRACT}\n```"
    accum = StreamAccum()
    reply_filter = ReplyFilter(accum, PHYSICS)
    seen: list[str] = []
    for start in range(0, len(reply), size):
        if sent := reply_filter.feed(reply[start : start + size]):
            accum.shown.append(sent)
        seen.append("".join(accum.shown))
    if tail := reply_filter.flush():
        accum.shown.append(tail)
    assert not accum.rewritten
    assert "".join(accum.shown).strip() == _laid_out(CONTRACT)
    for earlier, later in itertools.pairwise(seen):
        assert later.startswith(earlier)


@pytest.mark.parametrize(
    ("line", "inline"),
    [
        ("$v$ — speed", "$v$ (speed)"),
        (
            "(a) $d$ — displacement of the car (due East)",
            "(a) $d$ (displacement of the car (due East))",
        ),
        ("$a — b$", "$a — b$"),
        ("$t$", "$t$"),
        ("$v$ (speed)", "$v$ (speed)"),
    ],
)
def test_what_is_asked_names_its_meaning_inline(line: str, inline: str) -> None:
    assert asked_line(line) == inline


def test_a_single_part_names_what_it_finds_inline_and_keeps_its_where_line() -> None:
    text = _laid_out(f"{_CAR_GIVEN}\nrequired: v | speed of the car\n{_CAR}")
    assert "**Required**  \n$v$ (speed of the car)\n" in text
    assert "where $d$ = distance, $t$ = time" in text
    assert " — " not in text

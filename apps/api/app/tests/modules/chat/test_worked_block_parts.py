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
from types import SimpleNamespace
from typing import cast

import pytest

from app.modules.chat.finalize_passes import FinalizeState
from app.modules.chat.finalize_subjects import check_working
from app.modules.chat.stream_accum import StreamAccum
from app.modules.chat.worked_render import WorkedLayout, render_worked
from app.modules.chat.worked_solution import Given, assemble, read_record
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

# The contract since 2026-11-02: every given first, a part's own lettered, then what is
# asked, then each part.
CONTRACT = (
    "given (a): d | 100 | m | distance\ngiven (a): t | 5 | s | time\n"
    "given (b): d | 300 | m | distance\ngiven (b): t | 10 | s | time\n"
    f"{_ASKED}\npart: a | speed of the car\n{_CAR}\n"
    f"part: b | speed of the train\n{_TRAIN}"
)
# The contract before: what is asked first, then each part with its own givens.
PART_GIVENS = (
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
# Each part's label after its answer (live, 2026-11-02): what follows is the next part.
TRAILING = (
    f"{_CAR_GIVEN}\nrequired: v | speed of the car\n{_CAR}\npart: a | speed of the car\n"
    f"{_TRAIN_GIVEN}\nrequired: v | speed of the train\n{_TRAIN}\npart: b | speed of the train"
)
# The car unlabelled, then the train labelled "a" and every record lettered (a) (live,
# 2026-11-02): the label names what the second thing asked finds, so it is part (b).
MISLETTERED = (
    f"{_CAR_GIVEN}\nrequired: v | speed of the car\n{_CAR}\npart: a | speed of the train\n"
    + "\n".join(
        line.replace(":", " (a):", 1)
        for line in f"{_TRAIN_GIVEN}\nrequired: v | speed of the train\n{_TRAIN}".split("\n")
    )
)
# No label at all (live, 2026-11-01): two laws one after the other, both answers at the end.
_WORKING = "\n".join(line for line in _CAR.split("\n") if not line.startswith("answer"))
UNLABELLED = (
    f"{_CAR_GIVEN}\n{_TRAIN_GIVEN}\n{_ASKED}\n{_WORKING}\n"
    + "\n".join(line for line in _TRAIN.split("\n") if not line.startswith("answer"))
    + "\nanswer: v | 20 | m/s\nanswer: v | 30 | m/s"
)


def _laid_out(block: str) -> str:
    records = [read_record(line) for line in block.split("\n")]
    return render_worked(assemble([r for r in records if r is not None]), PHYSICS)


def _opening_and_parts(text: str) -> tuple[str, list[str]]:
    opening, _, parts = text.partition("**Solution**")
    return opening, parts.split("\n\n---\n\n")


_ONE_GIVEN = (
    "**Given**  \n(a) $d = 100\\,\\mathrm{m}$  \n(a) $t = 5\\,\\mathrm{s}$  \n"
    "(b) $d = 300\\,\\mathrm{m}$  \n(b) $t = 10\\,\\mathrm{s}$  \n"
    "where $d$ = distance, $t$ = time\n\n"
)


@pytest.mark.parametrize(
    "block", [CONTRACT, PART_GIVENS, GIVENS_FIRST, LIVE, TRAILING, MISLETTERED, UNLABELLED]
)
def test_two_questions_have_one_given_lettered_by_part(block: str) -> None:
    text = _laid_out(block)
    opening, (car, train) = _opening_and_parts(text)
    # One Given, every value lettered by the part that uses it; none under a part.
    assert text.count("**Given**") == 1
    assert opening.startswith(_ONE_GIVEN)
    assert "**Required**  \n(a) $v$ (speed of the car)  \n(b) $v$ (speed of the train)" in opening
    assert car.strip().startswith("**(a) speed of the car**\n\n**Average speed formula**")
    assert "30\\," not in car
    assert train.startswith("**(b) speed of the train**\n\n**Average speed formula**")
    assert re.findall(r"\*\*Answer \(([a-z])\)\*\*", text) == ["a", "b"]
    assert car.rstrip().endswith("$20\\,\\mathrm{m/s}$")
    assert train.rstrip().endswith("$30\\,\\mathrm{m/s}$")


def test_parts_with_nothing_asked_still_list_what_each_part_finds() -> None:
    # Live: the model wrote the parts with no ``required`` record at all.
    text = _laid_out(CONTRACT.replace(f"{_ASKED}\n", ""))
    assert text == _laid_out(CONTRACT)


def test_every_shape_is_the_same_layout() -> None:
    shapes = (CONTRACT, PART_GIVENS, GIVENS_FIRST, LIVE, TRAILING, MISLETTERED, UNLABELLED)
    assert len({_laid_out(block) for block in shapes}) == 1


def test_a_symbol_the_parts_name_apart_is_named_once_by_what_they_share() -> None:
    block = TRAILING.replace("| distance", "| distance for car", 1).replace(
        "d | 300 | m | distance", "d | 300 | m | distance for train"
    )
    opening, _parts = _opening_and_parts(_laid_out(block))
    assert "where $d$ = distance, $t$ = time\n" in opening


def test_a_part_titled_with_the_contracts_placeholder_is_named_by_what_is_asked() -> None:
    text = _laid_out(CONTRACT.replace("part: b | speed of the train", "part: b | what is asked"))
    assert "**(b) speed of the train**" in text and "what is asked" not in text


@pytest.mark.parametrize(
    ("line", "part"),
    [
        ("given (a): t | 1 | s | time", "a"),
        ("given(B): t | 1 | s", "b"),
        ("given: (c) t | 1 | s", "c"),
        ("given: t | 1 | s", ""),
    ],
)
def test_a_given_reads_its_part_letter(line: str, part: str) -> None:
    record = read_record(line)
    assert isinstance(record, Given) and record.symbol == "t" and record.part == part


def test_one_question_asking_one_thing_stays_whole_whatever_laws_it_uses() -> None:
    block = (
        "given: m | 2 | kg\ngiven: a | 3 | m/s^2\nrequired: W | work done\n"
        "formula: Newton's second law | F = m a\nsubstitution: F = 6\\,\\mathrm{N}\n"
        "formula: Work | W = F d\nsubstitution: W = 6 \\times 4\nanswer: W | 24 | J"
    )
    text = _laid_out(block)
    assert "**(a)" not in text and "---" not in text
    assert "**Answer**" in text


def test_a_given_every_part_uses_is_given_once() -> None:
    block = (
        "given: h | 20 | m | height\nrequired: v | speed after 1 s\nrequired: t | time to fall\n"
        "part: a | speed after 1 s\ngiven: g | 9.8 | m/s^2 | gravity\ngiven: t | 1 | s | time\n"
        "formula: Free fall | v = g t\nanswer: v | 9.8 | m/s\n"
        "part: b | time to fall\ngiven: g | 9.8 | m/s^2 | gravity\n"
        "formula: Free fall | t = \\sqrt{2h/g}\nanswer: t | 2.02 | s"
    )
    opening, (first, second) = _opening_and_parts(_laid_out(block))
    assert opening.startswith(
        "**Given**  \n$h = 20\\,\\mathrm{m}$  \n$g = 9.8\\,\\mathrm{m/s²}$  \n"
        "(a) $t = 1\\,\\mathrm{s}$  \nwhere $h$ = height, $g$ = gravity, $t$ = time\n"
    )
    assert "**Given**" not in first + second


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


def test_a_first_label_with_no_letter_and_no_matching_ask_is_part_a() -> None:
    # Review of #2238: "part: 1 | car" names no letter and no ask; it is the first part.
    block = (
        "required: v | speed of the car\nrequired: u | speed of the train\n"
        "part: 1 | car\nformula: Speed | v = d/t\nanswer: v | 20 | m/s\n"
        "part: 2 | train\nformula: Speed | u = d/t\nanswer: u | 30 | m/s"
    )
    records = [read_record(line) for line in block.split("\n")]
    solution = assemble([r for r in records if r is not None])
    assert [(part.letter, part.title) for part in solution.parts] == [
        ("a", "car"),
        ("b", "train"),
    ]


def test_an_unlabelled_block_in_parts_only_grows_while_it_streams() -> None:
    accum = StreamAccum()
    reply_filter = ReplyFilter(accum, PHYSICS)
    seen: list[str] = []
    reply = f"```worked\n{UNLABELLED}\n```"
    for start in range(0, len(reply), 3):
        if sent := reply_filter.feed(reply[start : start + 3]):
            accum.shown.append(sent)
        seen.append("".join(accum.shown))
    for earlier, later in itertools.pairwise(seen):
        assert later.startswith(earlier)
    if tail := reply_filter.flush():
        accum.shown.append(tail)
    # Its givens reach their parts once the block is whole; done carries that text.
    assert "".join(accum.shown).strip() == _laid_out(UNLABELLED)


def test_givens_after_a_part_label_reach_the_one_given_when_the_block_is_whole() -> None:
    # The contract before 2026-11-02: each part's givens after its label. They wait at
    # the part while it streams, then the finished reply has one Given (done carries it).
    reply = f"```worked\n{PART_GIVENS}\n```"
    accum = StreamAccum()
    reply_filter = ReplyFilter(accum, PHYSICS)
    for start in range(0, len(reply), 5):
        if sent := reply_filter.feed(reply[start : start + 5]):
            accum.shown.append(sent)
    if tail := reply_filter.flush():
        accum.shown.append(tail)
    final = "".join(accum.shown).strip()
    assert final == _laid_out(PART_GIVENS) and final.count("**Given**") == 1


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


_LETTERED = "**Required**  \n(a) $v$ (speed of the car)  \n(b) $v$ (speed of the train)\n"


@pytest.mark.parametrize(
    "asked",
    [
        "",  # none
        "required: v | average speed\n",  # one for both parts (live, 2026-11-02)
        f"{_ASKED}\n",  # one per part
    ],
)
def test_what_is_asked_has_one_lettered_line_per_part(asked: str) -> None:
    opening, _parts = _opening_and_parts(_laid_out(CONTRACT.replace(f"{_ASKED}\n", asked)))
    assert _LETTERED in opening


def test_untitled_parts_mean_what_their_one_record_asks() -> None:
    block = (
        f"{_CAR_GIVEN}\nrequired: v | average speed\npart: a\n{_CAR}\npart: b\n"
        "formula: Average speed | v = \\frac{d}{t}\nanswer: v | 30 | m/s\n"
        "part: c\nformula: Time | t = \\frac{d}{v}\nanswer: t | 5 | s"
    )
    opening, _parts = _opening_and_parts(_laid_out(block))
    assert (
        "**Required**  \n(a) $v$ (average speed)  \n(b) $v$ (average speed)  \n(c) $t$\n"
    ) in opening


def test_one_part_keeps_its_one_unlettered_line_however_it_was_asked() -> None:
    for asked in ("", "required: v | speed of the car\n"):
        text = _laid_out(f"{_CAR_GIVEN}\n{asked}part: a | speed of the car\n{_CAR}")
        assert "**Required**  \n$v$ (speed of the car)\n" in text
        assert "(a) $v$" not in text


def test_the_finished_reply_letters_what_is_asked_and_states_each_answer_once() -> None:
    # Live 2026-11-02: one `required` for both parts, and a closing sentence repeating
    # both answers under their cards.
    block = CONTRACT.replace(f"{_ASKED}\n", "required: v | average speed\n")
    reply = (
        f"{_laid_out(block)}\n\nThe car's speed is **20 m/s**, and the train's speed is **30 m/s**."
    )
    state = SimpleNamespace(
        text=reply,
        server_text=False,
        was_cancelled=False,
        ctx=SimpleNamespace(
            verified_subject=None,
            solver_unverified=True,
            user_message_content=(
                "A car goes 100 m in 5 s; find its speed. A train goes 300 m in 10 s; "
                "find its speed."
            ),
        ),
    )
    text = check_working(cast(FinalizeState, state))
    assert _LETTERED in text
    assert text.count("```answer") == 2
    assert text.rstrip().endswith("```") and "The car's speed" not in text

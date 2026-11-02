"""A ```worked block: its records read and validated, laid out as a verified reply, and
streamed as the layout, never as records."""

from __future__ import annotations

import itertools

import pytest

from app.modules.chat.stream_accum import StreamAccum
from app.modules.chat.worked_render import WorkedLayout, render_worked, unit_tex
from app.modules.chat.worked_solution import (
    Answer,
    Formula,
    Given,
    PartLabel,
    Required,
    Step,
    WorkedSolution,
    assemble,
    read_record,
)
from app.modules.chat.worked_stream import ReplyFilter, WorkedFilter

PHYSICS = WorkedLayout(law_heading=True)
OTHER = WorkedLayout()

DISPLACEMENT = r"""```worked
given: v | 20 | m/s | speed
given: t | 120 | s | time
required: s | displacement
formula: Constant velocity | s = v t
substitution: s = 20 \times 120
substitution: s = 2400\,\mathrm{m}
answer: s | 2400 | m | east
```"""

DISPLACEMENT_LAID_OUT = (
    "**Given**  \n$v = 20\\,\\mathrm{m/s}$  \n$t = 120\\,\\mathrm{s}$  \n"
    "where $v$ = speed, $t$ = time\n\n"
    "**Required**  \n$s$ — displacement\n\n"
    "**Solution**\n\n"
    "**Constant velocity formula**  \n$s = v t$\n\n"
    "**Substitution**  \n$s = 20 \\times 120$  \n$s = 2400\\,\\mathrm{m}$\n\n"
    "**Answer**\n\n$2400\\,\\mathrm{m}\\ \\text{east}$"
)

POLES = r"""Here is the conversion.

```worked
given: d | 100 | m | distance between the poles
required: d_{cm} | distance in centimetres
required: d_{km} | distance in kilometres
part: a | Distance in centimetres
formula: Conversion | 1\,\mathrm{m} = 100\,\mathrm{cm}
substitution: d_{cm} = 100 \times 100 = 10000\,\mathrm{cm}
answer: d_{cm} | 10000 | cm
part: b | Distance in kilometres
formula: Conversion | 1\,\mathrm{km} = 1000\,\mathrm{m}
substitution: d_{km} = \frac{100}{1000} = 0.1\,\mathrm{km}
answer: d_{km} | 0.1 | km
```
"""


@pytest.mark.parametrize(
    ("line", "record"),
    [
        ("given: v | 20 | m/s | speed", Given(symbol="v", value="20", unit="m/s", meaning="speed")),
        ("given: v = 20 | m/s | speed", Given(symbol="v", value="20", unit="m/s", meaning="speed")),
        ("- given: $m_1$ | $1$ | kg", Given(symbol="m_1", value="1", unit="kg")),
        (
            r"given: t | 40 | min | time | 2400\,\mathrm{s}",
            Given(
                symbol="t", value="40", unit="min", meaning="time", converted=r"2400\,\mathrm{s}"
            ),
        ),
        ("Required: s | displacement", Required(symbol="s", meaning="displacement")),
        ("formula: Ohm's law | V = IR", Formula(name="Ohm's law", tex="V = IR")),
        ("formula: V = IR", Formula(tex="V = IR")),
        (
            r"solve_for: t | t = \frac{d}{v}",
            Step(kind="solve_for", symbol="t", tex=r"t = \frac{d}{v}"),
        ),
        ("step: 2x = 8 | subtract 3", Step(kind="step", tex="2x = 8", move="subtract 3")),
        (r"substitution: $s = 20 \times 120$", Step(kind="substitution", tex=r"s = 20 \times 120")),
        (
            "answer: s | 2400 | m | due East",
            Answer(symbol="s", value="2400", unit="m", note="due East"),
        ),
        ("answer: x = 3", Answer(symbol="x", value="3")),
        ("answer: 15", Answer(value="15")),
        ("part: (b) | Speed", PartLabel(letter="(b)", title="Speed")),
    ],
)
def test_read_record_validates_each_kind(line: str, record: object) -> None:
    assert read_record(line) == record


@pytest.mark.parametrize(
    "line",
    [
        "",
        "The answer is 2400 m.",
        "given:",
        "given: v",  # a symbol with no value
        "answer: s |",  # no value
        "formula: Name |",
        "note: something",
        "substitution: ```",
        "given: " + "x" * 400 + " | 1",
    ],
)
def test_read_record_leaves_out_what_is_no_record(line: str) -> None:
    assert read_record(line) is None


def _solution(block: str) -> WorkedSolution:
    records = [read_record(line) for line in block.split("\n")]
    return assemble([record for record in records if record is not None])


def test_render_lays_physics_out_as_its_verified_replies() -> None:
    assert render_worked(_solution(DISPLACEMENT), PHYSICS) == DISPLACEMENT_LAID_OUT


def test_render_heads_the_formula_with_its_name_and_keeps_the_symbol_elsewhere() -> None:
    laid_out = render_worked(_solution(DISPLACEMENT), OTHER)
    # The name heads the formula ("<name> formula"), never a note beside it.
    assert "**Constant velocity formula**  \n$s = v t$\n" in laid_out
    assert "— Constant velocity" not in laid_out
    assert laid_out.endswith("**Answer**\n\n$s = 2400\\,\\mathrm{m}\\ \\text{east}$")


def test_render_puts_a_rearrangement_under_its_formula_and_moves_under_steps() -> None:
    rearranged = _solution(
        "given: d | 100 | m\ngiven: v | 5 | m/s\nrequired: t\nformula: Speed | v = \\frac{d}{t}\n"
        "solve_for: t | t = \\frac{d}{v}\nsubstitution: t = \\frac{100}{5}\nanswer: t | 20 | s"
    )
    assert "**Speed formula**  \n$v = \\frac{d}{t}$  \nSolve for $t$  \n$t = \\frac{d}{v}$" in (
        render_worked(rearranged, OTHER)
    )
    moves = _solution("step: 2x + 3 = 11 | given\nstep: 2x = 8 | subtract 3\nanswer: x | 4")
    assert render_worked(moves, OTHER) == (
        "**Steps**  \n$2x + 3 = 11$ — given  \n$2x = 8$ — subtract 3\n\n**Answer**\n\n$x = 4$"
    )


def test_render_lays_a_question_in_parts_out_part_by_part() -> None:
    laid_out = render_worked(_solution(POLES), OTHER)
    assert laid_out.startswith("**Given**  \n$d = 100\\,\\mathrm{m}$")
    # One Required naming what each part finds, then Solution, then the parts.
    assert (
        "**Required**  \n(a) $d_{cm}$ — distance in centimetres  \n"
        "(b) $d_{km}$ — distance in kilometres\n\n**Solution**\n\n**(a) Distance" in laid_out
    )
    assert "**(a) Distance in centimetres**\n\n**Conversion formula**" in laid_out
    assert "**Answer (a)**\n\n$d_{cm} = 10000\\,\\mathrm{cm}$\n\n---\n\n**(b) Distance" in laid_out
    assert laid_out.endswith("**Answer (b)**\n\n$d_{km} = 0.1\\,\\mathrm{km}$")


def test_render_writes_no_answer_heading_without_an_answer() -> None:
    cut = _solution("given: v | 20 | m/s\nformula: Speed | v = d/t")
    assert "**Answer**" not in render_worked(cut, PHYSICS)


@pytest.mark.parametrize(
    ("unit", "tex"),
    [
        ("", ""),
        ("m/s", r"\,\mathrm{m/s}"),
        ("m/s^2", r"\,\mathrm{m/s²}"),
        ("kg*m", r"\,\mathrm{kg·m}"),
        (r"\text{km}", r"\,\mathrm{km}"),
        ("°C", r"\,^\circ\mathrm{C}"),
        ("°", r"^\circ"),
        ("%", r"\,\%"),
        (r"\Omega", r"\,\Omega"),
    ],
)
def test_unit_tex_writes_units_upright(unit: str, tex: str) -> None:
    assert unit_tex(unit) == tex


def _stream(
    reply: str, size: int, layout: WorkedLayout | None = PHYSICS
) -> tuple[str, list[str], StreamAccum]:
    """``reply`` through a ReplyFilter in chunks of ``size``: the text the client was sent,
    the text after each chunk, and the accumulator the stream path appends to."""
    accum = StreamAccum()
    reply_filter = ReplyFilter(accum, layout)
    seen: list[str] = []
    for start in range(0, len(reply), size):
        if sent := reply_filter.feed(reply[start : start + size]):
            accum.shown.append(sent)
        seen.append("".join(accum.shown))
    if tail := reply_filter.flush():
        accum.shown.append(tail)
    return "".join(accum.shown), seen, accum


@pytest.mark.parametrize("size", [1, 2, 3, 7, 40, 10_000])
def test_a_block_streams_as_its_layout_at_any_chunk_size(size: int) -> None:
    sent, seen, accum = _stream(DISPLACEMENT, size)
    assert sent.strip() == DISPLACEMENT_LAID_OUT
    assert not accum.rewritten
    # What the phone was sent only ever grows, and it never shows a record.
    for earlier, later in itertools.pairwise(seen):
        assert later.startswith(earlier)
    assert all("given:" not in text and "```" not in text for text in seen)


def test_a_block_streams_section_by_section() -> None:
    _sent, seen, _accum = _stream(DISPLACEMENT, 5)
    assert any(text.startswith("**Given**") and "**Required**" not in text for text in seen)
    assert any("**Required**" in text and "**Substitution**" not in text for text in seen)


@pytest.mark.parametrize("size", [1, 4, 10_000])
def test_text_around_a_block_passes_through(size: int) -> None:
    sent, _seen, accum = _stream(POLES + "\nThe poles are far apart.", size, OTHER)
    assert sent.startswith("Here is the conversion.\n\n**Given**")
    assert sent.rstrip().endswith("$d_{km} = 0.1\\,\\mathrm{km}$\n\n\nThe poles are far apart.")
    assert not accum.rewritten


@pytest.mark.parametrize(
    "reply",
    [
        "Plain prose with no block.\n\n**Answer**\n\n$x = 4$",
        "```python\nprint(1)\n```",
        "    ```worked\nindented four spaces is code",
        "Some text ```worked on the same line",
    ],
)
def test_a_reply_without_a_block_is_unchanged(reply: str) -> None:
    sent, _seen, accum = _stream(reply, 3)
    assert sent == reply
    assert not accum.rewritten


def test_without_a_layout_the_filter_only_strips_scaffolding() -> None:
    sent, _seen, _accum = _stream(DISPLACEMENT, 4, None)
    assert sent == DISPLACEMENT


def test_a_block_of_no_records_is_shown_as_written() -> None:
    reply = "```worked\n**Given:** v = 20 m/s\n**Answer:** 2400 m\n```"
    sent, _seen, _accum = _stream(reply, 5)
    assert sent.strip() == "**Given:** v = 20 m/s\n**Answer:** 2400 m"


def test_a_block_cut_off_by_the_stream_end_is_laid_out_as_far_as_it_went() -> None:
    cut = DISPLACEMENT.split("substitution:")[0]
    sent, _seen, _accum = _stream(cut, 6)
    assert sent.strip().endswith("**Constant velocity formula**  \n$s = v t$")
    assert "**Answer**" not in sent


def test_a_record_out_of_order_rewrites_the_reply_and_marks_it() -> None:
    late_given = DISPLACEMENT.removesuffix("```") + "given: m | 5 | kg | mass\n```"
    sent, _seen, accum = _stream(late_given, 3)
    assert accum.rewritten
    assert sent.startswith(
        "**Given**  \n$v = 20\\,\\mathrm{m/s}$  \n$t = 120\\,\\mathrm{s}$  \n$m = 5"
    )
    assert sent.rstrip().endswith("$2400\\,\\mathrm{m}\\ \\text{east}$")


def test_the_worked_filter_counts_the_blocks_it_laid_out() -> None:
    worked = WorkedFilter(PHYSICS)
    worked.feed(DISPLACEMENT + "\n\n" + DISPLACEMENT)
    worked.close()
    assert worked.blocks == 2
    assert worked.text.count("**Given**") == 2


def test_render_tidies_the_models_tex_and_drops_a_conversion_to_itself() -> None:
    beam = _solution(
        "given: m1 | 1 | kg | first mass | 1000\\,\\mathrm{g}\n"
        "given: m2 | 500 | g | second mass | 500\\,\\mathrm{g}\n"
        "required: M | mass on the other side\n"
        "formula: Balance | M = m_1 + m_2\n"
        "substitution: M = 1000 + 500 = 1500\\,\\mathrm{g}\n"
        "answer: M | 1500 | g"
    )
    laid_out = render_worked(beam, OTHER)
    assert "$m_1 = 1\\,\\mathrm{kg} = 1000\\,\\mathrm{g}$" in laid_out
    assert "$m_2 = 500\\,\\mathrm{g}$  \n" in laid_out  # never "500 g = 500 g"
    displacement = _solution("formula: Displacement | \\Delta x = x_final - x_initial\nanswer: 1")
    assert "x_{final} - x_{initial}" in render_worked(displacement, OTHER)


def test_render_keeps_one_part_when_the_model_names_it_twice() -> None:
    poles = _solution(
        "given: d | 100 | m | distance\nrequired: a. length in cm, b. length in km\n"
        "part: a | In centimetres\nformula: Unit conversion | 1\\,\\mathrm{m} = 100\\,\\mathrm{cm}\n"
        "part: a\nsubstitution: d = 100 \\times 100\nanswer: cm | 10000 | cm\n"
        "part: b | In kilometres\nsubstitution: d = 100 \\div 1000\nanswer: d | 0.1 | km"
    )
    laid_out = render_worked(poles, OTHER)
    assert laid_out.count("**(a)") == 1 and laid_out.count("---") == 1
    # Words in a symbol's place are text, and a symbol that repeats the unit is dropped.
    assert "**Required**  \na. length in cm, b. length in km\n" in laid_out
    assert "**Answer (a)**\n\n$10000\\,\\mathrm{cm}$" in laid_out


def test_render_writes_a_sentence_in_a_maths_field_as_text() -> None:
    azeb = _solution(
        "formula: Displacement | \\Delta x = x_C - x_A\n"
        "step: Let A be the origin and the direction from A to B positive | set up\n"
        "substitution: \\Delta x = 100 - 0\nanswer: \\Delta x | 100 | m"
    )
    laid_out = render_worked(azeb, OTHER)
    assert "\nLet A be the origin and the direction from A to B positive — set up" in laid_out
    assert "$Let" not in laid_out


@pytest.mark.parametrize(
    ("symbol", "words"),
    [("a) in cm, b) in km", True), ("length in cm", True), ("\\Delta x", False), ("v_i", False)],
)
def test_a_symbol_in_words_is_text(symbol: str, words: bool) -> None:
    from app.modules.chat.worked_render import names_nothing

    assert names_nothing(symbol) is words


def test_moves_then_a_substitution_stay_in_the_order_written() -> None:
    block = "```worked\nstep: 2x + 3 = 11 | given\nstep: 2x = 8 | subtract 3\nsubstitution: x = 8 / 2\nanswer: x | 4\n```"
    sent, _seen, accum = _stream(block, 4, OTHER)
    assert not accum.rewritten
    assert sent.strip().startswith(
        "**Steps**  \n$2x + 3 = 11$ — given  \n$2x = 8$ — subtract 3  \n$x = 8 / 2$"
    )
    assert "**Substitution**" not in sent


def test_a_formula_before_the_first_part_label_is_that_parts() -> None:
    block = _solution(
        "given: d | 100 | m\nformula: Speed | v = d/t\npart: a | speed\nsubstitution: v = 100/5\n"
        "answer: v | 20 | m/s\npart: b | time\nsubstitution: t = 100/20\nanswer: t | 5 | s"
    )
    laid_out = render_worked(block, OTHER)
    assert laid_out.count("**(a)") == 1 and laid_out.count("---") == 1
    assert "**(a) speed**\n\n**Speed formula**  \n$v = d/t$\n" in laid_out


def test_a_rewrite_keeps_the_list_length_and_a_stop_after_it_keeps_the_reply_whole() -> None:
    accum = StreamAccum()
    accum.shown.append("Before.\n\n")
    reply_filter = ReplyFilter(accum, PHYSICS)
    late = DISPLACEMENT.removesuffix("```") + "given: m | 5 | kg | mass\n```"
    for start in range(0, len(late), 3):
        if sent := reply_filter.feed(late[start : start + 3]):
            accum.shown.append(sent)
    if tail := reply_filter.flush():
        accum.shown.append(tail)
    assert accum.rewritten and accum.shown[0] == "Before.\n\n"
    accum.mark_user_stop()
    # The client's count is of the text it drew before the rewrite: never cut by it.
    assert accum.reply_text(client_shown_chars=20).endswith("$2400\\,\\mathrm{m}\\ \\text{east}$")


def test_the_closer_of_a_block_cut_at_the_cap_is_dropped() -> None:
    from app.modules.chat.worked_stream import MAX_BLOCK_CHARS

    filler = "".join(f"substitution: x = {n}\n" for n in range(MAX_BLOCK_CHARS // 15))
    worked = WorkedFilter(OTHER)
    worked.feed(f"```worked\ngiven: x | 1\n{filler}```\n\nAfter the block.")
    worked.close()
    assert "```" not in worked.text
    assert worked.text.rstrip().endswith("After the block.")


@pytest.mark.parametrize(
    "tex",
    ["x_{final} = x_{initial} + v_{avg} t", "v_{avg} = \\frac{distance}{time}"],
)
def test_a_line_with_latex_is_maths_however_many_words_it_holds(tex: str) -> None:
    block = _solution(f"substitution: {tex}\nstep: {tex} | carried on\nanswer: x | 1")
    laid_out = render_worked(block, OTHER)
    assert laid_out.count(f"${tex}$") == 2


# Words in a maths field, a sentence as a step, and a symbol in words, as a model wrote them.
SLOPPY = (
    "```worked\ngiven: d_AB | 300 | m | distance\nrequired: a) in cm, b) in km\n"
    "formula: Displacement | \\Delta x = x_final - x_initial\n"
    "step: Let A be the origin and the direction from A to B positive | set up\n"
    "substitution: v_{avg} = \\frac{distance}{time}\nanswer: \\Delta x | 100 | m | east\n```"
)


@pytest.mark.parametrize("block", [DISPLACEMENT, POLES, SLOPPY])
def test_no_laid_out_block_shows_latex_source(block: str) -> None:
    from app.tests.behavior.latex_check import latex_problems

    worked = WorkedFilter(OTHER)
    worked.feed(block)
    worked.close()
    assert latex_problems(worked.text) == []

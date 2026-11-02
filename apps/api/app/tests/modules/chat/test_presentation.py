"""Reply presentation: the shared corpus, plus the server-only orphan-answer rule.

`docs/fixtures/presentation_cases.json` holds every presentation case both sides
must agree on: REPL transcripts, word spaces outside inline tokens, inline code
against maths, and one calculation state per row. This test presents each input
with `present_assistant_markdown` and expects the output exactly; the phone test
(`lib/__tests__/presentationCorpus.test.ts`) does the same with
`presentAssistantMarkdown`. A presented row presents to itself, which is why the
phone can leave a persisted row as the server saved it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.modules.chat.calculation_layout import split_math_expression
from app.modules.chat.inline_boundaries import repair_inline_token_boundaries
from app.modules.chat.presentation import drop_orphan_leading_answer, present_assistant_markdown

FIXTURE = Path(__file__).resolve().parents[6] / "docs" / "fixtures" / "presentation_cases.json"
CASES: list[dict[str, Any]] = json.loads(FIXTURE.read_text())["cases"]


@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
def test_presentation_corpus_case(case: dict[str, Any]) -> None:
    assert present_assistant_markdown(case["input"]) == case["expected"]


@pytest.mark.parametrize("case", CASES, ids=[case["id"] for case in CASES])
def test_presented_text_presents_to_itself(case: dict[str, Any]) -> None:
    assert present_assistant_markdown(case["expected"]) == case["expected"]


def test_corpus_ids_are_unique_and_every_area_is_covered() -> None:
    ids = [case["id"] for case in CASES]
    assert len(ids) == len(set(ids))
    areas = {case["area"] for case in CASES}
    assert areas == {
        "boundaries",
        "inline_code",
        "notation",
        "calculation",
        "maths",
        "fences",
        "lists",
        "repl",
        "replies",
        "lead_lines",
    }


def test_a_why_question_drops_the_previous_sum() -> None:
    question = (
        "Why does adding two positive numbers always result in a larger number "
        "than either of the original numbers?"
    )
    reply = "7\n\nAdding two positive numbers moves further along the number line."
    assert drop_orphan_leading_answer(reply, question) == (
        "Adding two positive numbers moves further along the number line."
    )
    fenced = "```answer\n7\n```\n\nAdding two positive numbers moves further along the number line."
    assert "7" not in drop_orphan_leading_answer(fenced, question)
    assert drop_orphan_leading_answer("7", "What is 3 + 4?") == "7"


def test_split_math_expression_rows() -> None:
    rows = split_math_expression(r"t_{\text{total}} = d/60 + d/40 = (2d+3d)/120 = 5d/120")
    assert rows == [
        r"t_{\text{total}} = d/60 + d/40",
        r"t_{\text{total}} = (2d+3d)/120",
        r"t_{\text{total}} = 5d/120",
    ]
    assert split_math_expression("f(x, y) = 1") is None
    assert split_math_expression(r"\begin{aligned} a &= b \end{aligned}") is None


def test_plain_prose_is_copied_without_trying_each_reader(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every reply is presented before it saves. Its prose used to go through every inline
    reader, and the display-maths scan, a character at a time (a 16,000-character reply's
    presentation took 10.7 ms, 5.2 ms now): only a character that may open a token is read,
    and a line with no ``$`` or backslash is not scanned for maths."""
    from app.modules.chat import inline_boundaries, markdown_regions

    tried: list[str] = []
    real_url = inline_boundaries._read_url

    def counting_url(text: str, index: int) -> int | None:
        tried.append(text)
        return real_url(text, index)

    def no_scan(line: str, start: int) -> int | None:
        raise AssertionError(f"scanned a line with no maths: {line!r}")

    monkeypatch.setattr(inline_boundaries, "_read_url", counting_url)
    prose = "The quick brown fox jumps over the lazy dog, then the wheel turns. " * 30
    text = f"{prose}\n\nSee https://example.com and **at**40 for $x$."
    presented = present_assistant_markdown(text)
    assert presented.startswith(prose.rstrip())
    assert presented.rsplit("\n", 1)[-1] == "See https://example.com and **at** 40 for $x$."
    # The URL, the bold and the maths are each read; the line of prose before them is not.
    assert tried
    assert all(line.startswith("See ") for line in tried)
    monkeypatch.setattr(markdown_regions, "read_inline_code_span", no_scan)
    assert present_assistant_markdown(f"{prose}`code` here") == f"{prose}`code` here"


@pytest.mark.wall_clock
def test_a_long_run_of_punctuation_is_peeled_in_one_pass() -> None:
    """The trailing marks after a formula were peeled by cutting a copy per mark: a reply
    of 64,000 dots spent 196 ms in it (24 ms now), and 200,000 several seconds."""
    import time

    text = "$x = 1$" + "." * 200_000
    start = time.perf_counter()
    presented = present_assistant_markdown(text)
    assert time.perf_counter() - start < 0.5
    assert presented == text


@pytest.mark.parametrize(
    ("written", "presented"),
    [
        # Live (2026-10-29): a mnemonic's bold first letters were split from their words.
        ("**A**ffect is **A**ction, **E**ffect is the **E**nd result.", None),
        ("Set **S**pecific, **M**easurable goals.", None),
        ("the**US**economy", "the **US** economy"),
        # A longer span, or one against a digit, still gets its missing space.
        ("the**answer**is", "the **answer** is"),
        ("See **at**40 for it.", "See **at** 40 for it."),
    ],
)
def test_bold_inside_a_word_stays_inside_it(written: str, presented: str | None) -> None:
    assert repair_inline_token_boundaries(written) == (presented or written)

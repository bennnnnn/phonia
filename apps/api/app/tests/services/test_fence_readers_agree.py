"""Every reader of a reply's fences agrees with the renderer (code-health audit DUP-03).

A reply that teaches markdown shows a ``` line inside a ~~~ block. To the phone that
line is code; the readers that toggled on every ``` line, or closed a fence on the
first triple backtick anywhere, read the rest of the reply inside out.
"""

from __future__ import annotations

from app.modules.chat.finalize_parts import divide_sections
from app.modules.chat.related_questions import answer_excerpt
from app.modules.chat.reply_labels import one_answer_label
from app.modules.images.answer_photo import strip_photo_fences
from app.modules.math.text_plot import strip_text_plots
from app.modules.todos.reminder_fence_parse import find_reminder_fences
from app.modules.todos.reply_claims import without_claim_lines
from app.services.draft_fences import draft_langs, has_draft

# A how-to: the ~~~ block shows a fence opener, and the reply goes on after it.
_SHOWN = "~~~\n```python\n### not a heading\n~~~"


def test_a_shown_fence_line_does_not_turn_the_sections_inside_out() -> None:
    text = f"### First\nIntro\n{_SHOWN}\n### Second\nMore"

    assert divide_sections(text) == f"### First\nIntro\n{_SHOWN}\n\n---\n\n### Second\nMore"


def test_a_plot_shown_inside_a_longer_fence_is_left_as_written() -> None:
    text = "Write it like this:\n````markdown\n```\n 4 |    *\n 2 |  *\n 0 |*____\n```\n````"

    assert strip_text_plots(text) == text


def test_a_reminder_fence_closes_on_its_closer_line_only() -> None:
    body = '{"title": "read ``` in the docs", "due": "2026-10-22T09:00"}\n'
    text = f"Sure.\n```reminder\n{body}```\nSaved."

    assert find_reminder_fences(text) == [(6, len(text) - len("\nSaved."), body)]


def test_an_empty_reply_has_no_claim_lines() -> None:
    assert without_claim_lines([]) == []


def test_answer_labels_in_a_shown_block_stay() -> None:
    text = "**Find**\n$x$\n\n~~~\n```\n**Answer**\n~~~\n\n**Answer**\n$x = 2$"

    assert one_answer_label(text) == text


def test_a_photo_fence_in_any_spelling_is_the_photo() -> None:
    assert strip_photo_fences("~~~photo\nan ear\n~~~\n\nThe ear has three parts.") == (
        "The ear has three parts."
    )


def test_a_draft_is_a_fence_not_a_shown_line() -> None:
    assert draft_langs("Here:\n~~~email\nHi Sam,\n~~~") == ["email"]
    assert not has_draft("To draft, write:\n~~~\n```email\n~~~")


def test_the_answer_excerpt_drops_fence_lines() -> None:
    assert answer_excerpt("Use this:\n~~~js\nlet x = 1\n~~~\nDone.") == "Use this: let x = 1 Done."

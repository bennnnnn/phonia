"""Inline code and inline maths stay apart before a reply is saved.

The phone reads code spans the same way (apps/mobile/lib/markdown/inlineCode.ts).
How presentation treats code beside maths is in docs/fixtures/presentation_cases.json
(area inline_code), which both sides run.
"""

from __future__ import annotations

from app.modules.chat.inline_code import code_span_opens_within, read_inline_code_span


def test_a_code_span_is_read_like_markdown_it() -> None:
    text = "a `b` c ``d ` e`` f `g"
    assert read_inline_code_span(text, 2) == 5
    assert read_inline_code_span(text, 8) == 17
    assert read_inline_code_span(text, text.rindex("`")) is None
    assert code_span_opens_within(text, 0, 4)
    assert not code_span_opens_within("no code here", 0, 12)

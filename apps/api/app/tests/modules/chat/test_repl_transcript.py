"""A ``>>>`` transcript outside a fence is code, not three nested quotes.

The whole presentation step on transcripts is in docs/fixtures/presentation_cases.json.
"""

from __future__ import annotations

import pytest

from app.modules.chat.repl_transcript import fence_repl_transcripts


def test_transcript_becomes_a_python_block() -> None:
    text = "Test it:\n\n>>> two_sum([2, 7, 11, 15], 9)\n[0, 1]\n\nIt returns the indexes."
    assert fence_repl_transcripts(text) == (
        "Test it:\n\n```python\n>>> two_sum([2, 7, 11, 15], 9)\n[0, 1]\n```\n\n"
        "It returns the indexes."
    )


def test_continuation_lines_stay_in_the_block() -> None:
    text = ">>> for n in [1, 2]:\n...     print(n)\n1\n2"
    assert fence_repl_transcripts(text) == (
        "```python\n>>> for n in [1, 2]:\n...     print(n)\n1\n2\n```"
    )


@pytest.mark.parametrize(
    "text",
    [
        "```python\n>>> two_sum([2, 7], 9)\n[0, 1]\n```",
        "> A real quote.",
        "No transcript here.",
        "Compare a >>> b in prose.",
    ],
)
def test_leaves_fenced_code_quotes_and_prose_alone(text: str) -> None:
    assert fence_repl_transcripts(text) == text

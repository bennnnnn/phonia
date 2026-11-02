"""A Python ``>>>`` transcript written as prose becomes a code block.

Markdown reads ``>>> two_sum([2, 7], 9)`` as three nested quotes, so a reply
that shows a REPL session outside a fence draws stacked quote bars and runs
the call into its output. The transcript, up to the next blank line, is
wrapped in a ```python fence instead. The phone does the same
(``apps/mobile/lib/markdown/replTranscript.ts``).
"""

from __future__ import annotations

import re

from app.modules.chat.markdown_regions import rewrite_fenced

_PROMPT = re.compile(r"^[ \t]{0,3}>>>(?:[ \t]|$)")


def _fence_prose(prose: str) -> str:
    lines = prose.split("\n")
    out: list[str] = []
    index = 0
    while index < len(lines):
        if not _PROMPT.match(lines[index]):
            out.append(lines[index])
            index += 1
            continue
        block: list[str] = []
        while index < len(lines) and lines[index].strip():
            block.append(lines[index].strip())
            index += 1
        out.extend(["```python", *block, "```"])
    return "\n".join(out)


def fence_repl_transcripts(text: str) -> str:
    """Wrap ``>>>`` transcripts outside code fences in a ```python fence."""
    if not text or ">>>" not in text:
        return text
    return rewrite_fenced(text, _fence_prose, lambda _opener, _body, _closer: None)

"""An apology or a line about the reply itself is never a Note card.

"Not so good" got "> Note: I apologize for the formatting glitch. Here is the plain-text
explanation." above the answer, and the phone drew it as a Note card: the box for what
the reader must not miss. A Note callout (``> Note:``, ``> **Note:**``, ``> [!NOTE]``)
that opens with an apology, thanks or a remark about the reply ("Here is…", "As
requested…") becomes the plain lines it holds; nothing in it is dropped. A real note
stays a card, and a Warning is left alone: a correction may rightly open with "Sorry".
"""

from __future__ import annotations

import re

from app.services.md_fence_scan import line_fences
from app.services.text_normalize import straighten_apostrophes

_EMPHASIS = r"(?:\*\*|__|\*|_)?"
# The callout's first line: its indent, then the label and whatever follows on that line.
_NOTE_HEAD = re.compile(
    rf"^(?P<indent>[ \t]*)>[ \t]*(?:\[!(?:note|info|tip)\]|{_EMPHASIS}(?:note|info|tip)"
    rf"{_EMPHASIS}[ \t]*:{_EMPHASIS})[ \t]*(?P<rest>.*)$",
    re.IGNORECASE,
)
# A labeled quote line starts the next callout (the labels ``preprocessCallouts.ts`` reads).
_LABELED = re.compile(
    rf"^>[ \t]*(?:\[!\w+\]|{_EMPHASIS}(?:tip|note|warning|important|info|hint|caution)"
    rf"{_EMPHASIS}[ \t]*:)",
    re.IGNORECASE,
)
# How a remark about the reply opens, matched on the note's text lowercased.
_ABOUT_THE_REPLY = re.compile(
    r"^(?:(?:i(?:'m| am) )?(?:so |very |really |truly )?sorry\b"
    r"|i (?:do |sincerely |truly )?apologi[sz]e\b|(?:my )?(?:sincere )?apologies\b"
    r"|thanks? (?:you )?for\b|here(?:'s| is| are) (?:the|a|an|your|my|that|this)\b"
    r"|below (?:is|are)\b|as (?:requested|you asked)\b|i hope (?:this|that|it)\b"
    r"|let me (?:try|explain|rephrase|redo|fix)\b)"
)


def _about_the_reply(body: list[str]) -> bool:
    words = " ".join(" ".join(body).split()).lstrip("*_ ")
    return bool(_ABOUT_THE_REPLY.match(straighten_apostrophes(words).lower()))


def unwrap_meta_notes(text: str) -> str:
    """``text`` with each Note callout about the reply itself written as plain lines."""
    if ">" not in text:
        return text
    lines = text.split("\n")
    owners = line_fences(text)
    out: list[str] = []
    index = 0
    while index < len(lines):
        head = None if owners[index] is not None else _NOTE_HEAD.match(lines[index])
        if head is None:
            out.append(lines[index])
            index += 1
            continue
        indent = head.group("indent")
        body = [head.group("rest").strip()] if head.group("rest").strip() else []
        end = index + 1
        while end < len(lines) and lines[end].startswith(f"{indent}>"):
            quoted = lines[end][len(indent) :]
            if _LABELED.match(quoted):
                break
            body.append(re.sub(r"^>[ \t]?", "", quoted))
            end += 1
        if body and _about_the_reply(body):
            out.extend(f"{indent}{line}" if line else line for line in body)
        else:
            out.extend(lines[index:end])
        index = end
    return "\n".join(out)

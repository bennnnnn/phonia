"""Chat-template control tokens a model leaks into its reply.

A provider's end-of-turn token is the model's own signal, never text for a reader: a
Grade 10 answer card ended "2 x 10^-8 s<|im_end|>" and the reply then ran "</|im_end|>"
for 1,100 lines, to the length limit (2026-10-30). A reply about chat templates writes the
same tokens on purpose, so only a leak's own shape is acted on: a token ending the reply or
an answer card, or one token over and over. Code a reply quotes (a fence, `inline` code) is
never touched.

A run of one token ends the stream: the model is no longer writing a reply, and reading on
kept the user waiting up to the stream's cap and marked a clean reply cut short (2026-11-01).
"""

from __future__ import annotations

import re
from collections.abc import AsyncGenerator, AsyncIterator

from app.services.answer_fence import OWNED_FENCE_LANGS
from app.services.md_fence_scan import iter_fences, last_fence, read_fence_marker

# "<|im_end|>", "</|im_end|>", "<|endoftext|>", "<|eot_id|>", and the full-width bar form
# one provider ends a sentence with.
_BAR = chr(0xFF5C)
_TOKEN = rf"</?\|[a-z_]{{2,24}}\|>|<{_BAR}[^{_BAR}\n]{{1,40}}{_BAR}>"
CONTROL_TOKEN = re.compile(_TOKEN)
# One token over and over: the model is no longer writing a reply.
_RUN = re.compile(rf"({_TOKEN})(?:\s*\1){{2,}}")
# A token a stretch of reply text ends on: the reply's last line, or an answer card's.
_ENDING = re.compile(rf"(?:{_TOKEN})\s*\Z")
# `code` or ``code``; "``" alone opens a span, it is no empty one.
_INLINE_CODE = re.compile(r"``[^\n]*?``|`[^`\n]+`")
_BLANK_RUN = re.compile(r"\n(?:[ \t]*\n){2,}")
# A token that ends a turn: past it the model writes notes to itself (2026-10-31: a Grade 11
# answer ran on after "</|assistant|>" into "el if (rounded amounts) total? compute…"), or
# another speaker's turn begins: "<|user|>" is one model family's stop token, and "Hello!
# <|user|>What's the weather?<|assistant|>Sunny" wrote both sides of a chat.
_TURN_END = re.compile(
    rf"</\|[a-z_]{{2,24}}\|>|<\|(?:im_end|eot_id|eom_id|endoftext|end)\|>"
    rf"|<\|(?:user|system|human|observation)\|>"
    rf"|<\|(?:im_start|start_header_id)\|>\s*(?:user|system)\b"
    rf"|<{_BAR}end[^{_BAR}\n]{{0,36}}{_BAR}>"
)
# A message about chat templates, whose reply may write the tokens on purpose.
_TEMPLATE_TALK = re.compile(r"<\||\|>|\btokens?\b|\btemplates?\b|chatml|tokeni[sz]", re.IGNORECASE)


def _reply_parts(text: str) -> list[tuple[str, bool]]:
    """The reply in order as (piece, is_reply_text): prose and the app's own cards are
    its text; any other fence is code it quotes."""
    parts: list[tuple[str, bool]] = []
    cursor = 0
    for fence in iter_fences(text):
        parts.append((text[cursor : fence.body_start], True))
        parts.append((text[fence.body_start : fence.body_end], fence.lang in OWNED_FENCE_LANGS))
        cursor = fence.body_end
    parts.append((text[cursor:], True))
    return parts


def _outside_inline_code(piece: str) -> str:
    return _INLINE_CODE.sub(lambda code: " " * len(code.group(0)), piece)


def strip_control_tokens(text: str, asked: str | None = None) -> str:
    """``text`` without a leak's control tokens and the blank lines a run of them leaves;
    a reply that only quotes them, or writes them in code, is left as it is.

    ``asked`` is the user's message. When it says nothing of tokens or templates, no token
    in the reply's own text was written on purpose: each goes, and the reply ends at the
    first turn-ending one in its prose. Unknown (None), only a leak's shape is acted on."""
    if CONTROL_TOKEN.search(text) is None:
        return text
    ends_line = text.endswith("\n")
    unasked = asked is not None and _TEMPLATE_TALK.search(asked) is None
    if unasked:
        text = _cut_at_turn_end(text)
    parts = _reply_parts(text)
    own_text = [_outside_inline_code(piece) for piece, own in parts if own]
    visible = "\n".join(own_text)
    shaped = _RUN.search(visible) is not None or any(_ENDING.search(p) for p in own_text)
    if not (shaped or unasked):
        return text
    cleaned = "".join(_strip_piece(piece) if own else piece for piece, own in parts)
    if CONTROL_TOKEN.match(text.lstrip()):
        # A token that opened the reply leaves no blank lines above it.
        cleaned = cleaned.lstrip()
    return cleaned.rstrip() + ("\n" if ends_line else "")


def _cut_at_turn_end(text: str) -> str:
    """``text`` up to the first turn-ending token in its prose that follows some reply; a
    card or quoted code keeps what it holds (a token closing a card is stripped there, not
    cut at). A token before any reply opens it ("<|im_end|>\n\n2 + 2 = 4."): cutting there
    saved an empty reply, so it is only stripped."""
    cursor = 0
    for fence in [*iter_fences(text), None]:
        end = len(text) if fence is None else fence.body_start
        for turn_end in _TURN_END.finditer(_outside_inline_code(text[cursor:end])):
            at = cursor + turn_end.start()
            if CONTROL_TOKEN.sub("", text[:at]).strip():
                return text[:at]
        if fence is None:
            break
        cursor = fence.body_end
    return text


def drop_control_tokens(text: str) -> str:
    """Every control token gone, code included: the closed strip that stands in when the
    control-token pass fails, so a fallback never saves a leaked token."""
    return CONTROL_TOKEN.sub("", text)


def _strip_piece(piece: str) -> str:
    """One stretch of reply text without its control tokens; inline code keeps them."""
    pieces: list[str] = []
    cursor = 0
    for code in _INLINE_CODE.finditer(piece):
        pieces.append(CONTROL_TOKEN.sub("", piece[cursor : code.start()]))
        pieces.append(code.group(0))
        cursor = code.end()
    pieces.append(CONTROL_TOKEN.sub("", piece[cursor:]))
    return _BLANK_RUN.sub("\n\n", "".join(pieces))


async def until_control_run(tokens: AsyncIterator[str]) -> AsyncGenerator[str]:
    """``tokens`` until one control token repeats outside code, then no more: the stream is
    left unread and closed by its caller, and its usage is estimated at settle as for a
    stop. A run in a fence or `inline` code a reply quotes, closed or still open, is text."""
    text = ""
    async for token in tokens:
        text += token
        start = max(0, len(text) - len(token) - 200)
        for run in _RUN.finditer(text, start):
            if not _in_open_fence(text[: run.start()]) and not _in_inline_code(text, run.start()):
                return
        yield token


def _in_open_fence(text: str) -> bool:
    fence = last_fence(text)
    return fence is not None and not fence.closed


# An `inline` span still open this far past its backtick is a stray backtick ("Press the `
# key"), not quoted code: a run a reply quotes follows its backtick closely.
_OPEN_SPAN_MAX = 80


def _in_inline_code(text: str, at: int) -> bool:
    """``at`` is inside `inline` code on its line: a closed span, or one just opened whose
    closing backtick has not streamed yet. A fence's line and a stray backtick are no span,
    so a run after them still ends the stream."""
    line_start = text.rfind("\n", 0, at) + 1
    line_end = text.find("\n", at)
    line = text[line_start : len(text) if line_end == -1 else line_end]
    if read_fence_marker(line) is not None:
        # A fence's own line ("```" closing a block): its backticks open no span.
        return False
    at -= line_start
    cursor = 0
    for span in _INLINE_CODE.finditer(line):
        if span.start() >= at:
            break
        if at < span.end():
            return True
        cursor = span.end()
    opener = line.find("`", cursor, at)
    return opener != -1 and at - opener <= _OPEN_SPAN_MAX

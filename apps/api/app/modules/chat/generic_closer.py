"""A generic closing line ("Let me know if you have any other questions") comes off a reply.

FORMAT_CONTRACT already asks for no such ending; this pass removes the ones a model writes
anyway. It is deliberately narrow: only the reply's last line, only a sentence from the fixed
list in ``_CLOSER``, never inside a code fence, a quote, a table or a list, never the whole
reply, and never on a turn whose words the user shaped: a draft, a rewrite or a translation
(an email may end "Let me know if you have any questions"), or a message that quotes a closer.
A concrete offer ("Let me know if you want it in TypeScript") is not on the list.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from app.modules.turn_reading.routing import EMOJI
from app.modules.turn_reading.writing import draft_followup
from app.modules.turn_reading.writing_kind import writing_request_kind
from app.services.md_fence_scan import last_fence
from app.services.text_normalize import collapse_ws, straighten_apostrophes

if TYPE_CHECKING:
    from app.modules.chat.finalize_passes import FinalizeState

_MORE = r"(?:any )?(?:other |more |further |additional )?"
_QUESTIONS = rf"{_MORE}questions"
_HELP = rf"{_MORE}(?:help|assistance|clarification)"
# Matched against one whole sentence, lowercased, ``collapse_ws``-ed, end punctuation off.
_CLOSER = re.compile(
    r"(?:i )?hope (?:this|that|it) helps(?: you)?(?: a lot| out)?"
    r"|(?:please |just )?(?:let me know|feel free to (?:ask|reach out|let me know))"
    r"(?: me)?(?: anything(?: else)?)?"
    rf"(?: if (?:you have {_QUESTIONS}(?: or need {_HELP})?"
    rf"|you need (?:anything else|anything more|{_HELP})"
    r"|(?:there's |there is )?anything else (?:i can (?:help (?:you )?with|do for you)|you need)"
    r"|i can help with anything else))?"
    rf"|if you have {_QUESTIONS},? (?:feel free to ask|(?:just )?let me know|(?:just )?ask)"
    r"|(?:is there )?anything else (?:i can (?:help (?:you )?with|do for you)"
    r"|you(?:'d| would) like to know)"
)
# Words that mean the user asked about (or for) such a line themselves.
_ASKED_ABOUT = ("hope this helps", "let me know", "feel free", "any other questions")
_SENTENCE_BREAK = re.compile(r"(?<=[.!?…]) +")
_LIST_ITEM = re.compile(r"(?:[-*+]|\d{1,3}[.)]) ")
_BLOCK_STARTS = ("```", ">", "|", "#")
_CODE_INDENT = ("    ", "\t")
_RULES = frozenset({"---", "***", "___"})
_MAX_CLOSERS = 2


def strip_generic_closer(state: FinalizeState) -> str:
    """The finalize pass: a model reply loses a generic closing sentence."""
    if state.was_cancelled or state.server_text:
        return state.text
    if _user_shaped_the_words(state):
        return state.text
    return drop_generic_closer(state.text)


def drop_generic_closer(text: str) -> str:
    """``text`` without its last line's generic closer (up to two), or unchanged."""
    body = text.rstrip()
    for _ in range(_MAX_CLOSERS):
        trimmed = _without_last_closer(body)
        if trimmed is None:
            break
        body = trimmed
    return text if body == text.rstrip() else body


def _user_shaped_the_words(state: FinalizeState) -> bool:
    query = state.ctx.user_message_content or ""
    if writing_request_kind(query) is not None:
        return True
    lowered = straighten_apostrophes(query).lower()
    if any(phrase in lowered for phrase in _ASKED_ABOUT):
        return True
    # "Make it more polite" goes on with a draft written a few turns ago.
    prior = [
        (role, content)
        for message in state.ctx.prompt_messages
        if (role := str(message.get("role"))) in {"user", "assistant"}
        and isinstance(content := message.get("content"), str)
    ]
    if prior and prior[-1] == ("user", query):
        prior.pop()
    return draft_followup(query, prior) is not None


def _without_last_closer(body: str) -> str | None:
    if _ends_inside_fence(body):
        return None
    head, _, last = body.rpartition("\n")
    line = _without_trailing_emoji(last.strip())
    if not line or last.startswith(_CODE_INDENT) or line.startswith(_BLOCK_STARTS):
        return None
    if _LIST_ITEM.match(line):
        return None
    cut = 0
    for match in _SENTENCE_BREAK.finditer(line):
        cut = match.end()
    # "Happy cooking! 🇳🇬 Let me know…": the emoji stays with the sentence before it.
    while cut < len(line) and (line[cut] == " " or EMOJI.fullmatch(line[cut])):
        cut += 1
    if not _is_closer(line[cut:]):
        return None
    # Emoji alone is not a sentence left to keep.
    rest = line[:cut].rstrip() if _without_trailing_emoji(line[:cut]) else ""
    kept = "\n".join(part for part in (head, rest) if part)
    lines = kept.rstrip().split("\n")
    while lines and lines[-1].strip() in _RULES:
        lines.pop()
    kept = "\n".join(lines).rstrip()
    return kept if kept.strip() else None


def _without_trailing_emoji(line: str) -> str:
    end = len(line)
    while end and (line[end - 1] == " " or EMOJI.fullmatch(line[end - 1])):
        end -= 1
    return line[:end]


def _is_closer(sentence: str) -> bool:
    cleaned = collapse_ws(straighten_apostrophes(sentence)).lower()
    cleaned = cleaned.strip(" *_").rstrip(" .!?…:)").strip(" *_")
    return bool(cleaned) and _CLOSER.fullmatch(cleaned) is not None


def _ends_inside_fence(text: str) -> bool:
    last = last_fence(text)
    return last is not None and not last.closed

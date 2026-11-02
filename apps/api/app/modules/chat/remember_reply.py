"""A "remember …" turn's reply claims no to-do.

"Remember that I want to try cacio e pepe again" is saved to memory; the reply "I've added
that to your to-do list so you don't forget" claimed a to-do nothing wrote (live chat,
2026-10-25). On a remember turn with no reminder card, a sentence that says it put
something in the to-do list or set a reminder goes. Only that shape counts: "Saved — your
flight is Friday at 6 AM", "I've noted that…" and "I won't add it to your to-dos" are
memory's words and stay.
"""

from __future__ import annotations

import re

from app.models.orm import User
from app.modules import memory as memory_service
from app.modules.memory.switch import memory_switch_on
from app.services.md_fence_scan import iter_fences, line_fences
from app.services.text_normalize import straighten_apostrophes

_PROPOSAL_FENCE_LANG = "reminder_proposal"
_ADDED_TO_TODOS = re.compile(
    r"\b(?:i(?:'ve|\s+have)?|i'll|i\s+will)\s+(?:just\s+|also\s+|now\s+|gone\s+ahead\s+and\s+)?"
    r"(?:added|put|saved|placed|add|put|save)\b[^.!?\n]{0,80}?"
    r"\b(?:to|on|in|onto|into)\s+(?:your\s+)?(?:to-?do(?:\s+list)?|to-?dos|reminders|"
    # "Your list of dishes to try" is a list the reply keeps, not the to-do list.
    r"tasks|task\s+list|list(?!\s+of))\b"
    r"|\b(?:i(?:'ve|\s+have)?|i'll|i\s+will)\s+(?:just\s+|also\s+)?(?:set|created|scheduled|"
    r"set\s+up|create|schedule)\s+(?:a|the|your)\s+reminder\b"
    r"|\bit(?:'s|\s+is)\s+(?:now\s+)?(?:in|on)\s+your\s+(?:to-?do(?:\s+list)?|to-?dos|list)\b",
    re.IGNORECASE,
)
_SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+")
_WORD = re.compile(r"[^\W_]")
REMEMBERED = "Got it, I'll remember that."
NOTED = "Got it."
MEMORY_OFF = "Memory is off, so I didn't save that. You can turn it on in Settings → Memory."


def _without_todo_claims(line: str) -> str | None:
    sentences = _SENTENCE_BREAK.split(line)
    kept = [part for part in sentences if not _ADDED_TO_TODOS.search(straighten_apostrophes(part))]
    if kept == sentences:
        return line
    joined = " ".join(kept).strip()
    return joined if _WORD.search(joined) else None


def without_remember_turn_claims(message: str, user: User | None, text: str) -> str:
    """The reply to a remember command, minus any claim that it became a to-do."""
    if not memory_service.asks_to_remember(message):
        return text
    if any(fence.lang == _PROPOSAL_FENCE_LANG for fence in iter_fences(text)):
        return text
    lines: list[str] = []
    for line, fence in zip(text.split("\n"), line_fences(text), strict=True):
        kept = line if fence is not None else _without_todo_claims(line)
        if kept is not None:
            lines.append(kept)
    body = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    if body == text.strip():
        return text
    if body:
        return body
    if not memory_switch_on(user):
        return MEMORY_OFF
    return REMEMBERED if memory_service.asks_to_keep(message) else NOTED

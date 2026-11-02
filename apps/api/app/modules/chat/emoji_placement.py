"""Emoji where the user's setting puts them (``users.emoji_use``, Settings → Emoji).

The prompt says where, and a model does not always listen: at "A few", "what are the
benefits of drinking water" ended every list line with an emoji ("…the fuel for that
system 🌡️") instead of leading its label, and 🌊 opened the reply. The setting is kept
here:

- ``off``: no emoji, unless the user wrote one (then the reply may mirror it).
- ``some``: one emoji may lead a heading, a list item or a bold label line; one written
  later in such a line moves to its front, and any in a sentence goes.
- ``more``: as written.

A worked maths, physics or chemistry solution (Given, Required, Substitution, Answer…) has
none at any setting: the prompt says so, and at "Lots" its headings still got them. Nor
does the answer to a school exercise in a textbook's own shape: at "Lots" a book's answers
ended "**D. Milk** … 💧" (2026-10-31). Only when the whole message is that exercise and
the user wrote no emoji: "Calculate the tip on $80 at 20% 🍕" or a maths part beside
other requests keeps the user's setting, and a solver that only read a message decides
nothing.

Fences (code, cards, the clarify card's options), inline code and table rows are never
touched, nor is a lesson (its 🐍 and 🎉 are the lesson's own) or server text.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import TYPE_CHECKING

from app.modules.chat.markdown_regions import map_prose_outside_fences
from app.modules.chat.response_tone import DEFAULT_EMOJI_USE
from app.modules.chat.turn_prep.reading import plan_of
from app.modules.turn_reading.routing import EMOJI
from app.modules.turn_reading.school_question import in_textbook_form
from app.services.md_fence_scan import line_fences
from app.services.workout import REQUIRED_PATTERN

if TYPE_CHECKING:
    from app.modules.chat.finalize_passes import FinalizeState

# A heading, a list item or a bold label paragraph: its marker, then the text it leads.
_LABELLED = re.compile(r"^(?P<lead>\s*(?:#{1,6}\s+|(?:[-*+]|\d{1,3}[.)])\s+)?)(?P<body>.*)$")
_BOLD_START = re.compile(r"^(?:\*\*|__)")
_INLINE_CODE = re.compile(r"(`+)[^`]*?\1")
# "### Lesson 2: Loops": a lesson keeps the emoji its own rules give it.
_LESSON = re.compile(r"^#{1,6}\s.*\bLesson\s+\d", re.MULTILINE)
# A worked solution's sections, an emoji before one or not ("🎯 **Required**", "**✅ Answer**"):
# none belongs there at any setting, and "✅ **Answer**" was no Answer heading, so a Class 8
# speed came back with no answer box (2026-10-30).
_EMOJI_LEAD = rf"(?:(?:{EMOJI.pattern})[ \t]*)?"
_WORKED_SECTION = re.compile(
    rf"^[^\S\n]*(?:#{{1,4}}[ \t]+)?{_EMOJI_LEAD}\*\*{_EMOJI_LEAD}"
    rf"(?P<name>Given|{REQUIRED_PATTERN}|Solution|Formula|Substitution|Answer|Check)"
    r"(?:\s*\([a-h]\))?\s*:?\*\*",
    re.MULTILINE | re.IGNORECASE,
)


def _outside_code(text: str, change: Callable[[str], str]) -> str:
    """``change`` applied to ``text`` between inline code spans, never inside one."""
    parts: list[str] = []
    last = 0
    for span in _INLINE_CODE.finditer(text):
        parts.append(change(text[last : span.start()]))
        parts.append(span.group(0))
        last = span.end()
    parts.append(change(text[last:]))
    return "".join(parts)


# An emoji with the spaces after it: "🧠 Brain" leaves "Brain", "**🧠 Brain**" "**Brain**".
_EMOJI_AND_SPACE = re.compile(rf"(?:{EMOJI.pattern})[ \t]*")
# A space left before a closing bold marker ("**Brain power **") or punctuation. A run
# is read from its first blank only: tried from every blank in it, a long run was quadratic.
_SPACE_BEFORE_CLOSE = re.compile(
    r"(?<![ \t])[ \t]+(\*\*|__)(?=[\s.,;:!?)]|$)|(?<![ \t])[ \t]+(?=[.,;:!?)])"
)


# An emoji used as a sentence break: "Hey bini 👋 How's it going?" lost its 👋 and read
# "Hey bini How's it going?". Between a word and a capitalised word it becomes a full
# stop, unless the word leads into the next ("to 🇫🇷 France") or it is a flag.
_LEADS_ON = frozenset(
    {
        "to", "in", "at", "on", "of", "from", "for", "with", "by", "about", "like", "the",
        "a", "an", "my", "your", "our", "their", "his", "her", "its", "and", "or", "i",
    }
)  # fmt: skip
_FLAG = re.compile(r"[\U0001f1e6-\U0001f1ff]")
_NEXT_WORD = re.compile(r"[A-Z][a-z']")
# A word longer than every lead-on word is not one: the last few letters are enough.
_WORD_KEEP = max(map(len, _LEADS_ON)) + 1


def _is_word_char(char: str) -> bool:
    """The same letters as the phone's twin, whose regex has no Unicode classes."""
    return (
        "a" <= char <= "z"
        or "A" <= char <= "Z"
        or "0" <= char <= "9"
        or char == "'"
        or "\u00c0" <= char <= "\u024f"
    )


def _word_end(text: str) -> str:
    """The last ``_WORD_KEEP`` letters of the word ``text`` ends with ("" when none)."""
    start = len(text)
    while start > 0 and len(text) - start < _WORD_KEEP and _is_word_char(text[start - 1]):
        start -= 1
    return text[start:]


def _strip_blank_end(pieces: list[str]) -> None:
    while pieces:
        kept = pieces[-1].rstrip(" \t")
        if kept:
            pieces[-1] = kept
            return
        pieces.pop()


def _drop_emoji(part: str) -> str:
    """``part`` without its emoji; one that broke two sentences becomes a full stop.

    The word before each emoji is read from the end of the text kept so far, never by
    searching all of it again: on a long line every emoji re-read the whole line.
    """
    pieces: list[str] = []
    # The word the kept text ends with, and the one it ends with once its trailing
    # blanks go (each cut to ``_WORD_KEEP`` letters).
    word_at_end = word_before_blanks = ""
    last = 0
    for match in _EMOJI_AND_SPACE.finditer(part):
        between = part[last : match.start()]
        text = between.rstrip(" \t")
        if not text:
            word = word_before_blanks
            ends_on_word = word_at_end if not between else ""
        else:
            word = _word_end(text)
            if len(word) == len(text):
                word = (word_at_end + word)[-_WORD_KEEP:]
            ends_on_word = word if len(text) == len(between) else ""
        breaks = (
            bool(word)
            and word.lower() not in _LEADS_ON
            and _FLAG.search(match.group(0)) is None
            and _NEXT_WORD.match(part, match.end()) is not None
        )
        if breaks:
            if text:
                pieces.append(text)
            else:
                _strip_blank_end(pieces)
            pieces.append(". ")
            word_at_end = word_before_blanks = ""
        else:
            pieces.append(between)
            word_at_end, word_before_blanks = ends_on_word, word
        last = match.end()
    pieces.append(part[last:])
    return "".join(pieces)


def _without_emoji(line: str) -> str:
    """``line`` with no emoji outside inline code; its indent and list marker kept."""
    indent = line[: len(line) - len(line.lstrip())]
    body = _outside_code(line[len(indent) :], _drop_emoji)
    body = _SPACE_BEFORE_CLOSE.sub(lambda m: m.group(1) or "", body)
    return f"{indent}{body}".rstrip()


def _first_emoji(text: str) -> str | None:
    """The first emoji outside inline code; a lone joiner or variation mark is none."""
    runs = EMOJI.findall(_INLINE_CODE.sub(" ", text))
    return next((run for run in runs if run.strip("\ufe0f\u200d")), None)


def _leading_emoji(line: str) -> str:
    """``line`` with at most one emoji, at the front of its label."""
    match = _LABELLED.match(line)
    if match is None:
        return _without_emoji(line)
    lead, body = match.group("lead"), match.group("body")
    labelled = bool(lead.strip()) or _BOLD_START.match(body) is not None
    emoji = _first_emoji(body)
    if not labelled or emoji is None:
        return _without_emoji(line)
    rest = _without_emoji(body)
    return f"{lead}{emoji} {rest}" if rest else line


def _is_worked_solution(text: str) -> bool:
    """Two sections, one of them the working: "Answer" and "Check out" are a list."""
    names = {match.group("name").lower() for match in _WORKED_SECTION.finditer(text)}
    return len(names) >= 2 and bool(names & {"given", "formula", "substitution"})


def place_emoji(
    text: str, level: str | None, *, user_wrote_emoji: bool, homework: bool = False
) -> str:
    """``text`` with its emoji where ``level`` puts them; a worked solution, or any reply
    to ``homework``, has none."""
    level = level if level in {"off", "some", "more"} else DEFAULT_EMOJI_USE
    if not EMOJI.search(text) or (_LESSON.search(text) and level != "off"):
        return text
    if homework or _is_worked_solution(text):
        level, user_wrote_emoji = "off", False
    if level == "more" or (level == "off" and user_wrote_emoji):
        return text
    lines = text.split("\n")
    owners = line_fences(text)
    for index, line in enumerate(lines):
        if owners[index] is not None or line.lstrip().startswith("|") or not EMOJI.search(line):
            continue
        lines[index] = _without_emoji(line) if level == "off" else _leading_emoji(line)
    return "\n".join(lines)


# A person and the object of a job side by side, "👩🚀" for 👩‍🚀: the model behind a searched
# reply wrote astronauts without the joiner (2026-10-29), and the phone drew a woman and a
# rocket. Only the pairs Unicode joins into one emoji (a role, a hair style) are joined.
_PERSON = "\U0001f468\U0001f469\U0001f9d1"
_SKIN = "[\U0001f3fb-\U0001f3ff]?"
_JOINED_WITH_PERSON = (
    "\u2695\u2696\u2708\U0001f33e\U0001f373\U0001f37c\U0001f393\U0001f3a4\U0001f3a8"
    "\U0001f3eb\U0001f3ed\U0001f4bb\U0001f4bc\U0001f527\U0001f52c\U0001f680\U0001f692"
    "\U0001f9af\U0001f9b0\U0001f9b1\U0001f9b2\U0001f9b3\U0001f9bc\U0001f9bd"
)
# 🧑‍🎄 is a sequence; a man or a woman with a tree is not.
_SPLIT_PERSON = re.compile(
    rf"([{_PERSON}]{_SKIN})(?=[{_JOINED_WITH_PERSON}])|(\U0001f9d1{_SKIN})(?=\U0001f384)"
)


def join_split_emoji(text: str) -> str:
    """``text`` with each person-and-role pair written apart joined into its one emoji,
    outside code."""
    if not any(person in text for person in _PERSON):
        return text
    return map_prose_outside_fences(text, lambda prose: _SPLIT_PERSON.sub(_joined, prose))


def _joined(match: re.Match[str]) -> str:
    return f"{match.group(1) or match.group(2)}\u200d"


def place_reply_emoji(state: FinalizeState) -> str:
    """The finalize pass: a model reply's emoji follow the user's setting."""
    if state.server_text:
        return state.text
    text = join_split_emoji(state.text)
    if state.ctx.user is None:
        return text
    asked = state.ctx.user_message_content or ""
    user_wrote_emoji = EMOJI.search(asked) is not None
    homework = (
        not user_wrote_emoji
        and in_textbook_form(asked)
        and not plan_of(asked, state.settings).multi
    )
    return place_emoji(
        text, state.ctx.user.emoji_use, user_wrote_emoji=user_wrote_emoji, homework=homework
    )

"""What the user tells memory to do in a chat line: remember, forget, mute, reset, correct.

Pure text rules, no IO. Markers are scanned as literals, not a regex (CodeQL ReDoS),
and only count at the start of a clause, after nothing but "please", "can you" or
"and": "I always forget my keys" and "do you remember that song?" are talk.
"""

from __future__ import annotations

from typing import Literal

MemoryReset = Literal["clear", "off"]

# "Save to memory that I'm allergic to peanuts", "add this to your memory: …".
_SAVE_TO_MEMORY = tuple(
    f"{verb} {what}to {whose}memory"
    for verb in ("save", "add")
    for what in ("", "this ", "that ", "it ")
    for whose in ("", "your ")
)
_MEMORY_COMMAND_MARKERS = (
    "remember this",
    "remember that",
    "remember i'",
    "remember im ",
    "remember i ",
    "remember my ",
    "keep in mind",
    "please remember",
    "don't forget",
    "do not forget",
    "forget that",
    "forget this",
    "forget i ",
    "forget i'",
    "forget my ",
    "forget about",
    "stop remembering",
    "don't remember",
    "do not remember",
    *_SAVE_TO_MEMORY,
)

_FORGET_MARKERS = (
    "forget that",
    "forget this",
    "forget i ",
    "forget i'",
    "forget my ",
    "forget about",
    "stop remembering",
    "don't remember",
    "do not remember",
)

# "Stop mentioning my job": keep the fact, stop using it. These say "from now on"
# themselves, so a possessive object is enough ("never mention the war" is not).
_MUTE_ONGOING = (
    "stop mentioning",
    "stop bringing up",
    "quit mentioning",
    "quit bringing up",
    "never mention",
    "never bring up",
)
# These need the line to say it lasts: "don't mention my name" is about the draft
# in hand; "don't bring up my divorce again" is about every reply.
_MUTE_IF_LASTING = (
    "stop using my",
    "don't mention",
    "do not mention",
    "dont mention",
    "don't bring up",
    "do not bring up",
    "dont bring up",
)
_MUTE_MARKERS = (*_MUTE_ONGOING, *_MUTE_IF_LASTING)
_MUTE_LASTING = (
    "again",
    "anymore",
    "any more",
    "ever",
    "from now on",
    "going forward",
    "in answers",
    "in your answers",
    "in replies",
    "in your replies",
    "in responses",
    "in chats",
    "when you reply",
    "when you answer",
)
# "Don't mention my age in the email" shapes the draft in hand, not memory.
_DRAFT_WORDS = frozenset(
    {
        "email",
        "letter",
        "message",
        "post",
        "essay",
        "draft",
        "bio",
        "cv",
        "resume",
        "caption",
        "story",
        "speech",
        "text",
        "tweet",
        "note",
        "card",
        "toast",
        "intro",
    }
)

# "Forget everything you know about me" empties memory; "stop remembering things
# about me" turns it off. Both wait for the user to tap a card.
_RESET_CLEAR_MARKERS = (
    "forget everything",
    "forget all",
    "delete everything you know",
    "erase everything you know",
    "wipe everything you know",
    "clear everything you know",
    "delete all my memories",
    "delete my saved memories",
    "clear my saved memories",
    "clear your memory",
    "wipe your memory",
    "erase your memory",
    "delete your memory",
    "reset your memory",
)
# After "forget everything": the user's memory, not this conversation's last answer.
_ABOUT_THE_USER = (
    "about me",
    "you know",
    "you remember",
    "you've saved",
    "you saved",
    "you've learned",
    "you learned",
    "you have on me",
)
_RESET_OFF_MARKERS = (
    "stop remembering things",
    "stop remembering stuff",
    "stop remembering anything",
    "stop remembering me",
    "stop remembering what i",
    "stop saving things about me",
    "stop saving stuff about me",
    "stop saving anything about me",
    "stop learning about me",
    "don't remember anything",
    "do not remember anything",
    "turn memory off",
    "turn off your memory",
)
# Only as the whole ask: "turn off memory leak warnings in Xcode" is not one.
_RESET_OFF_ALONE = ("turn off memory", "disable memory", "disable your memory")
_ALONE_TAIL = frozenset({"", "please", "pls", "now", "for me", "thanks", "thank you"})

# "That's wrong, I'm at Stripe now", "I switched from FastAPI to Django": a saved
# fact may have changed. Read anywhere in the line; it only makes the memory pass run.
_CORRECTION_MARKERS = (
    "that's wrong",
    "that is wrong",
    "that's not right",
    "that's not true",
    "that's incorrect",
    "that's outdated",
    "you got that wrong",
    "not anymore",
    "no longer",
    "i switched from",
    "i switched to",
    "i've switched",
    "i moved to",
    "i've moved to",
    "i changed jobs",
    "i changed my",
    "i now work",
    "i now live",
    "i don't work at",
    "i dont work at",
    "i quit my",
    "i left my job",
    "actually i",
    "actually, i",
    "actually my",
)

_REMEMBER_MARKERS = frozenset(
    {
        "remember this",
        "remember that",
        "remember i'",
        "remember im ",
        "remember i ",
        "remember my ",
    }
)
# Words that may come before an instruction in the same clause: "oh and",
# "please", "can you". Anything else makes it a statement or a question about
# remembering: "I always forget my keys", "do you remember that song?".
_CONNECTIVES = frozenset(
    {"and", "but", "also", "so", "now", "ok", "okay", "oh", "hey", "actually", "wait"}
)
_POLITE_LEADS: tuple[tuple[str, ...], ...] = (
    ("please",),
    ("pls",),
    ("can", "you"),
    ("could", "you"),
    ("would", "you"),
    ("will", "you"),
    ("i", "want", "you", "to"),
    ("i", "need", "you", "to"),
    ("i'd", "like", "you", "to"),
    ("make", "sure", "to"),
    ("make", "sure", "you"),
    ("go", "ahead", "and"),
    ("for", "future", "chats"),
    ("for", "future", "reference"),
    ("going", "forward"),
    ("from", "now", "on"),
)
_CLAUSE_BREAKS = ".!?;:,\n\u2014\u2013"
# "Forget about the previous question" drops a turn, not a saved fact.
_CHAT_PARTS = frozenset(
    {
        "question",
        "questions",
        "request",
        "prompt",
        "problem",
        "answer",
        "reply",
        "message",
        "part",
        "chat",
        "conversation",
        "topic",
    }
)
_CHAT_PART_LEADS = frozenset(
    {
        "the",
        "my",
        "your",
        "that",
        "this",
        "previous",
        "last",
        "earlier",
        "above",
        "first",
        "other",
        "whole",
    }
)
_DRAFT_SCOPE_WORDS = 8


def is_explicit_memory_command(text: str) -> bool:
    """True when the user asked memory to remember, forget, mute or reset in this turn."""
    lowered = _fold_quotes(text)
    if not lowered:
        return False
    if any(
        _is_command_at(lowered, marker, index)
        for marker in _MEMORY_COMMAND_MARKERS
        for index in _marker_positions(lowered, marker)
    ):
        return True
    return is_explicit_mute_command(text) or memory_reset_request(text) is not None


def asks_to_remember(text: str) -> bool:
    """True when the user asked memory to keep something: not forget, mute or reset."""
    return (
        is_explicit_memory_command(text)
        and not is_explicit_forget_command(text)
        and not is_explicit_mute_command(text)
        and memory_reset_request(text) is None
    )


def is_explicit_forget_command(text: str) -> bool:
    """True when the user asked to drop a stored fact, not to remember one."""
    lowered = _fold_quotes(text)
    if not lowered:
        return False
    return any(
        not _forget_marker_is_negated(lowered, index) and _is_command_at(lowered, marker, index)
        for marker in _FORGET_MARKERS
        for index in _marker_positions(lowered, marker)
    )


def is_explicit_mute_command(text: str) -> bool:
    """True for "stop mentioning my job": keep a saved fact but stop using it."""
    lowered = _fold_quotes(text)
    if not lowered:
        return False
    lasting = any(_has_phrase(lowered, cue) for cue in _MUTE_LASTING)
    for marker in _MUTE_MARKERS:
        for index in _marker_positions(lowered, marker):
            if not _is_command_at(lowered, marker, index):
                continue
            words = [word.strip(".,!?;:") for word in lowered[index + len(marker) :].split()]
            if _DRAFT_WORDS.intersection(words[:_DRAFT_SCOPE_WORDS]):
                continue
            if lasting or (marker in _MUTE_ONGOING and words and words[0] == "my"):
                return True
    return False


def forget_requests(text: str) -> list[str]:
    """What each "forget …" instruction names: "forget that I use React" → "I use React"."""
    return _named_after(text, _FORGET_MARKERS, forget=True)


def remember_requests(text: str) -> list[str]:
    """What each "remember …" instruction names: "remember I'm vegetarian" → "vegetarian"."""
    return _named_after(text, tuple(_REMEMBER_MARKERS), forget=False)


def mute_requests(text: str) -> list[str]:
    """What each "stop mentioning …" instruction names: "my job"."""
    if not is_explicit_mute_command(text):
        return []
    return _named_after(text, _MUTE_MARKERS, forget=False)


def _named_after(text: str, markers: tuple[str, ...], *, forget: bool) -> list[str]:
    lowered = _fold_quotes(text)
    # Slice the user's own casing ("React" vs "React Native") when lowering kept the length.
    source = text if len(text) == len(lowered) else lowered
    named: list[str] = []
    for marker in sorted(markers, key=len, reverse=True):
        for index in _marker_positions(lowered, marker):
            if forget and _forget_marker_is_negated(lowered, index):
                continue
            if not _is_command_at(lowered, marker, index):
                continue
            # "forget my …" and "forget i'm …" keep who the fact is about.
            start = index + len(marker)
            for lead in ("my ", "i ", "i'"):
                if marker.endswith(f" {lead}") or marker.endswith(f" {lead.strip()}"):
                    start -= len(lead)
                    break
            rest = source[start:]
            cut = min((pos for mark in ".!?;,\n" if (pos := rest.find(mark)) >= 0), default=-1)
            phrase = (rest[:cut] if cut >= 0 else rest).strip()
            if phrase and all(phrase not in seen and seen not in phrase for seen in named):
                named.append(phrase)
    return named


def memory_reset_request(text: str) -> MemoryReset | None:
    """ "clear" for "forget everything you know about me", "off" for "stop remembering
    things about me", else None. Neither is applied from chat: Settings → Memory does it."""
    lowered = _fold_quotes(text)
    if not lowered:
        return None
    for marker in _RESET_OFF_MARKERS:
        if any(
            _is_command_at(lowered, marker, index) for index in _marker_positions(lowered, marker)
        ):
            return "off"
    for marker in _RESET_OFF_ALONE:
        for index in _marker_positions(lowered, marker):
            tail = lowered[index + len(marker) :].strip(" .!?,")
            if _is_command_at(lowered, marker, index) and tail in _ALONE_TAIL:
                return "off"
    for marker in _RESET_CLEAR_MARKERS:
        for index in _marker_positions(lowered, marker):
            if not _is_command_at(lowered, marker, index):
                continue
            rest = lowered[index + len(marker) :]
            if marker.startswith("forget") and not any(
                _has_phrase(rest, cue) for cue in _ABOUT_THE_USER
            ):
                continue
            return "clear"
    return None


def is_memory_correction(text: str) -> bool:
    """True when the line corrects something the user said before ("not anymore")."""
    lowered = _fold_quotes(text)
    return bool(lowered) and any(_has_phrase(lowered, marker) for marker in _CORRECTION_MARKERS)


def _fold_quotes(text: str | None) -> str:
    lowered = (text or "").lower().replace("\u2019", "'").replace("\u2018", "'")
    # "Remember, I'm allergic to peanuts" and "remember: my wife is Sara" ask what
    # "remember I'm …" asks.
    for mark in ("remember, ", "remember: ", "remember,", "remember:"):
        lowered = lowered.replace(mark, "remember ")
    return lowered


def _has_phrase(lowered: str, phrase: str) -> bool:
    """``phrase`` as whole words: "ever" is not in "everything"."""
    end = len(phrase)
    return any(
        index + end >= len(lowered) or not lowered[index + end].isalnum()
        for index in _marker_positions(lowered, phrase)
    )


def _marker_positions(lowered: str, marker: str) -> list[int]:
    positions: list[int] = []
    start = 0
    while (index := lowered.find(marker, start)) >= 0:
        if index == 0 or not lowered[index - 1].isalnum():
            positions.append(index)
        start = index + 1
    return positions


def _is_command_at(lowered: str, marker: str, index: int) -> bool:
    """The marker starts its clause, after nothing but "please", "can you" or "and"."""
    before = lowered[:index]
    cut = max(before.rfind(mark) for mark in _CLAUSE_BREAKS)
    clause = before[cut + 1 :].split()
    led = False
    while clause:
        if clause[0] in _CONNECTIVES:
            clause = clause[1:]
            continue
        lead = next((lead for lead in _POLITE_LEADS if tuple(clause[: len(lead)]) == lead), None)
        if lead is None:
            break
        clause = clause[len(lead) :]
        led = True
    if clause:
        return False
    after = lowered[index + len(marker) :].split()
    if (marker.startswith("forget") or marker in _MUTE_MARKERS) and _names_a_chat_part(after):
        return False
    # "Remember that song from Titanic?" asks; "can you remember that …?" tells.
    return not (marker in _REMEMBER_MARKERS and not led and lowered.rstrip().endswith("?"))


def _names_a_chat_part(words: list[str]) -> bool:
    head = [word.strip(".,!?;:") for word in words[:3]]
    while head and head[0] in _CHAT_PART_LEADS:
        head = head[1:]
    return bool(head) and head[0] in _CHAT_PARTS


def _forget_marker_is_negated(lowered: str, index: int) -> bool:
    before = lowered[:index]
    return before.endswith("don't ") or before.endswith("do not ") or before.endswith("dont ")

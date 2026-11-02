"""Sentences in a reply that say a reminder change already happened.

The app's own result line or card is the only confirmation of a reminder. With
reminder cards on (the default) nothing is saved until the user taps, so the
model's "Done! I've set a reminder for 9 AM" above the card is false.
``without_claims`` drops those sentences and keeps the rest of the reply:
"Water boils at 100 °C" stays above the card.

A claim names a reminder, the card's item or a time, or is a bare "Done!" or
"All set!". "I set aside time to write" in a story, "the meeting is set for
Friday" and a question ("Want me to add another?") are not claims.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from app.services.md_fence_scan import line_fences

# The words a change's result line opens with: the app's own ("Set:", "Moved:", "Done:")
# and a model's copies of them ("Updated: Study bio — 8:00 PM" with nothing changed).
CLAIM_VERBS = (
    r"(?:added|set|moved|deleted|done|reopened|scheduled|rescheduled|saved|created|"
    r"date removed|removed|updated|changed|completed|edited|renamed|marked(?:\s+done)?)"
)
# The app's own result line: "Set: gym — Thursday, 6:00 PM.", "Added: milk".
# On one line: "Updated:" above an edited draft on the lines after it claims nothing.
CLAIM_LINE_RE = re.compile(rf"^{CLAIM_VERBS}[ \t]*:[ \t]+\S", re.IGNORECASE)
COLON_CLAIM_RE = re.compile(rf"(?:got it!?\s*)?{CLAIM_VERBS}[ \t]*:[ \t]+\S", re.IGNORECASE)
# Prose that says a change was made, checked only for a message that asked for one.
PROSE_CLAIM_RE = re.compile(
    r"\b(?:i(?:['\u2019]ve| have)?\s+added|"
    r"i(?:['\u2019]ll| will)\s+add|"
    r"added (?:your|it|that|a reminder|to your)|"
    r"you(?:['\u2019]ll| will)\s+now (?:get|have)|"
    r"marked as done|changed to|updated!|(?:to|on) your (?:grocery|shopping) list|"
    r"(?:moved|marked|deleted|removed|pushed|rescheduled|postponed|reopened|unchecked)\s+\**\w"
    r"|checked off|(?:is|are) open again|back on your list)",
    re.IGNORECASE,
)

_NOUN = r"(?:reminders?|alarms?|to-?dos?|tasks?|notifications?)"
_YOUR_LIST = r"your\s+(?:reminders?|to-?dos?|to-?do\s+list|list|tasks?|schedule)"
_DID = r"\b(?:i|we)(?:'ve| have)?(?:\s+(?:just|now|also|already|gone ahead and|went ahead and))?"
_WILL = (
    r"\b(?:i|we)(?:'ll| will|'m going to| am going to| are going to)"
    r"(?:\s+(?:also|definitely|go ahead and|make sure to|be sure to))?"
)
_CHANGED = (
    r"(?:moved|marked|deleted|removed|rescheduled|postponed|reopened|unchecked|updated"
    r"|changed|cancell?ed|completed|checked off|cleared)"
)
# "Setting that reminder for you now!", "I'm adding it": nothing is being set either.
# Said by the assistant: after "I'm", after an "OK", or opening the sentence on the one
# just asked for ("Setting that…"). "Setting a reminder for your snack is a good idea"
# and "Adding a reminder the night before helps" are advice.
_ACK_LEAD = r"(?:ok|okay|sure|great|perfect|got it|alright|all right)[,!.]?\s+"
_GERUND = r"(?:setting|adding|saving|scheduling|creating|putting)"
_DOING = rf"(?:^{_ACK_LEAD}|\b(?:i|we)(?:'m| am|'re| are)\s+)(?:now\s+|just\s+|also\s+)?{_GERUND}"
_DOING_THAT = rf"(?:{_DOING}|^{_GERUND})\s+(?:up\s+)?(?:that|this|it|them)"
# A claim on its own: about a reminder by its words alone.
_CLAIM_RE = re.compile(
    "|".join(
        (
            rf"{_DID}\s+(?:set|added|saved|scheduled|created|made|put|booked|logged|noted)\s+"
            rf"(?:up\s+)?(?:a|an|the|your|you|one|two|three|both|these|those|this|that)\s+"
            rf"(?:[\w'-]+\s+){{0,4}}?{_NOUN}\b",
            rf"{_WILL}\s+(?:\w+\s+){{0,2}}?(?:remind|ping|nudge|notify|alert)\s+you\b",
            rf"(?:{_DOING}\s+(?:up\s+)?(?:a|an|the|your|that|this|one)|{_DOING_THAT})\s+"
            rf"(?:[\w'-]+\s+){{0,3}}?{_NOUN}\b(?!\s+(?:system|app|feature|tool|habit|routine"
            r"|settings?)\b)",
            rf"{_DOING}\s+(?:[\w'-]+\s+){{1,4}}?(?:to|on|in|into)\s+{_YOUR_LIST}\b",
            # "Sure thing! I'll set that for you." above the card.
            rf"{_WILL}\s+(?:set|add|save|schedule|create|put)\s+(?:it|that|this|them)\s+"
            r"(?:up\s+)?for you(?:\s+(?:now|right away))?(?=[\s!.]*$)",
            rf"{_WILL}\s+(?:\w+\s+){{0,2}}?(?:set|add|save|schedule|create|put)\s+(?:up\s+)?"
            rf"(?:a|an|the|that|this|it)\s+(?:[\w'-]+\s+){{0,3}}?{_NOUN}\b",
            r"\byou(?:'ll| will)\s+(?:now\s+|also\s+)?(?:be\s+(?:reminded|notified|pinged|alerted)"
            r"|(?:get|receive|have|see)\s+(?:a|an|your|the)\s+(?:[\w'-]+\s+){0,2}?"
            r"(?:reminders?|notifications?|nudges?|pings?|alerts?))\b",
            r"\breminders?(?:'s|\s+(?:is|are|was|were|has been|have been))?\s+(?:now\s+|all\s+)?"
            r"(?:set|saved|added|scheduled|created|booked)\b",
            rf"\b(?:added|saved|put)\s+(?:(?:it|that|this|them)\s+)?(?:to|on|in|into)\s+{_YOUR_LIST}\b",
            rf"\b(?:it|that|this|they)(?:'s|'re| is| are| has been| have been)\s+(?:now\s+)?"
            rf"(?:on|in)\s+{_YOUR_LIST}\b",
        )
    )
)
# A claim only beside a reminder word, the card's item, or a time: "I've set it
# for 9 AM", "Moved gym to Sunday". "It's set to 180°C" in a recipe is not one.
_CONTEXT_CLAIM_RE = re.compile(
    "|".join(
        (
            rf"{_DID}\s+(?:set|added|saved|scheduled|created|put|noted|booked|logged|{_CHANGED})\s+"
            r"(?:it|that|this|them|those|both|one|up|everything)\b",
            rf"{_DID}\s+{_CHANGED}\b",
            r"\b(?:it|that|this|everything|they)(?:'s|'re| is| are| was| has been| have been)\s+"
            r"(?:all\s+|now\s+)?(?:set|scheduled|saved|booked|added|created|done|updated|moved"
            r"|deleted|removed|marked)\b",
            r"^(?:(?:ok|okay|sure|great|perfect|got it|alright|all right|done)[,!.]?\s+)?"
            r"(?:scheduled|saved|added|created|booked|moved|deleted|removed|marked"
            r"|rescheduled|updated|postponed|reopened)\b",
            # "Got it, set for 7 PM", "All set for tomorrow": not "Set a reminder for 12:30",
            # which is advice.
            rf"^(?:{_ACK_LEAD}(?:all\s+)?|all\s+)set\b",
            r"\bgot (?:it|that|this|you|them|everything) (?:all\s+)?(?:set|scheduled|saved|added)\b",
            # Not a sentence opening on the doing: "Setting it to 350°F for 20 minutes
            # tonight works best", "Setting this up takes 5 minutes each morning".
            rf"{_DOING}\s+(?:up\s+)?(?:that|this|it|them)\b",
            r"^done\b",
        )
    )
)
_CONTEXT_RE = re.compile(
    rf"\b{_NOUN}\b|\b{_YOUR_LIST}\b|\bas\s+(?:done|complete|completed|finished)\b"
    r"|\b\d{1,2}(?::\d{2})?\s*(?:am|pm|a\.m\.|p\.m\.)|\b\d{1,2}:\d{2}\b"
    r"|\b(?:today|tonight|tomorrow|monday|tuesday|wednesday|thursday|friday|saturday|sunday"
    r"|noon|midnight|morning|afternoon|evening|daily|weekly|weekdays|monthly)\b",
    re.IGNORECASE,
)
_ACK = r"(?:ok|okay|sure|great|perfect|got it|alright|all right|no problem|of course|absolutely)"
# "Done!", "All set ✅", "Okay, reminder set." on their own.
_BARE_CLAIM_RE = re.compile(
    rf"(?:{_ACK}[,!.]?\s+)?(?:done|all done|all set|you're all set|you're set|you are all set"
    r"|consider it done|noted|saved|scheduled|added|booked|sorted|taken care of"
    r"|reminder (?:set|added|saved|created|scheduled))"
)
# "Sure!" on its own above the card says nothing.
_ACK_ONLY_RE = re.compile(rf"{_ACK}|got it|you got it|will do|sounds good")
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+(?=[^a-z])")
# A claim that ends a sentence: "Water boils at 100 °C, and I've set a reminder…".
_CLAUSE_RE = re.compile(
    r"(?:,|;|\s[\u2014\u2013-])\s+(?:and\s+|so\s+)?(?=(?:i|you|it|your)\b)"
    r"|\s+and\s+(?=i(?:'ve|'ll| have| will)\b)",
    re.IGNORECASE,
)
_MARKER_RE = re.compile(r"^(\s*(?:[-*+>]\s+|\d+[.)]\s+)?)(.*)$", re.DOTALL)
_WORD_RE = re.compile(r"[^\W_]")


def without_claim_lines(lines: list[str]) -> list[str]:
    """Drop "Added: …" lines outside code fences; a ``done: false`` field stays."""
    if not lines:
        return []
    owners = line_fences("\n".join(lines))
    return [
        line
        for line, fence in zip(lines, owners, strict=True)
        if fence is not None or not CLAIM_LINE_RE.match(line.strip())
    ]


def without_claims(text: str, titles: Iterable[str] = ()) -> str:
    """The reply without sentences that say a reminder change already happened.

    ``titles`` are the card's items: "I've marked call mom as done" names one.
    Code is left alone. A reply left with only "Sure!" says nothing beside the
    app's own line or card, so it goes too.
    """
    named = tuple(title.strip().lower() for title in titles if len(title.strip()) >= 3)
    kept: list[str] = []
    for line, fence in zip(text.split("\n"), line_fences(text), strict=True):
        cleaned = line if fence is not None else _line_without_claims(line, named)
        if cleaned is not None:
            kept.append(cleaned)
    body = re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()
    return "" if _ACK_ONLY_RE.fullmatch(_plain(body)) else body


# "When should I remind you?", "What time works?": a question the card already answers.
_ASKS_WHEN_RE = re.compile(r"\b(?:when|what time|which day)\b", re.IGNORECASE)


def without_when_questions(text: str) -> str:
    """The reply without a question asking when, once the app's card holds the time.

    "Remind me to stretch in 3 minutes" answered "When should I remind you?" above
    a card due in three minutes contradicted itself. Code is left alone.
    """
    kept: list[str] = []
    for line, fence in zip(text.split("\n"), line_fences(text), strict=True):
        sentences = _SENTENCE_RE.split(line) if fence is None else [line]
        left = [
            part
            for part in sentences
            if fence is not None or not (part.rstrip().endswith("?") and _ASKS_WHEN_RE.search(part))
        ]
        if left == sentences:
            kept.append(line)
            continue
        joined = " ".join(left).strip()
        if _WORD_RE.search(joined) and not _ACK_ONLY_RE.fullmatch(_plain(joined)):
            kept.append(joined)
    body = re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()
    return "" if _ACK_ONLY_RE.fullmatch(_plain(body)) else body


def split_sentences(line: str) -> list[str]:
    """One line of prose as its sentences."""
    return _SENTENCE_RE.split(line)


def is_claim(sentence: str, titles: Iterable[str] = ()) -> bool:
    """One sentence that says a reminder change happened (see the module doc)."""
    plain = _plain(sentence)
    if not plain or sentence.rstrip().endswith("?"):
        return False
    if _BARE_CLAIM_RE.fullmatch(plain) or COLON_CLAIM_RE.match(plain) or _CLAIM_RE.search(plain):
        return True
    if not (_CONTEXT_CLAIM_RE.search(plain) or PROSE_CLAIM_RE.search(plain)):
        return False
    return bool(_CONTEXT_RE.search(plain)) or any(title in plain for title in titles)


def _line_without_claims(line: str, titles: tuple[str, ...]) -> str | None:
    """The line minus its claim sentences; None when nothing worth keeping is left."""
    if not line.strip():
        return line
    if CLAIM_LINE_RE.match(line.strip()):
        return None
    marker = _MARKER_RE.match(line)
    prefix, body = (marker.group(1), marker.group(2)) if marker else ("", line)
    sentences = _SENTENCE_RE.split(body)
    kept = [part for part in (_without_claim_tail(s, titles) for s in sentences) if part]
    if kept == sentences:
        return line
    joined = " ".join(kept).strip()
    return f"{prefix}{joined}" if _WORD_RE.search(joined) else None


def _without_claim_tail(sentence: str, titles: tuple[str, ...]) -> str:
    """The sentence with its claim clause cut off, or "" when all of it is a claim."""
    for boundary in _CLAUSE_RE.finditer(sentence):
        head, tail = sentence[: boundary.start()], sentence[boundary.end() :]
        if _WORD_RE.search(head) and not is_claim(head, titles) and is_claim(tail, titles):
            return head.rstrip(" ,;\u2014\u2013-") + "."
    return "" if is_claim(sentence, titles) else sentence


def _plain(text: str) -> str:
    """Lower case, straight apostrophes, no markdown emphasis, no edge punctuation or emoji."""
    lowered = text.lower().replace("\u2019", "'").replace("*", "").replace("`", "")
    lowered = re.sub(r"(?<!\w)_|_(?!\w)", "", lowered)
    return re.sub(r"^[^\w]+|[^\w)]+$", "", lowered.strip())

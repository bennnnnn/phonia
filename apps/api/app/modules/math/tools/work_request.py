"""Find a student's worked lines in a "check my work" message.

String level only, no SymPy: the routing gate runs this on every math-looking
message. It returns the lines to check, the one letter they solve for, and
whether the student asked for a hint instead of the fix. A message it cannot
read with confidence returns None and keeps the normal math path, so a line
it half-understood is never graded.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.modules.math.function_names import MATH_FUNCTION_NAMES
from app.services.glyphs import OPERATOR_GLYPHS
from app.services.number_text import FRACTION_OR_DECIMAL
from app.services.student_claim import CLAIM_LEAD

_MAX_TEXT = 1000
_MAX_LINES = 12
_MAX_TOKENS = 40

_CHECK_CUES: tuple[str, ...] = (
    "check my work",
    "check my steps",
    "check my solution",
    "check my answer",
    "check my working",
    "check my math",
    "check my algebra",
    "check this work",
    "check my attempt",
    "check if i",
    "check whether i",
    "is this right",
    "is this correct",
    "is that right",
    "is that correct",
    "is my work",
    "is my answer",
    "is my solution",
    "am i right",
    "am i correct",
    "did i do this right",
    "did i do it right",
    "did i get it right",
    "did i get this right",
    "did i solve",
    "where did i go wrong",
    "where did i mess up",
    "where did i make a mistake",
    "where is my mistake",
    "where's my mistake",
    "find my mistake",
    "find the mistake",
    "find my error",
    "spot my mistake",
    "what did i do wrong",
    "what's wrong with my",
    "what is wrong with my",
    "is there a mistake",
    "any mistakes",
    "grade my work",
    "mark my work",
)

# "Don't finish it for me": point at the slip, never show the fixed line.
_HINT_CUES: tuple[str, ...] = (
    "don't finish",
    "dont finish",
    "do not finish",
    "just a hint",
    "only a hint",
    "just give me a hint",
    "give me a hint",
    "hint only",
    "just hint",
    "don't give me the answer",
    "dont give me the answer",
    "do not give me the answer",
    "don't tell me the answer",
    "dont tell me the answer",
    "do not tell me the answer",
    "don't solve it",
    "dont solve it",
    "do not solve it",
    "without the answer",
    "without giving the answer",
    "let me finish",
    "i want to finish",
)

# The operators are the shared table (services/glyphs.py); the rest are this reader's.
_UNICODE = (
    ("\u2019", "'"),
    *OPERATOR_GLYPHS.items(),
    ("\u2264", "<="),
    ("\u2265", ">="),
    ("\u00b1", "+-"),
    ("\u00b2", "^2"),
    ("\u00b3", "^3"),
)

# A new line of work starts after a newline, ";", ", ", a sentence end, an
# arrow, or a connective ("so", "then", "and got", …). A comma without a space
# stays inside a line ("1,000"), so an unsplit pair is refused later instead
# of being read as two lines.
_SEGMENT_SPLIT = re.compile(
    r"\n|;|,\s+|[.?!](?=\s|$)|=>|->|\u2192|\u21d2|\u2234"
    r"|\b(?:then|so|therefore|thus|hence|which\s+gives|which\s+means|that\s+gives"
    r"|giving|gives|and\s+i\s+got|and\s+i\s+get|and\s+got|and\s+get|i\s+got|i\s+get"
    r"|we\s+get|we\s+got)\b",
    re.IGNORECASE,
)
_NUMBERING = re.compile(r"^(?:(?:step|line)\s*\d{1,2}\s*[:.)-]?|\(?\d{1,2}[.)])\s+", re.IGNORECASE)
_BULLET = re.compile(r"^[*\u2022]\s+")
_LINE_NUMBERING = re.compile(
    r"^[ \t]*(?:(?:step|line)[ \t]*\d{1,2}[ \t]*[:.)-]?|\(?\d{1,2}[.)])[ \t]+",
    re.IGNORECASE | re.MULTILINE,
)
_COMMENT_PARENS = re.compile(r"\(([^()]*)\)")
_COMPARATOR = re.compile(r"<=|>=|<|>|=")
_MATH_CHARS = re.compile(r"^[0-9A-Za-z\s+\-*/^().=<>]+$")
_WORD = re.compile(r"[A-Za-z]+")
_WORDY_TOKEN = re.compile(r"^[A-Za-z']+[:,!?]?$")
_ISOLATED = re.compile(
    rf"^\s*(?:(?P<var>[A-Za-z])\s*(?:<=|>=|<|>|=)\s*{FRACTION_OR_DECIMAL}"
    rf"|{FRACTION_OR_DECIMAL}\s*(?:<=|>=|<|>|=)\s*(?P<var2>[A-Za-z]))\s*$"
)
_EQUALS_VALUE = re.compile(rf"^\s*(?P<var>[A-Za-z])\s*=\s*(?P<value>{FRACTION_OR_DECIMAL})\s*$")
_BARE_VALUE = re.compile(rf"^\s*(?P<value>{FRACTION_OR_DECIMAL})\s*$")
_PLUS_MINUS = re.compile(
    rf"^\s*(?P<var>[A-Za-z])\s*=\s*(?:\+-|\+/-)\s*(?P<value>{FRACTION_OR_DECIMAL})\s*$"
)
_OR_SPLIT = re.compile(r"\s(?:or|and)\s+", re.IGNORECASE)
_AND_SPLIT = re.compile(r"\sand\s+", re.IGNORECASE)
_ORDER = re.compile(r"[<>]")
_ROOT_CLAIM = re.compile(
    r"\b(?:i\s+(?:got|found)|i\s+think|my)\s+(?:the\s+)?roots?"
    r"(?:\s+(?:are|is))?\s+(\S(?:.*?\S)??)\s+for\s+(.+)",
    re.IGNORECASE,
)

# "I got x = 4 for 3x - 2 = 10": the answer comes before the equation.
_ANSWER_CLAIM = re.compile(
    # "I get / I have" too: a ``var = value`` follows, so it is a claim, not a given.
    rf"(?:{CLAIM_LEAD}|\bi\s+(?:get|have)\b)\s+"
    rf"(?P<var>[A-Za-z])\s*=\s*(?P<value>{FRACTION_OR_DECIMAL})"
    rf"\s+(?:for|in|on|when\s+solving|solving)\s+(?P<equation>.+)",
    re.IGNORECASE,
)

FUNCTION_WORDS = MATH_FUNCTION_NAMES | {"pi"}
# Letters that name a constant somewhere in the parser, never the unknown.
_RESERVED_LETTERS = frozenset("eEiI")


@dataclass(frozen=True)
class WorkRequest:
    """The student's lines, each one relation as written (``"2x+3=11"``).

    A final ``"x = 2 or x = 3"`` line lists every value the student found.
    """

    lines: tuple[str, ...]
    variable: str
    hint_only: bool
    cued: bool


class _Prose:
    """A segment with no relation in it: commentary, skipped."""


_PROSE = _Prose()


def parse_work_request(text: str) -> WorkRequest | None:
    """The student's worked lines, or None when this is not a work check."""
    if not text or len(text) > _MAX_TEXT:
        return None
    normalized = _normalize(text)
    lowered = normalized.lower()
    hint_only = any(cue in lowered for cue in _HINT_CUES)
    cued = hint_only or any(cue in lowered for cue in _CHECK_CUES)
    claimed = _claimed_roots_request(normalized, hint_only=hint_only, cued=cued)
    if claimed is None:
        claimed = _claimed_answer_request(normalized, hint_only=hint_only, cued=cued)
    if claimed is not None:
        return claimed
    if not cued and not _uncued_shape(normalized):
        return None
    lines: list[str] = []
    segments = [
        piece for segment in _SEGMENT_SPLIT.split(normalized) for piece in _and_pieces(segment)
    ]
    for segment in segments:
        line = _math_line(segment)
        if line is None:
            return None
        if isinstance(line, _Prose):
            continue
        bare = _BARE_VALUE.match(line) if "=" not in line else None
        if bare is not None:
            # "x = 2, 3": a second value for the line before it.
            if not lines or not _only_values(lines[-1]):
                return None
            var = _EQUALS_VALUE.match(lines[-1].split(" or ")[0])
            if var is None:
                return None
            lines[-1] = f"{lines[-1]} or {var['var']} = {bare['value'].strip()}"
            continue
        lines.append(line)
    lines = _merge_final_values(lines)
    if len(lines) < 2 or len(lines) > _MAX_LINES:
        return None
    variable = _single_variable(lines)
    if variable is None:
        return None
    if not cued and not _uncued_chain(lines):
        return None
    return WorkRequest(tuple(lines), variable, hint_only, cued)


def _claimed_roots_request(text: str, *, hint_only: bool, cued: bool) -> WorkRequest | None:
    """Turn “I got roots 2 and 6 for …” into a two-line work check."""
    if not cued:
        return None
    match = _ROOT_CLAIM.search(text)
    if match is None:
        return None
    raw_values, raw_equation = match.group(1), match.group(2)
    value_parts = re.split(r"(?:,|\band\b|\bor\b)\s*", raw_values, flags=re.IGNORECASE)
    values: list[str] = []
    for part in value_parts:
        parsed = _BARE_VALUE.fullmatch(part.strip())
        if parsed is None:
            return None
        values.append(parsed["value"].replace(" ", ""))
    if not 1 <= len(values) <= 4:
        return None
    equation = raw_equation
    lower_equation = equation.lower()
    for cue in _CHECK_CUES:
        index = lower_equation.find(cue)
        if index > 0:
            equation = equation[:index]
            break
    equation = equation.strip().rstrip(" .?!")
    line = _math_line(equation)
    if not isinstance(line, str) or "=" not in line:
        return None
    equation_letters = set(re.findall(r"[A-Za-z]", line)) - _RESERVED_LETTERS
    variable = next((name for name in ("x", "y", "z", "t", "n") if name in equation_letters), None)
    if variable is None:
        return None
    answer_line = " or ".join(f"{variable} = {value}" for value in values)
    return WorkRequest((line, answer_line), variable, hint_only, cued)


def _equation_before_cue(raw: str) -> str:
    """The equation in "… for 3x - 2 = 10, is that right?", without the question."""
    lower = raw.lower()
    for cue in _CHECK_CUES:
        index = lower.find(cue)
        if index > 0:
            raw = raw[:index]
            break
    return raw.strip().rstrip(" .,?!")


def _claimed_answer_request(text: str, *, hint_only: bool, cued: bool) -> WorkRequest | None:
    """Turn “I got x = 4 for 3x - 2 = 10, is that right?” into a two-line work check."""
    if not cued:
        return None
    match = _ANSWER_CLAIM.search(text)
    if match is None:
        return None
    line = _math_line(_equation_before_cue(match["equation"]))
    if not isinstance(line, str) or "=" not in line:
        return None
    variable = match["var"]
    if variable in _RESERVED_LETTERS or variable not in re.findall(r"[A-Za-z]", line):
        return None
    answer_line = f"{variable} = {match['value'].replace(' ', '')}"
    return WorkRequest((line, answer_line), variable, hint_only, cued)


def _and_pieces(segment: str) -> list[str]:
    """``2x = 8 and x = 4`` is two lines. Inequalities joined by "and" are one
    answer (an intersection), so they are left whole and refused later."""
    parts = _AND_SPLIT.split(segment)
    if len(parts) > 1 and all("=" in part and not _ORDER.search(part) for part in parts):
        return parts
    return [segment]


def _normalize(text: str) -> str:
    for glyph, replacement in _UNICODE:
        text = text.replace(glyph, replacement)
    # "1. 2x + 3 = 11": the list number's period is not a sentence end.
    text = _LINE_NUMBERING.sub("", text)
    return text.replace("=<", "<=")


def _uncued_shape(text: str) -> bool:
    """Without a cue, only a bare column of relations reads as work to check."""
    rows = [row.strip() for row in text.strip().splitlines() if row.strip()]
    return len(rows) >= 2 and all(_COMPARATOR.search(row) for row in rows)


def _uncued_chain(lines: list[str]) -> bool:
    """A worked chain ends on the answer and starts on the problem."""
    return not _is_isolated(lines[0]) and _is_isolated(lines[-1])


def _is_isolated(line: str) -> bool:
    return _ISOLATED.match(line) is not None or _only_values(line)


def _only_values(line: str) -> bool:
    parts = line.split(" or ")
    return all(_EQUALS_VALUE.match(part) for part in parts)


def _merge_final_values(lines: list[str]) -> list[str]:
    """``x = 2`` then ``x = 3`` at the end are one answer: ``x = 2 or x = 3``."""
    tail = len(lines)
    while tail > 0 and _only_values(lines[tail - 1]):
        tail -= 1
    if len(lines) - tail < 2:
        return lines
    values = [part for line in lines[tail:] for part in line.split(" or ")]
    matches = [_EQUALS_VALUE.match(part) for part in values]
    names = {match["var"] for match in matches if match is not None}
    if len(names) != 1:
        return lines
    return [*lines[:tail], " or ".join(values)]


def _math_line(segment: str) -> str | _Prose | None:
    """One relation from a segment; _PROSE for commentary; None when unsure."""
    text = _strip_comments(segment).strip().strip(":,").strip()
    text = _NUMBERING.sub("", text)
    text = _BULLET.sub("", text).strip()
    if not text:
        return _PROSE
    if not _COMPARATOR.search(text):
        if _BARE_VALUE.match(text):
            return text
        return _PROSE
    plus_minus = _PLUS_MINUS.match(text)
    if plus_minus is not None:
        var, value = plus_minus["var"], plus_minus["value"].strip()
        return f"{var} = {value} or {var} = -{value.lstrip('+')}"
    tokens = text.split()
    if len(tokens) > _MAX_TOKENS:
        return None
    # The longest run of tokens that is one clean relation, with only words
    # before it ("I solved", "Answer:") and a comment after it.
    for start in range(len(tokens)):
        if not all(_WORDY_TOKEN.match(token) for token in tokens[:start]):
            break
        for end in range(len(tokens), start, -1):
            rest = tokens[end:]
            # A trailing note is words; one holding a relation is another
            # line that would be dropped unread.
            if rest and (not _comment_start(rest[0]) or _COMPARATOR.search(" ".join(rest))):
                continue
            candidate = " ".join(tokens[start:end])
            or_line = _or_line(candidate)
            if or_line is not None:
                return or_line
            if _clean_relation(candidate):
                return candidate
    return None


def _strip_comments(segment: str) -> str:
    """Drop ``(subtract 3)``-style notes; keep math brackets like ``4(x-2)``."""

    def replace(match: re.Match[str]) -> str:
        return "" if _prose_words(match.group(1)) else match.group(0)

    return _COMMENT_PARENS.sub(replace, segment)


def _comment_start(token: str) -> bool:
    word = token.strip(":,!?").lower()
    return len(word) >= 2 and word.isalpha() and word not in FUNCTION_WORDS


def _prose_words(text: str) -> list[str]:
    return [
        word
        for word in _WORD.findall(text)
        if len(word) >= 2 and word.lower() not in FUNCTION_WORDS and not _implicit_product(word)
    ]


def _implicit_product(word: str) -> bool:
    # "2x" never reaches here (digits split it); a lone repeated letter such
    # as "xx" is still a product of the unknown, not prose.
    return len(set(word)) == 1 and len(word) <= 3


def _clean_relation(text: str) -> bool:
    if not _MATH_CHARS.match(text) or _prose_words(text):
        return False
    comparators = _COMPARATOR.findall(text)
    if len(comparators) != 1:
        return False
    left, right = _COMPARATOR.split(text)
    if not left.strip() or not right.strip():
        return False
    return text.count("(") == text.count(")")


def _or_line(text: str) -> str | None:
    """``x = 2 or x = 3`` / ``x = 2 or 3`` / ``x = 2 and x = 3``."""
    parts = _OR_SPLIT.split(text)
    if len(parts) < 2:
        return None
    first = _EQUALS_VALUE.match(parts[0])
    if first is None:
        return None
    var = first["var"]
    values = [first["value"].strip()]
    for part in parts[1:]:
        match = _EQUALS_VALUE.match(part)
        if match is not None and match["var"] == var:
            values.append(match["value"].strip())
            continue
        bare = _BARE_VALUE.match(part)
        if bare is None:
            return None
        values.append(bare["value"].strip())
    return " or ".join(f"{var} = {value}" for value in values)


def _single_variable(lines: list[str]) -> str | None:
    letters: set[str] = set()
    for line in lines:
        for word in _WORD.findall(line.replace(" or ", " ")):
            if word.lower() in FUNCTION_WORDS:
                continue
            letters.update(word)
    if len(letters) != 1:
        return None
    (letter,) = letters
    return None if letter in _RESERVED_LETTERS else letter

"""Does the model's prose state the verified answer, a different one, or none?

The post-stream fence passes used to ask "is the verified text somewhere in the
reply?" with a substring test, so ``12.75`` was found inside ``112.75`` and
``12.755``, and a reply stating ``x = 7`` beside a verified ``x = 6`` hid the
verified card. This reads the values as numbers instead:

- ``same``: the reply's final value is the verified one (to the precision the
  verified answer was written at; ``x = 6.0`` and ``R = 35.31 m`` against
  ``35.3 m`` count).
- ``rounded``: the reply gives a coarser rounding of it (``12.8`` for ``12.75``).
  The card is still shown; nothing is corrected.
- ``conflict``: the reply's final value is a different number, a different set
  of roots, or only some of them. The card is shown with a correction line.
- ``absent``: the reply states no final value at all.
- ``unknown``: the verified answer is not a plain number (an expression, an
  interval, a system); the callers keep their string checks for those.

Question sentences ("Want the maximum height too?") never count as a statement.
Pure text work: no SymPy, so it is safe after a solver timeout.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from fractions import Fraction
from typing import Literal

from app.services.answer_fence import CHEMISTRY_NOTATION_LINE, answer_header_and_value
from app.services.glyphs import SUBSCRIPT_DIGITS, SUPERSCRIPT_SIGNED
from app.services.md_fence_scan import Fence, map_fence_blocks
from app.services.school_rounding import round_places
from app.services.workout import names_a_formula

Verdict = Literal["same", "rounded", "conflict", "absent", "unknown"]


@dataclass(frozen=True)
class _Number:
    value: Fraction
    places: int | None  # decimal places as written; None for an exact fraction
    unit: str = ""  # as written after the number, spacing removed ("kJ/mol", "m/s^2")


@dataclass(frozen=True)
class VerifiedValue:
    label: str | None
    numbers: tuple[_Number, ...]


# --- Cleaning ------------------------------------------------------------------------------

_SUPERSCRIPTS = SUPERSCRIPT_SIGNED
_SUBSCRIPTS = SUBSCRIPT_DIGITS
_SUPERSCRIPT_RUN = re.compile(r"[⁰¹²³⁴⁵⁶⁷⁸⁹⁻⁺]+")
_TEX_WRAPPERS = re.compile(r"\\(?:mathrm|text|textrm|mathbf|operatorname|mathit|rm)\s*\{([^{}]*)\}")
_TEX_FRAC = re.compile(r"\\[dt]?frac\s*\{\s*(-?\d+(?:\.\d+)?)\s*\}\s*\{\s*(-?\d+(?:\.\d+)?)\s*\}")
_TEX_SPACING = re.compile(r"\\(?:qquad|quad|[,;:! ])")
_TEX_WORDS = {
    r"\times": "\u00d7",  # multiplication sign
    r"\cdot": "·",
    r"\approx": "≈",
    r"\simeq": "≈",
    r"\pm": "±",
    r"\%": "%",
    r"\left": "",
    r"\right": "",
    r"\circ": "°",
    r"\degree": "°",
}


def _clean(text: str) -> str:
    """Prose or a TeX answer as plain text a number scanner can read."""
    out = text.replace("\r\n", "\n").replace("\u2212", "-").replace("\u2009", " ")
    out = out.replace("\u00a0", " ").replace("\u202f", " ")
    out = _SUPERSCRIPT_RUN.sub(lambda match: "^" + match.group(0).translate(_SUPERSCRIPTS), out)
    out = out.translate(_SUBSCRIPTS)
    out = _TEX_SPACING.sub(" ", out)
    for word, plain in _TEX_WORDS.items():
        out = re.sub(re.escape(word) + r"(?![A-Za-z])", plain, out)
    out = re.sub(r"\^\s*\{\s*([-+]?\d+)\s*\}", r"^\1", out)
    for _ in range(3):
        out = _TEX_WRAPPERS.sub(r"\1", out)
    out = _TEX_FRAC.sub(r"\1/\2", out)
    out = re.sub(r"\^\s*\{\s*°\s*\}|\^\s*°", "°", out)
    # Math delimiters and emphasis are presentation only.
    out = re.sub(r"\\[()\[\]]", " ", out)
    out = out.replace("$", " ").replace("**", " ").replace("__", " ").replace("`", " ")
    return out


# --- Reading numbers -------------------------------------------------------------------------

_NUMBER = re.compile(
    r"(?P<mant>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+\.\d+|\d+|\.\d+)"
    r"(?:\s*(?:\u00d7|x|\*|·)\s*10\s*\^\s*\{?\s*(?P<exp>[-+]?\d+)\s*\}?|[eE](?P<eexp>[-+]?\d+))?"
)
_FILLER = re.compile(
    r"^(?:about|approximately|approx\.?|roughly|around|exactly|just|only|nearly|"
    r"almost|so|then|therefore|thus|hence)\s+",
    re.IGNORECASE,
)
# Units written as one letter (m, s, N, K, ...); any other lone letter is a variable.
_UNIT_LETTERS = frozenset("msghLNJWVAKCFTHMΩ")
# What may follow a final value (a unit, °, %, a closing mark); one letter per repeat, not 2^n.
_UNIT_TAIL = re.compile(r"(?:[A-Za-zµμΩ°%](?:\^-?\d+)?|[/·*]|\s|[()])*")
# Where a stated value ends: punctuation or a joining word ("pH = 2 for a strong
# acid"). A comma before three digits is a thousands separator (1,500), not a list.
_SEPARATORS = re.compile(
    r"\s*(?:,(?!\d{3}(?!\d))|;|\b(?:or|and|but|which|because|since|so|for|in|at|with|when|"
    r"if|as|from|after|before|on)\b)\s*"
)


def _to_number(mant: str, exp: str | None) -> _Number:
    digits = mant.replace(",", "")
    decimal = Decimal(digits)
    if exp:
        decimal = decimal.scaleb(int(exp))
    exponent = decimal.as_tuple().exponent
    places = -exponent if isinstance(exponent, int) else 0
    return _Number(Fraction(decimal), places)


def _read_value(segment: str) -> list[_Number] | None:
    """A segment that is one final value (``-2``, ``±3``, ``35.3 m``, ``12/2``), else None.

    An expression (``2x + 3``, ``0.15 * 85``, ``20^2``) is working, not a value.
    """
    text = segment.strip()
    for _ in range(3):
        text = _FILLER.sub("", text).strip()
    sign = 1
    both = False
    # "" is in every string: a segment that ends on "is:" or "$R =$" holds no value.
    if text and text[0] in "+-±":
        both = text[0] == "±"
        sign = -1 if text[0] == "-" else 1
        text = text[1:].lstrip()
    match = _NUMBER.match(text)
    if match is None:
        return None
    number = _to_number(match.group("mant"), match.group("exp") or match.group("eexp"))
    rest = text[match.end() :]
    fraction = re.match(r"\s*/\s*(\d+)(?![\d.])", rest)
    if fraction is not None and "." not in match.group("mant") and not match.group("exp"):
        denominator = int(fraction.group(1))
        if denominator == 0:
            return None
        number = _Number(number.value / denominator, None)
        rest = rest[fraction.end() :]
    if rest[:1].isalpha() and not re.match(r"[A-Za-zµμΩ°%]{1,6}\b|[A-Za-z]+/", rest):
        return None  # 2x, 3pi: a coefficient, not a value
    tail = _UNIT_TAIL.match(rest)
    if tail is None or tail.end() != len(rest) or len(rest.split()) > 2:
        return None  # an expression, or words ("2 D elastic collision"), not a unit
    if re.search(r"[A-Za-z]\s*\^|\^\s*\(", rest) and not re.fullmatch(
        r"[\sA-Za-zµμΩ°%/·*()]*(?:\^-?\d+[\sA-Za-zµμΩ°%/·*()]*)*", rest
    ):
        return None
    variables = [w for w in rest.split() if len(w) == 1 and w.isalpha() and w not in _UNIT_LETTERS]
    if variables:
        return None  # "6 x", "55555 K a": a product with a variable, not a unit
    value = number.value * sign
    unit = _unit(rest)
    numbers = [_Number(value, number.places, unit)]
    if both:
        numbers.append(_Number(-value, number.places, unit))
    return numbers


def _unit(rest: str) -> str:
    unit = re.sub(r"\s+", "", rest).replace("·", "*").replace("µ", "u").replace("μ", "u")
    return unit.strip("()") if unit.count("(") != unit.count(")") else unit


# --- The verified answer -------------------------------------------------------------------

# A name for the value: x, pH, M(H2O), or one of a few Greek letters.
_GREEK = "\u0394\u03b8\u03bb\u03bc\u03c1\u03c3\u03c9\u03b1"
_LABEL = re.compile(rf"[A-Za-z{_GREEK}][A-Za-z0-9_{{}}()\[\]+\-]*")


def _normalize_label(label: str) -> str:
    """Spacing and TeX grouping go; case stays (M is molar mass, m is mass)."""
    return re.sub(r"[\s{}_\\]", "", label)


def read_verified_value(answer_body: str) -> VerifiedValue | None:
    """The verified answer as numbers, or None when it is not a plain value."""
    _headers, value = answer_header_and_value(answer_body)
    if not value or "\n" in value:
        return None
    text = _clean(value).replace("\u2248", "=")  # x ≈ 1.41421 is Newton's x = 1.41421
    parts = [part for part in re.split(r"\s+or\s+|\s+and\s+|;|,\s*(?=[A-Za-z]\s*=)", text) if part]
    label: str | None = None
    numbers: list[_Number] = []
    for part in parts:
        if "=" in part:
            left, _sep, right = part.partition("=")
            right = right.rsplit("=", 1)[-1]
            left = left.strip()
            if not left or not _LABEL.fullmatch(left.replace(" ", "")):
                return None
            this_label = _normalize_label(left)
            if label is not None and this_label != label:
                return None  # x = 2, y = 3: a system, not one value
            label = this_label
        else:
            right = part
        read = _read_value(right)
        if read is None:
            return None
        numbers.extend(read)
    if not numbers:
        return None
    return VerifiedValue(label, tuple(numbers))


# --- The prose -----------------------------------------------------------------------------

_MARKDOWN_HEADING = re.compile(r"^[ \t>]*#{1,6}[ \t]+(?P<title>.+?)[ \t#]*$")
_BOLD_HEADING = re.compile(
    r"^[ \t>]*(?:\*\*|__)(?P<title>[^*_\n]+?)(?:\*\*|__)[ \t]*:?[ \t]*(?P<rest>.*)$"
)
_PLAIN_HEADING = re.compile(
    r"^[ \t>]*(?P<title>given|required|find|formula|answer|final answer)[ \t]*:[ \t]*(?P<rest>.*)$",
    re.IGNORECASE,
)
# A heading is words ("Given", "Final answer") or a numbered step label; "**x = 7**" is not.
_HEADING_TITLE = re.compile(r"[A-Za-z][A-Za-z .()'\u2019-]{0,40}|\d+[.)][ \t]+[^=\n]{1,80}")
# Sections that hold the problem's inputs, never the reply's result (Find: an older Required).
_INPUT_TITLES = frozenset("given givens required find formula formulas known knowns".split())
_ANSWER_TITLES = frozenset({"answer", "final answer", "the answer", "result", "final result"})
_CONNECTIVE = re.compile(
    r"=|≈|~|\bis\b|\bare\b|\bequals\b|\bequal\s+to\b|\bgives\b|\byields\b|\bcomes\s+to\b|"
    r"\bworks\s+out\s+to\b|\bof\s+about\b|\bto\s+get\b|\bget\b|:",
    re.IGNORECASE,
)
_SENTENCE_END = re.compile(r"(?<!\d)[.!?](?=\s|$)|(?<=\d)[.!?](?=\s|$)|\n")
# A result said without "=": "it lands about 70.6 m out", "takes 3.2 s". The first
# number after the verb is the value; "falls from 20 m" names a given, not a result.
_RESULT_STATEMENT = re.compile(
    r"\b(?:lands?|landed|travels?|travel(?:l)?ed|goes|went|reaches|reached|hits?|covers?|"
    r"covered|rises?|rose|takes?|took|lasts?|stops?|stopped|flies|flew|ends up|"
    r"comes to rest)\b(?P<between>[^.!?\n\d]{0,40}?)"
    r"(?P<value>[-+]?(?:\d+\.\d+|\d+))\s*(?P<unit>[A-Za-zµμΩ°%][A-Za-zµμΩ°%/^·*\d-]*)",
    re.IGNORECASE,
)


# Fences a client shows as ordinary text or math: what they say is prose too.
_READABLE_FENCE_LANGS = frozenset({"", "copy", "text", "plain", "math", "latex", "tex"})


def _without_fences(prose: str) -> str:
    """Drop data fences (graph JSON, cards); keep the body of a text or math fence."""

    def readable(fence: Fence, body: str) -> str:
        if fence.lang not in _READABLE_FENCE_LANGS:
            return "\n"
        return "\n" + body.rstrip("\n") + "\n"

    return map_fence_blocks(prose, readable)


def _pieces(text: str) -> list[str]:
    """Sentences and the line breaks between them, in order; joined they are ``text``."""
    out: list[str] = []
    start = 0
    for match in _SENTENCE_END.finditer(text):
        end = match.end()
        out.append(text[start:end])
        start = end
    out.append(text[start:])
    return out


def _sentences(text: str) -> list[str]:
    """Sentences in order; a decimal point never ends one."""
    return [sentence for sentence in _pieces(text) if sentence.strip()]


def _asks(sentence: str) -> bool:
    text = sentence.rstrip(" \t\n*_~`$")
    # "Required: x = ?" names the unknown; it asks the reader nothing.
    return text.endswith("?") and re.search(r"=\s*\?$", text) is None


def statement_text(prose: str) -> str:
    """The reply without fences and without its question sentences."""
    kept = [s for s in _pieces(_clean(_without_fences(prose))) if not _asks(s)]
    return "".join(kept)


def has_question(prose: str) -> bool:
    return any(_asks(s) for s in _sentences(_clean(_without_fences(prose))))


def _segments_after(sentence: str, pattern: re.Pattern[str]) -> list[str]:
    """Text after each match up to the next connective or separator."""
    out: list[str] = []
    for match in pattern.finditer(sentence):
        rest = sentence[match.end() :]
        stop = _CONNECTIVE.search(rest)
        if stop is not None:
            rest = rest[: stop.start()]
        rest = _SEPARATORS.split(rest, maxsplit=1)[0]
        rest = re.split(r"[.!?](?=\s|$)", rest, maxsplit=1)[0]
        out.append(rest)
    return out


def _label_values(sentence: str, label: str) -> list[_Number]:
    """Values stated for ``label`` in one sentence: ``x = 2 or x = 3``, ``pH is 1.00``."""
    found: list[_Number] = []
    pattern = re.compile(
        r"(?<![A-Za-z0-9_.^])" + r"\s*".join(map(re.escape, label)) + r"(?![A-Za-z0-9_])\s*"
        r"(?:=|≈|(?i:\bis\b|\bequals\b|\bof\b))"
    )
    for match in pattern.finditer(_label_comparable(sentence)):
        before = sentence[: match.start()].rstrip()
        if before and (before[-1].isdigit() or before[-1] in ")}]^*/·\u00d7"):
            continue  # "0.4 x = 0.8": a multiple of x, not a value for x
        rest = sentence[match.end() :]
        chain = re.split(r"\s+(?:or|and)\s+[A-Za-z]\s*=|,\s*[A-Za-z]\s*=|[;]", rest, maxsplit=1)[0]
        last = chain.rsplit("=", 1)[-1] if "=" in chain else chain
        value_text = _SEPARATORS.split(last, maxsplit=1)[0]
        value_text = re.split(r"[.!?](?=\s|$)", value_text, maxsplit=1)[0]
        read = _read_value(value_text)
        if read is None:
            continue
        found.extend(read)
        # "x = 2 or 3": bare values that continue the same statement.
        tail = last[len(value_text) :]
        for extra in re.finditer(
            r"^\s*(?:,|\bor\b|\band\b)\s*([-+±]?\s*\d+(?:\.\d+)?)(?![\d.]*\s*=)", tail
        ):
            more = _read_value(extra.group(1))
            if more:
                found.extend(more)
    return found


def _label_comparable(sentence: str) -> str:
    """Same length as ``sentence``: braces and subscript marks blanked for label matching."""
    return re.sub(r"[{}_\\]", " ", sentence)


def _connective_values(text: str) -> list[_Number]:
    values: list[_Number] = []
    for segment in _segments_after(text, _CONNECTIVE):
        read = _read_value(segment)
        if read:
            values.extend(read)
    return values


def _first_bare_value(region: str) -> list[_Number]:
    for line in region.split("\n"):
        stripped = line.strip(" \t*_-•")
        if not stripped:
            continue
        read = _read_value(stripped)
        if read:
            return read
        # "R = 20.4 m" on the Answer line: the value after its last equals sign.
        if "=" in stripped:
            read = _read_value(stripped.rsplit("=", 1)[-1])
            if read:
                return read
        return []
    return []


def _heading(line: str) -> tuple[str, str] | None:
    """``(title, text after it on the line)`` when the line opens a section."""
    match = _MARKDOWN_HEADING.match(line) or _BOLD_HEADING.match(line) or _PLAIN_HEADING.match(line)
    if match is None:
        return None
    title = match.group("title").strip().rstrip(":").strip()
    if not _HEADING_TITLE.fullmatch(title) and not names_a_formula(title):
        return None
    return title.lower(), (match.groupdict().get("rest") or "").strip()


def _sections(prose: str) -> tuple[str, str | None]:
    """The reply without its input sections, and its last Answer section (None if none).

    Given / Required / Formula lines (or a formula's own heading) restate the problem
    (``v = 3 m/s``), never the reply's result. Text after a heading on its line stays.
    """
    body: list[str] = []
    region: list[str] | None = None
    in_answer = False
    skipping = False
    for line in _without_fences(prose).split("\n"):
        heading = _heading(line)
        if heading is None:
            if in_answer and region is not None:
                region.append(line)
            elif skipping and not line.strip():
                skipping = False  # a section's lines end at the blank line after them
            elif not skipping:
                body.append(line)
            continue
        title, rest = heading
        in_answer = title in _ANSWER_TITLES
        skipping = title in _INPUT_TITLES or names_a_formula(title)
        if in_answer:
            region = [rest] if rest else []
        elif rest:
            body.append(rest)
    return "\n".join(body), None if region is None else "\n".join(region)


def _labelled(text: str, label: str) -> tuple[list[_Number], list[_Number]]:
    per_sentence = [_label_values(sentence, label) for sentence in _sentences(text)]
    stated = [values for values in per_sentence if values]
    if not stated:
        return [], []
    return stated[-1], [number for values in stated for number in values]


def _stated_values(prose: str, verified: VerifiedValue) -> tuple[list[_Number], list[_Number]]:
    """(final statement's values, every stated value) — empty when nothing is stated."""
    raw_body, raw_region = _sections(prose)
    body = statement_text(raw_body)
    region = statement_text(raw_region).strip() if raw_region is not None else None
    if region:
        if verified.label is not None:
            final, every = _labelled(region, verified.label)
            if final:
                return final, every
        connective = _connective_values(region.split("\n\n")[0])
        if connective:
            return connective[-1:], connective
        bare = _first_bare_value(region)
        if bare:
            return bare, bare
    if verified.label is not None:
        # x = 6 in the working above an Answer heading the card itself follows.
        final, every = _labelled(body, verified.label)
        if final or region is not None:
            return final, every
        result = _result_statement(body, verified)
        return result, result
    if region is not None:
        return [], []  # an Answer heading that states nothing: nothing to compare
    for sentence in reversed(_sentences(body)):
        values = _connective_values(sentence)
        if values:
            return values[-1:], values
    result = _result_statement(body, verified)
    return (result, result) if result else ([], [])


def _result_statement(body: str, verified: VerifiedValue) -> list[_Number]:
    """The last "lands about 70.6 m" in the reply, in a unit the verified answer uses."""
    units = {number.unit for number in verified.numbers if number.unit}
    if not units:
        return []  # a bare number in prose is too easy to misread as the result
    for sentence in reversed(_sentences(body)):
        for match in reversed(list(_RESULT_STATEMENT.finditer(sentence))):
            if re.search(r"\bfrom\b", match.group("between"), re.IGNORECASE):
                continue
            read = _read_value(f"{match.group('value')} {match.group('unit')}")
            if read and any(_in_one_unit(read[0], target) for target in verified.numbers):
                return read
    return []


# --- Comparing -----------------------------------------------------------------------------


Closeness = Literal["same", "rounded", "different", "incomparable"]
_GRADES: tuple[Closeness, ...] = ("same", "rounded", "different", "incomparable")
_PREFIXES = {"k": 3, "M": 6, "G": 9, "c": -2, "m": -3, "u": -6, "n": -9, "p": -12}


def _scaled(number: _Number, power: int) -> _Number:
    places = None if number.places is None else number.places - power
    return _Number(number.value * Fraction(10) ** power, places, number.unit)


def _in_one_unit(stated: _Number, verified: _Number) -> tuple[_Number, _Number] | None:
    """Both values in one unit (55 kJ/mol against 5.5e4 J/mol), or None.

    A missing unit compares as written; units that differ by more than one SI
    prefix (cm^2 against m^2, °C against K) are not compared at all.
    """
    if not stated.unit or not verified.unit or stated.unit == verified.unit:
        return stated, verified
    for prefix, power in _PREFIXES.items():
        if "^" in stated.unit or "^" in verified.unit:
            break
        if stated.unit == prefix + verified.unit:
            return _scaled(stated, power), verified
        if verified.unit == prefix + stated.unit:
            return stated, _scaled(verified, power)
    return None


def _agree(a: Fraction, b: Fraction, places: int) -> bool:
    return round_places(a, places) == round_places(b, places)


def _closeness(stated: _Number, verified: _Number) -> Closeness:
    converted = _in_one_unit(stated, verified)
    if converted is None:
        return "incomparable"
    stated, verified = converted
    if stated.value == verified.value:
        return "same"
    if stated.places is None:
        # An exact fraction stated: the same only when the verified decimal is its rounding.
        if verified.places is None:
            return "different"
        return "same" if _agree(stated.value, verified.value, verified.places) else "different"
    if verified.places is not None and stated.places >= verified.places:
        # As precise as the verified answer (35.31 for 35.3): the same if it rounds to it.
        return "same" if _agree(stated.value, verified.value, verified.places) else "different"
    # Coarser than the verified answer: 12.8 for 12.75, 0.33 for 1/3. A whole number
    # for a fraction is a different answer, not a rounding: x = 4 for x = 7/2.
    whole = stated.value.denominator == 1 and stated.places <= 0
    if whole and verified.value.denominator != 1:
        return "different"
    return "rounded" if _agree(stated.value, verified.value, stated.places) else "different"


def _best(number: _Number, verified: tuple[_Number, ...]) -> Closeness:
    return min((_closeness(number, target) for target in verified), key=_GRADES.index)


def _matches(stated: list[_Number], verified: tuple[_Number, ...]) -> Closeness:
    """Set equality of values, each matched within its written precision and unit."""
    if not stated:
        return "different"
    grades = [_best(number, verified) for number in stated]
    if all(grade == "incomparable" for grade in grades):
        return "incomparable"
    if "different" in grades:
        return "different"
    for target in verified:
        if all(_closeness(number, target) == "different" for number in stated):
            return "different"
    return "rounded" if "rounded" in grades else "same"


def stated_verdict(prose: str, answer_body: str) -> Verdict:
    """How the reply's own final value relates to the verified answer."""
    verified = read_verified_value(answer_body)
    if verified is None:
        return "unknown"
    final, every = _stated_values(prose, verified)
    if not final:
        return "absent"
    grade = _matches(final, verified.numbers)
    if grade == "incomparable":
        return "absent"  # 300 K against 26.85 °C: not something to correct
    if grade != "different":
        return grade
    # Only some roots in the last sentence, the rest stated just before it.
    if all(_best(number, verified.numbers) != "different" for number in final):
        overall = _matches(every, verified.numbers)
        if overall in {"same", "rounded"}:
            return overall
    return "conflict"


def asks_without_answering(prose: str, answer_body: str | None) -> bool | None:
    """True when the reply asks a question and states no result of its own.

    None when the verified answer is not a plain value, so the caller keeps its
    own string check for those.
    """
    if not answer_body or not has_question(prose):
        return False
    verdict = stated_verdict(prose, answer_body)
    if verdict == "unknown":
        return None
    return verdict == "absent"


def correction_line(answer_body: str) -> str:
    """One short line before the card when the prose states a different value."""
    headers, value = answer_header_and_value(answer_body)
    if CHEMISTRY_NOTATION_LINE in headers:
        shown = value
    else:
        shown = f"${value}$"
    return f"The verified answer is {shown}."

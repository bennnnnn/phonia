"""The answer-card protocol: which ```answer fence the server vouches for.

The phone draws the green check on an ```answer fence only when the fence body
opens with ``verified: true`` (the same header-line style as
``notation: chemistry``). Only the server writes that line, and only on a card
whose value came from a solver: the post-stream fence pass appends it to the
cards it writes, and an instant reply (wholly server text) gets it on every
card. Model text never keeps it:

1. ``strip_forged_verified_markers`` removes the line from the model's reply
   before any server card is added, so the model cannot forge a check.
2. ``normalize_owned_fences`` rewrites every spelling of a model answer fence
   (indented in a list, ``~~~answer``, four backticks, ``` answer``, capital
   ``Answer``, ``result`` / ``final``) to the plain column-0 form, so each
   subject's fence pass sees and demotes all of them, not only ``\\n```answer``.
3. ``modules/chat/verification_claims`` drops the model's own "✅ Verified with SymPy",
   and ``strip_model_simulation_fences`` its own ```simulation scene.

The server writes the line with ``verified_answer_fence`` (post-stream cards) and
``mark_server_answer_fences`` (an instant reply, once, when it is sent). ``land_answer_card``
puts a reply's final answer in one card under one **Answer** heading: the verified card, or
the model's own final line in a card marked ``verified: false`` ("not checked" on the
phone). The fence scan is a linear line scan, no nested regex on untrusted text.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass

from app.services.card_value import final_answer_only
from app.services.md_fence_scan import fence_lang as fence_lang
from app.services.md_fence_scan import map_closed_fences, read_fence_marker

VERIFIED_ANSWER_MARKER = "verified: true"
UNCHECKED_ANSWER_MARKER = "verified: false"  # a card no solver checked ("not checked")
_CHECK_LINES = frozenset({VERIFIED_ANSWER_MARKER, UNCHECKED_ANSWER_MARKER})
CHEMISTRY_NOTATION_LINE = "notation: chemistry"
# Header lines a client reads off the top of an answer body. Older phone builds
# also wrote ``label: answer`` when they moved an **Answer** heading inside.
ANSWER_HEADER_LINES = _CHECK_LINES | {CHEMISTRY_NOTATION_LINE, "label: answer"}
ANSWER_FENCE_LANGS = ("answer", "result", "final")
# Server-owned fences a model must not ship in any spelling.
OWNED_FENCE_LANGS = (*ANSWER_FENCE_LANGS, "simulation")
# Fences whose body a client may read as an answer card. A marker line inside
# any other fence (```yaml, ```python) is code the user asked for, so it stays.
_MARKER_SCRUB_LANGS = frozenset(
    {*ANSWER_FENCE_LANGS, "", "copy", "text", "plain", "clike", "math", "latex", "tex"}
)
_DIAGRAM_FAIL_NOTE = "*Could not render that diagram.*"


def answer_header_and_value(body: str) -> tuple[list[str], str]:
    """Split the protocol header lines off the top of an answer body."""
    lines = body.replace("\r\n", "\n").strip().split("\n")
    headers: list[str] = []
    while lines and lines[0].strip() in ANSWER_HEADER_LINES:
        headers.append(lines.pop(0).strip())
    return headers, "\n".join(lines).strip()


def answer_fence_value(body: str) -> str:
    """The value a reader sees: the body without its protocol header lines."""
    return answer_header_and_value(body)[1]


def verified_answer_body(body: str) -> str:
    """``body`` marked verified, holding its final answer alone (idempotent)."""
    headers, value = answer_header_and_value(body)
    rest = [line for line in headers if line not in _CHECK_LINES]
    return "\n".join([VERIFIED_ANSWER_MARKER, *rest, final_answer_only(value)]).strip()


def verified_answer_fence(body: str) -> str:
    """The one way the server writes a card it vouches for."""
    return f"```answer\n{verified_answer_body(body)}\n```"


# --- A lenient fence scan for model text -------------------------------------------------


@dataclass(frozen=True)
class _Fence:
    start: int  # line index of the opener
    end: int  # line index of the closer
    lang: str
    tick: str
    prefix: str  # indent and blockquote markers before the opener
    info: str


def _line_prefix(line: str) -> tuple[str, str]:
    """Leading indent and ``>`` quote markers, and the rest of the line."""
    index = 0
    while index < len(line) and line[index] in " \t>":
        index += 1
    return line[:index], line[index:]


def _opener(line: str) -> tuple[str, str, str] | None:
    """(prefix, tick, info) of a fence opener, on the shared lenient grammar.

    ``info`` is as written ("``` answer" keeps its space), so a fence is canonical
    only when it is spelled exactly ```answer.
    """
    marker = read_fence_marker(line, lenient=True)
    if marker is None:
        return None
    tick = marker.char * marker.length
    return marker.prefix, tick, line.rstrip("\r")[len(marker.prefix) + len(tick) :]


def _closes(line: str, tick: str) -> bool:
    marker = read_fence_marker(line, lenient=True)
    return (
        marker is not None
        and not marker.info
        and marker.char == tick[0]
        and (marker.length >= len(tick))
    )


def _scan(lines: list[str]) -> tuple[list[_Fence], dict[int, str]]:
    """Closed fences, and for every line inside an open or closed fence its lang."""
    fences: list[_Fence] = []
    inside: dict[int, str] = {}
    index = 0
    while index < len(lines):
        opened = _opener(lines[index])
        if opened is None:
            index += 1
            continue
        prefix, tick, info = opened
        lang = fence_lang(info)
        cursor = index + 1
        while cursor < len(lines) and not _closes(lines[cursor], tick):
            inside[cursor] = lang
            cursor += 1
        if cursor >= len(lines):
            break  # unclosed: the rest of the reply is this fence's body
        fences.append(_Fence(index, cursor, lang, tick, prefix, info))
        index = cursor + 1
    return fences, inside


def _is_marker_line(line: str) -> bool:
    """``verified: true`` however it is dressed: any case, spacing, or invisible marks."""
    _prefix, rest = _line_prefix(line)
    compact = "".join(
        char
        for char in rest
        if not char.isspace() and unicodedata.category(char) not in {"Cf", "Cc", "Zs"}
    )
    return compact.lower() == "verified:true"


def strip_forged_verified_markers(text: str) -> str:
    """Drop every ``verified: true`` line a model wrote where a client could read it."""
    if "verified" not in text.lower():
        return text
    lines = text.split("\n")
    _fences, inside = _scan(lines)
    kept = [
        line
        for number, line in enumerate(lines)
        if not (_is_marker_line(line) and inside.get(number, "") in _MARKER_SCRUB_LANGS)
    ]
    return "\n".join(kept)


def _dedent(line: str, prefix: str) -> str:
    if line.startswith(prefix):
        return line[len(prefix) :]
    head, rest = _line_prefix(line)
    return rest if len(head) <= len(prefix) else line[len(prefix) :]


def normalize_owned_fences(text: str, langs: tuple[str, ...] = OWNED_FENCE_LANGS) -> str:
    """Rewrite each closed server-owned fence to a column-0 ```lang block.

    The subject fence passes match ``\\n```answer`` exactly. A model that
    indents its answer fence in a list, or writes ``~~~answer`` or four
    backticks, gets the same card on the phone, so it must get the same
    demotion here.
    """
    lower = text.lower()
    if not any(lang in lower for lang in langs):
        return text
    lines = text.split("\n")
    fences, _inside = _scan(lines)
    out: list[str] = []
    cursor = 0
    for fence in fences:
        if fence.lang not in langs:
            continue
        canonical = fence.prefix == "" and fence.tick == "```" and fence.info == fence.lang
        if canonical:
            continue
        out.extend(lines[cursor : fence.start])
        if out and out[-1].strip():
            out.append("")  # a column-0 fence after a list line starts its own block
        out.append(f"```{fence.lang}")
        out.extend(_dedent(line, fence.prefix) for line in lines[fence.start + 1 : fence.end])
        out.append("```")
        if fence.end + 1 < len(lines) and lines[fence.end + 1].strip():
            out.append("")
        cursor = fence.end + 1
    if cursor == 0:
        return text
    out.extend(lines[cursor:])
    return "\n".join(out)


def mark_server_answer_fences(text: str) -> str:
    """Add the verified marker to every answer card in wholly server-written text."""
    ended_open = not text.endswith("\n")
    for lang in ANSWER_FENCE_LANGS:
        # The scan consumes the closer's newline, so the replacement restores it.
        text = map_closed_fences(text, lang, lambda body: verified_answer_fence(body) + "\n")
    return text.rstrip("\n") if ended_open else text


def demote_answer_body(body: str) -> str:
    """A model answer fence as plain prose: its value, never its header lines.

    One line of TeX (``x = 2 \\text{ or } x = 3``) is wrapped in ``$...$`` so
    it reads as math, not as backslashes; chemistry text stays as written.
    """
    headers, value = answer_header_and_value(body)
    if not value:
        return ""
    tex = CHEMISTRY_NOTATION_LINE not in headers and "\n" not in value
    if tex and "$" not in value and any(mark in value for mark in ("\\", "^", "_", "{")):
        value = f"${value}$"
    return f"{value}\n"


def demote_answer_fences(text: str) -> str:
    """Unwrap every answer fence to prose. No solver, so safe after a timeout."""
    text = normalize_owned_fences(text, ANSWER_FENCE_LANGS)
    for lang in ANSWER_FENCE_LANGS:
        text = map_closed_fences(text, lang, demote_answer_body)
    return text


# --- One place for the final answer ------------------------------------------------------

_HEADING_LINE = "**Answer**"
# **Answer**, **Answer:**, **Answer**:, ## Answer, Answer: — the value may follow on the
# line. One anchored match per line; "Answer the question" has no colon, so it is prose.
_ANSWER_HEADING = re.compile(
    r"(?P<atx>#{1,4}[ \t]+)?(?P<bold>\*\*)?answer(?P<inner>:)?(?(bold)\*\*)(?P<outer>:)?"
    r"(?P<rest>.*)",
    re.IGNORECASE,
)
_LIST_MARKER = re.compile(r"(?:[-*+•]|\d{1,3}[.)])[ \t]+")


def _plain_line(line: str, *, hard_break: bool = True) -> str:
    """A line without its quote markers and (``hard_break``) its trailing ``\\`` break.

    Inside a display block a trailing ``\\\\`` is a LaTeX row break and stays."""
    text = line.strip()
    while text.startswith(">"):
        text = text[1:].lstrip()
    return text.rstrip("\\ \t") if hard_break else text


def _value_line(line: str) -> str:
    """A value line as a card shows it: no list marker, no bold around it."""
    text = _plain_line(line)
    marker = _LIST_MARKER.match(text)
    if marker is not None:
        text = text[marker.end() :]
    if len(text) > 4 and text.startswith("**") and text.endswith("**"):
        text = text[2:-2].strip()
    return text.removesuffix(".") if text.endswith("$.") else text


def answer_heading(line: str) -> str | None:
    """The value on an Answer heading's own line ("" for none; bare "Answer" too), else None."""
    match = _ANSWER_HEADING.fullmatch(line.strip())
    if match is None:
        return None
    rest = _value_line(match.group("rest"))
    if match.group("inner") or match.group("outer"):
        return rest
    return "" if not match.group("rest").strip() else None


def _ends_section(line: str) -> bool:
    """A heading line after the answer: ``**Check**``, ``**(b) Speed:** …``, ``## Notes``."""
    text = _plain_line(line)
    if text.startswith("#"):
        return True
    close = text.find("**", 2)
    if not text.startswith("**") or close < 0:
        return False
    label = text[2:close].strip()
    # A bold value (**x = 3**, **35.3 m**) is the answer, not a heading.
    return (
        bool(label)
        and (label[0].isalpha() or label[0] == "(")
        and not any(mark in label for mark in "=\u2248$\\^_{}")
    )


_EQUATION_START = re.compile(r"[^\s=]+\s*=")
_LATEX_COMMAND = re.compile(r"\\[A-Za-z]+")
_WORD = re.compile(r"[A-Za-z]{3,}")
_MATH_SPAN = re.compile(r"\$\$.*?\$\$|\$[^$\n]*\$|\\\(.*?\\\)", re.DOTALL)


def _wordy(value: str) -> bool:
    """A paragraph, not a value: over twenty words outside its maths and no equation."""
    prose = _MATH_SPAN.sub(" ", value[:2000])  # no card holds more; the spans read it once
    return len(value) > 2000 or ("=" not in _relations(prose) and len(_WORD.findall(prose)) > 20)


# Display maths spanning lines: its opener and the closer that ends it.
_DISPLAY = {"$$": "$$", "\\[": "\\]"}


def _relations(text: str) -> str:
    """``≈`` and ``\\approx`` read as ``=``: an approximate answer is still the answer."""
    return text.replace("\\approx", "=").replace("\u2248", "=")


def _is_maths(line: str) -> bool:
    """``$…$``, ``\\[…``, or a bare equation: one name before the ``=`` or ``≈``
    (``Area = 12 cm²``) or no words at all (``2x + 3 - 3 = 7 - 3``). "So x = 3 is the
    answer." is a sentence."""
    text = _relations(_value_line(line))
    return (
        text.startswith(("$", "\\[", "\\("))
        or _EQUATION_START.match(text) is not None
        or ("=" in text and _WORD.search(_LATEX_COMMAND.sub("", text)) is None)
    )


def _answer_values(lines: list[str], start: int) -> tuple[list[tuple[int, str]], int, bool]:
    """``(first line, value)`` for each value from ``start``, the last line read, and
    whether an answer card already follows the heading.

    After the first value, only lines of maths are values: they run to a fence, a heading
    or a sentence, and past a blank line only into another line of maths, so a sentence
    after the answer stays after it. A ``$$`` or ``\\[`` display block is one value
    however many lines it spans.
    """
    values: list[tuple[int, str]] = []
    index, end = start, start - 1
    while index < len(lines):
        if not lines[index].strip():
            follow = index + 1
            while follow < len(lines) and not lines[follow].strip():
                follow += 1
            if follow == len(lines) or (
                values and _opener(lines[follow]) is None and not _is_maths(lines[follow])
            ):
                break
            index = follow
        opened = _opener(lines[index])
        if opened is not None:
            return values, end, fence_lang(opened[2]) in ANSWER_FENCE_LANGS
        if _ends_section(lines[index]) or (values and not _is_maths(lines[index])):
            break
        first, text = index, _value_line(lines[index])
        raw = _plain_line(lines[index], hard_break=False)
        opener = next((mark for mark in _DISPLAY if raw.startswith(mark)), None)
        if opener is not None and (raw == opener or not raw.endswith(_DISPLAY[opener])):
            block = [raw]
            while index + 1 < len(lines) and lines[index + 1].strip():
                index += 1
                block.append(_plain_line(lines[index], hard_break=False))
                if block[-1].endswith(_DISPLAY[opener]):
                    break
            text = "\n".join(block)
        values.append((first, text))
        end = index
        index += 1
    return values, end, False


_BARE_SYMBOL = re.compile(r"[A-Za-z](?:_\{?\w+\}?)?")
_UNIT_TEXT = re.compile(r"\\(?:text|mathrm)\{[^}]*\}")
# Arithmetic still to do: a product, quotient, fraction, power, sum, or a minus
# after a term (a leading minus is the value's sign).
_ARITHMETIC = re.compile(r"\\(?:times|cdot|div|frac)|[\u00d7\u00b7*/\u00f7+^]|\S\s*[-\u2212]")
# An exact fraction is a value, not a division still to do: x = \frac{1}{2}.
_EXACT_FRACTION = re.compile(r"\\d?frac\{-?\d+\}\{-?\d+\}")


def _is_final_value(value: str) -> bool:
    """``x = 2``, ``x_1 = -3``, ``v = 19.6\\ \\text{m/s}``: a name set to a value with no
    arithmetic left, unlike the working line ``v = 9.8 \\times 2`` or ``2x = 4``."""
    left, equals, right = _relations(value.replace("$", "")).partition("=")
    right = _EXACT_FRACTION.sub("1", _UNIT_TEXT.sub("", right)).strip()
    return (
        bool(equals and right)
        and _BARE_SYMBOL.fullmatch(left.strip()) is not None
        and _ARITHMETIC.search(right) is None
    )


def _card_start(values: list[tuple[int, str]]) -> int:
    """Where the card's values begin: the last one, and the final values just before it
    (both roots, ``x = 2`` and ``x = -2``); earlier lines are working."""
    start = len(values) - 1
    while start > 0 and all(_is_final_value(values[i][1]) for i in (start - 1, start)):
        start -= 1
    return start


def land_answer_card(text: str, verified_body: str | None, *, above: str | None = None) -> str:
    """Put the reply's final answer in one card under one **Answer** heading.

    The reply's last Answer section (``**Answer**``, ``**Answer:** $x = 3$``, ``## Answer``,
    ``Answer:``) outside code fences becomes ``**Answer**`` and a card: the server's verified
    card when ``verified_body`` is given, otherwise the section's last line of maths (with the
    plain values just before it, so both roots stay) in a card marked ``verified: false``.
    Earlier lines under the heading are working: they stay as prose above it; a sentence after
    the answer stays below. ``above`` (written working, a correction line) goes directly above
    the heading. With no Answer section, a verified card is added at the end unless the reply
    already has one; an unverified reply, or one whose answer is not maths, is left as written.
    """
    lines = text.split("\n")
    fences, inside = _scan(lines)
    heading, same_line = -1, ""
    for number, line in enumerate(lines):
        found = None if number in inside else answer_heading(line)
        if found is not None:
            heading, same_line = number, found
    values: list[tuple[int, str]] = []
    if heading < 0:
        if verified_body is None or any(fence.lang in ANSWER_FENCE_LANGS for fence in fences):
            return text
        heading = end = len(lines)
    else:
        if same_line:
            # The value on the heading's own line is the section's first line.
            lines[heading] = same_line
        values, end, landed = _answer_values(lines, heading if same_line else heading + 1)
        if landed:
            return text
        end = max(end, heading)
    shown = _card_start(values) if values else 0
    if verified_body is not None:
        card = verified_answer_fence(verified_body)
    else:
        parts = [v for _, v in values[shown:]] or [""]
        # Both roots read on one line (x = 2, x = -2): a card draws one line of maths.
        joined = parts[0] if len(parts) == 1 else ", ".join(" ".join(p.split()) for p in parts)
        value = answer_header_and_value(joined)[1]
        if value.startswith("\\[") and value.endswith("\\]"):
            value = f"$${value[2:-2]}$$"  # the card reads $$ display maths
        # A card draws maths; "Paris" under a quiz's Answer, or a paragraph, stays prose.
        if ("$" not in value and "=" not in _relations(value)) or _wordy(value):
            return text
        card = f"```answer\n{UNCHECKED_ANSWER_MARKER}\n{value}\n```"
    steps = lines[values[0][0] : values[shown][0]] if values else []
    while steps and not steps[-1].strip():
        steps.pop()
    before = lines[:heading]
    while before and (not before[-1].strip() or answer_heading(before[-1]) == ""):
        before.pop()
    block = [*steps, *([""] if steps else []), *([above, ""] if above else [])]
    block += [_HEADING_LINE, "", card]
    after = lines[end + 1 :]
    if after and after[0].strip():
        after = ["", *after]
    return "\n".join([*before, *([""] if before else []), *block, *after])


def strip_model_simulation_fences(text: str) -> str:
    """A ```simulation scene is solver-sampled. The model's own never ships."""
    if "simulation" not in text.lower():
        return text
    normalized = normalize_owned_fences(text, ("simulation",))
    stripped = map_closed_fences(normalized, "simulation", lambda _body: "")
    if stripped == normalized:
        return text
    cleaned = re.sub(r"\n{3,}", "\n\n", stripped).strip()
    return cleaned or _DIAGRAM_FAIL_NOTE


def map_outside_fences(text: str, transform: Callable[[str], str]) -> str:
    """Apply ``transform`` to each run of lines outside any fence."""
    lines = text.split("\n")
    fences, inside = _scan(lines)
    fenced = set(inside)
    for fence in fences:
        fenced.update((fence.start, fence.end))
    if not fenced:
        return transform(text)
    # An unclosed fence's opener line is fenced too.
    for number in inside:
        opener = number - 1
        while opener >= 0 and opener in inside:
            opener -= 1
        if opener >= 0:
            fenced.add(opener)
    out: list[str] = []
    run: list[str] = []
    for number, line in enumerate(lines):
        if number in fenced:
            if run:
                out.append(transform("\n".join(run)))
                run = []
            out.append(line)
        else:
            run.append(line)
    if run:
        out.append(transform("\n".join(run)))
    return "\n".join(out)

"""One worked-solution layout for every subject.

A worked reply has the same sections everywhere, in this order, each only when
it has lines:

- **Given**: the problem as the student wrote it, or the stated values, closed by a
  ``where`` line naming their symbols (``where_line``)
- **Required**: what is asked (**Find** before November 2026; a reader takes both)
- **Solution**: a heading alone, over the working below (none before November 2026)
- **Formula**: the law or rule that governs it, headed by its name and "formula"
  (**Average speed formula**, **Kinetic energy formula**; ``formula_heading``); a name
  that says what it is already keeps it (**Ohm's law**, **Pythagorean theorem**), and
  a formula with no name is headed **Formula**. The name is never a note on the
  formula's line. A rearrangement for the unknown is a line of its own,
  ``Solve for $t$`` (``solve_for_line``), then the rearranged formula
- **Substitution**: values put into that formula
- **Steps**: an equation changed one move at a time
- **Answer**: the verified result (the caller's answer fence follows)

Each line is one state. A move is a short note after the state
(``$2x = 8$ — subtract 3 from both sides``), never a heading of its own.
Maths numbers each move instead (``modules/math/tools/lesson.py``): a bold
``**1. Subtract 4 from both sides**`` over the move written on both sides,
then the simplified line.
Lines in a section are hard line breaks, so the section reads as one block
and every client keeps the breaks.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.services.times_sign import with_times

GIVEN = "Given"
REQUIRED = "Required"
# What is asked was headed "Find" until November 2026. A reader takes both spellings: older
# replies keep theirs, and a model may still write it.
REQUIRED_HEADINGS = (REQUIRED, "Find")
# The same as a regex alternation, ``Required|Find``.
REQUIRED_PATTERN = "|".join(REQUIRED_HEADINGS)
SOLUTION = "Solution"
FORMULA = "Formula"
SUBSTITUTION = "Substitution"
STEPS = "Steps"
ANSWER = "Answer"

_NOTE_SEPARATOR = " — "
_HARD_BREAK = "  \n"


@dataclass(frozen=True)
class Workout:
    given: tuple[str, ...] = ()
    find: tuple[str, ...] = ()
    formula: tuple[str, ...] = ()
    substitution: tuple[str, ...] = ()
    steps: tuple[str, ...] = ()
    # None: each formula line named by its note (``math_line(tex, "Discriminant")``) heads
    # a section of its own (``formula_sections``); a caller that knows the name sets it.
    formula_heading: str | None = None


def math_line(tex: str, note: str | None = None) -> str:
    """``$2x = 8$ — subtract 3``: one state in math, its move as a short note.

    A product prints ``\\times`` whatever the row was built with (``times_sign``)."""
    body = f"${with_times(tex.strip())}$"
    return f"{body}{_NOTE_SEPARATOR}{note.strip()}" if note and note.strip() else body


def text_line(text: str, note: str | None = None) -> str:
    """A line that is not one formula (chemistry text, a named given)."""
    body = text.strip()
    return f"{body}{_NOTE_SEPARATOR}{note.strip()}" if note and note.strip() else body


# A law named for a person keeps its capital: "Newton's second law".
_PROPER_FIRST_WORD = re.compile(
    r"^(?:Pythagorean|Pythagoras|Newton|Ohm|Hooke|Boyle|Charles|Coulomb|Kepler|Snell|"
    r"Archimedes|Pascal|Bernoulli|Faraday|Avogadro|Bayes|Heron|Hess|Dalton|Graham|Henry|"
    r"Raoult|Nernst|Arrhenius|Beer|Gibbs|Hardy|Planck|Einstein|Lenz|Gauss|Kirchhoff|SUVAT)"
)


def solve_for_line(symbol: str) -> str:
    """``Solve for $t$``: a rearrangement for the unknown, a line of its own before the
    rearranged formula. Every subject words it the same."""
    return text_line(f"Solve for ${symbol.strip()}$")


def note_from_label(label: str) -> str:
    """``Subtract 3 from both sides`` → ``subtract 3 from both sides``."""
    text = label.strip().rstrip(".:")
    if _PROPER_FIRST_WORD.match(text):
        return text
    if len(text) > 1 and text[0].isupper() and not text[1].isupper():
        return text[0].lower() + text[1:]
    return text


# A name that already says what it is keeps it: "Ohm's law", "Heron's formula",
# "Pythagorean theorem", "Slope-intercept form", "Newton's method".
_NAMED_KIND = re.compile(
    r"\b(?:law|formula|theorem|rule|principle|equation|identity|form|method)s?$", re.I
)
# The phone reads a formula's own heading as one when it is a few words with no
# sentence end (``lib/markdown/workoutSection.ts``, ``lawHeading``).
_HEADING_WORDS = 10


def formula_heading(name: str | None) -> str:
    """The heading over a formula: ``Average speed`` → ``Average speed formula``.

    One rule for every subject. A name that says what it is already stays as it is
    (``Ohm's law``, ``Triangle area formula``); no name, or one too long to read as a
    heading, is **Formula**.
    """
    text = re.sub(r"\s+", " ", name or "").strip().rstrip(".:")
    if not text or "$" in text or re.search(r"[.?!]$", text):
        return FORMULA
    text = text[:1].upper() + text[1:]
    heading = text if _NAMED_KIND.search(text) else f"{text} formula"
    return heading if len(heading.split()) <= _HEADING_WORDS else FORMULA


def names_a_formula(title: str) -> bool:
    """A heading over a formula by its name ("Average speed formula", "Ohm's law")."""
    return _NAMED_KIND.search(title.strip().rstrip(":")) is not None


def _named(line: str) -> tuple[str, str] | None:
    """``$a^2 + b^2 = c^2$ — Pythagorean theorem`` → (the formula, its name). A name is
    capitalised; a lower-case note says something else (``on the x-axis``)."""
    in_math = False
    for at, char in enumerate(line):
        if char == "$":
            in_math = not in_math
        elif not in_math and line.startswith(_NOTE_SEPARATOR, at):
            note = line[at + len(_NOTE_SEPARATOR) :].strip()
            if note[:1].isupper() and formula_heading(note) != FORMULA:
                return line[:at].strip(), note
            return None
    return None


def formula_sections(
    lines: tuple[str, ...], heading: str | None = None
) -> list[tuple[str, list[str]]]:
    """The formula lines under their headings. With ``heading`` they are one section;
    without, a named line opens a section headed by its name (the name leaves the line),
    and an unnamed line stays in the section above it (**Formula** when it is first)."""
    kept = _clean(lines)
    if heading is not None:
        return [(heading, kept)] if kept else []
    sections: list[tuple[str, list[str]]] = []
    for line in kept:
        named = _named(line)
        if named is None:
            if sections:
                sections[-1][1].append(line)
            else:
                sections.append((FORMULA, [line]))
            continue
        title = formula_heading(named[1])
        if sections and sections[-1][0] == title:
            sections[-1][1].append(named[0])
        else:
            sections.append((title, [named[0]]))
    return sections


def _clean(lines: tuple[str, ...]) -> list[str]:
    kept: list[str] = []
    for line in lines:
        text = re.sub(r"\s*\n\s*", " ", line).strip()
        if text and (not kept or kept[-1] != text):
            kept.append(text)
    return kept


def _section(heading: str, lines: list[str]) -> str:
    return f"**{heading}**{_HARD_BREAK}" + _HARD_BREAK.join(lines)


def render_workout(
    workout: Workout,
    answer: str | None = None,
    *,
    before_answer: str | None = None,
    answer_heading: str | None = ANSWER,
    solution: bool | None = None,
) -> str:
    """The sections in order; with ``answer``, the answer fence closes it.

    ``before_answer`` is already-rendered markdown (numbered equation steps)
    placed after the sections and before **Answer**. ``answer_heading`` names a
    part's answer (``Answer (a)``); None leaves it out, for the Given and Required a
    question in parts opens with. **Solution** heads the working after Given and
    Required; ``solution`` True puts it there when the working follows elsewhere (the
    parts of a question in parts), False leaves it out.
    """
    opening = [
        _section(heading, kept)
        for heading, lines in ((GIVEN, workout.given), (REQUIRED, workout.find))
        if (kept := _clean(lines))
    ]
    working = [
        _section(heading, kept)
        for heading, kept in (
            *formula_sections(workout.formula, workout.formula_heading),
            (SUBSTITUTION, _clean(workout.substitution)),
            (STEPS, _clean(workout.steps)),
        )
        if kept
    ]
    if before_answer and before_answer.strip():
        working.append(before_answer.strip())
    if solution is None:
        solution = bool(opening and working)
    sections = [*opening, *([f"**{SOLUTION}**"] if opening and solution else []), *working]
    if answer_heading is not None:
        sections.append(f"**{answer_heading}**")
    body = "\n\n".join(sections)
    if answer is None:
        return body
    return f"{body}\n\n```answer\n{answer.strip()}\n```\n"


# Headings a worked reply names by role; any other bold line over maths after Given or
# Required (a follow-up may skip Required) is a law.
_OPENING_HEADINGS = frozenset({GIVEN.lower(), *(name.lower() for name in REQUIRED_HEADINGS)})
_ROLE_HEADINGS = _OPENING_HEADINGS | frozenset(
    {"formula", "substitution", "steps", "answer", "working", "check"}
    | {"result", "final answer", "solution", "method", "calculation"}
)
_BOLD_LINE = re.compile(r"^\s*\*\*(?P<title>[^*\n]+?)\*\*[ \t]*$")


def as_formula_heading(text: str) -> str:
    """The reply with each formula's own heading read as **Formula**, for a checker.

    "**Constant acceleration formula**" over ``$v = u + at$`` heads formulas, which are inputs
    and never the reply's result; a checker that skips **Formula** skips them too.
    """
    lines = text.split("\n")
    worked = False
    for number, line in enumerate(lines):
        bold = _BOLD_LINE.match(line)
        if bold is None:
            continue
        title = bold.group("title").strip().rstrip(":").lower()
        if title in _OPENING_HEADINGS:
            worked = True
            continue
        following = next((later for later in lines[number + 1 :] if later.strip()), "")
        # A formula's own heading ("Average speed formula", "Ohm's law") names it whatever
        # its lines are; another bold line heads a formula when maths follows it.
        named = _NAMED_KIND.search(title) is not None
        if worked and title not in _ROLE_HEADINGS and (named or following.lstrip().startswith("$")):
            lines[number] = line.replace(f"**{bold.group('title')}**", f"**{FORMULA}**", 1)
    return "\n".join(lines)


_IRREGULAR_PLURALS = {"index": "indices"}


def _plural(noun: str) -> str:
    """``mass`` → ``masses``; the last word of a phrase takes the plural."""
    head, _, last = noun.rpartition(" ")
    if last in _IRREGULAR_PLURALS:
        word = _IRREGULAR_PLURALS[last]
    elif last.endswith("y") and last[-2:-1] not in ("a", "e", "i", "o", "u"):
        word = last[:-1] + "ies"  # velocity → velocities
    else:
        word = last + ("es" if last.endswith(("s", "sh", "ch", "x")) else "s")
    return f"{head} {word}" if head else word


def where_line(definitions: list[tuple[str, str]]) -> str | None:
    """``where $v_0$ = initial speed; $m_1$, $m_2$ = masses`` from (symbol, meaning) pairs.

    A symbol named twice is named once; symbols with the same meaning are named together,
    and then semicolons keep one group's commas from running into the next.
    """
    groups: dict[str, list[str]] = {}
    for symbol, meaning in definitions:
        shown = groups.setdefault(meaning, [])
        if symbol not in shown and all(symbol not in other for other in groups.values()):
            shown.append(symbol)
    parts = [
        f"{', '.join(f'${symbol}$' for symbol in symbols)} = "
        + (_plural(meaning) if len(symbols) > 1 else meaning)
        for meaning, symbols in groups.items()
        if symbols
    ]
    grouped = any(len(symbols) > 1 for symbols in groups.values())
    return f"where {('; ' if grouped else ', ').join(parts)}" if parts else None


def split_equality_chain(tex: str) -> list[str]:
    """``a = b = c`` → ``["a = b", "= c"]``: one equals sign per line on a phone.

    Only top-level ``=`` split; one inside braces or ``\\left( … \\right)``
    belongs to a sub-expression.
    """
    if re.search(r"\\text|\\quad|\\;|,|<|>|\\(?:le|ge|ne)(?![a-z])", tex):
        # Two statements ("x = 2 or x = 3", "du = dx, v = e^x") are not a chain.
        return [tex]
    parts: list[str] = []
    depth = 0
    start = 0
    i = 0
    while i < len(tex):
        if tex.startswith("\\left", i):
            depth += 1
            i += 5
            continue
        if tex.startswith("\\right", i):
            depth -= 1
            i += 6
            continue
        char = tex[i]
        if char in "{(":
            depth += 1
        elif char in "})":
            depth -= 1
        elif char == "=" and depth == 0:
            parts.append(tex[start:i].strip())
            start = i + 1
        i += 1
    parts.append(tex[start:].strip())
    if len(parts) <= 2 or any(not part for part in parts):
        return [tex]
    return [f"{parts[0]} = {parts[1]}", *(f"= {part}" for part in parts[2:])]


def _sections(formula: str) -> str:
    return (
        "**Given** (the problem exactly as written, or the stated values), **Required** (what "
        f"is asked), **Solution** (a heading alone, over the working), {formula}, "
        "**Substitution** (values put into that formula)"
    )


# Every subject heads a formula with its name and "formula" (``formula_heading``).
_WORKOUT_SECTIONS = _sections(
    'the governing law or rule under a bold heading of its name followed by "formula" '
    "(`**Average speed formula**`; a name that already ends in law, theorem, rule, "
    "principle or equation stays as it is: `**Ohm's law**`), or **Formula** when it has "
    "no name; never the name after the formula on its line"
)
_WORKOUT_SECTION_LINES = (
    "Put each heading on its own line with its lines directly under it: one state per "
    "line, no blank line inside a section, one blank line between sections."
)
# A rearrangement is a step a learner takes, so it is a line of its own (``solve_for_line``).
_WORKOUT_REARRANGED = (
    "Rearranging a formula for the unknown is a line of its own, never a note: "
    "`Solve for $t$`, then `$t = \\frac{d}{v}$`."
)
_WORKOUT_PARTS = (
    "A question in parts: one **Given** for the whole question, then **Solution**, then for "
    "each part a bold label alone on its line naming its letter and what it finds "
    "(`**(a) Acceleration**`), "
    "followed by that part's formula heading, **Substitution** and **Answer**, with no "
    "**Required** under a part; a later part may use an earlier part's answer as a given."
)
# Physics answers each part in its own card ("Answer (a)"), a hairline between parts.
_PHYSICS_PARTS = (
    "A question in parts: one **Given** and one **Required** naming every quantity asked, "
    "**Solution**, then for each part a bold label alone on its line naming its letter and "
    "what it finds (`**(a) Acceleration**`), followed by that part's own formula heading, "
    "**Substitution** "
    "carried to its value, and its answer under **Answer (a)** (its own letter), with a "
    "line `---` between two parts; a later part may use an earlier part's answer as a given."
)
_WORKOUT_UNITS = (
    "Write units upright inside math (`$m = 5\\ \\text{kg}$`), never as italic letters "
    "(`$m = 5 kg$`)."
)
_WORKOUT_ONE_EXPRESSION = (
    "Trivial one-step arithmetic is one line with no headings. Write an expression once: "
    "`$\\frac{6!}{4!} = \\frac{720}{24}$`, then the result alone as the answer, never "
    "a second row that repeats the left side (`$\\frac{6!}{4!} = 30$`)."
)

# A learner reads each step: a converted given says how, the arithmetic reaches the
# number, and the answer is labelled once.
_PHYSICS_WORKING = (
    "A given in a unit that is not SI stays one line, with the factor that converts it: "
    "`$v = 100\\ \\text{km/h} \\times 1000/3600 = 27.78\\ \\text{m/s}$`, never the "
    "symbol written twice. Carry **Substitution** one step at a time to the final value "
    "with its unit: `$a = \\frac{27.78 - 0}{8}$`, `$a = \\frac{27.78}{8}$`, "
    "`$a = 3.47\\ \\text{m/s}^2$`. Write **Answer** once, the value under it, never a "
    "second `Answer:` line."
)


def _workout_rule(sections: str, working: str = "", parts: str = _WORKOUT_PARTS) -> str:
    return (
        "Worked-solution layout: bold headings in this order, each only when it has "
        f"something to show: {sections} or **Steps** (an equation changed one move at a "
        f"time), then **Answer**. {_WORKOUT_SECTION_LINES} Write a move as a short note "
        "after its line, e.g. `$2x = 8$ — subtract 3 from both sides`. "
        f"{_WORKOUT_REARRANGED} No numbered steps, no separate Simplify lines, no prose "
        f"between lines. {parts} {_WORKOUT_UNITS} "
        f"{working}{_WORKOUT_ONE_EXPRESSION}"
    )


# What the model is told for a chemistry reply it writes itself, and physics' own.
WORKOUT_PROMPT_RULE = _workout_rule(_WORKOUT_SECTIONS)
PHYSICS_WORKOUT_PROMPT_RULE = _workout_rule(
    _WORKOUT_SECTIONS, f"{_PHYSICS_WORKING} ", _PHYSICS_PARTS
)

# What the model is told for a maths reply it writes itself: numbered moves, as the
# verified equation lesson renders them, so the phone draws each number as a badge.
MATH_WORKOUT_PROMPT_RULE = (
    "Worked-solution layout for maths: bold headings in this order, each only when it has "
    f"something to show: {_WORKOUT_SECTIONS} or numbered moves, then **Answer**. "
    f"{_WORKOUT_SECTION_LINES} {_WORKOUT_REARRANGED} Number every move in place of a "
    "**Steps** heading: a bold "
    "line naming the move, then an em dash and the rule it uses "
    "(`**1. Subtract 4 from both sides** — Subtraction property of equality`; never a "
    "**Steps** heading or a plain `1.` list), then its working, each "
    "`$...$` alone on its own line with no note after it. For an equation that working is "
    "the move written on both sides, then the simplified equation: `$4x + 4 - 4 = 0 - 4$`, "
    "then `$4x = -4$`; next `**2. Divide both sides by 4**`, "
    "`$\\frac{4x}{4} = \\frac{-4}{4}$`, then `$x = -1$`. A simplification is the last line "
    "of its move, never a number of its own. One blank line between numbered moves, no "
    f"prose between lines. {_WORKOUT_PARTS} {_WORKOUT_ONE_EXPRESSION}"
)

# Physics' rule in one sentence, for hints with a tight character budget.
PHYSICS_WORKOUT_PROMPT_SHORT = (
    "Use the worked-solution layout: **Given** (a converted value keeps one line, with its "
    "factor), **Required**, **Solution**, the law as heading "
    "(`**Constant acceleration formula**`), **Substitution** step by step to the final "
    "value, then **Answer** once; one state per line; no numbered steps."
)

# Questions in parts and upright units, for a reply the model writes with no
# verified block to copy (the short rule above has no room for them).
PHYSICS_WORKOUT_PARTS_PROMPT = f"{_PHYSICS_PARTS} {_WORKOUT_UNITS}"

# A reply the model works out itself has no server check behind it, so it checks
# its own answer before writing it, and shows that check when one line can.
SELF_CHECK_PROMPT_RULE = (
    "No server check stands behind this answer, so check it yourself before you write "
    "**Answer**: put the result back into the formula or the original equation, redo "
    "every multiplication and division, and check the units and that the size makes "
    "sense. If a check fails, fix the working first; never show a line you know is "
    "wrong. When one line can show the check, add **Check** after **Answer** with that "
    "line (`$2(8) + 5 = 21$`); otherwise leave it out. Never mark the check with ✓ and "
    "never call the result verified."
)

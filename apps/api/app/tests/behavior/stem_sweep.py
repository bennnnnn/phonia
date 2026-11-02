"""Run STEM homework questions through the real chat path and judge the replies.

Each subject has a corpus in ``stem_corpus/<subject>/*.json``. An entry is a
question a student would type, worked independently from the textbook formula
(g = 9.81 m/s², CODATA constants), and what should happen:

- ``answer``: a verified reply whose answer card holds the worked answer:
  - ``answer`` = [value, unit], or ``answers`` = several right spellings, any
    one of which may match (1% tolerance, any unit of the same kind; signs are
    compared as magnitudes; ``abs_tol`` for a pH-like scale); ``parts`` for a
    multi-part question, every one of which the card must hold;
  - ``text``: words the reply must contain (a formula, a balanced equation);
  - ``check``: a maths check judged by SymPy alone, or a regex over the reply
    (``stem_math_judge.py``);
- ``explain``: a question without numbers, left to the model, never "solved";
- ``decline``: an underdetermined question, never given a number;
- ``not_subject``: an everyday message that only sounds like the subject.

``history`` gives earlier turns for a follow-up, and ``locale`` the asker's app language
(English when absent). ``shared`` names the peer
subject that owns a law both use (gases, Q = mcΔT, half-lives are physics'), so
its claiming the turn is no misread. ``gap`` marks a known miss: a strict
expected failure until the fix deletes the line. Every verified physics and
chemistry reply is also checked for its shape (Given, Required, [Solution,] Formula,
Substitution, Answer; no calculator notation; no invented zero given), and
every picture it carries is validated: a ``simulation`` scene against the
server schema and its own bounds, a ``graph`` for finite points. Its LaTeX is
held to what the phone draws (``latex_check.py``): no command the phone lacks,
no TeX outside maths. ``visual`` names the picture a student would want, and is
counted, not required.

A problem is ``critical`` (a wrong number, a misread turn, a broken picture, LaTeX shown as source)
or ``coverage`` (a question declined or not recognised, a picture missing). The test fails on
the first kind; the second is held entry by entry in ``stem_snapshot.json``.

    uv run python -m app.tests.behavior.stem_sweep physics --show

The sweep models production, so a maths decline stays silent; ``RECALL_STRICT_DECLINES=1``
in front raises the programming errors a decline would hide (``math/solve/declines.py``).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pint

from app.modules.physics.schemas.simulation import SimulationBlockSpec
from app.services.answer_fence import answer_fence_value
from app.services.workout import REQUIRED_HEADINGS, SOLUTION, as_formula_heading
from app.tests.behavior.harness import Case, Expect, Route, route_case, saved_reply
from app.tests.behavior.latex_check import latex_problems
from app.tests.behavior.stem_math_judge import judge_check

CORPUS = Path(__file__).with_name("stem_corpus")
EXPECTS = {"answer", "explain", "decline", "not_subject"}
SUBJECT_NAMES = {"physics": "physics", "chemistry": "chemistry", "math": "math"}
TOLERANCE = 0.01
CRITICAL = {"wrong", "misread", "shape", "broken_visual", "latex"}

_UNITS = pint.UnitRegistry()
_UNITS.define("diopter = 1 / meter = D")
_UNITS.define("kWh = kilowatt * hour")
# "5 rev/s": Pint spells a revolution out in full.
_UNITS.define("rev = revolution")
# Results shown to the inputs' significant figures: 0.2 mol for 0.204 is right.
ROUNDED = {"chemistry"}


@dataclass(frozen=True)
class Entry:
    id: str
    area: str
    prompt: str
    expect: str
    answers: tuple[tuple[float, str], ...] = ()
    parts: tuple[tuple[float, str], ...] = ()
    text: tuple[str, ...] = ()
    check: tuple[str, Any] | None = None
    abs_tol: float | None = None
    history: tuple[tuple[str, str], ...] = ()
    shared: str | None = None
    visual: str | None = None
    note: str | None = None
    gap: str | None = None
    # The asker's app language, which reads their numbers ("1.200" is 1200 in Spanish).
    locale: str = "en"

    @property
    def checked(self) -> bool:
        """Whether the entry says what a right answer is."""
        return bool(self.answers or self.parts or self.text or self.check)


@dataclass
class Problem:
    kind: str
    text: str

    @property
    def critical(self) -> bool:
        return self.kind in CRITICAL


@dataclass
class Outcome:
    entry: Entry
    route: Route | None = None
    reply: str = ""
    got: str = ""
    visuals: list[str] = field(default_factory=list)
    problems: list[Problem] = field(default_factory=list)

    @property
    def critical(self) -> list[Problem]:
        return [problem for problem in self.problems if problem.critical]


def load(subject: str) -> list[Entry]:
    entries: list[Entry] = []
    for path in sorted((CORPUS / subject).glob("*.json")):
        for raw in json.loads(path.read_text()):
            answers = [raw["answer"]] if raw.get("answer") else raw.get("answers", [])
            check = raw.get("check")
            entries.append(
                Entry(
                    id=raw["id"],
                    area=raw["area"],
                    prompt=raw["prompt"],
                    expect="not_subject" if raw["expect"].startswith("not_") else raw["expect"],
                    answers=tuple((float(value), str(unit)) for value, unit in answers),
                    parts=tuple((float(value), str(unit)) for value, unit in raw.get("parts", [])),
                    text=tuple(raw.get("text", [])),
                    check=(check[0], check[1]) if check else None,
                    abs_tol=raw.get("abs_tol"),
                    history=tuple((role, said) for role, said in raw.get("history", [])),
                    shared=raw.get("shared"),
                    visual=raw.get("visual"),
                    note=raw.get("note"),
                    gap=raw.get("gap"),
                    locale=raw.get("locale", "en"),
                )
            )
    return entries


# --- reading the reply -------------------------------------------------------

_FENCE = re.compile(r"```([\w-]+)[ \t]*\n(.*?)\n?```", re.DOTALL)
_SUPER = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁻", "0123456789-")


def fences(reply: str) -> list[tuple[str, str]]:
    return [(lang.lower(), body.strip()) for lang, body in _FENCE.findall(reply)]


def latex_to_plain(latex: str) -> str:
    """``3.97 \\times 10^{-19}\\,\\mathrm{J}`` → ``3.97e-19 J``."""
    text = latex.strip().strip("$")
    text = re.sub(r"\\mathrm\{([^{}]*)\}", r"\1", text)
    text = re.sub(r"\\text\{([^{}]*)\}", r"\1", text)
    text = re.sub(r"\s*\\times\s*10\^\{?(-?\d+)\}?", r"e\1", text)
    text = re.sub(r"\s*×\s*10([⁰¹²³⁴⁵⁶⁷⁸⁹⁻]+)", lambda m: "e" + m.group(1).translate(_SUPER), text)
    text = text.replace("^\\circ", " deg").replace("^{\\circ}", " deg").replace("°", " deg ")
    text = (
        text.replace("\\,", " ").replace("\\ ", " ").replace("\\%", "%").replace("\\Omega", "ohm")
    )
    text = text.replace("{", "").replace("}", "").replace("\\", "")
    return " ".join(text.split())


_NUMBER = re.compile(r"^\s*(-?\d+(?:\.\d+)?)(?:e(-?\d+))?\s*(.*)$")


def answer_card(reply: str) -> str:
    """The first card's value, without the header lines the server writes above it
    (``verified: true`` on a saved reply's card)."""
    card = next((text for lang, text in fences(reply) if lang == "answer"), "")
    return answer_fence_value(card)


def card_values(reply: str) -> list[tuple[float, str, str]]:
    """Each value, unit and shown digits on the reply's answer card.

    One card can hold several results: "2.45 m/s² and 36.8 N",
    "50.0 N at 53.1°", "0 m/s and 4 m/s"; a question in parts has a card per part.
    """
    found: list[tuple[float, str, str]] = []
    cards = [text for lang, text in fences(reply) if lang == "answer"]
    for line in (line for card in cards for line in card.splitlines()):
        plain = latex_to_plain(line.replace("\u2212", "-"))
        for part in re.split(r"\s+(?:and|at)\s+|;|,\s+(?=[a-zA-Z\\]*\s*=)|\s+/\s+", plain):
            part = re.sub(r"^[^\d-]*=\s*", "", part.strip())  # "R = 62.7 m"
            match = _NUMBER.match(part)
            if not match and "=" in part:  # "M(CuSO₄·5H₂O) = 249.68 g/mol"
                match = _NUMBER.match(part.rsplit("=", 1)[1])
            if match:
                shown, power, rest = match.groups()
                # "0.4 (40%)": the bracket restates the value; "J/(kg·K)" keeps its own.
                unit = "" if rest.startswith("(") else re.split(r"\s\(|,", rest)[0].strip()
                found.append((float(shown + (f"e{power}" if power else "")), unit, shown))
    return found


def read_answers(reply: str) -> list[tuple[float, str]]:
    return [(value, unit) for value, unit, _shown in card_values(reply)]


def read_answer(reply: str) -> tuple[float, str] | None:
    answers = read_answers(reply)
    return answers[0] if answers else None


def _pint_unit(unit: str) -> str:
    text = unit.strip()
    if not text:
        return "dimensionless"
    text = text.replace("²", "2").replace("³", "3")
    text = re.sub(r"\^?(\d)\b", r"**\1", text)
    text = text.replace("·", "*").replace("Ω", "ohm").replace("µ", "u").replace("μ", "u")
    text = re.sub(r"\bdeg\s*C\b|\bdegC\b", "degC", text)
    text = re.sub(r"\bdeg\b", "degree", text)
    return text.replace("%", "percent")


_SUBSCRIPTS = str.maketrans("₀₁₂₃₄₅₆₇₈₉⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻−", "01234567890123456789+--")
_PARTICLES = re.compile(
    r"^(?:molecules?|atoms?|particles?|formula\s+units?|ions?)\b|"
    r"^[A-Z][\w()]*\s+(?:molecules?|atoms?|particles?)\b",
    re.IGNORECASE,
)


def _chemistry_unit(unit: str) -> str:
    """``g CO₂`` → ``g``; ``molecules`` → a pure number; ``°C`` → ``degC``."""
    text = re.sub(r"\s+\(.*$", "", unit.strip().rstrip(".")).translate(_SUBSCRIPTS)
    if not text or _PARTICLES.match(text):
        return "dimensionless"
    text = re.sub(r"([a-zA-Z])([23])$", r"\1**\2", text)
    text = re.sub(r"^([a-zA-Z]+)\^?-1$", r"1/\1", text)
    # A species after the unit: "g CO2", "mol O2", "g of water".
    text = re.sub(
        r"^(g|mg|kg|mol|mmol|L|mL|M|kJ|J|atm|kPa|mmHg)\s+(?:of\s+)?[A-Za-z(].*$", r"\1", text
    )
    if text in {"°C", "° C", "degC", "deg C", "C"}:
        return "degC"
    text = re.sub(r"\s*deg\s*C\b|°C", "K", text).replace(" ", "")
    for old, new in (("·", "*"), ("µ", "u"), ("μ", "u"), ("%", "percent"), ("^", "**")):
        text = text.replace(old, new)
    return text


def same_quantity(
    got: tuple[float, str],
    want: tuple[float, str],
    *,
    shown: str | None = None,
    abs_tol: float | None = None,
    chemistry: bool = False,
) -> tuple[bool, str]:
    """Whether a card value is the worked answer, in any unit of the same kind.

    ``shown`` is the value's digits on the card: a result rounded to the
    inputs' significant figures matches within half its last place.
    """
    value, unit = got
    want_value, want_unit = want
    if want_unit == "dB" or unit == "dB":
        converted = value if unit == want_unit else math.nan
    else:
        try:
            if chemistry:
                source = _chemistry_unit(unit)
                if want_unit == "delta_degC" and source == "degC":
                    source = "delta_degC"
                target_unit = (
                    want_unit if want_unit in {"degC", "delta_degC"} else _chemistry_unit(want_unit)
                )
                converted = _UNITS.Quantity(value, source).to(target_unit).magnitude
            else:
                quantity = _UNITS.Quantity(abs(value), _pint_unit(unit))
                converted = quantity.to(_pint_unit(want_unit)).magnitude
        except Exception as exc:  # A unit that does not convert is a wrong answer.
            return (
                False,
                f"{value} {unit} is not a {want_unit or 'pure number'} ({exc.__class__.__name__})",
            )
    target = abs(want_value)
    difference = abs(abs(converted) - target)
    if abs_tol is not None:
        decimals = len(shown.split(".")[1]) if shown and "." in shown else 0
        ok = difference <= max(abs_tol, 0.55 * 10**-decimals)
    else:
        ok = math.isclose(abs(converted), target, rel_tol=TOLERANCE)
        if not ok and shown and value:
            last_place = 10 ** (math.floor(math.log10(abs(value))) - _sig_figs(shown) + 1)
            ok = difference <= 0.55 * last_place * abs(converted / value)
    return ok, f"{value:g} {unit} = {converted:.4g} {want_unit}, want {target:.4g}"


def _sig_figs(shown: str) -> int:
    digits = shown.lstrip("-")
    if "." in digits:
        return max(len(digits.replace(".", "").lstrip("0")), 1)
    return max(len(digits.lstrip("0").rstrip("0")), 1)


def _normalized(text: str) -> str:
    """Formulas and equations compared without subscripts, spacing or arrow style."""
    plain = text.translate(_SUBSCRIPTS)
    for arrow in ("⟶", "→", "-->", "=>", "⇌", "<=>"):
        plain = plain.replace(arrow, "->")
    return re.sub(r"\s+", "", plain.replace("·", ".")).lower()


def check_answer(
    entry: Entry, subject: str, reply: str, *, whole: bool = True
) -> tuple[str, list[Problem]]:
    """What the card says, and a ``wrong`` problem when it is not the worked answer.

    ``whole`` is false when the model writes the reply around one verified result:
    that result must be one of the parts, and the model writes the rest.
    """
    problems: list[Problem] = []
    wanted = entry.answers if whole else (*entry.answers, *entry.parts)
    got = ""
    if entry.check is not None:
        card = answer_card(reply)
        got = " ".join(card.split())
        if not judge_check(entry.check, card, reply):
            problems.append(Problem("wrong", f"{got!r} is not {entry.check[1]!r}"))
    if wanted:
        values = card_values(reply)

        def matches(want: tuple[float, str]) -> list[tuple[bool, str]]:
            return [
                same_quantity(
                    (value, unit),
                    want,
                    shown=shown if subject in ROUNDED else None,
                    abs_tol=entry.abs_tol,
                    chemistry=subject == "chemistry",
                )
                for value, unit, shown in values
            ]

        if not values:
            problems.append(Problem("shape", "verified reply has no readable answer card"))
        else:
            checks = [check for want in wanted for check in matches(want)]
            match = next((detail for ok, detail in checks if ok), None)
            got = match or checks[0][1]
            if match is None:
                problems.append(Problem("wrong", "; ".join(detail for _ok, detail in checks[:3])))
            if whole:
                for part in entry.parts:
                    if not any(ok for ok, _detail in matches(part)):
                        problems.append(Problem("wrong", f"the card drops the part {part}"))
    for want in entry.text:
        if _normalized(want) not in _normalized(reply):
            problems.append(Problem("wrong", f"the reply never says {want!r}"))
    return got, problems


# --- judging -------------------------------------------------------------------

# The sections a verified reply carries, in order; a slot may take several names. What is
# asked is Required, or Find in a reply written the older way. **Solution** (November
# 2026) is checked apart: an older reply has none (``_solution_out_of_place``).
_SECTIONS: dict[str, tuple[tuple[str, ...], ...]] = {
    "physics": (
        ("Given",),
        REQUIRED_HEADINGS,
        ("Formula",),
        ("Substitution",),
        ("Answer", "Answer (a)"),
    ),
    # A balanced equation or an empirical formula works in Steps, not a substitution.
    "chemistry": (
        ("Given",),
        REQUIRED_HEADINGS,
        ("Formula", "Method"),
        ("Substitution", "Steps", "Working"),
        ("Answer",),
    ),
}
_CALCULATOR = re.compile(r"\d(?:\.\d+)?[eE][-+]?\d")
_GIVEN_ROW = re.compile(r"^\$([^$=]+?)\s*=\s*0(?:\.0+)?(?:\\,|\s|\$)", re.MULTILINE)
_ZERO_WORDS = re.compile(
    r"\b(?:rest|stops?|stopped|dropp?ed|drops?|stationary|horizontal(?:ly)?|frictionless|"
    r"smooth|still|zero|falls?|released?|starting|starts|stopping|brakes?|braking|halts?)\b|\b0\b",
    re.IGNORECASE,
)


def _prose(reply: str) -> str:
    return _FENCE.sub("", reply)


def _section_at(prose: str, names: tuple[str, ...]) -> int:
    found = [at for name in names if (at := prose.find(f"**{name}**")) >= 0]
    return min(found) if found else -1


def _given_part(prose: str) -> str:
    """The reply up to what is asked: its givens."""
    at = _section_at(prose, REQUIRED_HEADINGS)
    return prose if at < 0 else prose[:at]


def _solution_out_of_place(prose: str, required: int, formula: int) -> bool:
    """**Solution** sits after Required and before the formula; a reply with none (one
    written before November 2026) passes."""
    at = prose.find(f"**{SOLUTION}**")
    return at >= 0 and not required < at < formula


def check_shape(entry: Entry, reply: str, subject: str = "physics") -> list[Problem]:
    """A worked reply's sections and notation; maths replies are checked for notation only."""
    problems: list[Problem] = []
    # A formula is headed by its name ("**Constant acceleration formula**"): its Formula.
    prose = as_formula_heading(_prose(reply))
    if subject == "physics":
        problems.extend(_physics_working(_prose(reply)))
    sections = _SECTIONS.get(subject, ())
    positions = [_section_at(prose, names) for names in sections]
    missing = [names[0] for names, at in zip(sections, positions, strict=True) if at < 0]
    if missing:
        problems.append(Problem("shape", f"reply has no {', '.join(missing)}"))
    elif positions != sorted(positions):
        problems.append(Problem("shape", "sections out of order"))
    elif sections and _solution_out_of_place(prose, positions[1], positions[2]):
        problems.append(Problem("shape", "Solution is not between Required and the formula"))
    if calculator := _CALCULATOR.search(prose):
        problems.append(Problem("shape", f"calculator notation: {calculator.group(0)!r}"))
    if re.search(r"\b(?:nan|inf|None)\b", prose):
        problems.append(Problem("shape", "nan, inf or None in the reply"))
    # An equation's "= 0" is the question, not a given.
    given = _given_part(prose) if subject != "math" else ""
    for symbol in _GIVEN_ROW.findall(given):
        if not _ZERO_WORDS.search(entry.prompt):
            problems.append(Problem("shape", f"invented a zero given: {symbol.strip()} = 0"))
    return problems


_ANSWER_LABEL = re.compile(r"^\*\*Answer(?: \([a-h]\))?:?\*\*", re.MULTILINE)
_GIVEN_SYMBOL = re.compile(r"^\$([^$=]+?)\s*=", re.MULTILINE)
_FIRST_NUMBER = re.compile(r"-?\d+(?:\.\d+)?")
_ROW = re.compile(r"\$([^$]+)\$")


def _physics_working(prose: str) -> list[Problem]:
    """What a learner reads: the law by name, each given once, the arithmetic to its end,
    one Answer label."""
    problems: list[Problem] = []
    if "**Formula**" in prose:
        problems.append(Problem("shape", "Formula heading instead of the law's name"))
    labels = _ANSWER_LABEL.findall(prose)
    parts = re.findall(r"^\*\*Answer \(([a-h])\)\*\*", prose, re.MULTILINE)
    # One label, or in a question in parts one per part, lettered in order.
    if parts and (len(parts) != len(labels) or parts != list("abcdefgh"[: len(parts)])):
        problems.append(Problem("shape", f"part answers {parts} among {len(labels)} labels"))
    elif not parts and len(labels) != 1:
        problems.append(Problem("shape", f"{len(labels)} Answer labels"))
    given = _given_part(prose)
    symbols = [symbol.strip() for symbol in _GIVEN_SYMBOL.findall(given)]
    if repeated := sorted({symbol for symbol in symbols if symbols.count(symbol) > 1}):
        problems.append(Problem("shape", f"given twice: {', '.join(repeated)}"))
    # Each part's working ends on a value: no operation left in its last row (a unit's "/"
    # is none).
    for substitution in prose.split("**Substitution**")[1:]:
        rows = _ROW.findall(substitution.split("**Answer", 1)[0])
        last = re.sub(r"\\(?:mathrm|text)\{[^}]*\}", "", rows[-1].split("=")[-1]) if rows else ""
        if re.search(r"\\frac|\\cdot|\\sqrt|\\sin|\\cos|\\tan|[+*/]", last):
            problems.append(Problem("shape", f"working stops short: {rows[-1][:60]!r}"))
    return problems


def _in_bounds(point: list[float], spec: SimulationBlockSpec, slack: float) -> bool:
    x, y = point
    return (
        spec.x_min - slack <= x <= spec.x_max + slack
        and spec.y_min - slack <= y <= spec.y_max + slack
    )


def check_visuals(reply: str) -> tuple[list[str], list[Problem]]:
    kinds: list[str] = []
    problems: list[Problem] = []
    # A height-time or x-y curve redraws the path a scene animates; a v-t graph
    # beside a fall says something the scene does not.
    path_graph = False
    for lang, body in fences(reply):
        if lang not in {"simulation", "graph"}:
            continue
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            problems.append(Problem("broken_visual", f"{lang} fence is not JSON"))
            continue
        if lang == "graph":
            kinds.append(f"graph:{data.get('type')}")
            path_graph = path_graph or (
                data.get("type") == "trajectory"
                and data.get("trajectory_type") in {None, "parametric", "position_vs_time"}
            )
            points = data.get("points") or []
            if any(not all(math.isfinite(v) for v in point) for point in points):
                problems.append(Problem("broken_visual", "graph has a non-finite point"))
            continue
        try:
            spec = SimulationBlockSpec.model_validate(data)
        except Exception as exc:
            problems.append(Problem("broken_visual", f"simulation fails its schema: {exc}"))
            continue
        kinds.append(spec.type)
        width, height = spec.x_max - spec.x_min, spec.y_max - spec.y_min
        if not 1 / 25 <= width / height <= 25:
            problems.append(
                Problem("broken_visual", f"{spec.type} box is {width:.3g} × {height:.3g}")
            )
        for body_spec in spec.bodies:
            slack = body_spec.radius * 1.05 + 1e-9
            outside = [p for p in body_spec.path if not _in_bounds(p, spec, slack)]
            if outside:
                problems.append(
                    Problem("broken_visual", f"{spec.type} body leaves the box at {outside[0]}")
                )
            share = body_spec.radius / max(width, height)
            if not 0.004 <= share <= 0.3:
                problems.append(
                    Problem("broken_visual", f"{spec.type} body radius is {share:.1%} of the box")
                )
    if "projectile_motion" in kinds and path_graph:
        problems.append(
            Problem("duplicate_visual", "a trajectory graph and an animation of one path")
        )
    return kinds, problems


def judge(entry: Entry, subject: str, route: Route) -> Outcome:
    outcome = Outcome(entry=entry, route=route, reply=route.instant_text)
    problems = outcome.problems
    if route.photo:
        problems.append(Problem("misread", f"photo lookup took the turn ({route.photo!r})"))
    if route.image_gen:
        problems.append(Problem("misread", "image generation took the turn"))
    if entry.expect == "not_subject":
        if route.subject == subject:
            problems.append(Problem("misread", f"read as a {subject} question"))
        return outcome
    if entry.expect in {"explain", "decline"}:
        if route.instant and route.instant != "solver":
            problems.append(Problem("misread", f"instant {route.instant} reply"))
        if route.solved:
            answer = read_answer(route.instant_text)
            problems.append(Problem("wrong", f"gave a number to a question with none: {answer}"))
        if entry.visual:
            # "Draw the forces on a box on an incline": no number, still its picture.
            outcome.visuals, visual_problems = check_visuals(route.server_pictures)
            problems.extend(visual_problems)
            if entry.visual not in outcome.visuals:
                problems.append(Problem("no_visual", f"no {entry.visual} picture"))
        return outcome
    if not route.subject:
        problems.append(Problem("missed", f"not read as a {subject} question"))
    elif route.subject not in {subject, entry.shared} and not route.solved:
        problems.append(Problem("misread", f"read as {route.subject}, not {subject}"))
    if route.search == "yes":
        problems.append(Problem("misread", "searched the web"))
    if route.instant and route.instant != "solver":
        # "How far is the image from the lens?" answered "Turn on Location".
        problems.append(
            Problem("misread", f"instant {route.instant} reply: {route.instant_text[:70]!r}")
        )
    if not route.solved:
        problems.append(Problem("unsolved", "no verified answer"))
        return outcome
    if not route.instant_text:
        # Verified, but the model writes the reply around the verified result
        # (an image question, a law kept off the direct path). Check the result.
        if not route.verified_answer:
            problems.append(Problem("unsolved", "no verified answer"))
            return outcome
        card = f"```answer\n{route.verified_answer}\n```\n\n{route.verified_text}"
        outcome.got, answer_problems = check_answer(entry, subject, card, whole=False)
        problems.extend(answer_problems)
        return outcome
    outcome.got, answer_problems = check_answer(entry, subject, route.instant_text)
    problems.extend(answer_problems)
    if route.subject == subject:
        problems.extend(check_shape(entry, route.instant_text, subject))
    problems.extend(Problem("latex", text) for text in latex_problems(route.instant_text))
    outcome.visuals, visual_problems = check_visuals(route.instant_text)
    problems.extend(visual_problems)
    if entry.visual and entry.visual not in outcome.visuals:
        problems.append(Problem("no_visual", f"no {entry.visual} picture"))
    return outcome


async def run_entry(entry: Entry, subject: str) -> Outcome:
    case = Case(
        entry.id, entry.area, entry.prompt, Expect(), "", history=entry.history, locale=entry.locale
    )
    route = await route_case(case)
    if route.instant_text:
        # The reply the student reads is the one that saves: the finalize passes held its
        # cards to the verified result, and a question in parts lost every card there.
        route.instant_text = await saved_reply(route)
    return judge(entry, subject, route)


async def run(entries: list[Entry], subject: str) -> list[Outcome]:
    outcomes: list[Outcome] = []
    for entry in entries:
        try:
            outcomes.append(await run_entry(entry, subject))
        except Exception as exc:  # A crash is a finding too.
            outcomes.append(
                Outcome(entry=entry, problems=[Problem("misread", f"crashed: {exc!r}")])
            )
    return outcomes


def answered(outcomes: list[Outcome]) -> list[Outcome]:
    """The ``answer`` turns that got a verified answer."""
    return [
        o
        for o in outcomes
        if o.entry.expect == "answer" and not any(p.kind == "unsolved" for p in o.problems)
    ]


def drawn(outcomes: list[Outcome]) -> list[Outcome]:
    """The ``answer`` and ``explain`` turns that carry the picture a student would want."""
    return [
        o
        for o in outcomes
        if o.entry.expect in {"answer", "explain"}
        and o.entry.visual
        and not any(p.kind == "no_visual" for p in o.problems)
    ]


def report(outcomes: list[Outcome], *, show: bool = False) -> str:
    kinds = Counter(problem.kind for outcome in outcomes for problem in outcome.problems)
    answers = [o for o in outcomes if o.entry.expect == "answer"]
    solved = answered(outcomes)
    wanted = [o for o in outcomes if o.entry.expect in {"answer", "explain"} and o.entry.visual]
    lines = [
        f"{len(outcomes)} turns: {len(solved)}/{len(answers)} answered, "
        f"{len(drawn(outcomes))}/{len(wanted)} with the picture a student would want",
        "problems: "
        + (", ".join(f"{kind} {count}" for kind, count in kinds.most_common()) or "none"),
    ]
    by_area: dict[str, list[int]] = {}
    for outcome in answers:
        tally = by_area.setdefault(outcome.entry.area, [0, 0, 0])
        tally[0] += 1
        tally[1] += outcome in solved
        tally[2] += bool(outcome.critical)
    lines.append(f"  {'area':<15} answered  critical")
    for area, (total, solved_here, bad) in sorted(by_area.items()):
        lines.append(f"  {area:<15} {solved_here:>3} / {total:<3} {bad:>4}")
    for outcome in outcomes:
        shown = outcome.problems if show else outcome.critical
        if not shown:
            continue
        entry = outcome.entry
        lines.append(f"\n[{entry.id}] ({entry.area}, expect {entry.expect}) {entry.prompt}")
        for problem in shown:
            lines.append(f"  - {problem.kind}: {problem.text}")
        if outcome.visuals:
            lines.append(f"  pictures: {', '.join(outcome.visuals)}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("subject", choices=sorted(SUBJECT_NAMES))
    parser.add_argument("--only", help="comma-separated entry ids")
    parser.add_argument("--area", help="one area")
    parser.add_argument("--show", action="store_true", help="also list coverage problems")
    args = parser.parse_args()
    from app.core.sympy_executor import set_sympy_executor
    from app.tests.sympy_support import ThreadSympyExecutor

    set_sympy_executor(ThreadSympyExecutor(max_workers=1))
    entries = load(args.subject)
    if args.only:
        wanted = {item.strip() for item in args.only.split(",")}
        entries = [entry for entry in entries if entry.id in wanted]
    if args.area:
        entries = [entry for entry in entries if entry.area == args.area]
    outcomes = asyncio.run(run(entries, SUBJECT_NAMES[args.subject]))
    print(report(outcomes, show=args.show))
    sys.exit(1 if any(outcome.critical for outcome in outcomes) else 0)


if __name__ == "__main__":
    main()

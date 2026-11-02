# ruff: noqa: RUF002 -- docstrings show the multiplication sign the reader sees.
"""Complete literal physics requests may display their existing verified result.

The stored intent is checked against a fresh extraction of the user text.
The reply reads the solver's formula and substitution; it does not parse them
back out of the prompt line.
"""

from __future__ import annotations

import json
import math
import re
from typing import Any

from app.modules.chat import present_assistant_markdown
from app.modules.physics.ask import has_ask
from app.modules.physics.bodies import side_questions
from app.modules.physics.catalog import (
    formula_spec,
    select_formula,
    symbol_for,
    variable_for,
    visible_assumptions,
)
from app.modules.physics.claims import claim_verdict, read_claims
from app.modules.physics.display import (
    is_conversion_row,
    latex_factor,
    latex_given,
    latex_unit,
    si_symbol,
)
from app.modules.physics.extract import extract_physics_intent
from app.modules.physics.glossary import given_meaning
from app.modules.physics.law_titles import law_heading
from app.modules.physics.notation import shown
from app.modules.physics.parts import asks_more_than_answered
from app.modules.physics.schemas import PhysicsIntent
from app.modules.physics.schemas.simulation import SIMULATION_SPEC_TYPES
from app.modules.physics.solvers.si import PARAM_SI_DIMENSIONS, si_factor, to_si
from app.modules.physics.working import result_symbol_for
from app.modules.physics.working_steps import carried_to_answer
from app.services.glyphs import SUPERSCRIPT_SIGNED
from app.services.solving import SolveServiceError, VerifiedPhysicsBlock
from app.services.worked_parts import WorkedPart, render_parts
from app.services.workout import (
    FORMULA,
    Workout,
    math_line,
    render_workout,
    solve_for_line,
    text_line,
    where_line,
)

_EXTRA_REQUEST = re.compile(
    r"\b(?:hint|air resistance|(?<!stokes )(?<!stokes' )drag|wind|"
    r"convert the answer|convert (?:it|this|that))\b"
    r"|\b(?:and|also|then)\s+(?:solve|calculate|compute|find|convert|explain|show|tell)\b",
    re.IGNORECASE,
)


def _expected_trajectory_type(intent: PhysicsIntent) -> str:
    """The one ``trajectory_type`` ``solve_physics`` emits for this intent.

    Must stay in lockstep with ``solve_kinematics`` / ``solve_projectile``. This
    guard exists to prove the fence came from that solve rather than from the
    model, so an extra value here would be a hole — and a missing one silently
    drops the whole direct reply, which is the harder failure to notice.
    """
    if intent.kind == "projectile":
        # One labelled scene, no graph: a trajectory fence here is not the solver's.
        return ""
    if intent.kind == "suvat":
        if intent.physics_op == "suvat_distance" or (
            intent.physics_op == "suvat_time" and "d" in (intent.physics_params or {})
        ):
            return "position_vs_time"
        return "velocity_vs_time"
    if intent.physics_op in ("velocity", "speed"):
        return "velocity_vs_time"
    if intent.kind in ("spring", "oscillations"):
        return "position_vs_time"
    # A fall is drawn as its scene; the height-time curve is gone.
    return ""


def _answers_every_ask(text: str, intent: PhysicsIntent) -> bool:
    """Whether the verified result is the whole reply this text asks for.

    Not when the text asks nothing (a statement), asks more parts than were
    solved, asks the question again on another body, or asks yes or no about
    a value: those go to the model with the verified block, so no part is
    dropped and the yes or no is said.
    """
    if not has_ask(text) or asks_more_than_answered(text, intent):
        return False
    if side_questions(text):
        return False
    return not any(claim.yes_no for claim in read_claims(text))


def can_direct_physics(
    verified: VerifiedPhysicsBlock, text: str, fences: list[dict[str, Any]]
) -> bool:
    intent = verified.physics_intent
    if intent is None:
        return False
    # The answer fence carries the typeset card; the plain answer is for guards.
    answer = verified.display_answer or verified.canonical_answer
    # P14 attaches a scene alongside the trajectory graph, so a projectile
    # carries two fences where the rule below expects one. A scene is not a
    # second answer — it is an illustration of the same one, server-owned and
    # never model-written — so it is set aside before the count rather than
    # counted. Without this, adding the scene silently switched every
    # projectile back to the provider path: this returned False, the
    # pre-computed reply was dropped, and nothing anywhere reported it.
    answering = [f for f in fences if f.get("type") not in SIMULATION_SPEC_TYPES]
    if not answer or len(answer) > 800 or len(answering) != 1:
        return False
    if not verified.physics_working:
        return False
    fence = answering[0]
    actual = extract_physics_intent(text)
    if actual is None or _EXTRA_REQUEST.search(text):
        return False
    if actual.model_dump() != intent.model_dump():
        return False
    if not _answers_every_ask(text, actual):
        return False
    if fence.get("type") == "answer":
        return fence.get("type") == "answer" and fence.get("content") == answer
    if fence.get("type") != "trajectory" or fence.get("expr2") or fence.get("points2"):
        return False
    points = fence.get("points")
    return bool(
        isinstance(points, list)
        and len(points) >= 2
        and all(
            isinstance(point, list)
            and len(point) == 2
            and all(type(value) in {int, float} and math.isfinite(value) for value in point)
            for point in points
        )
        and all(
            type(fence.get(key)) in {int, float} and math.isfinite(fence[key])
            for key in ("x_min", "x_max")
        )
        and fence["x_min"] < fence["x_max"]
        and bool(expected := _expected_trajectory_type(actual))
        and fence.get("trajectory_type") == expected
    )


def _parameter_symbol(name: str, operation: str) -> str:
    """Display symbol declared on this operation, as the reply shows it (``v_i`` for ``u``).
    The raw name is not a symbol."""
    spec = formula_spec(operation)
    if spec is None:
        raise ValueError(f"no physics formula named {operation}")
    symbol = symbol_for(spec, name)
    if symbol is None:
        raise ValueError(f"{operation} does not declare {name}")
    return shown(symbol, operation)


# A script of one character with or without braces (v^{2}, v^2), and a function of one
# argument with or without brackets (\sin(\theta), \sin\theta; \arcsin(\frac{1}{n}),
# \arcsin\frac{1}{n}), print the same law.
_BRACED_SCRIPT = re.compile(r"([_^])\{(\\[A-Za-z]+|[A-Za-z0-9])\}")
_FUNCTION_BRACKET = re.compile(r"\\(?:arcsin|arccos|arctan|sin|cos|tan|ln|log)\(")
_ONE_ARGUMENT = re.compile(r"\\?[A-Za-z]+(?:_[A-Za-z0-9])?|\\(?:frac|sqrt)(?:\{[^{}]*\})+")


def _unbracket_functions(text: str) -> str:
    """Drop the brackets round a function's argument when the argument is one atom."""
    out: list[str] = []
    cursor = 0
    for match in _FUNCTION_BRACKET.finditer(text):
        if match.start() < cursor:
            continue
        depth, close = 1, match.end()
        while close < len(text) and depth:
            depth += {"(": 1, ")": -1}.get(text[close], 0)
            close += 1
        inner = text[match.end() : close - 1]
        if depth == 0 and _ONE_ARGUMENT.fullmatch(inner):
            out.append(text[cursor : match.end() - 1] + inner)
            cursor = close
    return "".join(out) + text[cursor:]


def _formula_identity(formula: str) -> str:
    """Ignore presentation-only differences when comparing laws: spacing,
    multiplication dots, braces round a one-character script, brackets round a
    one-atom argument. Torque and centripetal force were each listed twice."""
    text = formula.replace(r"\cdot", "").replace(r"\times", "").replace(r"\,", "").replace(" ", "")
    return _unbracket_functions(_BRACED_SCRIPT.sub(r"\1\2", text))


def _formula_rows(
    intent: PhysicsIntent, formulas: list[str], operation: str | None = None
) -> list[str]:
    """The governing law's base form, then any rearrangement, as a step: ``Solve for $t$``
    over the rearranged formula. The law's name is the section's heading (``law_heading``),
    so no row repeats it. ``operation`` is one part's, in a question in parts."""
    operation = operation or intent.physics_op or ""
    spec = formula_spec(operation)
    params = intent.physics_params or {}
    base: str | None = None
    lines: tuple[str, ...] = ()
    if spec is not None:
        base, lines, _assumptions = select_formula(spec, params)
        base = None if base is None else shown(base, operation)
        lines = tuple(shown(line, operation) for line in lines)
    if lines:
        return [math_line(line) for line in lines]
    if base is None:
        return [math_line(formula) for formula in formulas]

    rows = [math_line(base)]
    base_lhs = base.split(" = ", 1)[0].strip()
    for formula in formulas:
        formula_lhs = formula.split(" = ", 1)[0].strip()
        if _formula_identity(formula) == _formula_identity(base):
            continue
        if formula_lhs == base_lhs:
            rows.append(math_line(formula, "the same law for these quantities"))
        else:
            rows.extend((solve_for_line(formula_lhs), math_line(formula)))
    return rows


def _given_value(name: str, value: float, unit: str, substitution: str) -> str:
    """The value as written and, when that is not SI, the value the solver used.

    A substitution in SI numbers needs the step that produced them first, on the
    given's own line with its factor: 500 nm × 10⁻⁹ = 5 × 10⁻⁷ m. A solver that
    works in the written units (150 km in 2 h) needs none, and neither do angles or
    rpm, whose formula converts.
    """
    written = f"{latex_given(value)}{latex_unit(unit)}"
    dimension = PARAM_SI_DIMENSIONS.get(name)
    if (
        not unit
        or dimension in (None, "dimensionless", "revolution / minute")
        or name.startswith("angle")
        # Written into the arithmetic as typed: "4 µF", not the "4 µF" ending "2.4 µF".
        or re.search(rf"(?<![\d.]){re.escape(written)}", substitution) is not None
    ):
        return written
    try:
        si_value = to_si(value, unit, expected_key=name)
    except SolveServiceError:
        return written
    si_unit = si_symbol(dimension)
    if latex_unit(si_unit) == latex_unit(unit) and math.isclose(si_value, value):
        return written
    # The factor that makes the SI value, so the step reads as one: 100 km/h * 1000/3600.
    # A unit that is SI under another name (N/m² is Pa) has none to show.
    factor = si_factor(unit, expected_key=name) if value else None
    scales = factor is not None and not math.isclose(factor[0], factor[1])
    times = f" {latex_factor(*factor)}" if factor and scales else ""
    return f"{written}{times} = {latex_given(si_value)}{latex_unit(si_unit)}"


def format_direct_physics_working(verified: VerifiedPhysicsBlock) -> str | None:
    """Five-section worked layout for a solver-verified instant reply.

    This formats the intent and the formula and substitution the solver stored.
    It never derives a result. The answer remains the canonical answer fence
    appended by the generic direct formatter.
    """
    intent = verified.physics_intent
    if intent is None or not verified.physics_working:
        return None
    if not verified.physics_formulas or not verified.physics_substitutions:
        return None

    params = intent.physics_params or {}
    units = intent.physics_units or {}
    given_rows: list[str] = []
    # The arithmetic only: a conversion row restates the answer, and an answer equal to a
    # given (λ = d in Bragg's law at 30°) would read as that given written into the working.
    arithmetic = " ".join(
        row for row in verified.physics_substitutions if not is_conversion_row(row)
    )
    operation = intent.physics_op or ""
    given_spec = formula_spec(operation)
    definitions: list[tuple[str, str]] = []
    for name, value in params.items():
        variable = variable_for(given_spec, name) if given_spec is not None else None
        if variable is not None and not variable.visible:
            continue
        symbol = _parameter_symbol(name, operation)
        shown = _given_value(name, value, units.get(name, ""), arithmetic)
        given_rows.append(f"${symbol} = {shown}$")
        meaning = given_meaning(operation, given_spec.kind if given_spec else "", name)
        if meaning:
            definitions.append((symbol, meaning))
    # Each given on its own line, then what each symbol stands for.
    naming = where_line(definitions)
    if naming:
        given_rows.append(naming)

    if len(verified.physics_parts) > 1:
        return _format_parts(verified, intent, given_rows)
    formulas = list(verified.physics_formulas)
    substitutions = list(verified.physics_substitutions)
    result_symbol = result_symbol_for(intent)
    find_symbol = result_symbol or formulas[0].split(" = ", 1)[0]
    formula_rows = _formula_rows(intent, formulas)
    spec = formula_spec(intent.physics_op or "")
    if spec is not None:
        formula_rows.extend(
            text_line(f"Assumes {assumption}.") for assumption in visible_assumptions(spec, params)
        )
    return render_workout(
        Workout(
            given=tuple(given_rows),
            # What is asked, named as the where-line names a given ("$v$ — speed").
            find=(math_line(find_symbol, _meaning(operation, find_symbol)),),
            formula=tuple(formula_rows),
            substitution=tuple(
                math_line(row)
                for row in carried_to_answer(
                    substitutions, verified.display_answer or verified.canonical_answer
                )
            ),
            formula_heading=law_heading(spec.law_name) if spec is not None else FORMULA,
        )
    )


_SUPERSCRIPT_DIGITS = SUPERSCRIPT_SIGNED
# The first value of a plain verified answer: "19.8 m/s", "3.97 × 10⁻¹⁹ J".  # noqa: RUF003 - the answer's glyphs
_PLAIN_ANSWER = re.compile(
    r"^\s*(?P<number>-?\d+(?:\.\d+)?)(?:\s*×\s*10(?P<power>[⁰¹²³⁴⁵⁶⁷⁸⁹⁻]+))?"  # noqa: RUF001 - the answer's glyphs
    r"\s*(?P<unit>[^\s(;,]+)?"
)


def _claim_line(verified: VerifiedPhysicsBlock, user_text: str) -> str | None:
    """Whether the student's stated result matches the verified one, in one line."""
    match = _PLAIN_ANSWER.match(verified.canonical_answer or "")
    if match is None or not match.group("unit"):
        return None
    value = float(match.group("number"))
    if match.group("power"):
        value *= 10.0 ** int(match.group("power").translate(_SUPERSCRIPT_DIGITS))
    return claim_verdict(user_text, value, match.group("unit"))


def _solver_fences(verified: VerifiedPhysicsBlock) -> list[dict[str, Any]]:
    fences: list[dict[str, Any]] = []
    for fence in (verified.canonical_fence, *verified.canonical_fences):
        if fence is not None and fence not in fences:
            fences.append(fence)
    return fences


def _meaning(operation: str, symbol: str) -> str | None:
    """What an unknown stands for, from the glossary that names the givens."""
    spec = formula_spec(operation)
    return given_meaning(operation, spec.kind if spec is not None else "", symbol)


def _format_parts(
    verified: VerifiedPhysicsBlock, intent: PhysicsIntent, given_rows: list[str]
) -> str:
    """A question in parts: the givens and what is asked once, then each part worked on
    its own, closed by its own answer card, a hairline between parts."""
    worked: list[WorkedPart] = []
    for part in verified.physics_parts:
        spec = formula_spec(part.op)
        rows = _formula_rows(intent, list(part.formulas), part.op)
        if spec is not None:
            params = intent.physics_params or {}
            rows.extend(text_line(f"Assumes {item}.") for item in visible_assumptions(spec, params))
        working = render_workout(
            Workout(
                formula=tuple(rows),
                substitution=tuple(
                    math_line(row)
                    for row in carried_to_answer(part.substitutions, part.display_answer)
                ),
                formula_heading=law_heading(spec.law_name) if spec is not None else FORMULA,
            ),
            answer_heading=None,
        )
        worked.append(
            WorkedPart(
                title=part.title,
                working=working,
                answer=part.display_answer,
                required=(math_line(part.symbol, _meaning(part.op, part.symbol)),),
            )
        )
    # The one layout every question in parts has (``services/worked_parts``).
    return render_parts(worked, given_rows)


def maybe_direct_physics_reply(
    verified: VerifiedPhysicsBlock | None,
    user_text: str,
    *,
    has_image_attachment: bool = False,
) -> str | None:
    """Render a complete physics reply from solver-owned data only."""
    if verified is None or has_image_attachment:
        return None
    if verified.symbolic_request is not None:
        from app.modules.physics.symbolic.request import parse_symbolic_physics_request

        if (
            verified.allow_direct
            and verified.direct_reply
            and verified.direct_request_text == user_text
            and verified.symbolic_request == parse_symbolic_physics_request(user_text)
            and verified.direct_answer_binding == verified.display_answer
            and verified.canonical_fence == {"type": "answer", "content": verified.display_answer}
            and not verified.canonical_fences
        ):
            return present_assistant_markdown(verified.direct_reply)
        return None
    fences = _solver_fences(verified)
    if not can_direct_physics(verified, user_text, fences):
        return None
    working = format_direct_physics_working(verified)
    if working is None:
        return None
    answer = (verified.display_answer or verified.canonical_answer or "").strip()
    if not answer:
        return None
    # A question in parts carries a card per part already.
    parts = [working] if len(verified.physics_parts) > 1 else [working, f"```answer\n{answer}\n```"]
    for fence in fences:
        fence_type = fence.get("type")
        if fence_type == "answer":
            continue
        language = "simulation" if fence_type in SIMULATION_SPEC_TYPES else "graph"
        parts.append(f"```{language}\n{json.dumps(fence, separators=(',', ':'))}\n```")
    reply = "\n\n".join(parts) + "\n"
    verdict = _claim_line(verified, user_text)
    if verdict is not None:
        reply = f"{verdict}\n\n{reply}"
    intent = verified.physics_intent
    if (
        intent is not None
        and intent.kind == "kinematics"
        and intent.physics_op
        in {
            "velocity",
            "acceleration",
        }
    ):
        return present_assistant_markdown(f"Upward is positive.\n\n{reply}")
    return present_assistant_markdown(reply)

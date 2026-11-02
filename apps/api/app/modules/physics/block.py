"""Physics verified blocks — numeric answer plus optional trajectory graph.

Builds the system-prompt hint for kinematics/projectile/force/energy/momentum
intents: a verified answer (so the model doesn't recompute) plus an
optional trajectory graph Recall attaches after the stream.
"""

from __future__ import annotations

import logging
from dataclasses import replace

from app.core.config import Settings
from app.modules.physics.answer_checks import (
    _answers_the_question,
    _in_context_units,
    _in_the_asked_unit,
)
from app.modules.physics.catalog import formula_spec
from app.modules.physics.display import conversion_row
from app.modules.physics.law_titles import law_heading, law_title
from app.modules.physics.notation import shown
from app.modules.physics.schemas import PhysicsIntent
from app.modules.physics.solver import PhysicsResult, solve_physics
from app.modules.physics.solvers.chip import render_quantity, render_quantity_latex
from app.modules.physics.solvers.results import PartResult, QuantityResult
from app.modules.physics.working_steps import carried_to_answer
from app.services.solving import (
    PhysicsPartWorking,
    SolveServiceError,
    VerifiedPhysicsBlock,
    wrap_verified_physics,
)
from app.services.workout import PHYSICS_WORKOUT_PROMPT_RULE

logger = logging.getLogger(__name__)

# Display labels only, in the catalog's letters (``notation.shown`` writes v as v_f).
# Supported operations and validation live on PhysicsIntent.
_PROJECTILE_LABELS = {
    "time_of_flight": r"t_{\mathrm{flight}}",
    "max_height": r"H_{\mathrm{max}}",
    "range": "R",
    "impact_speed": r"v_{\mathrm{impact}}",
}
_SUVAT_LABELS = {
    "suvat_velocity": "v",
    "suvat_distance": "s",
    "suvat_time": "t",
    "suvat_acceleration": "a",
}
# What each part of a question in parts finds, as its label reads: "(a) Time of flight".
_PART_TITLES = {
    "time_of_flight": "Time of flight",
    "max_height": "Maximum height",
    "range": "Range",
    "impact_speed": "Impact speed",
    "suvat_velocity": "Final velocity",
    "suvat_distance": "Distance",
    "suvat_time": "Time",
    "suvat_acceleration": "Acceleration",
}
_PROJECTILE_UNITS = {"s", "m", "m/s"}
_SUVAT_UNITS = {"s", "m", "m/s", "m/s^2", "m/s²"}


def _solve_requested_quantities(intent: PhysicsIntent) -> PhysicsResult:
    """Solve every requested part before publishing any multipart result.

    Reuse the existing solvers and their verified working. All supported parts
    share one launch and therefore the same path; keep that visual once, not
    one graph and scene per scalar quantity. A failure aborts the whole block.
    """
    if not intent.requested_ops:
        return solve_physics(intent)
    # Validate even a model_copy-constructed intent before trusting its parts.
    intent = PhysicsIntent.model_validate(intent.model_dump())
    suvat = intent.kind == "suvat"
    labels = _SUVAT_LABELS if suvat else _PROJECTILE_LABELS
    allowed = _SUVAT_UNITS if suvat else _PROJECTILE_UNITS
    results: list[PhysicsResult] = []
    labeled: list[QuantityResult] = []
    for op in intent.requested_ops:
        part = PhysicsIntent.model_validate(
            {**intent.model_dump(), "physics_op": op, "requested_ops": []}
        )
        result = solve_physics(part)
        if len(result.quantities) != 1:
            raise SolveServiceError("unexpected multipart result representation")
        item = result.quantities[0]
        if item.unit not in allowed or op not in labels:
            raise SolveServiceError("unexpected multipart result representation")
        labeled.append(QuantityResult(shown(labels[op], op), item.value, item.unit))
        results.append(result)
    first = results[0]
    return PhysicsResult(
        answer=r";\quad ".join(result.answer for result in results),
        quantities=tuple(labeled),
        formulas=tuple(formula for result in results for formula in result.formulas),
        substitutions=tuple(row for result in results for row in result.substitutions),
        joiner="projectile",
        graph_specs=[] if suvat else first.graph_specs,
        simulation_specs=[] if suvat else first.simulation_specs,
        parts=tuple(
            PartResult(op, quantity, part)
            for op, quantity, part in zip(intent.requested_ops, labeled, results, strict=True)
        ),
    )


def part_title(op: str, symbol: str) -> str:
    """What a part finds, as its label names it: "Time", "Power", "Weight"."""
    if op in _PART_TITLES:
        return _PART_TITLES[op]
    spec = formula_spec(op)
    return law_title(spec.law_name) if spec is not None else symbol


def _part_workings(result: PhysicsResult) -> tuple[PhysicsPartWorking, ...]:
    """Each part of a question in parts, with its own working and its own card."""
    return tuple(
        PhysicsPartWorking(
            op=part.op,
            symbol=part.quantity.symbol,
            title=_PART_TITLES.get(part.op, part.quantity.symbol),
            formulas=part.result.formulas,
            substitutions=part.result.substitutions,
            answer=render_quantity(replace(part.quantity, symbol="")),
            display_answer=render_quantity_latex(replace(part.quantity, symbol="")),
        )
        for part in result.parts
    )


def _with_conversions(solved: PhysicsResult, shown: PhysicsResult) -> PhysicsResult:
    """The shown result, with a row for each value it shows in another unit.

    The substitution works in SI, so "49.2 L" needs the step from the 0.0492 m³ it gives.
    """
    if len(solved.quantities) != len(shown.quantities):
        return shown
    # A catalog law's quantity has no label; its substitution row starts with the symbol.
    named = shown.substitutions[-1].split(" = ", 1)[0] if shown.substitutions else ""
    rows = tuple(
        conversion_row(
            after.symbol or named, (before.value, before.unit), (after.value, after.unit)
        )
        for before, after in zip(solved.quantities, shown.quantities, strict=True)
        if before.unit != after.unit
    )
    return replace(shown, substitutions=(*shown.substitutions, *rows)) if rows else shown


# The solver's scene is the drawing: the model neither denies it nor draws its own.
NATIVE_VISUAL_RULE = (
    "A verified native physics visual will render with this answer and will animate "
    "automatically when the scene contains motion. Never claim that you cannot show, "
    "embed, or provide an animation or diagram. Do not discuss how the visual is attached "
    "and do not emit a simulation fence yourself, or draw the situation again as a "
    "```mermaid diagram, ASCII art or a text sketch: the app's picture is the drawing."
)


def _build_physics_block(
    intent: PhysicsIntent, settings: Settings, lines: list[str]
) -> VerifiedPhysicsBlock | None:
    """Solve the physics problem and build a verified block with answer + graph."""
    result: PhysicsResult | None = None
    try:
        result = _solve_requested_quantities(intent)
    except SolveServiceError as exc:
        logger.info(
            "physics verification skipped kind=%s op=%s reason=%s",
            intent.kind,
            intent.physics_op,
            exc,
        )
        return None
    except Exception:
        logger.warning(
            "physics verification failed kind=%s op=%s",
            intent.kind,
            intent.physics_op,
            exc_info=True,
        )
        return None
    result = _with_conversions(
        result, _in_context_units(intent, _in_the_asked_unit(intent, result))
    )
    if not _answers_the_question(intent, result):
        logger.info(
            "physics verification skipped kind=%s op=%s reason=answers a different quantity",
            intent.kind,
            intent.physics_op,
        )
        return None

    if intent.requested_ops and intent.kind == "projectile":
        lines.append("Every requested projectile quantity below was solved for the same givens.")
        lines.append(
            "Working uses uniform gravity, no air resistance, and heights measured from "
            "the landing plane. Copy each verified formula; do not recalculate its numbers."
        )
    elif intent.requested_ops:
        lines.append(
            "Every requested constant-acceleration quantity below was solved for the same givens. "
            "Copy each verified formula; do not recalculate its numbers."
        )
    spec = formula_spec(intent.physics_op or "")
    law = law_heading(spec.law_name) if spec is not None else None
    lines.append(
        "Use this user-visible layout for this verified physics solution: "
        f"{PHYSICS_WORKOUT_PROMPT_RULE} Put every equation on its own line. Under Given, list "
        "the supplied quantities with units. Under Required, name the requested quantity. Head "
        'the formulas with the verified law\'s heading (its name and "formula"), not Formula; '
        "show its universal/base equation first, then any rearrangement for the unknown under a "
        "`Solve for` line. Under Substitution, insert the supplied numbers and copy the verified "
        "rows to the result. Under Answer, state the verified result exactly once."
    )
    if result.simulation_specs:
        lines.append(NATIVE_VISUAL_RULE)
    # Plain text for guards and readers without math; LaTeX for the card.
    answer, card = result.answer_value, result.answer_latex
    # The model sees the same rows the direct reply formats. The combined
    # solver chain stays on result.answer for internal checks.
    worked = carried_to_answer(result.substitutions, card)
    parts = _part_workings(result)
    verified_lines = [
        *([f"Verified law: {law}"] if law else []),
        "Verified formula:",
        *(f"${row}$" for row in result.formulas),
        "Verified substitution:",
        *(f"${row}$" for row in worked),
        f"Verified result: ${card}$",
    ]
    lines.extend(verified_lines)
    structured_working = "\n".join(verified_lines)

    # A solve may produce both a plot and a scene — a projectile's parabola and
    # the ball flying along it. `canonical_fences` is what carries more than one
    # fence through `validate_math_fences`, so every spec goes there and the
    # primary stays first for the callers that read `canonical_fence` alone.
    specs = [spec.model_dump() for spec in (*result.graph_specs, *result.simulation_specs)]
    if not specs:
        return VerifiedPhysicsBlock(
            text="\n".join(lines),
            subject="physics",
            canonical_fence={"type": "answer", "content": card},
            canonical_answer=answer,
            display_answer=card,
            allow_direct=False,
            physics_intent=intent.model_copy(deep=True),
            physics_working=structured_working,
            physics_formulas=result.formulas,
            physics_substitutions=result.substitutions,
            physics_parts=parts,
        )

    if result.graph_specs:
        # A graph *is* the answer in visual form, so it leads and the turn may
        # take the direct path exactly as it always could.
        block = VerifiedPhysicsBlock(
            text="\n".join(lines),
            subject="physics",
            canonical_fence=specs[0],
            canonical_answer=answer,
            display_answer=card,
            physics_intent=intent.model_copy(deep=True),
            physics_working=structured_working,
            physics_formulas=result.formulas,
            physics_substitutions=result.substitutions,
            physics_parts=parts,
        )
    else:
        # A scene attached to a scalar answer is decoration, not a second
        # answer. Keep the answer fence primary; the physics direct guard
        # separately requires the solver-owned working before it can format a
        # complete response, so the picture never grants directness by itself.
        block = VerifiedPhysicsBlock(
            text="\n".join(lines),
            subject="physics",
            canonical_fence={"type": "answer", "content": card},
            canonical_answer=answer,
            display_answer=card,
            allow_direct=False,
            physics_intent=intent.model_copy(deep=True),
            physics_working=structured_working,
            physics_formulas=result.formulas,
            physics_substitutions=result.substitutions,
            physics_parts=parts,
        )

    # Extras only. Every reader of `canonical_fences` already prepends
    # `canonical_fence`, so repeating it here would mean a caller that clears
    # the primary still finds a copy — and for a scalar answer the primary
    # *is* the authorisation for a direct reply.
    extras = [spec for spec in specs if spec is not block.canonical_fence]
    return replace(block, canonical_fences=extras)


def build_verified_physics_block(
    intent: PhysicsIntent, settings: Settings
) -> VerifiedPhysicsBlock | None:
    """Public synchronous physics verification entry point.

    Chat uses the asynchronous wrapper in :mod:`app.modules.physics.prompt`;
    tests and non-chat integrations use this function without reaching into
    math's block dispatcher.
    """
    block = _build_physics_block(intent, settings, [])
    if block is None:
        return None
    return replace(block, text=wrap_verified_physics(block.text))

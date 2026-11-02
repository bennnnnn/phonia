"""Whole-request guards before the existing heuristic physics extractors.

Normalize numeric spellings once. Bind two-body collision givens to their
bodies rather than silently supplying rest states. Preserve a closed list of
projectile questions rather than certifying only the first matching quantity.
No equations are solved here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.modules.physics.extractors.momentum import _COLLISION_SUBJECT_RE, _TWO_DIMENSIONAL_RE
from app.modules.physics.extractors.surface_gravity import detect_gravity, stated_gravity
from app.modules.physics.extractors.unit_patterns import (
    LENGTH_UNIT_PATTERN,
    MASS_UNITS,
    NUMBER,
    VELOCITY_UNIT_PATTERN,
)
from app.modules.physics.numbers import normalize_physics_numbers, normalize_physics_units
from app.modules.physics.registry import has_supported_physics_cue
from app.modules.physics.schemas import PhysicsIntent
from app.modules.physics.schemas.intent import ProjectileQuantity
from app.services.number_text import numeric_spans

if TYPE_CHECKING:
    from app.services.law_binding.spec import FormulaSpec

_MASS = re.compile(rf"({NUMBER})\s*({MASS_UNITS})(?![A-Za-z0-9/^])", re.IGNORECASE)
_SPEED = re.compile(rf"({NUMBER})\s*({VELOCITY_UNIT_PATTERN})(?![A-Za-z0-9/^])", re.IGNORECASE)
_LENGTH = re.compile(rf"({NUMBER})\s*({LENGTH_UNIT_PATTERN})(?![A-Za-z0-9/^])", re.IGNORECASE)
_REST = re.compile(r"\bat rest\b|\bstationary\b|\binitially still\b", re.IGNORECASE)
# "sticks to a stationary 1 kg cart": the rest word before a mass is that body's.
_REST_BEFORE_MASS = re.compile(
    r"(?:\bat rest\b|\bstationary\b|\binitially still\b)\s*$", re.IGNORECASE
)
_ELASTIC = re.compile(r"\belastic(?:ally)?\b", re.IGNORECASE)
_STICKING = re.compile(
    r"\b(?:perfectly|completely|totally)\s+inelastic(?:ally)?\b"
    r"|\bsticks? together\b|\bstuck together\b|\bcoupled?\b"
    # "collides with and sticks to a stationary 1 kg cart"
    r"|\b(?:sticks?|stuck|sticking)\s+to\b"
    r"|\bembed(?:s|ded)?\b|\blocks? together\b|\block(?:s|ed)?\s+bumpers\b"
    r"|\blodge[sd]?\b|\bmoves?\s+off\s+together\b",
    re.IGNORECASE,
)
# Restitution and a negated rest state introduce conditions the two-body
# reading does not bind. Do not silently drop them.
_COLLISION_QUALIFIER = re.compile(
    r"\b(?:not|never|neither|without|restitution|energy|impulse|momentum|force|friction)\b"
    r"|\baway from each other\b",
    re.IGNORECASE,
)
# A body's direction along the line: "a 0.5 kg puck moving east at 4 m/s".
_DIRECTION = re.compile(r"\b(east|west|north|south|left|right)(?:wards?)?\b", re.IGNORECASE)
_AXIS_SIGN = {
    "east": ("east-west", 1),
    "west": ("east-west", -1),
    "north": ("north-south", 1),
    "south": ("north-south", -1),
    "right": ("left-right", 1),
    "left": ("left-right", -1),
}
# Both moving, each toward the other: the second speed points back along the line.
_OPPOSED = re.compile(
    r"\btowards? each other\b|\bin\s+(?:the\s+)?opposite\s+directions?\b|\bhead[- ]on\s+toward",
    re.IGNORECASE,
)
# "How much kinetic energy is lost?": the energy a sticking collision turns to heat.
_ENERGY_LOST = re.compile(
    r"\b(?:kinetic\s+energy|energy|ke)\b[^.?!]{0,40}?\b(?:lost|loss|dissipated|converted|wasted)\b"
    r"|\b(?:loss|lost)\s+(?:of|in)\s+(?:the\s+)?(?:kinetic\s+energy|energy|ke)\b",
    re.IGNORECASE,
)
_ASK = re.compile(r"\b(?:find|calculate|compute|determine|what\s+are)\s+", re.IGNORECASE)
_QUANTITY = re.compile(
    r"\b(?:(?:total\s+)?(?:time of flight|flight time)|"
    r"(?:maximum|max|peak) height|(?:horizontal\s+)?range|(?:impact|landing) speed)\b",
    re.IGNORECASE,
)
_GRAVITY = re.compile(
    rf"\b(?:g\s*=|gravity\s*(?:of|is|=)?)\s*{NUMBER}(?:\s*m/s\^?2)?",
    re.IGNORECASE,
)
_ANGLE = re.compile(rf"{NUMBER}\s*(?:degrees?|deg|°|radians?|rad)(?![A-Za-z0-9])", re.IGNORECASE)
_MATH_POWER_REQUEST = re.compile(
    r"\b(?:raised\s+to|to)\s+(?:the\s+)?"
    r"(?:\d+(?:st|nd|rd|th)?|first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth)"
    r"\s+power\b"
    r"|\bto\s+the\s+power\s+of\s*[+-]?\d"
    r"|\b(?:\d+(?:st|nd|rd|th)|first|second|third|fourth|fifth|sixth|seventh|"
    r"eighth|ninth|tenth)\s+power\s+of\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class PhysicsRequest:
    text: str
    rejected: bool = False
    collision: PhysicsIntent | None = None
    projectile_ops: tuple[ProjectileQuantity, ...] = ()


def _accounted_for(text: str, quantities: list[re.Match[str]]) -> bool:
    return all(
        any(quantity.start() <= start and end <= quantity.end() for quantity in quantities)
        for start, end in numeric_spans(text)
    )


def _body_names(masses: list[re.Match[str]], ask_start: int) -> list[re.Match[str]] | None:
    """The two bodies; a mass in the asked clause that repeats one names that body.

    "What is the velocity of the 4 kg ball after?" asks about the second body;
    it states no third mass. None when the ask names a mass no body has.
    """
    stated = [mass for mass in masses if mass.start() < ask_start]
    for mass in masses[len(stated) :]:
        if not any(
            float(mass[1]) == float(body[1]) and mass[2].lower() == body[2].lower()
            for body in stated
        ):
            return None
    return stated


# A body said to move two ways at once ("east ... north").
_TWO_WAYS = ("", 0)


def _direction(clause: str) -> tuple[str, int] | None:
    """The one direction a body's clause gives; ``_TWO_WAYS`` when it gives two."""
    found = {_AXIS_SIGN[match[1].lower()] for match in _DIRECTION.finditer(clause)}
    if len(found) > 1:
        return _TWO_WAYS
    return next(iter(found), None)


def _collision_intent(text: str) -> PhysicsIntent | None:
    """Accept exactly two explicitly specified bodies and a supported model.

    Speeds are signed along the first body's motion. A second body moving the
    other way ("moving west" after "moving east", or "toward each other")
    carries a negative speed; a direction that is not on the first body's
    line is two-dimensional and declines.
    """
    from app.modules.physics.ask import ask_clause

    clause = ask_clause(text)
    ask_start = text.rfind(clause) if clause else len(text)
    all_masses = list(_MASS.finditer(text))
    masses = _body_names(all_masses, ask_start)
    if masses is None or len(masses) != 2 or _TWO_DIMENSIONAL_RE.search(text):
        return None
    energy_lost = clause is not None and _ENERGY_LOST.search(clause) is not None
    # The energy the ask names is the question, not a condition on the collision.
    if _COLLISION_QUALIFIER.search(text[:ask_start] if energy_lost else text):
        return None
    if not _accounted_for(text, [*all_masses, *_SPEED.finditer(text)]):
        return None
    elastic = _ELASTIC.search(text) is not None
    sticking = _STICKING.search(text) is not None
    if elastic == sticking or (energy_lost and not sticking):
        # Generic 'inelastic' does not say that the objects stick together, and
        # an elastic collision loses no kinetic energy to be asked about.
        return None
    if _DIRECTION.search(text[: masses[0].start()]) or _DIRECTION.search(text[ask_start:]):
        return None
    params: dict[str, float] = {"elastic": float(elastic)}
    units: dict[str, str] = {"elastic": ""}
    consumed_speeds = 0
    directions: list[tuple[str, int] | None] = []
    leading_rest = _REST_BEFORE_MASS.search(text[: masses[0].start()]) is not None
    for index, mass in enumerate(masses, start=1):
        value = float(mass[1])
        if value <= 0:
            return None
        end = masses[index].start() if index < len(masses) else ask_start
        body_clause = text[mass.end() : end]
        trailing = _REST_BEFORE_MASS.search(body_clause) if index < len(masses) else None
        if trailing is not None:
            body_clause = body_clause[: trailing.start()]
        velocities = list(_SPEED.finditer(body_clause))
        at_rest = leading_rest or _REST.search(body_clause) is not None
        leading_rest = trailing is not None
        if len(velocities) > 1 or (not velocities and not at_rest):
            return None
        velocity, velocity_unit = (
            (float(velocities[0][1]), velocities[0][2]) if velocities else (0.0, "m/s")
        )
        if at_rest and velocity != 0:
            return None
        direction = _direction(body_clause)
        if direction == _TWO_WAYS:
            return None
        directions.append(direction if velocity != 0 else None)
        consumed_speeds += len(velocities)
        params.update({f"m{index}": value, f"v{index}": velocity})
        units.update({f"m{index}": mass[2], f"v{index}": velocity_unit})
    if consumed_speeds != len(list(_SPEED.finditer(text))):
        return None
    first, second = directions
    moving = params["v1"] != 0 and params["v2"] != 0
    opposed = _OPPOSED.search(text) is not None
    if first is not None and second is not None:
        if first[0] != second[0] or opposed:
            return None
        if first[1] != second[1]:
            params["v2"] = -params["v2"]
    elif (first is not None or second is not None) and moving:
        # One body's direction and the other's unsaid: the line's sense is unknown.
        return None
    elif opposed:
        if not moving:
            return None
        params["v2"] = -params["v2"]
    return PhysicsIntent(
        kind="momentum",
        physics_op="collision_energy_lost" if energy_lost else "final_velocity",
        physics_params=params,
        physics_units=units,
    )


# "(a) what is the max height (b) the range": a question in labelled parts.
_PART_LABEL = re.compile(r"\(\s*([a-d])\s*\)")
# What may sit beside a part's quantity: its question words and articles.
_PART_FILLER = re.compile(
    r"\b(?:what\s+is|what's|what\s+are|find|calculate|compute|determine|work\s+out"
    r"|the|its|and)\b|[\s,?.!:]",
    re.IGNORECASE,
)


def _labelled_quantities(text: str) -> tuple[list[re.Match[str]], int] | None:
    """Each labelled part's one quantity, and where the parts start.

    None when the text has no labelled parts, and an empty list when a part
    asks for something this reading does not know: that part would be dropped.
    """
    labels = list(_PART_LABEL.finditer(text))
    if len(labels) < 2 or [label.group(1) for label in labels] != list("abcd"[: len(labels)]):
        return None
    found: list[re.Match[str]] = []
    for index, label in enumerate(labels):
        end = labels[index + 1].start() if index + 1 < len(labels) else len(text)
        segment = text[label.end() : end]
        quantities = list(_QUANTITY.finditer(segment))
        if len(quantities) != 1 or _PART_FILLER.sub("", _QUANTITY.sub("", segment)):
            return [], labels[0].start()
        found.append(quantities[0])
    return found, labels[0].start()


def _projectile_parts(text: str) -> tuple[ProjectileQuantity, ...] | None:
    """Read a question-last list; None means a recognized but incomplete list.

    Unsupported tail requests cannot be peeled off: 'range, maximum height,
    and kinetic energy' must not be represented as two verified quantities.
    A question in labelled parts ("(a) what is the max height (b) the range")
    is the same list, read part by part. Other multipart question grammars
    remain outside this bounded extension.
    """
    labelled = _labelled_quantities(text)
    if labelled is not None:
        matches, ask_start = labelled
        if not matches:
            return None if len(list(_QUANTITY.finditer(text))) > 1 else ()
    else:
        requests = list(_ASK.finditer(text))
        if not requests:
            return None if len(list(_QUANTITY.finditer(text))) > 1 else ()
        if len(requests) > 1 and len(list(_QUANTITY.finditer(text))) >= 2:
            return None
        tail_and_suffix = re.split(r"[.?!]", text[requests[-1].end() :], maxsplit=1)
        tail = tail_and_suffix[0].strip()
        matches = list(_QUANTITY.finditer(tail))
        if len(matches) < 2:
            return None if len(list(_QUANTITY.finditer(text))) > 1 else ()
        if len(tail_and_suffix) > 1 and _QUANTITY.search(tail_and_suffix[1]):
            return None
        remainder = _QUANTITY.sub("", tail)
        if re.sub(r"\b(?:the|its|and)\b|[\s,]", "", remainder, flags=re.IGNORECASE):
            return None
        ask_start = requests[-1].start()
    ops: list[ProjectileQuantity] = []
    for match in matches:
        phrase = match.group().lower()
        op: ProjectileQuantity
        if "time" in phrase:
            op = "time_of_flight"
        elif "height" in phrase:
            op = "max_height"
        elif "range" in phrase:
            op = "range"
        else:
            op = "impact_speed"
        if op not in ops:
            ops.append(op)
    if len(ops) < 2:
        return ()
    context = re.sub(
        r"\b(?:ignor(?:e|ing)|neglect(?:ing)?|no|without)\s+(?:the\s+)?air resistance\b",
        "",
        text,
        flags=re.IGNORECASE,
    )
    if re.search(r"\b(?:air resistance|drag|wind|spin)\b", context, re.IGNORECASE):
        return None
    # All parts describe one launch; do not choose the first of two speeds or
    # angles, or turn an unrelated length (a wall) into the launch height.
    if len(list(_SPEED.finditer(text))) != 1 or len(list(_ANGLE.finditer(text))) != 1:
        return None
    lengths = list(_LENGTH.finditer(text))
    if len(lengths) > 1:
        return None
    if lengths and not re.search(
        r"\b(?:height|cliff|ledge|platform|h0)\b",
        text[:ask_start],
        re.IGNORECASE,
    ):
        return None
    gravities = list(_GRAVITY.finditer(text))
    if len(gravities) > 1 or not _accounted_for(
        text, [*_SPEED.finditer(text), *_ANGLE.finditer(text), *lengths, *gravities]
    ):
        return None
    return tuple(ops)


def prepare_physics_request(text: str) -> PhysicsRequest:
    """Preflight at the dispatch boundary so refusals cannot fall into algebra."""
    unit_normalized = normalize_physics_units(text)
    if not has_supported_physics_cue(unit_normalized):
        return PhysicsRequest(unit_normalized)
    normalized = normalize_physics_numbers(unit_normalized)
    if normalized is None:
        return PhysicsRequest(text, rejected=True)
    if _MATH_POWER_REQUEST.search(normalized):
        # Do not use earlier physical work/time data to answer a separate
        # exponent request later in the message. The subject layer may decline
        # the compound turn, but it must never certify the unrelated 20 W.
        return PhysicsRequest(normalized, rejected=True)
    if _COLLISION_SUBJECT_RE.search(normalized) and len(list(_MASS.finditer(normalized))) >= 2:
        collision = _collision_intent(normalized)
        return PhysicsRequest(normalized, rejected=collision is None, collision=collision)
    ops = _projectile_parts(normalized)
    return PhysicsRequest(normalized, rejected=ops is None, projectile_ops=ops or ())


_LATEX_COMMAND = re.compile(r"\\[A-Za-z]+")
# An expression names g as an identifier (m*g). Latex writes the product glued
# (mg, gh_1, 2g). Commands are removed first, so the g in \log or \gamma is not one.
_G_NAME = re.compile(r"(?<![A-Za-z0-9_])g(?![A-Za-z0-9_])")


def _text_uses_g(text: str | None) -> bool:
    if not text:
        return False
    if "\\" in text or "{" in text:
        return "g" in _LATEX_COMMAND.sub(" ", text)
    return _G_NAME.search(text) is not None


def _variant_uses_g(latex: str | None, expression: str | None, lines: tuple[str, ...]) -> bool:
    return _text_uses_g(latex) or _text_uses_g(expression) or any(map(_text_uses_g, lines))


def _selection_uses_gravity(spec: FormulaSpec, params: dict[str, float]) -> bool:
    """Whether this filled formula multiplies by g.

    A variable named g on the catalog is not enough. Bernoulli declares g for
    the height variant, and the horizontal form does not use it.
    """
    from app.modules.physics.catalog import matching_variant

    if not any(variable.name == "g" for variable in spec.variables):
        return False
    variant = matching_variant(spec, params)
    if variant is not None and (variant.latex is not None or variant.expression or variant.lines):
        return _variant_uses_g(variant.latex, variant.expression, variant.lines)
    if _text_uses_g(spec.base_latex) or _text_uses_g(spec.expression):
        return True
    # g appears only in a variant that this selection did not take.
    if any(_variant_uses_g(item.latex, item.expression, item.lines) for item in spec.variants):
        return False
    return True


def complete_physics_intent(intent: PhysicsIntent, request: PhysicsRequest) -> PhysicsIntent | None:
    """Attach every requested projectile quantity, or refuse a different solve.

    A solve that skipped a stated quantity of a kind it uses is refused too.
    The asked dimensions ride along so the block can refuse an answer to a
    different question.
    """
    from app.modules.physics.accounting import competing_given
    from app.modules.physics.ask import asked_dimensions, asked_phrases, asked_unit
    from app.modules.physics.bodies import SCHOOL_GRAVITY, names_body_without_school_gravity
    from app.modules.physics.catalog import formula_spec
    from app.modules.physics.counted import accounts_for_counted_items

    params = intent.physics_params or {}
    if intent.kind == "suvat":
        phrases = asked_phrases(request.text)
        displacement = (
            bool(phrases and phrases[0] == "displacement")
            if intent.physics_op == "suvat_distance"
            else "displacement" in request.text.lower()
        )
        params = {**params, "distance_path": float(not displacement)}
        intent = intent.model_copy(
            update={
                "physics_params": params,
                "physics_units": {**(intent.physics_units or {}), "distance_path": ""},
            }
        )
    if any(value < 0 for key, value in params.items() if key in {"m", "m1", "m2"}):
        return None
    spec = formula_spec(intent.physics_op or "")
    uses_g = spec is not None and _selection_uses_gravity(spec, params)
    # "On Jupiter" with no g written: Earth's school value would answer another planet.
    # Only a selection that actually multiplies by g. Horizontal Bernoulli declares
    # g for its height variant and does not use it.
    if (
        uses_g
        and stated_gravity(request.text) is None
        and names_body_without_school_gravity(request.text.lower())
    ):
        return None
    # Moon and Mars have a school g. A solver that would otherwise fill Earth's
    # must use that body's value when the question never wrote g.
    if uses_g and "g" not in params:
        detected = detect_gravity(request.text)
        if detected != SCHOOL_GRAVITY["earth"]:
            params = {**params, "g": detected}
            units = {**(intent.physics_units or {}), "g": "m/s^2"}
            intent = intent.model_copy(update={"physics_params": params, "physics_units": units})
    if competing_given(intent, request.text) is not None:
        return None
    if not accounts_for_counted_items(intent, request.text):
        # "Two 5 kg blocks", "two resistors, each 10 Ω": one value for several items.
        return None
    asked = asked_dimensions(request.text)
    unit = asked_unit(request.text)
    if request.projectile_ops:
        if intent.kind != "projectile":
            return None
        return PhysicsIntent.model_validate(
            {
                **intent.model_dump(),
                "physics_op": request.projectile_ops[0],
                "requested_ops": list(request.projectile_ops),
                "asked": asked,
                "asked_unit": unit,
            }
        )
    return intent.model_copy(update={"asked": asked, "asked_unit": unit})

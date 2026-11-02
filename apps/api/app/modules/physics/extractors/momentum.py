"""Momentum extractors: collisions, impulse, centre of mass, p = mv."""

from __future__ import annotations

import re

from app.modules.physics.extractors.assignments import strip_param_assignments
from app.modules.physics.extractors.cues import (
    has_cue,
)
from app.modules.physics.extractors.stated_values import ordered_values
from app.modules.physics.extractors.unit_patterns import (
    DEGREE_WORD,
    MASS_UNITS,
    VELOCITY_UNIT_PATTERN,
)
from app.modules.physics.givens import Given, scan_givens
from app.modules.physics.schemas import PhysicsIntent
from app.services.text_match import has_equation

_MOMENTUM_CUES = (
    "center of mass",
    "centre of mass",
    "elastically",
    "inelastically",
    "stick together",
    "sticks together",
)

# "The stock has momentum, up 12 percent" and "a three-car collision" are
# English. These words mean mechanics beside a mass, a velocity or a force.
_MOMENTUM_CUE_RES: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"\A(?=.*\b(?:momentum|impulse|collisions?|collid(?:e|es|ed|ing)|recoil(?:s|ed)?)\b)"
        r"(?=.*\d\s*(?:kg|g|grams?|m/s|km/h|mph|cm/s|N|newtons?|N\s*[·*]?\s*s)(?![A-Za-z0-9/]))",
        re.IGNORECASE | re.DOTALL,
    ),
    # A bullet that embeds, a car that rear-ends another: a collision only
    # beside a speed. "Someone rear-ended my 1500 kg car" is an insurance claim.
    re.compile(
        r"\A(?=.*\b(?:embed(?:s|ded)?|lodge[sd]?|rear[- ]ends?|lock(?:s|ed)?\s+bumpers)\b)"
        r"(?=.*\d\s*(?:m/s|km/h|mph|cm/s)(?![A-Za-z0-9/]))",
        re.IGNORECASE | re.DOTALL,
    ),
    # A body at rest that bursts into pieces of stated mass.
    re.compile(
        r"\A(?=.*\b(?:explodes?|exploded|breaks?\s+apart|splits?\s+into|blows?\s+apart)\b)"
        r"(?=.*\b(?:at\s+rest|stationary|from\s+rest)\b)"
        r"(?=.*\d\s*(?:kg|g|grams?)(?![A-Za-z0-9/]))(?=.*\d\s*(?:m/s|km/h)(?![A-Za-z0-9/]))",
        re.IGNORECASE | re.DOTALL,
    ),
)

_LANDING_TARGET = r"ground|floor|water|sea|surface|deck|earth|soil|sand|roof"

_COLLISION_SUBJECT_RE = re.compile(
    # Not "recoil": a gun's recoil is two bodies pushing apart, and a ball
    # that recoils off another has already said "hits" or "collides".
    r"\bcollision\b|\bcollides?\b|\bcolliding\b"
    # "A golf ball is hit at 40 m/s" is a launch: the passive is the club's
    # stroke, not two bodies meeting.
    rf"|(?<!\bis )(?<!\bwas )(?<!\bgets )\bhits?\b(?!\s+the\s+(?:{_LANDING_TARGET})\b)"
    rf"|(?<!\bis )(?<!\bwas )\bstrikes?\b(?!\s+the\s+(?:{_LANDING_TARGET})\b)"
    r"|sticks? together|stuck together"
    r"|\bembed(?:s|ded)?\b|\blodge[sd]?\b|\brear[- ]ends?\b"
    r"|\b(?:crash(?:es|ed)?|slams?|slammed|runs?|ran)\s+into\b",
    re.IGNORECASE,
)

_TWO_DIMENSIONAL_RE = re.compile(
    r"\b2-?d\b|\btwo[- ]dimensional\b|\bdeflect(?:s|ed|ion)?\b"
    r"|\bat an angle\b|\bglancing\b|\boblique\b"
    rf"|\d\s*{DEGREE_WORD}",
    re.IGNORECASE,
)

_ELASTIC_RE = re.compile(r"\belastic")

_INELASTIC_RE = re.compile(
    r"\binelastic|sticks? together|stuck together|\b(?:sticks?|stuck|sticking)\s+to\b|"
    r"\bcoupled?\b|\bembed(?:s|ded)?\b|\block(?:s|ed)? together\b"
    r"|\block(?:s|ed)?\s+bumpers\b|\blodge[sd]?\b|\bmoves?\s+off\s+together\b"
)

_MOMENTUM_TIME_UNITS = r"milliseconds?|ms|seconds?|secs?|sec|s|minutes?|mins?|min|hours?|hrs?|hr|h"

# The second speed points back the way the body came: "hits a wall at 10 m/s
# and rebounds at 8 m/s" is +10 then -8. Read as two forward speeds, the
# impulse came out -0.4 N·s instead of 3.6 N·s.
_REVERSAL_RE = re.compile(
    r"\b(?:rebound(?:s|ed|ing)?|bounc(?:es|ed|ing|e)\s+(?:back|off)|reverses?|reversed"
    r"|opposite\s+direction|comes?\s+back|returns?\s+at|back\s+at)\b",
    re.IGNORECASE,
)


_EXPLODES_RE = re.compile(
    r"\b(?:explodes?|exploded|bursts?|blows?\s+apart|flies\s+apart"
    r"|(?:breaks?|splits?)\s+(?:apart|up|in\s+two|into))\b",
    re.IGNORECASE,
)
_STARTS_AT_REST_RE = re.compile(
    r"\bat rest\b|\bstationary\b|\binitially still\b|\bfrom rest\b", re.IGNORECASE
)
_MASS_DIMENSION = "[mass]^1"
_SPEED_DIMENSION = "[length]^1 * [time]^-1"
_SENTENCE_BREAK_RE = re.compile(r"[.?!;](?:\s|$)")


def _same_mass(left: Given, right: Given) -> bool:
    return left.si is not None and right.si is not None and abs(left.si - right.si) < 1e-12


def _sentence_start(text: str, at: int) -> int:
    return max((match.end() for match in _SENTENCE_BREAK_RE.finditer(text, 0, at)), default=0)


def _explosion_intent(cleaned: str) -> PhysicsIntent | None:
    """A body at rest bursts into two pieces; one piece's speed gives the other's.

    "A 6 kg shell at rest explodes into two pieces, 2 kg and 4 kg. The 2 kg
    piece flies off at 30 m/s": the moving piece is the mass written just
    before the speed, and the other piece is the other mass the shell breaks
    into. The pieces are the two masses after the burst; a stated whole must
    be their sum. Any other mass, a second speed, or a moving piece that is
    neither declines.
    """
    burst = _EXPLODES_RE.search(cleaned)
    if burst is None or not _STARTS_AT_REST_RE.search(cleaned, 0, burst.start()):
        return None
    from app.modules.physics.ask import ask_clause

    clause = ask_clause(cleaned)
    ask_start = cleaned.rfind(clause) if clause else len(cleaned)
    givens = [given for given in scan_givens(cleaned) if given.dimension is not None]
    masses = [given for given in givens if given.dimension == _MASS_DIMENSION]
    speeds = [given for given in givens if given.dimension == _SPEED_DIMENSION]
    if len(speeds) != 1 or len(givens) != len(masses) + 1 or speeds[0].start > ask_start:
        return None
    before = [mass for mass in masses if mass.start < burst.start()]
    after = [mass for mass in masses if mass.start > burst.end()]
    if len(before) > 1 or len(before) + len(after) != len(masses):
        return None
    burst_end = _SENTENCE_BREAK_RE.search(cleaned, burst.end())
    pieces = [mass for mass in after if burst_end is None or mass.start < burst_end.start()]
    if len(pieces) != 2:
        return None
    speed = speeds[0]
    named = [
        mass for mass in after if _sentence_start(cleaned, speed.start) <= mass.start < speed.start
    ]
    moving_piece = named[-1] if named else None
    if moving_piece is None or not any(_same_mass(moving_piece, piece) for piece in pieces):
        return None
    moving = next(piece for piece in pieces if _same_mass(moving_piece, piece))
    other = next(piece for piece in pieces if piece is not moving)
    for mass in after:
        if mass is moving_piece or mass in pieces:
            continue
        # A later mention names a piece; in the ask it must be the other one.
        if mass.start >= ask_start:
            if not _same_mass(mass, other) or _same_mass(mass, moving):
                return None
        elif not (_same_mass(mass, moving) or _same_mass(mass, other)):
            return None
    params = {"m_moving": moving.value, "m_other": other.value, "v_moving": speed.value}
    units = {"m_moving": moving.unit, "m_other": other.unit, "v_moving": speed.unit}
    if before:
        params["m_total"] = before[0].value
        units["m_total"] = before[0].unit
    return PhysicsIntent(
        kind="momentum",
        physics_op="explosion_speed",
        physics_params=params,
        physics_units=units,
        operation="solve",
    )


def _extract_momentum_intent(cleaned: str) -> PhysicsIntent | None:
    lower = cleaned.lower()
    if not has_cue(lower, _MOMENTUM_CUES, _MOMENTUM_CUE_RES):
        return None
    if has_equation(strip_param_assignments(cleaned)):
        return None
    if _EXPLODES_RE.search(cleaned):
        return _explosion_intent(cleaned)

    masses = ordered_values(cleaned, MASS_UNITS)
    velocities = ordered_values(cleaned, VELOCITY_UNIT_PATTERN)

    # --- Centre of mass: x_cm = sum(m_i x_i) / sum(m_i) ---------------
    if "center of mass" in lower or "centre of mass" in lower:
        positions = ordered_values(cleaned, r"km|cm|mm|m|ft|yd|in|mi")
        if len(masses) == 3 and len(positions) == 3:
            return PhysicsIntent(
                kind="momentum",
                physics_op="center_of_mass_three",
                physics_params={
                    "m1": masses[0][0],
                    "m2": masses[1][0],
                    "m3": masses[2][0],
                    "x1": positions[0][0],
                    "x2": positions[1][0],
                    "x3": positions[2][0],
                },
                physics_units={
                    "m1": masses[0][1] or "kg",
                    "m2": masses[1][1] or "kg",
                    "m3": masses[2][1] or "kg",
                    "x1": positions[0][1] or "m",
                    "x2": positions[1][1] or "m",
                    "x3": positions[2][1] or "m",
                },
                operation="solve",
            )
        if len(masses) != 2 or len(positions) != 2:
            # Two and three stated point masses are closed. A fourth mass or a
            # continuous distribution is a different shape and must not be truncated.
            return None
        return PhysicsIntent(
            kind="momentum",
            physics_op="center_of_mass",
            physics_params={
                "m1": masses[0][0],
                "m2": masses[1][0],
                "x1": positions[0][0],
                "x2": positions[1][0],
            },
            physics_units={
                "m1": masses[0][1] or "kg",
                "m2": masses[1][1] or "kg",
                "x1": positions[0][1] or "m",
                "x2": positions[1][1] or "m",
            },
            operation="solve",
        )

    is_collision = (
        _COLLISION_SUBJECT_RE.search(cleaned) is not None or _INELASTIC_RE.search(lower) is not None
    )

    # --- 1D collision: two masses, at least one velocity ---
    if is_collision and len(masses) >= 2:
        # Only 1D conservation is implemented. Handing back the 1D number for a
        # 2D question is the same defect as the projectile answer it replaces,
        # just less obvious — the arithmetic is right for a problem nobody asked.
        if _TWO_DIMENSIONAL_RE.search(cleaned):
            return None
        elastic = _ELASTIC_RE.search(lower) is not None and not _INELASTIC_RE.search(lower)
        inelastic = _INELASTIC_RE.search(lower) is not None
        # Refuse rather than guess. Elastic and inelastic give genuinely
        # different answers from identical inputs, so an unstated collision type
        # would produce a confidently wrong number — the same failure mode the
        # tension guard closes off.
        if not elastic and not inelastic:
            return None
        m1, m1_unit = masses[0]
        m2, m2_unit = masses[1]
        v1, v1_unit = velocities[0] if velocities else (0.0, "m/s")
        # "hits a ball at rest" leaves v2 unwritten; "at rest" means zero.
        v2, v2_unit = velocities[1] if len(velocities) > 1 else (0.0, "m/s")
        return PhysicsIntent(
            kind="momentum",
            physics_op="final_velocity",
            physics_params={
                "m1": m1,
                "m2": m2,
                "v1": v1,
                "v2": v2,
                "elastic": 1.0 if elastic else 0.0,
            },
            physics_units={
                "m1": m1_unit or "kg",
                "m2": m2_unit or "kg",
                "v1": v1_unit or "m/s",
                "v2": v2_unit or "m/s",
                "elastic": "",
            },
            operation="solve",
        )

    # --- Impulse: J = F dt, or J = m (v2 - v1) ---
    if "impulse" in lower:
        forces = ordered_values(cleaned, r"N")
        times = ordered_values(cleaned, _MOMENTUM_TIME_UNITS)
        if forces and times:
            f, f_unit = forces[0]
            dt, dt_unit = times[0]
            return PhysicsIntent(
                kind="momentum",
                physics_op="impulse",
                physics_params={"F": f, "dt": dt},
                physics_units={"F": f_unit or "N", "dt": dt_unit or "s"},
                operation="solve",
            )
        if masses and len(velocities) >= 2:
            m, m_unit = masses[0]
            v1, v1_unit = velocities[0]
            v2, v2_unit = velocities[1]
            if _REVERSAL_RE.search(cleaned) and v1 * v2 > 0:
                v2 = -v2
            return PhysicsIntent(
                kind="momentum",
                physics_op="impulse",
                physics_params={"m": m, "v1": v1, "v2": v2},
                physics_units={"m": m_unit or "kg", "v1": v1_unit or "m/s", "v2": v2_unit or "m/s"},
                operation="solve",
            )
        return None

    # --- Plain momentum: p = m v ---
    if "momentum" in lower and masses and velocities:
        m, m_unit = masses[0]
        v, v_unit = velocities[0]
        return PhysicsIntent(
            kind="momentum",
            physics_op="momentum",
            physics_params={"m": m, "v": v},
            physics_units={"m": m_unit or "kg", "v": v_unit or "m/s"},
            operation="solve",
        )

    return None

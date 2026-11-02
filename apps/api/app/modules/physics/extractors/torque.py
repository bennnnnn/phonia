"""Torque and the balance of moments about a pivot."""

from __future__ import annotations

import re

from app.modules.physics.extractors.angles import INCLINE_ANGLE_RE
from app.modules.physics.extractors.assignments import strip_param_assignments
from app.modules.physics.extractors.cues import (
    has_cue,
)
from app.modules.physics.extractors.stated_values import positioned_values
from app.modules.physics.extractors.unit_patterns import LENGTH_UNIT_PATTERN, MASS_UNITS, NUMBER
from app.modules.physics.schemas import PhysicsIntent
from app.services.text_match import has_equation

_TORQUE_CUES = (
    "torque",
    "pivot",
    "fulcrum",
    "lever arm",
    "see-saw",
    "seesaw",
)

_PIVOT_WORDS = r"pivot|fulcrum|lever|see-?saw|balance"

_TORQUE_CUE_RES: tuple[re.Pattern[str], ...] = (
    re.compile(rf"\bmoments?\b.{{0,80}}?(?:{_PIVOT_WORDS})", re.IGNORECASE),
    re.compile(rf"(?:{_PIVOT_WORDS}).{{0,80}}?\bmoments?\b", re.IGNORECASE),
    re.compile(r"\blever\b", re.IGNORECASE),
)

_TORQUE_UNSUPPORTED = ("moment of inertia", "angular momentum", "rotational inertia")

_TORQUE_VALUE_RE = re.compile(
    rf"({NUMBER})\s*(?:N|newtons?)\s*(?:[·*]\s*)?(?:m|met(?:er|re)s?)(?![A-Za-z0-9/^])",
    re.IGNORECASE,
)

_PLAIN_FORCE_RE = re.compile(
    rf"({NUMBER})\s*(N|newtons?)(?!\s*(?:[·*]\s*)?(?:m|met(?:er|re)s?)\b)",
    re.IGNORECASE,
)


def _extract_torque_intent(cleaned: str) -> PhysicsIntent | None:
    lower = cleaned.lower()
    if not has_cue(lower, _TORQUE_CUES, _TORQUE_CUE_RES):
        return None
    # τ = μB sinθ is a catalog law. A lever reading of "torque" would guess.
    if "magnetic moment" in lower:
        return None
    if any(word in lower for word in _TORQUE_UNSUPPORTED):
        return None
    if has_equation(strip_param_assignments(cleaned)):
        return None

    torque_values = [
        (match.start(), float(match.group(1))) for match in _TORQUE_VALUE_RE.finditer(cleaned)
    ]
    if len(torque_values) >= 2 and (
        "clockwise" in lower or "counterclockwise" in lower or "anticlockwise" in lower
    ):
        direction_marks = [
            (match.start(), -1.0 if match.group(1).lower() == "clockwise" else 1.0)
            for match in re.finditer(
                r"\b(clockwise|counterclockwise|anticlockwise)\b", cleaned, re.I
            )
        ]
        if not direction_marks:
            return None
        clause_spans: list[tuple[int, int, float]] = []
        clause_start = 0
        for separator in re.finditer(r"\b(?:against|versus|vs\.?)\b", cleaned, re.I):
            clause = cleaned[clause_start : separator.start()]
            direction = re.search(r"\b(clockwise|counterclockwise|anticlockwise)\b", clause, re.I)
            if direction is not None:
                clause_spans.append(
                    (
                        clause_start,
                        separator.start(),
                        -1.0 if direction.group(1).lower() == "clockwise" else 1.0,
                    )
                )
            clause_start = separator.end()
        final_clause = cleaned[clause_start:]
        final_direction = re.search(
            r"\b(clockwise|counterclockwise|anticlockwise)\b", final_clause, re.I
        )
        if final_direction is not None:
            clause_spans.append(
                (
                    clause_start,
                    len(cleaned),
                    -1.0 if final_direction.group(1).lower() == "clockwise" else 1.0,
                )
            )
        signed: list[float] = []
        for position, value in torque_values:
            clause_sign = next(
                (sign for start, end, sign in clause_spans if start <= position < end),
                None,
            )
            if clause_sign is None:
                _, clause_sign = min(direction_marks, key=lambda item: abs(item[0] - position))
            signed.append(clause_sign * value)
        return PhysicsIntent(
            kind="torque",
            physics_op="net_torque",
            physics_params={f"tau{index}": value for index, value in enumerate(signed, start=1)},
            physics_units={f"tau{index}": "N*m" for index in range(1, len(signed) + 1)},
            operation="solve",
        )

    plain_forces = [
        (match.start(), float(match.group(1)), match.group(2))
        for match in _PLAIN_FORCE_RE.finditer(cleaned)
    ]
    if (
        len(torque_values) == 1
        and len(plain_forces) == 1
        and re.search(
            r"\b(?:lever arm|perpendicular distance|distance from (?:the )?pivot)\b", cleaned, re.I
        )
    ):
        return PhysicsIntent(
            kind="torque",
            physics_op="lever_arm",
            physics_params={"tau": torque_values[0][1], "F": plain_forces[0][1]},
            physics_units={"tau": "N*m", "F": plain_forces[0][2] or "N"},
            operation="solve",
        )

    placed_masses = positioned_values(cleaned, MASS_UNITS)
    placed_distances = positioned_values(cleaned, LENGTH_UNIT_PATTERN)
    balancing = "balance" in lower or "see-saw" in lower or "seesaw" in lower
    if balancing and len(placed_masses) >= 2 and placed_distances:
        d_pos, d_val, d_unit = placed_distances[0]
        preceding = [mass for mass in placed_masses if mass[0] < d_pos]
        known = preceding[-1] if preceding else placed_masses[0]
        others = [mass for mass in placed_masses if mass[0] != known[0]]
        if not others:
            return None
        unknown = others[0]
        return PhysicsIntent(
            kind="torque",
            physics_op="moment_balance",
            physics_params={"m1": known[1], "d1": d_val, "m2": unknown[1]},
            physics_units={
                "m1": known[2] or "kg",
                "d1": d_unit or "m",
                "m2": unknown[2] or "kg",
            },
            operation="solve",
        )

    placed_forces = positioned_values(cleaned, r"N")
    placed_distances = positioned_values(cleaned, LENGTH_UNIT_PATTERN)
    if not placed_forces or not placed_distances:
        return None

    # Two forces and one distance is the classic balance question. Pair the
    # distance with the force it actually belongs to rather than taking them in
    # written order: "the distance for a 10 N force to balance a 5 N force at
    # 2 m" mentions the 10 N first, but the 2 m is the *5 N* force's arm.
    # Written order answers 4 m there; the true answer is 1 m.
    if balancing and len(placed_forces) >= 2:
        d_pos, d_val, d_unit = placed_distances[0]
        preceding = [f for f in placed_forces if f[0] < d_pos]
        # The force nearest *before* the distance owns it; the remaining force
        # is the one whose arm we are solving for.
        known = preceding[-1] if preceding else placed_forces[0]
        others = [f for f in placed_forces if f[0] != known[0]]
        if not others:
            return None
        unknown = others[0]
        return PhysicsIntent(
            kind="torque",
            physics_op="moment_balance",
            physics_params={"F1": known[1], "d1": d_val, "F2": unknown[1]},
            physics_units={
                "F1": known[2] or "N",
                "d1": d_unit or "m",
                "F2": unknown[2] or "N",
            },
            operation="solve",
        )
    # One known force and two stated arms asks for the balancing force rather
    # than another arm. The known force owns the first arm stated after it;
    # this also handles question-first wording where the unknown arm comes
    # before the known force ("force at 4 m balances 50 N at 2 m").
    if balancing and len(placed_forces) == 1 and len(placed_distances) >= 2:
        known_force = placed_forces[0]
        following = [distance for distance in placed_distances if distance[0] > known_force[0]]
        known_distance = (
            min(following, key=lambda distance: distance[0])
            if following
            else min(
                placed_distances,
                key=lambda distance: abs(distance[0] - known_force[0]),
            )
        )
        unknown_distances = [
            distance for distance in placed_distances if distance[0] != known_distance[0]
        ]
        if not unknown_distances:
            return None
        unknown_distance = unknown_distances[0]
        return PhysicsIntent(
            kind="torque",
            physics_op="moment_balance",
            physics_params={
                "F1": known_force[1],
                "d1": known_distance[1],
                "d2": unknown_distance[1],
            },
            physics_units={
                "F1": known_force[2] or "N",
                "d1": known_distance[2] or "m",
                "d2": unknown_distance[2] or "m",
            },
            operation="solve",
        )
    forces = [(f[1], f[2]) for f in placed_forces]
    distances = [(d[1], d[2]) for d in placed_distances]

    angle_match = INCLINE_ANGLE_RE.search(cleaned)
    params: dict[str, float] = {"F": forces[0][0], "d": distances[0][0]}
    units: dict[str, str] = {"F": forces[0][1] or "N", "d": distances[0][1] or "m"}
    if angle_match:
        params["angle"] = float(angle_match.group(1))
        units["angle"] = "rad" if re.search(r"\b(?:rad|radians)\b", lower) else "deg"
    return PhysicsIntent(
        kind="torque",
        physics_op="torque",
        physics_params=params,
        physics_units=units,
        operation="solve",
    )

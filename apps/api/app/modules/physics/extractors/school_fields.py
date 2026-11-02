"""Closed Gauss and Faraday templates."""

from __future__ import annotations

import re

from app.modules.physics.extractors.school_common import (
    _SECOND,
    _WEBER,
    _intent,
    _one,
    _turns,
)
from app.modules.physics.extractors.stated_values import ordered_values
from app.modules.physics.extractors.unit_patterns import LENGTH_UNIT_PATTERN, NUMBER, TESLA_PATTERN
from app.modules.physics.schemas import PhysicsIntent
from app.services.text_match import word_index


def extract_gauss(text: str, lower: str) -> PhysicsIntent | None:
    # ``gaussian`` contains the letters but is not Gauss's law.
    if word_index(lower, "gauss") == -1:
        return None
    charge = _one(text, r"uC|µC|C|microcoulombs?|coulombs?")
    radius = _one(text, LENGTH_UNIT_PATTERN, ("radius", "shell"), require_keyword=True)
    # "at" is not a distance cue: it sits next to almost every quantity.
    distance = _one(
        text,
        LENGTH_UNIT_PATTERN,
        ("distance", "from the center"),
        require_keyword=True,
    )
    if "infinite line" in lower or "line charge" in lower:
        density = _one(text, r"C/m|uC/m|µC/m")
        if density is None or distance is None:
            return None
        return _intent(
            "magnetism",
            "gauss_line",
            {"lambda_line": density[0], "r": distance[0]},
            {"lambda_line": density[1] or "C/m", "r": distance[1] or "m"},
        )
    plane = ("infinite plane", "infinite sheet", "nonconducting sheet")
    if any(phrase in lower for phrase in plane):
        density = _one(text, r"C/m\^?2|C/m2|uC/m\^?2")
        if density is None:
            return None
        return _intent(
            "magnetism",
            "gauss_plane",
            {"sigma_charge": density[0]},
            {"sigma_charge": density[1] or "C/m^2"},
        )
    if "inside" in lower and any(word in lower for word in ("shell", "hollow")):
        if charge is None or radius is None or distance is None:
            return None
        return _intent(
            "magnetism",
            "gauss_inside_shell",
            {"Q": charge[0], "r": distance[0], "radius_body": radius[0]},
            {
                "Q": charge[1] or "C",
                "r": distance[1] or "m",
                "radius_body": radius[1] or "m",
            },
        )
    if "inside" in lower and "uniform" in lower:
        if charge is None or radius is None or distance is None:
            return None
        return _intent(
            "magnetism",
            "gauss_inside_sphere",
            {"Q": charge[0], "r": distance[0], "radius_body": radius[0]},
            {
                "Q": charge[1] or "C",
                "r": distance[1] or "m",
                "radius_body": radius[1] or "m",
            },
        )
    if "outside" not in lower and "surface" not in lower:
        return None
    # A point charge has no shell radius. The distance from the center is r.
    point = distance or radius
    if charge is None or point is None:
        return None
    return _intent(
        "magnetism",
        "gauss_outside",
        {"Q": abs(charge[0]), "r": point[0]},
        {"Q": charge[1] or "C", "r": point[1] or "m"},
    )


def extract_faraday(text: str, lower: str) -> PhysicsIntent | None:
    if "faraday" not in lower and "induced emf" not in lower and "flux changes" not in lower:
        return None
    turns = _turns(text, lower)
    seconds = _one(text, _SECOND, ("in", "over", "during"), require_keyword=True)
    if turns is None or seconds is None:
        return None
    flux = _one(text, _WEBER)
    if flux is not None:
        return _intent(
            "magnetism",
            "faraday_emf",
            {"turns": turns, "delta_flux": flux[0], "dt": seconds[0]},
            {"turns": "", "delta_flux": flux[1] or "Wb", "dt": seconds[1] or "s"},
        )
    area = _one(text, r"m\^?2|cm\^?2")
    fields = ordered_values(text, TESLA_PATTERN)
    if len(fields) == 1:
        # "drops from 0.5 T to 0": the second reading shares the first's unit.
        to_bare = re.search(
            rf"\bfrom\s+{NUMBER}\s*(?P<unit>{TESLA_PATTERN})\s+to\s+(?P<to>{NUMBER})"
            r"(?![\d.])",
            text,
        )
        if to_bare is not None:
            fields = [fields[0], (float(to_bare.group("to")), to_bare.group("unit"))]
    if area is None or len(fields) != 2:
        return None
    return _intent(
        "magnetism",
        "faraday_emf",
        {
            "turns": turns,
            "area": area[0],
            "b1": fields[0][0],
            "b2": fields[1][0],
            "dt": seconds[0],
        },
        {
            "turns": "",
            "area": area[1] or "m^2",
            "b1": fields[0][1] or "T",
            "b2": fields[1][1] or "T",
            "dt": seconds[1] or "s",
        },
    )

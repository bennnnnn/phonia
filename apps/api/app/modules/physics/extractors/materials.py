"""Materials extractors: stress, strain, Young's modulus."""

from __future__ import annotations

import re

from app.modules.physics.extractors.assignments import strip_param_assignments
from app.modules.physics.extractors.cues import (
    has_cue,
)
from app.modules.physics.extractors.fluid_readings import _PRESSURE_PATTERN, AREA_PATTERN
from app.modules.physics.extractors.stated_values import (
    find_value_with_specific_unit,
    ordered_values,
)
from app.modules.physics.extractors.unit_patterns import LENGTH_UNIT_PATTERN, NUMBER
from app.modules.physics.schemas import PhysicsIntent
from app.services.text_match import has_equation

_MATERIALS_CUES = ("young's modulus", "youngs modulus", "young modulus", "tensile stress")

_MATERIALS_CUE_RES: tuple[re.Pattern[str], ...] = (
    re.compile(
        rf"\bstress\b.{{0,80}}?\d\s*(?:N|newtons?|{_PRESSURE_PATTERN})(?![A-Za-z0-9])",
        re.IGNORECASE,
    ),
    re.compile(
        rf"\d\s*(?:N|newtons?|{_PRESSURE_PATTERN})(?![A-Za-z0-9]).{{0,80}}?\bstress\b",
        re.IGNORECASE,
    ),
    re.compile(
        rf"\bstrain\b.{{0,80}}?\d\s*(?:{LENGTH_UNIT_PATTERN})(?![A-Za-z0-9])", re.IGNORECASE
    ),
    re.compile(
        rf"\d\s*(?:{LENGTH_UNIT_PATTERN})(?![A-Za-z0-9]).{{0,80}}?\bstrain\b", re.IGNORECASE
    ),
)


def _extract_materials_intent(cleaned: str) -> PhysicsIntent | None:
    lower = cleaned.lower()
    if not has_cue(lower, _MATERIALS_CUES, _MATERIALS_CUE_RES):
        return None
    if has_equation(strip_param_assignments(cleaned)):
        return None

    stress = find_value_with_specific_unit(cleaned, _PRESSURE_PATTERN)
    strain_match = re.search(rf"strain\s*(?:of|is|=)?\s*({NUMBER})", cleaned, re.IGNORECASE)
    force = find_value_with_specific_unit(cleaned, r"N|newtons?", ("force", "load"))
    area = find_value_with_specific_unit(cleaned, AREA_PATTERN)
    original = find_value_with_specific_unit(
        cleaned, LENGTH_UNIT_PATTERN, ("wire", "rod", "bar", "long", "length", "original")
    )
    extension = find_value_with_specific_unit(
        cleaned,
        LENGTH_UNIT_PATTERN,
        ("extends", "extension", "stretches", "lengthens", "elongat"),
    )

    if "modulus" in lower:
        if "shear modulus" in lower or "bulk modulus" in lower or "poisson" in lower:
            return None
        if stress is None or strain_match is None:
            return None
        return PhysicsIntent(
            kind="materials",
            physics_op="youngs_modulus",
            physics_params={"sigma": stress[0], "strain": float(strain_match.group(1))},
            physics_units={"sigma": stress[1] or "Pa", "strain": ""},
            operation="solve",
        )

    if "strain" in lower:
        # Two distinct lengths, not one read twice. "a wire extends by 4 mm"
        # matches both keyword sets on the same value, which would give a
        # strain of exactly 1 for any wire.
        lengths = ordered_values(cleaned, LENGTH_UNIT_PATTERN)
        if len(lengths) == 2:
            original, extension = lengths
        if original is None or extension is None or len(lengths) < 2:
            return None
        if original[0] == extension[0]:
            return None
        return PhysicsIntent(
            kind="materials",
            physics_op="strain",
            physics_params={"L0": original[0], "dL": extension[0]},
            physics_units={"L0": original[1] or "m", "dL": extension[1] or "m"},
            operation="solve",
        )

    if force is not None and area is not None:
        return PhysicsIntent(
            kind="materials",
            physics_op="stress",
            physics_params={"F": force[0], "area": area[0]},
            physics_units={"F": force[1] or "N", "area": area[1] or "m^2"},
            operation="solve",
        )
    return None

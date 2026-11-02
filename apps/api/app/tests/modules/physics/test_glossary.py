"""Every physics given has a meaning, and the line under Given names them plainly."""

from __future__ import annotations

import re

import pytest

from app.modules.physics.catalog import CATALOG
from app.modules.physics.glossary import given_meaning
from app.services.workout import where_line


def test_every_visible_catalog_variable_has_a_meaning() -> None:
    # A new law's variable needs an entry: without one the where line silently skips it.
    missing = sorted(
        {
            f"{spec.id}:{variable.name}"
            for spec in CATALOG.values()
            for variable in spec.variables
            if variable.visible and not given_meaning(spec.id, spec.kind, variable.name)
        }
    )
    assert missing == []


def test_meanings_are_words_not_identifiers() -> None:
    for spec in CATALOG.values():
        for variable in (v for v in spec.variables if v.visible):
            meaning = given_meaning(spec.id, spec.kind, variable.name) or ""
            assert re.fullmatch(r"[A-Za-z][A-Za-z' -]*", meaning), (spec.id, variable.name)


@pytest.mark.parametrize(
    ("operation", "name", "meaning"),
    [
        ("range", "angle", "launch angle"),
        ("range", "h0", "launch height"),
        ("incline_acceleration", "angle", "angle of the incline"),
        ("snell_refraction_angle", "angle", "angle of incidence"),
        ("torque", "angle", "angle between the force and the arm"),
        ("torque", "d", "distance from the pivot"),
        ("suvat_distance", "v", "final velocity"),
        ("rate_distance", "v", "speed"),
        ("electric_force", "r", "separation"),
        ("centripetal_force", "r", "radius"),
        ("double_slit_fringe_spacing", "L", "distance to the screen"),
        ("carnot_efficiency", "temp", "hot reservoir temperature"),
        ("impulse", "v2", "final velocity"),
    ],
)
def test_a_name_reads_as_its_law_means_it(operation: str, name: str, meaning: str) -> None:
    spec = CATALOG[operation]
    assert given_meaning(operation, spec.kind, name) == meaning


@pytest.mark.parametrize(
    ("definitions", "line"),
    [
        (
            [("v_0", "initial speed"), (r"\theta", "launch angle")],
            r"where $v_0$ = initial speed, $\theta$ = launch angle",
        ),
        # The same meaning is named once, in the plural; semicolons then keep the groups apart.
        (
            [("R_1", "resistance"), ("R_2", "resistance"), ("R_3", "resistance")],
            "where $R_1$, $R_2$, $R_3$ = resistances",
        ),
        (
            [("m", "mass"), ("v_1", "velocity"), ("v_2", "velocity")],
            "where $m$ = mass; $v_1$, $v_2$ = velocities",
        ),
        (
            [("n_1", "refractive index"), ("n_2", "refractive index")],
            "where $n_1$, $n_2$ = refractive indices",
        ),
        ([("m_1", "mass"), ("m_2", "mass")], "where $m_1$, $m_2$ = masses"),
        # A given written twice (4 L, then 0.004 m³) is named once.
        ([("V_1", "initial volume"), ("V_1", "initial volume")], "where $V_1$ = initial volume"),
        ([], None),
    ],
)
def test_where_line(definitions: list[tuple[str, str]], line: str | None) -> None:
    assert where_line(definitions) == line

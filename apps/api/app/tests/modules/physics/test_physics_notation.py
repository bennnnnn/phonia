"""Initial and final velocity are shown v_i and v_f wherever a law tells them apart."""

from __future__ import annotations

import re

import pytest

from app.core.config import Settings
from app.modules.physics.catalog import CATALOG, symbol_for
from app.modules.physics.direct import format_direct_physics_working
from app.modules.physics.notation import renamed_operations, shown
from app.modules.physics.reply_policy import PHYSICS_VELOCITY_NOTATION, physics_prompt_hints
from app.services.law_binding.spec import FormulaSpec
from app.tests.modules.physics.support import build_verified_physics_block, extract_physics_intent


@pytest.mark.parametrize(
    "operation, written, expected",
    [
        ("suvat_velocity", "v = u + at", "v_f = v_i + at"),
        ("suvat_acceleration", r"a = \frac{v - u}{t}", r"a = \frac{v_f - v_i}{t}"),
        ("suvat_distance", r"s = ut + \tfrac{1}{2}at^2", r"s = v_i t + \tfrac{1}{2}at^2"),
        ("suvat_distance", r"s = \frac{v^2 - u^2}{2a}", r"s = \frac{v_f^2 - v_i^2}{2a}"),
        ("suvat_distance", r"s = \int_0^t |u+a\tau|\,d\tau", r"s = \int_0^t |v_i+a\tau|\,d\tau"),
        ("suvat_time", r"t = \frac{2s}{u + v}", r"t = \frac{2s}{v_i + v_f}"),
        (
            "energy_speed_from_moving_start",
            r"\tfrac{1}{2}mv^2 = \tfrac{1}{2}mu^2 + mgh",
            r"\tfrac{1}{2}mv_f^2 = \tfrac{1}{2}mv_i^2 + mgh",
        ),
        ("impulse", "J = m(v_2 - v_1)", "J = m(v_f - v_i)"),
        (
            "work_energy",
            r"W_{net} = \frac{1}{2}m(v_2^2 - v_1^2)",
            r"W_{net} = \frac{1}{2}m(v_f^2 - v_i^2)",
        ),
        ("final_velocity", r"v_1',\ v_2'", r"v_{1f},\ v_{2f}"),
        (
            "final_velocity",
            r"m_1v_1 + m_2v_{2} = (m_1+m_2)v_f",
            r"m_1v_{1i} + m_2v_{2i} = (m_1+m_2)v_f",
        ),
        ("stopping_distance", r"d_b = \frac{v^2}{2a}", r"d_b = \frac{v_i^2}{2a}"),
        # Units, words and commands are not symbols.
        ("suvat_velocity", r"v = 14\,\mathrm{m/s}", r"v_f = 14\,\mathrm{m/s}"),
        ("suvat_velocity", r"v \text{ value}", r"v_f \text{ value}"),
        ("suvat_velocity", r"\varepsilon \vec{u}", r"\varepsilon \vec{v_i}"),
    ],
)
def test_shown_writes_initial_and_final_velocity(
    operation: str, written: str, expected: str
) -> None:
    assert shown(written, operation) == expected


@pytest.mark.parametrize(
    "operation, written",
    [
        # A plain speed has no start or end: v = d/t stays v.
        ("speed", r"v = \frac{d}{t}"),
        ("momentum", "p = mv"),
        # A lens's u and v are distances.
        ("mirror_focal_length", r"\frac{1}{f} = \frac{1}{u} + \frac{1}{v}"),
        ("range", r"R = \frac{v_0^2 \sin(2\theta)}{g}"),
        (None, "v = u + at"),
    ],
)
def test_shown_leaves_other_laws_as_written(operation: str | None, written: str) -> None:
    assert shown(written, operation) == written


def _catalog_latex(spec: FormulaSpec) -> list[str]:
    rows = [spec.base_latex or ""]
    for variant in spec.variants:
        rows.extend((variant.latex or "", *variant.lines, variant.result_symbol or ""))
    return [row for row in rows if row]


# A bare u or v, or a before/after v_1 or v_2: what the table renames.
_OLD_SYMBOL = re.compile(
    r"(?<![\\A-Za-z])(?:u|v)(?![A-Za-z_{])|v_(?:[12]|\{[12]\})(?![A-Za-z0-9}])"
)


@pytest.mark.parametrize("operation", sorted(renamed_operations()))
def test_every_renamed_law_shows_no_old_symbol(operation: str) -> None:
    """Each operation in the table is a catalog law, and nothing it shows keeps u or v."""
    spec = CATALOG[operation]
    rows = [shown(row, operation) for row in _catalog_latex(spec)]
    rows.append(shown(spec.result_symbol, operation))
    rows.extend(
        shown(symbol_for(spec, variable.name) or "", operation)
        for variable in spec.variables
        if variable.visible
    )
    assert [row for row in rows if _OLD_SYMBOL.search(row)] == []


@pytest.mark.parametrize(
    "question, rows",
    [
        (
            "A car started from rest and accelerated uniformly and reached a speed of 20m/s "
            "after 5 s. What is the acceleration?",
            [
                r"$v_i = 0\,\mathrm{m/s}$",
                r"$v_f = 20\,\mathrm{m/s}$",
                "where $v_i$ = initial velocity, $v_f$ = final velocity, $t$ = time",
                "$v_f = v_i + at$",
                r"$a = \frac{v_f - v_i}{t}$",
            ],
        ),
        (
            "A ball is thrown at 10 m/s and accelerates at 3 m/s^2 over 16 m. "
            "What is its final velocity?",
            ["**Required**  \n$v_f$", r"$v_f = \sqrt{v_i^2 + 2as}$", r"$v_f = 14\,\mathrm{m/s}$"],
        ),
    ],
)
def test_direct_reply_shows_v_i_and_v_f(question: str, rows: list[str]) -> None:
    intent = extract_physics_intent(question)
    assert intent is not None
    block = build_verified_physics_block(intent, Settings(math_tools_enabled=True))
    assert block is not None
    reply = format_direct_physics_working(block)
    assert reply is not None
    for row in rows:
        assert row in reply
    assert "$u" not in reply


def test_model_is_told_the_same_notation() -> None:
    assert PHYSICS_VELOCITY_NOTATION in physics_prompt_hints(short=False)
    assert "$v_f = v_i + at$" in PHYSICS_VELOCITY_NOTATION

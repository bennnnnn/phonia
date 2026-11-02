# ruff: noqa: RUF002 -- the point of these tests is superscripts and the times sign.
"""A unit's power reads and shows the same however it is typed: m/s^2, m/s², m/s2, m s-2.

"A 10 kg toy car accelerates at 2 m/s2" showed its Given as "a = 2 m/s2 × 1 = 2 m/s²"
(2026-10-29): the typed spelling was printed as written, so it looked like another unit
and earned a conversion by 1. "3 m s-2" was read as 3 metres and "3 m s⁻²" not at all.
"""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.modules.physics.display import plain_unit
from app.modules.physics.givens import scan_givens, unit_dimension
from app.modules.physics.numbers import normalize_physics_units
from app.services.symbolic_text import fold_numeric_superscripts
from app.tests.modules.physics.support import (
    build_verified_physics_block,
    extract_physics_intent,
    maybe_direct_physics_reply,
)

_SETTINGS = Settings(math_tools_enabled=True, mcp_tool_loop_enabled=True)


def _given(query: str) -> tuple[str, str]:
    """(canonical answer, the reply's Given section)."""
    intent = extract_physics_intent(query)
    assert intent is not None, query
    verified = build_verified_physics_block(intent, _SETTINGS)
    assert verified is not None, query
    reply = maybe_direct_physics_reply(verified, query)
    assert reply is not None and verified.canonical_answer is not None, query
    return verified.canonical_answer, reply.split("**Required**", 1)[0]


@pytest.mark.parametrize(
    "spelling",
    ["m/s2", "m/s^2", "m/s²", "m s-2", "m s^-2", "m s⁻²", "m·s⁻²"],
)
def test_an_acceleration_reads_and_shows_however_it_is_typed(spelling: str) -> None:
    answer, given = _given(
        f"A 10 kg toy car accelerates at 2 {spelling}. What net force acts on it?"
    )
    assert answer == "20 N"
    assert r"$a = 2\,\mathrm{m/s²}$" in given
    assert r"\times" not in given


@pytest.mark.parametrize("spelling", ["m s-1", "m s^-1", "m·s⁻¹"])
def test_a_speed_written_as_a_power_is_a_speed(spelling: str) -> None:
    answer, given = _given(f"A car travels 100 m at 20 {spelling}. How long does it take?")
    assert answer == "5 s"
    assert r"$v = 20\,\mathrm{m/s}$" in given


def test_a_real_conversion_still_shows_its_factor() -> None:
    _, given = _given("Find the force on a 500 g object with acceleration 2 m/s2.")
    assert r"$m = 500\,\mathrm{g} \times 0.001 = 0.5\,\mathrm{kg}$" in given


@pytest.mark.parametrize(
    ("written", "read"),
    [
        ("g = 9.8 m s-2", "g = 9.8 m/s^2"),
        ("at 3 m·s^-2 east", "at 3 m/s^2 east"),
        ("20 m s-1", "20 m/s"),
        # "ms" is milliseconds, and a range is not a power.
        ("after 5 ms-2 more", "after 5 ms-2 more"),
        ("between 2 m-3 m", "between 2 m-3 m"),
    ],
)
def test_a_product_of_powers_is_written_with_a_slash(written: str, read: str) -> None:
    assert normalize_physics_units(written) == read


@pytest.mark.parametrize(
    ("written", "folded"),
    [("s⁻²", "s^-2"), ("10⁻⁹", "10^-9"), ("x²", "x^2"), ("an e⁻ beam", "an e⁻ beam")],
)
def test_a_superscript_sign_belongs_to_its_power(written: str, folded: str) -> None:
    assert fold_numeric_superscripts(written) == folded


@pytest.mark.parametrize(
    ("text", "expression"),
    [
        ("g is 9.8 m s-2", "meter / second ** 2"),
        ("g = 9.8 m·s-2", "meter / second ** 2"),
        ("a speed of 10 m s-1", "meter / second"),
        ("10 m s⁻¹ east", "meter / second"),
        ("c = 4200 J·kg⁻¹·K⁻¹", "joule / kilogram / kelvin"),
        ("between 2 m-3 m", "meter"),
        ("an area of 4 m²", "meter ** 2"),
        ("a density of 800 kg/m³", "kilogram / meter ** 3"),
        ("a pressure of 200 N/m2", "pascal"),
        ("decays at 0.5 s⁻¹", "1 / second"),
    ],
)
def test_the_givens_scan_reads_a_power_however_it_is_typed(text: str, expression: str) -> None:
    given = scan_givens(text)[0]
    reading = unit_dimension(expression)
    assert reading is not None
    assert given.dimension == reading[0]


@pytest.mark.parametrize(
    ("unit", "shown"),
    [
        ("m/s2", "m/s²"),
        ("kg/m3", "kg/m³"),
        ("N/m2", "N/m²"),
        ("mm2", "mm²"),
        ("A m2", "A·m²"),
        # Not a unit the table reads, so its digit is not a power.
        ("H2", "H2"),
    ],
)
def test_a_power_typed_bare_shows_raised(unit: str, shown: str) -> None:
    assert plain_unit(unit) == shown

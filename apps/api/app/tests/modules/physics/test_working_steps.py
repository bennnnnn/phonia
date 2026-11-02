"""The working reaches the verified answer, and a given in another unit shows its factor."""

from __future__ import annotations

import pytest

from app.modules.physics.display import latex_factor
from app.modules.physics.solvers.si import si_factor
from app.modules.physics.working_steps import answer_parts, carried_to_answer


@pytest.mark.parametrize(
    ("rows", "answer", "carried"),
    [
        # Worked to the verified answer, which the last row states as verified.
        (
            [r"a = \frac{27.7778 - 0}{8}"],
            r"3.47\,\mathrm{m/s²}",
            [r"a = \frac{27.7778 - 0}{8}", r"a = \frac{27.7778}{8}", r"a = 3.47\,\mathrm{m/s²}"],
        ),
        # A size with a direction: the working keeps its sign.
        (
            [r"F = \frac{1000 \times (0 - 15)}{3}"],
            r"5000\,\mathrm{N}\ (\text{opposing the motion})",
            [
                r"F = \frac{1000 \times (0 - 15)}{3}",
                r"F = \frac{1000 \times (-15)}{3}",
                r"F = \frac{-15000}{3}",
                r"F = -5000\,\mathrm{N}",
            ],
        ),
        # Shown in eV: the SI value, then the answer, on one row.
        (
            [r"E = \frac{6.6261 \times 10^{-34} \times 299792458}{1.2 \times 10^{-6}}"],
            r"1.03\,\mathrm{eV}",
            [
                r"E = \frac{6.6261 \times 10^{-34} \times 299792458}{1.2 \times 10^{-6}}",
                r"E = \frac{1.98645 \times 10^{-25}}{1.2 \times 10^{-6}}",
                r"E = 1.65538 \times 10^{-19}\,\mathrm{J} = 1.03\,\mathrm{eV}",
            ],
        ),
        # A law in 1/R: the sum, then its reciprocal.
        (
            [r"\frac{1}{R_p} = \frac{1}{6} + \frac{1}{3}"],
            r"2\,\Omega",
            [
                r"\frac{1}{R_p} = \frac{1}{6} + \frac{1}{3}",
                r"\frac{1}{R_p} = 0.166667 + 0.333333",
                r"\frac{1}{R_p} = 0.5",
                r"R_p = \frac{1}{0.5}",
                r"R_p = 2\,\Omega",
            ],
        ),
        # 1/R_p equals R_p (two 2 Ω in parallel): the working still ends on R_p.
        (
            [r"\frac{1}{R_p} = \frac{1}{2} + \frac{1}{2}"],
            r"1\,\Omega",
            [
                r"\frac{1}{R_p} = \frac{1}{2} + \frac{1}{2}",
                r"\frac{1}{R_p} = 0.5 + 0.5",
                r"\frac{1}{R_p} = 1",
                r"R_p = \frac{1}{1}",
                r"R_p = 1\,\Omega",
            ],
        ),
        # Two values: each row is matched by its value, whatever it is named.
        (
            [r"a = \frac{2 \times 9.81}{5 + 2}", r"T = 5 \times \frac{2 \times 9.81}{5 + 2}"],
            r"2.8\,\mathrm{m/s²}\ \text{and}\ 14\,\mathrm{N}",
            [
                r"a = \frac{2 \times 9.81}{5 + 2}",
                r"a = \frac{19.62}{7}",
                r"a = 2.8\,\mathrm{m/s²}",
                r"T = 5 \times \frac{2 \times 9.81}{5 + 2}",
                r"T = 5 \times \frac{19.62}{7}",
                r"T = 5 \times 2.80286",
                r"T = 14\,\mathrm{N}",
            ],
        ),
    ],
)
def test_carried_to_answer(rows: list[str], answer: str, carried: list[str]) -> None:
    assert carried_to_answer(rows, answer) == carried


@pytest.mark.parametrize(
    "rows",
    [
        # Already worked by the solver.
        [r"E = 2000 \times 10800", r"E = 2.16 \times 10^{7}\,\mathrm{J}"],
        # Worked to a different value (a rounded row): left as the solver wrote it.
        [r"R = 2\cos(0^\circ)\times 0.4", r"x = 1"],
    ],
)
def test_rows_that_do_not_reach_the_answer_are_left_alone(rows: list[str]) -> None:
    assert carried_to_answer(rows, r"0.808\,\mathrm{m}") == rows


def test_answer_parts_read_each_value_and_drop_a_note() -> None:
    assert answer_parts(r"50\,\mathrm{N}\ \text{at 53.1°}") == [
        (r"50\,\mathrm{N}", 50.0),
        ("53.1°", 53.1),
    ]
    assert answer_parts(r"459\,\mathrm{Hz}\ (\text{receding, sound at 340 m/s})") == [
        (r"459\,\mathrm{Hz}", 459.0)
    ]
    assert answer_parts(r"H_{\mathrm{max}} = 13.2\,\mathrm{m};\quad R = 62.7\,\mathrm{m}") == [
        (r"13.2\,\mathrm{m}", 13.2),
        (r"62.7\,\mathrm{m}", 62.7),
    ]


@pytest.mark.parametrize(
    ("unit", "key", "factor"),
    [
        ("km/h", "v", r"\times 1000/3600"),
        ("mph", "v", r"\times 0.44704"),
        ("cm", "d", r"\times 0.01"),
        ("nm", "wavelength", r"\times 10^{-9}"),
        ("kW", "P", r"\times 1000"),
        ("h", "t", r"\times 3600"),
        ("m/min", "v", r"\times 1/60"),
    ],
)
def test_a_given_in_another_unit_shows_its_factor(unit: str, key: str, factor: str) -> None:
    scale = si_factor(unit, expected_key=key)
    assert scale is not None
    assert latex_factor(*scale) == factor


@pytest.mark.parametrize(("unit", "key"), [("degC", "T"), ("turns", "N"), ("", "v")])
def test_no_factor_for_an_offset_a_count_or_no_unit(unit: str, key: str) -> None:
    assert si_factor(unit, expected_key=key) is None

"""A formula is headed by its name and "formula", and **Solution** heads the working."""

from __future__ import annotations

import pytest

from app.modules.physics.law_titles import law_heading
from app.services.workout import (
    FORMULA,
    Workout,
    formula_heading,
    formula_sections,
    math_line,
    render_workout,
    text_line,
)


@pytest.mark.parametrize(
    ("name", "heading"),
    [
        ("Average speed", "Average speed formula"),
        ("kinetic energy", "Kinetic energy formula"),
        ("Mass–mole relation", "Mass–mole relation formula"),
        ("Triangle area formula", "Triangle area formula"),
        ("Heron's formula", "Heron's formula"),
        ("Ohm's law", "Ohm's law"),
        ("Pythagorean theorem", "Pythagorean theorem"),
        ("Cosine rule", "Cosine rule"),
        ("Bernoulli's principle", "Bernoulli's principle"),
        ("Continuity equation", "Continuity equation"),
        ("Slope-intercept form", "Slope-intercept form"),
        ("Newton's method", "Newton's method"),
        ("", FORMULA),
        (None, FORMULA),
        ("Average speed.", "Average speed formula"),
        ("$v = d/t$", FORMULA),
        ("one two three four five six seven eight nine ten", FORMULA),
    ],
)
def test_formula_heading_names_the_formula(name: str | None, heading: str) -> None:
    assert formula_heading(name) == heading


@pytest.mark.parametrize(
    ("law_name", "heading"),
    [
        ("Kinetic-energy formula", "Kinetic energy formula"),
        ("SUVAT constant-acceleration equation", "Constant acceleration formula"),
        ("Snell's law", "Snell's law"),
        ("Charge-current relation", "Charge and current formula"),
    ],
)
def test_law_heading_is_the_shared_rule(law_name: str, heading: str) -> None:
    assert law_heading(law_name) == heading


def test_formula_sections_move_each_name_to_its_heading() -> None:
    lines = (
        math_line(r"\Delta = b^2 - 4ac", "Discriminant"),
        math_line(r"x = \frac{-b \pm \sqrt{\Delta}}{2a}", "Quadratic formula"),
        text_line("Solve for $x$"),
    )
    assert formula_sections(lines) == [
        ("Discriminant formula", [r"$\Delta = b^2 - 4ac$"]),
        ("Quadratic formula", [r"$x = \frac{-b \pm \sqrt{\Delta}}{2a}$", "Solve for $x$"]),
    ]


def test_formula_sections_keep_a_note_that_is_no_name() -> None:
    lines = (math_line("y = 0", "on the x-axis"), math_line("x = 1", "Discriminant"))
    assert formula_sections(lines) == [
        (FORMULA, ["$y = 0$ — on the x-axis"]),
        ("Discriminant formula", ["$x = 1$"]),
    ]


def test_formula_sections_with_a_heading_keep_every_line() -> None:
    lines = (math_line("v = d/t"), math_line("t = d/v", "the same law"))
    assert formula_sections(lines, "Average speed formula") == [
        ("Average speed formula", ["$v = d/t$", "$t = d/v$ — the same law"])
    ]


def test_render_workout_heads_the_working_with_solution() -> None:
    reply = render_workout(
        Workout(
            given=(math_line(r"d = 3000\,\mathrm{m}"),),
            find=(math_line("v"),),
            formula=(math_line(r"v = \frac{d}{t}", "Average speed"),),
            substitution=(math_line(r"v = \frac{3000}{900}"),),
        ),
        r"3.33\,\mathrm{m/s}",
    )
    assert reply.startswith(
        "**Given**  \n$d = 3000\\,\\mathrm{m}$\n\n**Required**  \n$v$\n\n**Solution**\n\n"
        "**Average speed formula**  \n$v = \\frac{d}{t}$\n\n**Substitution**"
    )
    assert "Average speed$" not in reply and "— Average speed" not in reply


def test_render_workout_has_no_solution_without_working_or_opening() -> None:
    assert "**Solution**" not in render_workout(Workout(given=("$x = 1$",)), "1")
    assert "**Solution**" not in render_workout(Workout(substitution=("$x = 1$",)), "1")
    opening = render_workout(Workout(given=("$x = 1$",)), answer_heading=None, solution=True)
    assert opening.endswith("**Solution**")

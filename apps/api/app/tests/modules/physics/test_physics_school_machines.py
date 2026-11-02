"""A machine in a school book's words, and an equivalence a question states
(2026-10-29, a grade 7 physics book: "the M.A of the machine", "a. VR", "Take 1 liter
of water = 1 kg of water")."""

import pytest

from app.modules.physics.numbers import normalize_physics_units
from app.modules.physics.stated_equivalence import apply_stated_equivalence


@pytest.mark.parametrize(
    ("text", "read"),
    [
        ("the M.A of the machine?", "the mechanical advantage of the machine?"),
        ("b. MA of the machine", "b. mechanical advantage of the machine"),
        ("a. VR of the machine. Calculate", "a. velocity ratio of the machine. Calculate"),
        ("the M.A. of a lever", "the mechanical advantage of a lever"),
        ("the MA. Calculate the effort", "the mechanical advantage. Calculate the effort"),
    ],
)
def test_a_machines_abbreviations_read_as_their_words(text: str, read: str) -> None:
    assert normalize_physics_units(text) == read


@pytest.mark.parametrize(
    "text",
    [
        "I live in MA",  # a state, with no machine in sight
        "a current of 5 mA in the machine",  # a milliamp
        "is a VR headset worth it",
        # Review (2026-10-29): a voltage and a resistance, a megaamp, points on a lever.
        "The load is connected to 12 V. R is 6 ohm.",
        "20 MA flows through the machine",
        "Points M A B C on the lever",
    ],
)
def test_the_letters_elsewhere_are_left_alone(text: str) -> None:
    assert normalize_physics_units(text) == text


def test_a_stated_equivalence_converts_the_questions_own_amount() -> None:
    text = "Take 1 L of oil = 0.9 kg of oil. A pump lifts 1,500 L of oil 10 m in 60 s."
    assert apply_stated_equivalence(text) == "A pump lifts 1350 kg of oil 10 m in 60 s."


def test_water_at_its_own_density_only_loses_the_statement() -> None:
    text = (
        "An electric motor pumps 200 liter of water to a reservoir of height 6 m in 2 s. "
        "Calculate the power developed by the motor. Take 1 liter of water = 1 kg of water."
    )
    assert apply_stated_equivalence(text) == (
        "An electric motor pumps 200 liter of water to a reservoir of height 6 m in 2 s. "
        "Calculate the power developed by the motor."
    )


@pytest.mark.parametrize(
    "text",
    [
        # Nothing stated, or stated about something the question has no amount of.
        "Pump 200 liter of water up 6 m in 2 s. What power?",
        "A tank holds 50 litres of oil. 1 litre of water has a mass of 1 kg. Find the mass.",
    ],
)
def test_without_a_matching_statement_the_text_is_kept(text: str) -> None:
    assert apply_stated_equivalence(text) == text


@pytest.mark.parametrize(
    ("question", "answer"),
    [
        # Review (2026-10-29): the noun before a value is no name for it.
        (
            "A ramp 2 m high and 10 m long is used to push a 500 N box up with an effort of "
            "150 N. What is the velocity ratio?",
            "5",
        ),
        (
            "A ramp 2 m high and 10 m long is used to push a 500 N box up with an effort of "
            "150 N. Calculate the input work.",
            r"1500\,\mathrm{J}",
        ),
        (
            "Take 1 L of oil = 0.9 kg of oil. A pump lifts 1,500 L of oil 10 m in 60 s. "
            "What power?",
            r"2207\,\mathrm{W}",
        ),
        ("The load is connected to 12 V. R is 6 ohm. What current flows?", r"2\,\mathrm{A}"),
    ],
)
def test_reviewed_machine_questions_get_the_right_number(question: str, answer: str) -> None:
    from app.core.config import Settings
    from app.modules.physics.prompt import solve_physics_request

    _, block = solve_physics_request(question, Settings(math_tools_enabled=True), None)
    assert block is not None and block.display_answer == answer


@pytest.mark.parametrize(
    "question",
    [
        "A pump moves 100 kg of oil 5 m horizontally in 20 s. What power?",
        "A 500 N box is pulled up a ramp 5 m high, 20 m long, with an effort of 150 N. What is "
        "the ideal mechanical advantage?",
        "A 2 m long lever raises a 300 N load 0.1 m high with an effort of 100 N. What is the "
        "efficiency of the lever?",
        "A pulley lifts a 100 N load 2 m high using a 4 m long rope with an effort of 60 N. "
        "What is the efficiency?",
    ],
)
def test_other_machines_are_not_read_as_a_plank(question: str) -> None:
    from app.core.config import Settings
    from app.modules.physics.prompt import solve_physics_request

    _, block = solve_physics_request(question, Settings(math_tools_enabled=True), None)
    assert block is None

"""A question in parts the solver reads one part of: each part solved on its own, and a
lone card under the part it answers (2026-10-29, a grade 7 physics book: the crane's
power and the car's time were never on a card)."""

import pytest

from app.core.config import Settings
from app.modules.physics.fence import validate_physics_fences
from app.modules.physics.part_answers import land_one_part_card
from app.modules.physics.prompt import solve_physics_request

_SETTINGS = Settings(math_tools_enabled=True)


@pytest.mark.parametrize(
    ("question", "parts"),
    [
        (
            "A certain car has an acceleration of 2.4 m/s^2. Assume that its acceleration "
            "remains constant. Starting from rest, how long does the car require to reach a "
            "velocity of 90 km/h? How far does it travel while reaching that velocity?",
            [("Time", r"10.4\,\mathrm{s}"), ("Distance", r"130\,\mathrm{m}")],
        ),
        (
            "A crane lifts a 450 kg concrete to the top of a 50 m building in 5 s. Assuming "
            "g = 10 m/s^2, calculate: a) The potential energy of the concrete. b) The power "
            "developed by the crane",
            [
                ("Potential energy", r"2.25 \times 10^{5}\,\mathrm{J}"),
                ("Power", r"45000\,\mathrm{W}"),
            ],
        ),
        (
            "A ball is dropped from 45 m. (a) How long does it take to hit the ground? "
            "(b) How fast is it going when it lands?",
            [("Time", r"3.03\,\mathrm{s}"), ("Speed", r"29.7\,\mathrm{m/s}")],
        ),
    ],
)
def test_every_part_gets_its_own_verified_card(question: str, parts: list[tuple[str, str]]) -> None:
    outcome, block = solve_physics_request(question, _SETTINGS, None)
    assert outcome == "verified" and block is not None
    assert [(part.title, part.display_answer) for part in block.physics_parts] == parts


def test_two_parts_of_one_kind_are_not_guessed_apart() -> None:
    # The normal force and the friction are both newtons: the friction answered both.
    question = (
        "A block of mass 5 kg is being pulled along a board horizontally with a constant "
        "velocity; the coefficient of friction between the two surfaces is 0.25. a) What is "
        "the normal reaction force between the board and the block? b) What is the "
        "frictional force that opposes the motion?"
    )
    _, block = solve_physics_request(question, _SETTINGS, None)
    assert block is not None and not block.physics_parts


_REPLY = """**(a) Normal reaction**

**Answer (a)**
$N = 49.05\\ \\text{N}$

---

**(b) Frictional force**

$F = 0.25 \\cdot 5 \\cdot 9.81$

**Answer (b)**
$F = 12.3\\ \\text{N}$

**Answer**
"""


def test_a_lone_card_lands_under_the_part_it_answers() -> None:
    landed = land_one_part_card(_REPLY, r"12.3\,\mathrm{N}")
    assert landed is not None
    assert landed.endswith("**Answer (b)**\n\n```answer\nverified: true\n12.3\\,\\mathrm{N}\n```")
    # The other part keeps the value the model wrote, and no empty Answer is left.
    assert "$N = 49.05\\ \\text{N}$" in landed
    assert landed.count("**Answer**") == 0


_BLOCK = (
    "A block of mass 5 kg is being pulled along a board horizontally with a constant "
    "velocity; the coefficient of friction between the two surfaces is 0.25. a) What is "
    "the normal reaction force between the board and the block? b) What is the "
    "frictional force that opposes the motion?"
)


def test_a_closing_answer_after_the_verified_part_is_never_carded() -> None:
    # Review (2026-10-30): "## Answer" stating another value read as part (b)'s answer
    # and got an unchecked card under the verified one.
    _, block = solve_physics_request(_BLOCK, _SETTINGS, None)
    reply = _REPLY.replace("**Answer**\n", "## Answer\n$F = 15\\ \\text{N}$\n")
    landed = validate_physics_fences(reply, verified=block, user_text=_BLOCK)
    assert landed.count("```answer") == 2
    assert landed.rstrip().endswith("## Answer\n$F = 15\\ \\text{N}$")


def test_the_parts_the_server_did_not_solve_get_a_card_marked_not_checked() -> None:
    _, block = solve_physics_request(_BLOCK, _SETTINGS, None)
    assert block is not None and block.display_answer == r"12.3\,\mathrm{N}"
    landed = validate_physics_fences(_REPLY, verified=block, user_text=_BLOCK)
    assert "**Answer (a)**\n\n```answer\nverified: false\n$N = 49.05\\ \\text{N}$\n```" in landed
    assert "**Answer (b)**\n\n```answer\nverified: true\n12.3\\,\\mathrm{N}\n```" in landed


def test_a_card_no_part_states_is_not_placed() -> None:
    assert land_one_part_card(_REPLY, r"99\,\mathrm{N}") is None


# Review (2026-10-29): a given written after the last part, or inside one part's ask,
# holds for every part; read as that part's alone, part (a) was solved with g = 9.8.
@pytest.mark.parametrize(
    ("question", "answers"),
    [
        (
            "A stone is dropped from the top of a tower and reaches the ground in 3 s. a) What "
            "is the height of the tower? b) What is its velocity when it hits the ground? "
            "(Take g = 10 m/s^2)",
            [r"45\,\mathrm{m}", r"-30\,\mathrm{m/s}"],
        ),
        (
            "A body falls freely from rest for 2 s. (a) How far does it fall? (b) What is its "
            "final velocity? [g = 10 m/s^2]",
            [r"20\,\mathrm{m}", r"20\,\mathrm{m/s}"],
        ),
        (
            "A ball is dropped from a 80 m building. What is its speed on impact, taking "
            "g = 10 m/s^2? How long does it take to fall?",
            [r"40\,\mathrm{m/s}", r"4\,\mathrm{s}"],
        ),
        (
            "A space woman has a mass of 65 kg on the earth surface. What is her weight on: "
            "a) the earth, where g = 10 m/s^2? b) the moon, where g = 1.6 m/s^2?",
            [r"650\,\mathrm{N}", r"104\,\mathrm{N}"],
        ),
    ],
)
def test_a_given_anywhere_holds_for_every_part(question: str, answers: list[str]) -> None:
    _, block = solve_physics_request(question, _SETTINGS, None)
    assert block is not None
    assert [part.display_answer for part in block.physics_parts] == answers


@pytest.mark.parametrize(
    "question",
    [
        # A part that changes the situation or follows on from another.
        "A 2 kg ball moves at 3 m/s. What is its momentum? What is its kinetic energy if the "
        "speed doubles?",
        "A car accelerates from rest at 2 m/s^2. a) What is its speed after 5 s? b) What is "
        "its speed 3 s later?",
        "A car accelerates from rest at 2 m/s^2. a) How far does it go in 5 s? b) How far "
        "does it go in the next 3 s?",
        "A block slides down a frictionless incline. What is its acceleration if the incline "
        "is at 30 degrees? What is its speed after sliding 5 m from rest?",
    ],
)
def test_a_part_that_depends_on_another_is_not_solved_alone(question: str) -> None:
    _, block = solve_physics_request(question, _SETTINGS, None)
    assert block is None or not block.physics_parts


def test_the_height_above_the_balcony_is_not_the_height_above_the_ground() -> None:
    question = (
        "A ball is thrown up at 15 m/s from a 10 m high balcony. How high above the balcony "
        "does it go?"
    )
    _, block = solve_physics_request(question, _SETTINGS, None)
    assert block is None or block.display_answer != r"21.5\,\mathrm{m}"


def test_a_part_stating_another_value_gets_no_card() -> None:
    from app.modules.physics.part_answers import parts_conflict

    reply = "**Answer (a)**\n$h = 11.5\\ \\text{m}$\n\n**Answer (b)**\n$t = 3.62\\ \\text{s}$\n"
    assert parts_conflict(reply, [r"21.5\,\mathrm{m}", r"3.62\,\mathrm{s}"])
    assert not parts_conflict(reply, [r"11.5\,\mathrm{m}", r"3.62\,\mathrm{s}"])

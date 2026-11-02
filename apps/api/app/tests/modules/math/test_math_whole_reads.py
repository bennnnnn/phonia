"""A reader certifies only what it read to the end, and a card never shows a rounding as exact.

Each wrong card came from a textbook question (Ethiopian MoE grades 8-11): a dice event
read without its "not" and its "or 9", the line through a point and its image given as
the line of reflection, and a pyramid's slant height of 50√2 read as a height of 50 with
the volume 166666.67 shown as an exact 166667.
"""

from __future__ import annotations

import time

import pytest

from app.core.config import Settings
from app.modules.math.match import measure_after
from app.modules.math.tools.school.single_draw import extract_single_draw_intent
from app.modules.math.tools.school.single_draw_events import (
    card_event,
    one_die_event,
    two_dice_event,
)
from app.services.subjects.dispatch import build_subject_augmentation, maybe_direct_subject_reply


async def _card(text: str) -> tuple[str | None, str | None]:
    """(the card the student sees, the direct reply) for one turn."""
    settings = Settings(math_llm_extract_enabled=False, math_word_problems_enabled=False)
    verified = (await build_subject_augmentation(text, settings)).verified
    if verified is None:
        return None, None
    shown = getattr(verified, "display_answer", None) or verified.canonical_answer
    return shown, maybe_direct_subject_reply(verified, text)


@pytest.mark.parametrize(
    ("text", "favourable", "total"),
    [
        (
            "A pair of fair dice is tossed. What is the probability of not getting a sum 5 or 9?"
            "\na. 2/9  b. 8/9  c. 7/9  d. 1/9",
            28,
            36,
        ),
        ("probability of rolling a sum of 7 with two dice", 6, 36),
        # An actor and a pronoun are the scene, not the event.
        ("Abebe rolls two dice. What is the probability that he gets a sum of 7?", 6, 36),
        ("Two dice are rolled. Find the probability that the sum is greater than 9.", 6, 36),
        ("Two dice are rolled. What is the probability that the sum is not 7?", 30, 36),
        (
            "If two dice are thrown, what is the probability of getting a total of 5, 6 or 7?",
            15,
            36,
        ),
        (
            "What is the probability of getting a sum of 5 or a sum of 9 when two dice are rolled?",
            8,
            36,
        ),
        (
            "Two six-sided dice are rolled. What is the probability that the sum is at least 10?",
            6,
            36,
        ),
        ("What is the probability of not getting a double when two fair dice are rolled?", 30, 36),
        ("probability of rolling a 6 on a die", 1, 6),
        ("A die is rolled. What is the probability of not getting a 6?", 5, 6),
        (
            "A fair die is rolled once. Find the probability of getting a number greater than 4.",
            2,
            6,
        ),
        ("A die is rolled. What is the probability that the number is not prime?", 3, 6),
        ("A die is rolled. What is the probability of getting an odd number or a 6?", 4, 6),
        ("A die is rolled. What is the probability of getting a multiple of 3?", 2, 6),
        ("probability of drawing a king from a standard deck", 4, 52),
        (
            "A card is drawn at random from a well-shuffled deck of 52 cards. "
            "What is the probability that it is a king or a heart?",
            16,
            52,
        ),
        (
            "A card is drawn from a deck of 52 playing cards. "
            "What is the probability of not drawing a heart?",
            39,
            52,
        ),
        (
            "A card is drawn from a standard deck. What is the probability that it is a red king?",
            2,
            52,
        ),
        (
            "A card is drawn from a standard deck. What is the probability that it is not a king "
            "or a queen?",
            44,
            52,
        ),
    ],
)
def test_a_draw_is_read_with_every_outcome_and_not(text: str, favourable: int, total: int) -> None:
    intent = extract_single_draw_intent(text)
    assert intent is not None
    assert (intent.combo_k, intent.combo_n) == (favourable, total)


@pytest.mark.parametrize(
    "text",
    [
        # A word the reader has no meaning for: the event is not read whole.
        "Two dice are rolled. What is the probability of a sum of 7 and a double?",
        "Two dice are rolled. Given that the first die shows 3, what is the probability that "
        "the sum is 8?",
        "Two dice are rolled. What is the probability that the product is 6?",
        "What's the probability of rolling two sixes with two dice?",
        "Two dice are rolled. What is the probability of a sum of 5 or more?",
        "Two dice are rolled. Find the probability that the sum is neither 5 nor 9.",
        "Two dice are rolled. Find the probability that (a) the sum is 5 (b) the sum is 9.",
        "A die is rolled. What is the probability of getting an even number and a 6?",
        "A die is rolled. What is the probability of getting a 7?",
        "A card is drawn from a standard deck. What is the probability that it is a king and a "
        "heart?",
        "A card is drawn from a standard deck. What is the probability that it is a 7?",
        # Four rolls, not one: this was certified as 6 of 6 faces, a probability of 1.
        "probability of getting at least one 6 in 4 rolls of a die",
    ],
)
def test_a_draw_with_words_the_reader_cannot_read_declines(text: str) -> None:
    assert extract_single_draw_intent(text) is None


@pytest.mark.asyncio
async def test_the_complement_of_two_sums_shows_its_working() -> None:
    card, reply = await _card(
        "A pair of fair dice is tossed. What is the probability of not getting a sum 5 or 9?"
    )
    assert card == r"\frac{7}{9} \approx 0.7778"
    assert reply is not None
    assert "the 4 ways to make 9" in reply
    assert r"$36 - 8 = 28$" in reply


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("text", "card"),
    [
        (
            "In a reflection, the image of the point P(3, 10) is P'(7, 2). "
            "Find the equation of the line of reflection.",
            r"y = \frac{1}{2} x + \frac{7}{2}",
        ),
        ("Find the line of reflection that maps (1, 2) onto (5, 2).", "x = 3"),
        (
            "The point A(2, 3) is reflected to A'(4, 7). Find the mirror line.",
            r"y = - \frac{1}{2} x + \frac{13}{2}",
        ),
        ("equation of the line through (1,2) and (3,8)", "y = 3 x - 1"),
        ("Find the equation of line AB where A(1, 2) and B(3, 4).", "y = x + 1"),
    ],
)
async def test_the_line_asked_is_the_line_answered(text: str, card: str) -> None:
    # A line of reflection is the perpendicular bisector, never the line through the two.
    shown, _ = await _card(text)
    assert shown == card


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text",
    [
        "Find the equation of the line equidistant from (1, 2) and (3, 4)",
        "Find the equation of the circle with diameter endpoints (1, 2) and (3, 4)",
        "Find the equation of the tangent to the curve at the points (1, 2) and (3, 4)",
    ],
)
async def test_a_line_related_to_two_points_another_way_is_not_the_line_through_them(
    text: str,
) -> None:
    shown, _ = await _card(text)
    assert shown is None or "y = x + 1" not in shown


@pytest.mark.parametrize(
    ("text", "label", "value"),
    [
        ("a slant height of 50√2 m", "height", None),
        ("a slant height of 13 m and a height of 12 m", "height", 12.0),
        ("height 50√2 m", "height", None),
        ("radius 3π cm", "radius", None),
        ("radius 1/2 m", "radius", None),
        ("side √2 m", "side", None),
        ("side 2.5 m.", "side", 2.5),
        ("height 7 cm", "height", 7.0),
    ],
)
def test_a_measure_is_read_whole_or_not_at_all(text: str, label: str, value: float | None) -> None:
    assert measure_after(text, label) == value


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text",
    [
        "What is the volume of a stone in an Egyptian pyramid with a square base of side 100 m "
        "and a slant height of 50√2 m for each of the triangular faces?",
        "volume of a cone with radius 3 cm and slant height 5 cm",
        "area of a triangle with base 4√2 cm and height 3 cm",
        "volume of a cylinder with radius 1/2 m and height 4 m",
    ],
)
async def test_a_solid_with_a_measure_it_cannot_read_gets_no_card(text: str) -> None:
    shown, _ = await _card(text)
    assert shown is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("text", "card"),
    [
        (
            "volume of a square pyramid with base side 10 cm and height 7 cm",
            r"\approx 233.3333\ \mathrm{cm}^{3}",
        ),
        ("find the diagonal of a rectangle 3 cm by 5 cm", r"\approx 5.831\ \mathrm{cm}"),
        ("area of a circle with radius 3 cm", r"\approx 28.27\ \mathrm{cm}^{2}"),
        (
            "volume of a cylinder with radius 3 cm and height 10 cm",
            r"\approx 282.74\ \mathrm{cm}^{3}",
        ),
        # Exact measures stay exact.
        ("find the diagonal of a rectangle 3 cm by 4 cm", r"5\ \mathrm{cm}"),
        ("volume of a square pyramid with base side 6 cm and height 4 cm", r"48\ \mathrm{cm}^{3}"),
        ("area of a triangle with base 7 cm and height 3 cm", r"10.5\ \mathrm{cm}^{2}"),
        ("volume of a cube with side 3 cm", r"27\ \mathrm{cm}^{3}"),
    ],
)
async def test_a_rounded_measure_is_shown_as_a_rounding(text: str, card: str) -> None:
    shown, reply = await _card(text)
    assert shown == card
    if reply is not None and card.startswith(r"\approx"):
        # The working ends where the card does: ≈, not =.
        number = card.split()[1].split("\\")[0]
        assert f"= {number}" not in reply


@pytest.mark.parametrize(
    "text",
    [
        "Two dice are rolled. What is the probability that the sum is less than 12?",
        "Two dice are rolled. What is the probability that the sum is greater than 2?",
        "A card is drawn from a deck of 52 cards. What is the probability of a red face card or "
        "a black ace?",
        "A card is drawn from a deck of 52 cards. What is the probability of a king of hearts or "
        "a queen?",
        "A card is drawn from a deck of 52 cards. What is the probability of a heart or king or "
        "queen?",
    ],
)
def test_a_long_event_travels_as_numbers_and_never_raises(text: str) -> None:
    # Its label once outgrew a 24-character field: the turn read no subject at all.
    intent = extract_single_draw_intent(text)
    assert intent is not None
    assert len(intent.trial_outcome or "") <= 24


_LONG = 10_000
_ADVERSARIAL = [
    "√" + " " * _LONG,
    "A)!" + " a)!" * (_LONG // 4),
    "a)!" * (_LONG // 3),
    " " * _LONG,
    "a sum of 5 or " * (_LONG // 14),
    "radius " * (_LONG // 7),
    "slant" + " " * _LONG,
    "(1, 2) " * (_LONG // 7),
    "the image of (1, 2) is (3, 4) " * (_LONG // 30),
    "a red king or " * (_LONG // 14),
    "if two dice are rolled " * (_LONG // 23),
]


@pytest.mark.wall_clock
@pytest.mark.parametrize("text", _ADVERSARIAL)
def test_the_whole_readers_stay_linear_on_a_long_run(text: str) -> None:
    from app.modules.math.tools.school.coordinate import _extract_coord_intent
    from app.modules.math.tools.school.geometry_measures import extract_geometry_measure_intent

    readers = (
        lambda: two_dice_event("two dice " + text),
        lambda: one_die_event("a die " + text),
        lambda: card_event("a deck of 52 cards " + text),
        lambda: measure_after(text + " 3", "radius"),
        lambda: measure_after("height" + text + "4", "height"),
        lambda: _extract_coord_intent("equation of the line through " + text),
        lambda: extract_geometry_measure_intent(text),
    )
    for read in readers:
        start = time.perf_counter()
        read()
        assert time.perf_counter() - start < 0.25

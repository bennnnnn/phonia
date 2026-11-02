"""Every question a reviewer found certified wrongly (or not at all) on the readers' PR.

A card is shown only for what was read in full: a dice, die or card event with every
word accounted for; a line asked as the line through its two points and nothing else;
a measure named right before its whole number. Each row is the student's question and
the card it must get, or None for no card at all. A rounded measure says so (≈), and an
exact one is printed whole, never in e-notation.
"""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.modules.math.tools.school.single_draw import extract_single_draw_intent
from app.services.subjects.dispatch import build_subject_augmentation

_DRAWS = [
    (
        "Two dice are rolled. Find the probability that the sum is 8 if the dice show the same number.",
        None,
    ),
    (
        "Two dice are rolled. Find the probability of getting a sum of 8 with the same number on the dice.",
        None,
    ),
    ("Two dice are rolled. Find the probability of a sum of 4 with the same number.", None),
    (
        "Two dice are rolled. What is the probability of getting a sum of 6 when the numbers are the same?",
        None,
    ),
    ("A die is rolled. What is the probability that the number is one more than 3?", None),
    ("A die is rolled. What is the probability that the number is one less than 6?", None),
    ("A die is rolled. What is the probability that the result is 6 when it is even?", None),
    (
        "Two dice are rolled at the same time. What is the probability of getting a sum of 9?",
        (4, 36),
    ),
    (
        "Two dice are rolled. What is the probability that the sum is 9 if it is greater than 6?",
        None,
    ),
    (
        "Two dice are rolled. What is the probability that the sum is at least 9 when it is not 12?",
        None,
    ),
    (
        "A card is drawn from a deck of 52 cards. What is the probability that it is a heart if it is red?",
        None,
    ),
    (
        "A card is drawn from a deck of 52 cards. What is the probability that it is a king of the same suit?",
        None,
    ),
    ("Two dice are rolled. What is the probability of a sum of 7 or 11 or a double?", None),
    ("Two dice are rolled. What is the probability that the sum is 3 or 4, or 5?", None),
    ("Two dice are rolled. What is the probability that the sum is 2, or 3?", (3, 36)),
    ("Two dice are rolled. What is the probability that the sum is not 7, 8 or 9?", (21, 36)),
    ("Two dice are rolled. What is the probability that the sum is greater than 4 or 5?", None),
    ("A die is rolled. What is the probability of getting a number greater than 2 or 3?", None),
    ("A die is rolled. What is the probability of getting a number not 2 or 3?", (4, 6)),
    ("A die is rolled. What is the probability of getting not 2 or 3?", (4, 6)),
    ("A die is rolled. What is the probability of getting a prime number or 1?", (4, 6)),
    ("A die is rolled. What is the probability of getting an odd prime?", None),
    ("A die is rolled. What is the probability of getting an even prime number?", None),
    ("A die is rolled. What is the probability of getting an odd number greater than 2?", None),
    ("A die is rolled. What is the probability of getting an even number less than 5?", None),
    ("A die is rolled. What is the probability of getting a prime number greater than 2?", None),
    ("A die is rolled. What is the probability of getting a multiple of 2 greater than 3?", None),
    (
        "Two dice are rolled. What is the probability that the sum is an even number greater than 8?",
        None,
    ),
    (
        "A card is drawn from a deck of 52 cards. What is the probability of a red face card or a black ace?",
        (8, 52),
    ),
    (
        "A card is drawn from a deck of 52 cards. What is the probability of a king of hearts or a queen?",
        (5, 52),
    ),
    (
        "A card is drawn from a deck of 52 cards. What is the probability of a black king or a red queen?",
        (4, 52),
    ),
    (
        "A card is drawn from a deck of 52 cards. What is the probability of a jack or queen?",
        (8, 52),
    ),
    (
        "A card is drawn from a deck of 52 cards. What is the probability of a heart or king or queen?",
        (19, 52),
    ),
    (
        "A card is drawn from a deck of 52 cards. What is the probability of a heart, king or queen?",
        (19, 52),
    ),
    ("A card is drawn from a deck of 52 cards. What is the probability of a red ace?", (2, 52)),
    (
        "A card is drawn from a deck of 52 cards. What is the probability of the ace of hearts or a heart?",
        (13, 52),
    ),
    (
        "A card is drawn from a deck of 52 cards. What is the probability of not a red card?",
        (26, 52),
    ),
    (
        "A card is drawn from a deck of 52 cards. What is the probability of drawing a card that is not a heart?",
        (39, 52),
    ),
    (
        "A card is drawn from a deck of 52 cards. What is the probability of drawing a black card that is a king?",
        (2, 52),
    ),
    (
        "A card is drawn from a deck of 52 cards. What is the probability of drawing a black card or a king?",
        (28, 52),
    ),
    ("A die is rolled. What is the probability of getting 6 on the die?", (1, 6)),
    ("A die is rolled. What is the probability that 6 is not on top?", None),
    ("A die is rolled. What is the probability of getting a 6 face up?", (1, 6)),
    ("A die is rolled. What is the probability that 6 does not show up?", None),
    ("A die is rolled. What is the probability that the face 6 is not shown?", None),
    ("A die is rolled. What is the probability that a 6 is not thrown?", None),
    ("A die is rolled. What is the probability of a 6 not showing?", None),
    ("A die is rolled. What is the probability of a 6 not being rolled?", None),
    (
        "A card is drawn from a deck of 52 cards. What is the probability that a king is not drawn?",
        None,
    ),
    (
        "A card is drawn from a deck of 52 cards. What is the probability of a king not being drawn?",
        None,
    ),
    ("Two dice are rolled. What is the probability of a double not being rolled?", None),
    ("Two dice are rolled. What is the probability that a double is not thrown?", None),
    ("Two dice are rolled. What is the probability that the sum is 7 is not true?", None),
    ("A die is rolled. What is the probability that it is not true that the number is even?", None),
    ("A die is rolled. What is the probability that 6 will not show?", None),
    ("A die is rolled. What is the probability that it will not land on 6?", None),
    ("A die is rolled. What is the probability that it lands on 6?", (1, 6)),
    ("A die is rolled. What is the probability that it does land on a 6?", None),
]


@pytest.mark.parametrize(("text", "expected"), _DRAWS)
def test_a_draw_is_certified_only_when_read_in_full(
    text: str, expected: tuple[int, int] | None
) -> None:
    intent = extract_single_draw_intent(text)
    if expected is None:
        assert intent is None
    else:
        assert intent is not None
        assert (intent.combo_k, intent.combo_n) == expected


_CARDS = [
    (
        "A card is drawn from a deck of 52 cards. What is the probability that it is a king or queen of hearts?",
        None,
    ),
    ("Two dice are rolled. What is the probability that the sum is less than 13?", None),
    (
        "A card is drawn from a deck of 52 cards. What is the probability that it is a red king or queen?",
        None,
    ),
    (
        "A card is drawn from a deck of 52 cards. What is the probability that it is a black heart?",
        None,
    ),
    (
        "Two dice are rolled. What is the probability that the sum is 8 if the numbers are the same?",
        None,
    ),
    (
        "Two dice are rolled. What is the probability that the sum is 8 when both show the same number?",
        None,
    ),
    (
        "Two dice are rolled. What is the probability that the sum is less than or equal to 4?",
        "\\frac{1}{6} \\approx 0.1667",
    ),
    (
        "Two dice are rolled. What is the probability that the sum is greater than or equal to 10?",
        "\\frac{1}{6} \\approx 0.1667",
    ),
    (
        "A die is rolled. What is the probability of getting a number less than or equal to 2?",
        "\\frac{1}{3} \\approx 0.3333",
    ),
    (
        "A card is drawn from a deck of 52 cards. What is the probability that it is a red card or a king?",
        "\\frac{7}{13} \\approx 0.5385",
    ),
    (
        "Two dice are rolled. What is the probability of not getting a sum of 7 or 11?",
        "\\frac{7}{9} \\approx 0.7778",
    ),
    (
        "Find the equation of the line through (1, 2) and perpendicular to the line joining (3, 4) and (5, 8).",
        None,
    ),
    (
        "Find the equation of the line through (1, 2) perpendicular to the line joining A(3, 4) and B(5, 8).",
        None,
    ),
    (
        "Find the equation of the line passing through (1, 2) and parallel to the line through (3, 4) and (5, 8).",
        None,
    ),
    ("Find the equation of the line through (1, 2) and the midpoint of (3, 4) and (5, 8).", None),
    ("Find the equation of the line passing through the point (2, 3) and the origin.", None),
    (
        "Find the equation of the line through (2, 3) with the same slope as the line through (0, 0) and (4, 4).",
        None,
    ),
    ("Find the equation of the line through (1, 2) and (3, 4).", "y = x + 1"),
    ("Find the slope of the line through (1, 2) and (3, 4).", "1"),
    ("Find the equation of the line joining (1, 2) and (3, 4).", "y = x + 1"),
    ("Find the equation of the line through (1, 2) and (3, 4) in the form ax + by + c = 0.", None),
    ("Find the x-intercept of the line through (1, 2) and (3, 4).", None),
    (
        "Find the equation of the line that passes through the midpoint of (1, 2) and (3, 4) with slope 2.",
        None,
    ),
    (
        "Find the equation of the line through (1, 2) that makes an angle of 45 degrees with the line through (0,0) and (3, 4).",
        None,
    ),
    (
        "Find the equation of the line through (1, 2) and the point of intersection of y = x and y = 2x - 1.",
        None,
    ),
    (
        "Find the equation of the line through (1, 2) and (3, 4) after it is shifted up 2 units.",
        None,
    ),
    ("Find the equation of the line through (1, 2) and (3, 4) reflected in the x-axis.", None),
    (
        "Find the equation of the line through (1, 2) and the centre of the circle x^2 + y^2 = 9.",
        None,
    ),
    ("Find the equation of the line from (1, 2) to (3, 4).", "y = x + 1"),
    ("Find the equation of the line between (1, 2) and (3, 4).", "y = x + 1"),
    ("Find the distance between (1, 2) and (3, 4).", r"2 \sqrt{2} \approx 2.828"),
    ("Find the equation of the line through (1, 2) and (3, 4), and its y-intercept.", None),
    (
        "Find the equation of the line through (1, 2) and (3, 4) and the line through (0, 0) and (1, 5).",
        None,
    ),
    ("Is (5, 6) on the line through (1, 2) and (3, 4)?", None),
    ("Find k if (5, k) lies on the line through (1, 2) and (3, 4).", None),
    ("Find the equation of the line through (2, 5) and (2, 9).", "x = 2"),
    (
        "In a reflection, the image of the point P(3, 10) is P'(7, 2). Find the equation of the line of reflection.",
        "y = \\frac{1}{2} x + \\frac{7}{2}",
    ),
    ("Find the mirror line that maps (1, 2) onto (5, 2).", "x = 3"),
    ("The point (2, 3) is reflected to (4, 7). Find the axis of symmetry.", None),
    ("The point (2, 3) is reflected to (4, 7). Find the line of symmetry.", None),
    (
        "The point (2, 3) is reflected to (4, 7). Find the equation of the mirror line.",
        r"y = - \frac{1}{2} x + \frac{13}{2}",
    ),
    ("Find the image of (2, 3) when reflected in the line y = x.", None),
    ("Find the image of the point (2, 3) in the line through (0, 0) and (1, 1).", None),
    ("Reflect (2, 3) in the line joining (0, 0) and (4, 4). Find the image.", None),
    ("The point (2, 3) is reflected in the line x + y = 1. Find the image.", None),
    ("Find the reflection of (2, 3) across the line y = 2x + 1.", None),
    ("A(1, 2) is reflected in the y-axis to A'. Find the line through A and A'.", None),
    ("The image of (1, 2) under a reflection is (1, 2). Find the line of reflection.", None),
    (
        "A point P(3, 10) is reflected to P'(7, 2) and then rotated 90 degrees. Find the line of reflection.",
        None,
    ),
    (
        "The image of (3, 10) after a reflection followed by a translation is (7, 2). Find the line of reflection.",
        None,
    ),
    (
        "The image of P(3, 10) under reflection in line L is P'(7, 2). Find the equation of the line through P and P'.",
        "y = 16 - 2 x",
    ),
    (
        "The image of P(3, 10) is P'(7, 2). Find the equation of the line of reflection and the distance PP'.",
        None,
    ),
    (
        "Under a glide reflection, the image of P(3, 10) is P'(7, 2). Find the line of reflection.",
        None,
    ),
    (
        "P(3, 10) maps to P'(7, 2) under a reflection followed by a dilation. Find the reflection line.",
        None,
    ),
    ("A cone has radius 5 cm and slant height 13 cm. Find its volume.", None),
    ("Find the volume of a cone whose slant height is 13 cm and radius is 5 cm.", None),
    ("Find the volume of a cone with radius 5 cm and slant-height 13 cm.", None),
    (
        "A square pyramid has base side 10 cm and the height of each triangular face is 13 cm. Find its volume.",
        None,
    ),
    ("A square pyramid has a base of side 10 cm and slant height 13 cm. Find its volume.", None),
    (
        "A square pyramid has base edge 10 cm, slant height 13 cm and height 12 cm. Find its volume.",
        "400\\ \\mathrm{cm}^{3}",
    ),
    ("Find the volume of a cylinder with radius 5 root 3 cm and height 4 cm.", None),
    ("Find the volume of a cylinder with radius ½ m and height 4 m.", None),
    ("Find the volume of a cylinder with radius 1½ m and height 4 m.", None),
    ("Find the volume of a cylinder with radius 2,5 m and height 4 m.", None),
    ("Find the volume of a cylinder with radius 3 × 10² cm and height 4 cm.", None),
    ("Find the volume of a cylinder with radius 5√3 cm and height 4 cm.", None),
    ("Find the volume of a cylinder whose height is twice its radius of 3 cm.", None),
    (
        "Find the volume of a cylinder whose height is twice the radius, and the radius is 3 cm.",
        None,
    ),
    ("Find the area of a circle with radius 2π cm.", None),
    ("Find the area of a circle with radius 3 cm in terms of π.", None),
    ("Find the area of a circle with radius 3 cm. Leave your answer in terms of pi.", None),
    ("Find the volume of a cylinder with radius 3 cm and height 10 cm in terms of π.", None),
    ("Find the circumference of a circle with radius 7 cm. Use π = 22/7.", None),
    ("Find the area of a circle with radius 7 cm (take π = 22/7).", None),
    ("Find the area of a circle with radius 7 cm using π = 3.14.", None),
    ("Find the volume of a cube with side 101 cm.", "1030301\\ \\mathrm{cm}^{3}"),
    ("Find the volume of a cube with side 120 cm.", "1728000\\ \\mathrm{cm}^{3}"),
    ("Find the area of a rectangle 1500 m by 1200 m.", "1800000\\ \\mathrm{m}^{2}"),
    ("Find the area of a rectangle 1234 m by 1001 m.", "1235234\\ \\mathrm{m}^{2}"),
    ("A triangle has sides 3, 4 and 5. Find its area.", "6\\ \\mathrm{units}^{2}"),
    ("A triangle has sides 5, 5 and 6. Find its area.", "12\\ \\mathrm{units}^{2}"),
    ("Find the area of a triangle with sides 4, 5 and 6.", "\\approx 9.9216\\ \\mathrm{units}^{2}"),
    ("Find the diagonal of a square with side 5 cm.", "\\approx 7.0711\\ \\mathrm{cm}"),
    ("Find the hypotenuse of a right triangle with legs 3 cm and 4 cm.", "5\\ \\mathrm{cm}"),
    (
        "Find the hypotenuse of a right triangle with legs 1 cm and 2 cm.",
        "\\approx 2.2361\\ \\mathrm{cm}",
    ),
    ("Find the perimeter of a right triangle with legs 3 cm and 4 cm.", "12\\ \\mathrm{cm}"),
    (
        "Find the perimeter of a right triangle with legs 1 cm and 1 cm.",
        "\\approx 3.4142\\ \\mathrm{cm}",
    ),
    (
        "Find the area of a sector with radius 6 cm and angle 60 degrees.",
        "\\approx 18.8496\\ \\mathrm{cm}^{2}",
    ),
    (
        "Find the arc length of a sector with radius 6 cm and angle 60°.",
        "\\approx 6.28\\ \\mathrm{cm}",
    ),
    (
        "Find the area of a trapezoid with top 3 cm, bottom 5 cm and height 4 cm.",
        "16\\ \\mathrm{cm}^{2}",
    ),
    ("Find the area of a trapezium with parallel sides 3 cm and 5 cm and height 2√3 cm.", None),
    ("Find the area of a parallelogram with base 6 cm and height 4√2 cm.", None),
    ("Find the area of a parallelogram with base 6 cm and slant height 5 cm.", None),
    (
        "Find the area of a parallelogram with base 8 cm, side 5 cm and height 4 cm.",
        "32\\ \\mathrm{cm}^{2}",
    ),
    ("Find the area of a triangle with base 6 cm and slant height 5 cm.", None),
    ("Find the area of a triangle with base 6 cm and height 1/2 cm.", None),
    ("Find the volume of a sphere with radius 3 cm.", "\\approx 113.1\\ \\mathrm{cm}^{3}"),
    ("Find the surface area of a sphere with radius 3 cm.", "\\approx 113.1\\ \\mathrm{cm}^{2}"),
    (
        "Find the volume of a hemisphere with radius 3 cm.",
        "18\\pi \\approx 56.55\\ \\mathrm{cm}^{3}",
    ),
    (
        "Find the volume of a cone with radius 3 cm and height 4 cm.",
        "\\approx 37.7\\ \\mathrm{cm}^{3}",
    ),
    (
        "Find the surface area of a cone with radius 3 cm and height 4 cm.",
        "\\approx 75.4\\ \\mathrm{cm}^{2}",
    ),
    (
        "Find the volume of a square pyramid with base side 6 cm and height 5 cm.",
        "60\\ \\mathrm{cm}^{3}",
    ),
    ("Find the volume of a cuboid 2.5 cm by 3 cm by 4 cm.", None),
    (
        "Find the volume of a cylinder with diameter 10 cm and height 7 cm.",
        "\\approx 549.78\\ \\mathrm{cm}^{3}",
    ),
    ("Find the area of a circle with diameter 10 cm.", "\\approx 78.54\\ \\mathrm{cm}^{2}"),
    ("Find the circumference of a circle with radius 3.5 cm.", "\\approx 21.99\\ \\mathrm{cm}"),
    (
        "A cylinder has a radius of 3 cm and a height of 7 cm. Find its total surface area.",
        "\\approx 188.5\\ \\mathrm{cm}^{2}",
    ),
    (
        "A rectangular prism has length 5 cm, width 3 cm and height 4 cm. Find the length of its diagonal.",
        None,
    ),
    ("Find the volume of a cone with slant height 10 cm and height 8 cm.", None),
    ("Find the lateral surface area of a cone with radius 3 cm and slant height 5 cm.", None),
    ("Find the volume of a regular square pyramid with base 8 m and slant height 5 m.", None),
    (
        "Find the volume of a cone with radius 6 cm and a height of 8 cm, and a slant height of 10 cm.",
        "\\approx 301.59\\ \\mathrm{cm}^{3}",
    ),
    ("The height of a cylinder is 10 cm and its radius is 3√2 cm. Find its volume.", None),
    (
        "The height of a cylinder is 10 cm and the radius of its base is 3 cm. Find the volume.",
        "\\approx 282.74\\ \\mathrm{cm}^{3}",
    ),
    (
        "Two dice are rolled. What is the probability that the sum is less than 12?",
        "\\frac{35}{36} \\approx 0.9722",
    ),
    (
        "Two dice are rolled. What is the probability that the sum is greater than 2?",
        "\\frac{35}{36} \\approx 0.9722",
    ),
    (
        "Two dice are rolled. Find the probability that the sum is 8 if the dice show the same number.",
        None,
    ),
    (
        "Find the equation of the line through the origin and the midpoint of (2, 4) and (6, 8).",
        None,
    ),
    (
        "Find the equation of the line through (2, 4) and (6, 8) after a dilation with scale factor 2 about the origin.",
        None,
    ),
    ("The line through (1, 2) and (3, 4) is moved 2 units up. Find its equation.", None),
    (
        "The line through (1, 2) and (3, 4) is shifted 3 units to the right. Find the equation of the new line.",
        None,
    ),
    (
        "Find the equation of the line through (1, 2) and (3, 4) after it is stretched vertically by a factor of 2.",
        None,
    ),
    (
        "Find the equation of the line passing through (1, 2) and the point that divides (3, 4) and (7, 8) in the ratio 1:1.",
        None,
    ),
    (
        "Find the equation of the line through (1, 2) whose y-intercept is the same as the line through (0, 5) and (3, 4).",
        None,
    ),
    (
        "Find the equation of the line that is 2 units above the line through (1, 2) and (3, 4).",
        None,
    ),
    ("Find the equation of the line through (1, 2) and (3, 4) when the axes are swapped.", None),
    (
        "Find the equation of the line through (1, 2) and (3, 4) written with x as the subject.",
        None,
    ),
    (
        "The point (2, 3) is reflected to (4, 7). Find the equation of the line of reflection.",
        r"y = - \frac{1}{2} x + \frac{13}{2}",
    ),
    (
        "After a reflection and then a translation, the image of P(3, 10) is P'(7, 2). Find the line of reflection.",
        None,
    ),
    (
        "The image of P(3, 10) under a reflection followed by a rotation is P'(7, 2). Find the line of reflection.",
        None,
    ),
    (
        "The image of A(2, 3) under the reflection in the line y = x is A'(3, 2). Find the line of reflection.",
        None,
    ),
    (
        "The image of A(2, 3) is A'(3, 2). Find the line of reflection and the image of B(5, 1).",
        None,
    ),
    ("Find the area of a square with side 100.5 cm.", "10100.25\\ \\mathrm{cm}^{2}"),
    ("Find the area of a rectangle 100.5 cm by 100.5 cm.", "10100.25\\ \\mathrm{cm}^{2}"),
    (
        "A card is drawn from a deck of 52 cards. What is the probability of a red face card or a black ace?",
        "\\frac{2}{13} \\approx 0.1538",
    ),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(("text", "card"), _CARDS)
async def test_the_card_shown_is_the_answer_read_in_full(text: str, card: str | None) -> None:
    settings = Settings(math_llm_extract_enabled=False, math_word_problems_enabled=False)
    verified = (await build_subject_augmentation(text, settings)).verified
    shown = None
    if verified is not None:
        shown = getattr(verified, "display_answer", None) or verified.canonical_answer
    assert shown == card


# What a whole-question review over 5,474 prompts found the first allowlists lost: the
# question's frame (an opener, an actor, the answer's format, a unit, a label) read as
# content, and a point to check read as a point the answer passes through. Each keeps the
# card main gave it, read and solved as the harness does.
_FRAMED = [
    ("Find the distance between the points (1, 2) and (4, 6) in units.", "5"),
    ("Find the distance between A(1, 2) and B(4, 6) in cm.", "5"),
    (
        "A card is drawn from a pack of 52 cards. Find the probability of getting a king. Express your answer in simplest form.",
        "\\frac{1}{13} \\approx 0.07692",
    ),
    ("Solve the system x + y = 5, x - y = 1 and check that (3, 2) works.", "x = 3, y = 2"),
    ("Solve the system 2x + y = 7 and x - y = 2. Is the solution (3, 1)?", "x = 3, y = 1"),
    (
        "Two dice are rolled. Find the probability that the sum is 7, in simplest form.",
        "\\frac{1}{6} \\approx 0.1667",
    ),
    (
        "A card is drawn from a 52-card deck. What is the probability that it is an ace of spades?",
        "\\frac{1}{52} \\approx 0.01923",
    ),
    ("Can you find the equation of the line through (1, 2) and (3, 6)?", "y = 2 x"),
    (
        "Find the equation of a line passing through the two points (1, 1) and (3, 5).",
        "y = 2 x - 1",
    ),
    ("Find the distance between the two points (2, 3) and (5, 7).", "5"),
    ("Can you find the distance between (1, 2) and (4, 6)?", "5"),
    ("What's the distance between (1,2) and (4,6)?", "5"),
    ("Find the distance between (1, 2) and (4, 6) units.", "5"),
    ("Find the midpoint of AB if A(2, 3) and B(4, 7).", "(3, 5)"),
    ("What's the slope between (1,2) and (3,4)?", "1"),
    ("Find the slope of the line joining the two points (1, 3) and (4, 12).", "3"),
    ("Can you find the slope of the line through (1, 2) and (3, 6)?", "2"),
    ("Could you find the midpoint of (2, 4) and (6, 8)?", "(4, 6)"),
    ("Hey, what's the slope of the line through (1, 2) and (3, 6)?", "2"),
    ("I need the distance between (1, 2) and (4, 6)", "5"),
    ("Help me find the midpoint of (2, 4) and (6, 8)", "(4, 6)"),
    ("What is the gradient of the line joining the two points (1, 2) and (3, 8)?", "3"),
    ("Find the distance between the two points A(1, 2) and B(4, 6).", "5"),
    ("Find the slope of the line passing through two points (1, 2) and (3, 8).", "3"),
    ("Find the distance between (1, 2) and (4, 6) and show your work.", "5"),
    ("Find the distance AB if A(1, 2) and B(4, 6).", "5"),
    ("Find the distance between the points (1, 2) and (4, 6) on the coordinate plane.", "5"),
    ("slope of line passing thru (1,2) and (3,6)", "2"),
    ("Find the distance between (1, 2) and (4, 6) using the distance formula.", "5"),
    ("Use the distance formula to find the distance between (1, 2) and (4, 6).", "5"),
    ("Use the midpoint formula to find the midpoint of (2, 4) and (6, 8).", "(4, 6)"),
    ("Find the slope of the line through (1, 2) and (3, 6) using the slope formula.", "2"),
    ("Find the distance between the points (1, 2) and (4, 6). Round to the nearest tenth.", "5"),
    (
        "Find the equation of the line passing through (1, 2) and (3, 6) in y = mx + b form.",
        "y = 2 x",
    ),
    ("Find the midpoint of the line segment whose endpoints are (2, 4) and (6, 8).", "(4, 6)"),
    ("Find the midpoint M of the segment joining A(2, 4) and B(6, 8).", "(4, 6)"),
    ("Find the coordinates of the midpoint of AB where A is (2, 4) and B is (6, 8).", "(4, 6)"),
    (
        "If you roll two dice, what is the probability of getting a sum of 7?",
        "\\frac{1}{6} \\approx 0.1667",
    ),
    ("If I roll two dice, what's the probability the sum is 7?", "\\frac{1}{6} \\approx 0.1667"),
    (
        "What is the probability of rolling two dice and getting a sum of 7?",
        "\\frac{1}{6} \\approx 0.1667",
    ),
    (
        "When rolling two dice, what is the probability of a sum of 8?",
        "\\frac{5}{36} \\approx 0.1389",
    ),
    (
        "Two dice are rolled. What is the probability that their sum is 7?",
        "\\frac{1}{6} \\approx 0.1667",
    ),
    (
        "Two dice are rolled. What is the probability of getting a sum of 7? Express your answer as a fraction.",
        "\\frac{1}{6} \\approx 0.1667",
    ),
    (
        "Kebede throws two dice. What is the probability that the sum is 8?",
        "\\frac{5}{36} \\approx 0.1389",
    ),
    (
        "John draws a card from a deck of 52 cards. What is the probability that he draws a queen?",
        "\\frac{1}{13} \\approx 0.07692",
    ),
    ("If you roll a die, what is the probability of getting a 6?", "\\frac{1}{6} \\approx 0.1667"),
    (
        "What is the probability of rolling a 4 with a fair 6-sided die?",
        "\\frac{1}{6} \\approx 0.1667",
    ),
    (
        "If you draw a card from a standard deck, what's the probability it's a king?",
        "\\frac{1}{13} \\approx 0.07692",
    ),
    (
        "A card is drawn from a standard 52-card deck. What is the probability that it is a king?",
        "\\frac{1}{13} \\approx 0.07692",
    ),
    (
        "What is the probability of drawing a heart from a standard 52-card deck?",
        "\\frac{1}{4} = 0.25",
    ),
    (
        "What is the probability of getting a sum of 7 when you roll two dice?",
        "\\frac{1}{6} \\approx 0.1667",
    ),
    (
        "Two dice are rolled. What is the probability of getting a sum of 7 in simplest form?",
        "\\frac{1}{6} \\approx 0.1667",
    ),
    (
        "Two dice are rolled. Find the probability of getting a sum of 9. Give your answer as a fraction in its simplest form.",
        "\\frac{1}{9} \\approx 0.1111",
    ),
    (
        "Abebe rolls two dice. What is the probability that he gets a sum of 7?",
        "\\frac{1}{6} \\approx 0.1667",
    ),
    (
        "A card is drawn from a deck of 52 cards. What is the probability of drawing a black card that is a king?",
        "\\frac{1}{26} \\approx 0.03846",
    ),
    (
        "The image of P(3, 10) under reflection in line L is P'(7, 2). Find the equation of the line through P and P'.",
        "y = 16 - 2 x",
    ),
    ("Solve 2x + 3 = 7 for x on the interval (0, 10).", "x = 2"),
    ("Solve x^2 = 4 on (0, 5)", None),
    ("Solve x^2 - 5x + 6 = 0 for x in (0, 2.5)", None),
]


@pytest.mark.parametrize(("text", "card"), _FRAMED)
def test_the_frame_of_a_question_is_not_its_content(text: str, card: str | None) -> None:
    from app.modules.math.tools.block import _build_verified_block
    from app.modules.math.tools.extract import extract_math_intent

    intent = extract_math_intent(text)
    settings = Settings(math_tools_enabled=True)
    block = None if intent is None else _build_verified_block(intent, settings)
    shown = None if block is None else (block.display_answer or block.canonical_answer)
    assert shown == card

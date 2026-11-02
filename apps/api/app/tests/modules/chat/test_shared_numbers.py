"""A message that lists numbers is answered about them, never with a greeting.

"Monthly rainfall in Addis Ababa: Jan 15, …, Dec 5 mm" got "Hey bini! How's it going?"
four times in four from the free plan's model (2026-10-24); told what the message was, it
once named November the driest month. The note says so, with the highest and lowest read
from the message.
"""

from __future__ import annotations

import time

import pytest

from app.modules.chat.prompt_constants.shared_numbers import (
    SHARED_NUMBERS_HINT,
    shared_numbers,
    shared_numbers_hint,
)

_RAIN = (
    "Monthly rainfall in Addis Ababa: Jan 15, Feb 30, Mar 60, Apr 85, May 80, Jun 135, "
    "Jul 280, Aug 290, Sep 190, Oct 30, Nov 6, Dec 5 mm"
)


@pytest.mark.parametrize(
    ("text", "highest", "lowest"),
    [
        # The unit on the last item is the series' unit; "Apr" is April, not a loan's APR.
        (_RAIN, "Aug (290 mm)", "Dec (5 mm)"),
        # Money keeps its sign, a minus included.
        ("Profit: Jan -$500, Feb $300, Mar $200", "Feb ($300)", "Jan (-$500)"),
        # A scale on every item; ties name every label.
        ("Q1 10k, Q2 15k, Q3 20k and Q4 20k", "Q3 and Q4 (20k)", "Q1 (10k)"),
        ("steps: Mon 8,200; Tue 6,400; Wed 10,100", "Wed (10,100)", "Tue (6,400)"),
        # One line per item, under a title line.
        ("sales this year\nQ1 100\nQ2 150\nQ3 120", "Q2 (150)", "Q1 (100)"),
        ("growth: 2023 5%, 2024 7%, 2025 6%", "2024 (7%)", "2023 (5%)"),
        (
            "weight log: week 1 80 kg, week 2 79.5 kg, week 3 78.8 kg",
            "week 1 (80 kg)",
            "week 3 (78.8 kg)",
        ),
    ],
)
def test_a_series_gets_its_highest_and_lowest(text: str, highest: str, lowest: str) -> None:
    hint = shared_numbers_hint(text)
    assert hint is not None
    assert hint.startswith(SHARED_NUMBERS_HINT)
    assert hint.endswith(f"the highest is {highest} and the lowest is {lowest}.")


@pytest.mark.parametrize(
    "text",
    [
        # Different things, not one quantity over time: no highest or lowest is stated.
        "Here are my exam marks: math 85, physics 78, chemistry 92, biology 88",
        "Budget: rent $1,500, groceries $400, car $300",
        "GDP: US 27360000000000, China 17790000000000, Japan 4210000000000",
        "Blood test: glucose 95, cholesterol 210, HDL 45, LDL 140, triglycerides 150",
        "Macros today: calories 2000, protein 150, carbs 200, fat 70",
        "Ausgaben: Miete 800, Essen 400, Freizeit 200, Summe 1400",
        "Versions: Python 3.12, Node 20.11, Postgres 16",
        # Times and dates written as one number, and thousands split by a space.
        "Saturday: brunch at 11, movie at 3, dinner at 8",
        "Demain : dentiste 15h, sport 18h, dîner 20h",
        "Exams: math 15 March, physics 18 March, chemistry 22 March",
        "Dépenses : loyer 1 200, courses 2 400, voiture 12 300",
        # A unit or scale on one item is that item's: eggs are not liters, 1.1k is not 950k.
        "Shopping list: eggs 12, bananas 6, milk 2 liters",
        "milk 2 liters, eggs 12, bread 1 loaf",
        "Kids' ages: Tom 5, Ann 8, Sam 6 months",
        "Followers: Jan 800, Feb 950, Mar 1.1k",
        # Scales, units or currencies that differ.
        "Sales: Jan $1.2M, Feb $800K, Mar $950K",
        "Cake: flour 500g, sugar 200g, butter 250g, eggs 4",
        "Coffee: US $5, UK £4, EU €4.5",
    ],
)
def test_other_lists_get_the_note_with_no_highest_or_lowest(text: str) -> None:
    assert shared_numbers_hint(text) == SHARED_NUMBERS_HINT


@pytest.mark.parametrize(
    "text",
    [
        # Asks something in English: a question, a request, a chart, a reminder, a sum.
        "Mon 5h, Tue 7h, Wed 6h, Thu 8h of sleep. How am I doing",
        "rent 1200, food 300, fun 200, can you chart it",
        "make a bar chart: rent 1200, food 300, fun 200",
        "Summarize: rent 1200, food 300, fun 200",
        "remind me to pay rent 1200, water 40 and power 60",
        "what's 15 + 30 + 60",
        "Total 1200, rent 800, food 400",
        "1月 15\n2月 30\n3月 60\n这是多少？",
        # A number left out of the list would make the highest or lowest wrong.
        "rent 1200, food 300, fun 200, transport 100 for 2 people",
        "Jan 15, Feb 30, Mar 60 for 3 years",
        "rent 1200, food 300, fun 200 - is that ok for a family of 4",
        # Numbers in a sentence, not a list of values.
        "My phone number is 555 123 4567",
        "my flight is at 10:30 on Jan 5, gate 23",
        "I'm 25, my brother is 30 and my sister is 22",
        "I ran 5km today",
        "My balance: -$45",
        # Dates and times of day, not amounts to compare.
        "born 1990, married 2015, moved 2020",
        "Tomorrow: dentist 3pm, gym 7pm, dinner 8pm",
        # A loan's or a card's terms are the money reader's.
        "car loan 20000, rate 6, years 5",
        "credit card balance 5000, apr 24, payment 200",
        # Ranges, scores, clock times, fractions, sets: a second number in the item.
        "Lows and highs: Mon 5-12, Tue 7-14, Wed 6-11",
        "Results: Arsenal 2-1, Chelsea 0-0, Spurs 3-2",
        "dentist 3:30, gym 6:15, dinner 7:45",
        "flour 1/2 cup, sugar 3/4 cup, butter 1/4 cup",
        "bench 100x5, squat 140x3, deadlift 180x1",
        # A dot or a space between thousands: twelve hundred, or one point two?
        "Gastos: alquiler 1.200, comida 300, ocio 200",
        "Miete 1.200, Essen 300, Freizeit 200",
        "Dépenses : loyer 1 200, courses 400, voiture 300",
        "Расходы: аренда 25 000, еда 8 000, транспорт 3 000",
        # Dates and phone numbers.
        "Exam dates: math Jan 15, physics Feb 3, chemistry Mar 20",
        "Birthdays: mom March 3, dad July 21, sis Oct 9",
        "Mom 0911234567, Dad 0912345678, Sis 0913456789",
        # Too few, no labels, or units that cannot be compared.
        "rent 1200, food 300",
        "3, 5, 7, 9, 11",
        "hi",
        "",
    ],
)
def test_what_asks_or_is_no_list_gets_no_note(text: str) -> None:
    assert shared_numbers(text) is None
    assert shared_numbers_hint(text) is None


def test_a_personal_disclosure_keeps_its_own_note() -> None:
    """Its note says how to acknowledge it, and must stay the one nearest the user's turn."""
    text = "My expenses: rent $1,500, groceries $400, car $300, phone $60"
    assert shared_numbers(text) is not None
    assert shared_numbers_hint(text) is None


@pytest.mark.wall_clock
@pytest.mark.parametrize(
    "text",
    [
        "a 1, " * 400,
        "x" * 1990 + " 1, b 2, c 3",
        "a" * 40 + " " * 1900 + "1, b 2, c 3",
        "1," * 900,
        "net -$" + "9" * 1500 + ", b 2, c 3",
        # Spaces in a name ran in quadratic time: four seconds.
        "a" + " " * 1990 + "x",
        "Name" + " " * 1500 + "John",
        ("word " * 15 + "1, ") * 30,
    ],
)
def test_reading_a_long_message_stays_quick_and_never_raises(text: str) -> None:
    started = time.perf_counter()
    shared_numbers_hint(text)
    assert time.perf_counter() - started < 0.05

"""A conversion asked in a textbook's words reads as one quantity and the unit to give it
in (2026-10-29: a grade 7 physics book's "reading in Fahrenheit scale when the reading is
310 K" went to the model, which searched the web and cited a homework site)."""

import pytest

from app.modules.math.tools.prompt import needs_symbolic_math
from app.modules.math.tools.school.worded_units import extract_worded_conversion


@pytest.mark.parametrize(
    ("text", "value", "src", "dest"),
    [
        (
            "What will be the temperature reading in Fahrenheit scale when the reading is 310 K?",
            310.0,
            "K",
            "Fahrenheit",
        ),
        (
            "What is the temperature reading in Kelvin scale if the reading in Celsius scale "
            "is 50 °C?",
            50.0,
            "°C",
            "Kelvin",
        ),
        (
            "The temperature of an object is 40 °C. What is this temperature in Fahrenheit scale?",
            40.0,
            "°C",
            "Fahrenheit",
        ),
        ("How many centimeters are there in 9.3 m?", 9.3, "m", "centimeters"),
        ("It's 20 °C outside, what's that in Fahrenheit?", 20.0, "°C", "Fahrenheit"),
        ("How many minutes is 2 hours?", 2.0, "hours", "minutes"),
        ("I ran 5 km today, how many miles is that?", 5.0, "km", "miles"),
        ("Express 2.5 kg in grams", 2.5, "kg", "grams"),
        ("How many days are there in 2 weeks?", 2.0, "weeks", "days"),
        ("How many kg is 150 lbs?", 150.0, "lbs", "kg"),
        ("A 5 kg bag of rice, what is its weight in pounds?", 5.0, "kg", "pounds"),
    ],
)
def test_a_worded_conversion_reads_its_quantity_and_unit(
    text: str, value: float, src: str, dest: str
) -> None:
    intent = extract_worded_conversion(text)
    assert intent is not None
    assert (intent.percent_base, intent.unit_from, intent.unit_to) == (value, src, dest)
    assert needs_symbolic_math(text)


@pytest.mark.parametrize(
    "text",
    [
        # Another kind of unit, a second number, or a question about something else.
        "How many calories in 100 g of rice?",
        "How many km is it from Paris to London in 2 hours?",
        "I ran 5 km in 30 minutes, how fast is that?",
        "how many hours of sleep do I need in 1 day?",
        "My son is 5 feet tall, what size bike in inches?",
        "How many hours do I work in 5 days?",
        "What is 2 km in my running plan?",
        "I have 5 m of rope, what can I make?",
        "Is 40 °C hot?",
        "What's 5 pm in Tokyo time?",
        "how many minutes until 5 pm?",
        "Can you remind me in 5 minutes?",
        "Remind me to drink 2 liters of water in the morning",
        # The converter's own grammar, which turns these down itself.
        "Convert 1 m to cm and tell me a joke",
        "convert pi/2 radians to degrees",
        # Review (2026-10-29): a change of temperature is not a temperature.
        "If the temperature drops by 10 °C, how much is that in Fahrenheit?",
        "The difference between two temperatures is 30 °C. What is this difference in Fahrenheit?",
        "The temperature of a metal rod increases by 50 °C. What is the increase in kelvin?",
        "It's 10 °C below zero, what is it in Fahrenheit?",
        "What is minus 40 °C in Fahrenheit?",
        "What is \u221240 °C in Fahrenheit?",
        # A number written with a comma is not read in half.
        "How many miles is 1,000 km?",
        "What is 10,5 km in miles?",
        # Physics, and a question about something the quantity is not.
        "A gas at 300 K is compressed at constant pressure to half its volume. "
        "What is the final temperature in °C?",
        "Water freezes at 0 °C. What is its boiling point in Fahrenheit?",
        "Normal body temperature is 37 °C. What temperature in Fahrenheit counts as a fever?",
        # Geometry the shape extractors answer.
        "Find the circumference in inches of a circle with radius 3 cm.",
        "A square has side 5 cm. What is its perimeter in mm?",
        "What is the length of the diagonal in cm of a square with side 2 m?",
        # A rate, a share, a reminder.
        "I walk 3 miles a day, how many km in a week?",
        "I sleep 7 hours a night. How many minutes is that in a week?",
        "A tap drips 2 mL per minute. How many liters in a day?",
        "What is half of 10 km in miles?",
        "How many minutes is 1 day and a half?",
        "Remind me to run 5 km tomorrow, how many miles is that?",
        # Everyday questions with a quantity in them.
        "My baby slept 2 hours, how long should the next nap be in minutes?",
        "How long in minutes should I rest after 1 hour of studying?",
        "My daughter is 120 cm tall, what is the average height in inches for her age?",
        "It's 25 °C today. What's the forecast in Fahrenheit for tomorrow?",
        "I finished the race in 25 minutes and came in second, how good is that?",
        "I have 3 inches of rope in hand, how long is it?",
        # Food calories and tons have no one reading.
        "I ate 2000 calories today, how many kJ is that?",
        "How many tons is 5000 kg?",
    ],
)
def test_anything_else_is_not_a_worded_conversion(text: str) -> None:
    assert extract_worded_conversion(text) is None


@pytest.mark.parametrize(
    ("text", "value", "src", "dest"),
    [
        ("2 hr + 20 min + 60 sec are equal to how many minutes?", 8460.0, "sec", "minutes"),
        ("How many minutes are in 1 hr + 30 min?", 90.0, "min", "minutes"),
        ("3 km + 500 m is how many meters?", 3500.0, "m", "meters"),
    ],
)
def test_a_sum_of_amounts_of_one_kind_is_one_amount(
    text: str, value: float, src: str, dest: str
) -> None:
    from app.modules.math.tools.school.worded_units import extract_quantity_sum

    intent = extract_quantity_sum(text)
    assert intent is not None
    assert (intent.percent_base, intent.unit_from, intent.unit_to) == (value, src, dest)


@pytest.mark.parametrize(
    "text",
    ["2 kg + 3 m is how many kg?", "2 apples + 3 apples is how many apples?", "5 + 3 is how many?"],
)
def test_a_sum_of_other_kinds_is_not_one_amount(text: str) -> None:
    from app.modules.math.tools.school.worded_units import extract_quantity_sum

    assert extract_quantity_sum(text) is None

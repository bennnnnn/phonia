"""A chart of the user's own numbers is the chart contract's turn, not maths'.

"Plot this experiment as a scatter plot …" once read as a maths graph with nothing
to verify: the maths note forbade a graph and the chart hint never came, so the
reply said "Here's your scatter plot" and drew none.
"""

from __future__ import annotations

import pytest

from app.modules.chat.prompt_constants import CHART_FORMAT_HINT
from app.modules.chat.prompt_constants.chart import CHART_SHAPES
from app.modules.chat.prompt_format import _style_format_hints
from app.modules.math.tools.extract import extract_math_intent
from app.modules.turn_reading.chart import chart_names_no_curve
from app.services.subjects.dispatch import detect_subject

DATA_CHARTS = (
    "Plot this experiment as a scatter plot with a best-fit line: "
    "x = 1,2,3,4,5 and y = 2.1,3.9,6.2,7.8,10.1",
    "draw a scatter plot of height vs weight: (150,50), (160,55), (170,65)",
    "make a line graph of my monthly sales: jan 10, feb 12, mar 9",
    "Make a bar chart of this data: Mon 12, Tue 19, Wed 7, Thu 15, Fri 22",
    "Make a histogram of these test scores: 55, 62, 68, 70, 71, 75",
    "Make a box plot of these test scores: 55, 62, 68, 70, 71, 75, 78, 80, 82, 85, 88, 90, 95",
    "draw a box and whisker plot for class A: 55, 62, 70 and class B: 61, 72, 93",
)
# Box plot words that ask for no chart.
NOT_CHARTS = (
    "what is a box plot?",
    "what is a box and whisker plot used for",
    "I have a box of plots for my garden, what should I plant?",
    "help me plot the boxes in my moving truck so the heavy ones go first",
    "my box plot homework is due tomorrow",
)
CURVES = (
    "Graph y = sin(x) and y = cos(x) from 0 to 2π",
    "draw the line graph of y = 2x+1",
    "make a bar chart of y = x^2",
    "graph y = x^2",
)


@pytest.mark.parametrize("text", DATA_CHARTS)
def test_a_chart_of_data_is_not_maths_and_gets_the_chart_contract(text: str) -> None:
    assert chart_names_no_curve(text, extract_math_intent)
    assert detect_subject(text) is None
    hints = _style_format_hints(query_text=text, is_day_plan=False, minimal_personal_context=False)
    assert CHART_FORMAT_HINT in hints


@pytest.mark.parametrize("text", NOT_CHARTS)
def test_box_plot_words_that_ask_for_no_chart_get_no_contract(text: str) -> None:
    assert not chart_names_no_curve(text, extract_math_intent)
    hints = _style_format_hints(query_text=text, is_day_plan=False, minimal_personal_context=False)
    assert CHART_FORMAT_HINT not in hints


@pytest.mark.parametrize("text", CURVES)
def test_a_curve_stays_maths(text: str) -> None:
    assert not chart_names_no_curve(text, extract_math_intent)
    assert detect_subject(text) == "math"


def test_a_chart_with_a_statistic_to_find_stays_maths() -> None:
    text = "Make a bar chart of these numbers and find the mean: 3, 5, 7, 9"
    assert detect_subject(text) == "math"
    hints = _style_format_hints(query_text=text, is_day_plan=False, minimal_personal_context=False)
    assert CHART_FORMAT_HINT in hints


def test_the_contract_names_every_shape_it_shows() -> None:
    assert set(CHART_SHAPES) == {
        "bar",
        "line",
        "scatter with best-fit line",
        "histogram",
        "pie",
        "box plot",
    }
    for name, spec in CHART_SHAPES.items():
        assert f"{name}:\n```chart\n" in CHART_FORMAT_HINT
        assert spec["$schema"] == "https://vega.github.io/schema/vega-lite/v5.json"
        assert spec["data"]["values"]  # type: ignore[index]
    # The shapes the phone used to leave blank are named and ruled out.
    assert '"bin": "binned"' in CHART_FORMAT_HINT
    assert "regression" in CHART_FORMAT_HINT
    assert '"fn":"sin(x)"' in CHART_FORMAT_HINT

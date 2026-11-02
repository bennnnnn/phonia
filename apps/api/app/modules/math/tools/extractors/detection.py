"""The extractors the math gate asks once no lexical signal has fired.

These are the requests that carry no equation, operator or command word for a
lexical signal to see, so only the grammar that reads them can say they are maths.
Each read goes through ``readings.read``, and the extraction step that follows a
yes reuses it rather than running the extractor again.

This is a chosen few, not the whole registry: some registry extractors read prose
("compare React and Vue" as two curves) and rely on the gate to keep it away.
"""

from __future__ import annotations

from app.modules.math.tools.extractors.calculus import _extract_critical_points_intent
from app.modules.math.tools.extractors.calculus_applications import CALCULUS_APPLICATION_EXTRACTORS
from app.modules.math.tools.extractors.fractions import extract_fraction_intent
from app.modules.math.tools.extractors.functions import _extract_function_analysis_intent
from app.modules.math.tools.extractors.geometry import _extract_square_intent
from app.modules.math.tools.extractors.readings import Reader, read
from app.modules.math.tools.function_def import substituted_eval_expr
from app.modules.math.tools.school.algebra_facts import extract_algebra_fact_intent
from app.modules.math.tools.school.arithmetic import extract_arithmetic_formulas
from app.modules.math.tools.school.bag_draws import extract_bag_draws_intent
from app.modules.math.tools.school.equation_features import extract_equation_feature_intent
from app.modules.math.tools.school.function_value import extract_function_value_intent
from app.modules.math.tools.school.geometry_facts import extract_geometry_fact_intent
from app.modules.math.tools.school.geometry_measures import extract_geometry_measure_intent
from app.modules.math.tools.school.number_facts import extract_number_fact_intent
from app.modules.math.tools.school.probability import extract_at_least_one_intent
from app.modules.math.tools.school.shopping import extract_change_intent
from app.modules.math.tools.school.single_draw import extract_single_draw_intent
from app.modules.math.tools.school.units import extract_how_many_in_intent
from app.modules.math.tools.school.worded_units import (
    extract_quantity_sum,
    extract_worded_conversion,
)
from app.services.text_match import word_index

_ALWAYS_ASKED: tuple[Reader, ...] = (
    # "3/4 divided by 2/5", "2/3 of 60": the fraction grammar reads the whole request.
    extract_fraction_intent,
    # "if f(x) = 3x + 1, what is f(2)": a function's value at a number.
    extract_function_value_intent,
    # Area under or between curves, arc length, volume, tangents, stationary points.
    *CALCULUS_APPLICATION_EXTRACTORS,
    # A missing leg or polygon angles; roots, percentages, standard form and
    # sums in words; completing the square and the cosine rule.
    extract_geometry_fact_intent,
    extract_geometry_measure_intent,
    extract_number_fact_intent,
    extract_algebra_fact_intent,
    extract_equation_feature_intent,
    # "probability of rolling a sum of 7 with two dice", "drawing a king from a deck".
    extract_single_draw_intent,
    # "a bag has 3 red and 5 blue marbles, pick 2 without replacement, probability both red".
    extract_bag_draws_intent,
    # "the probability of getting at least one head in 3 coin flips".
    extract_at_least_one_intent,
    # "how many seconds in a day": a conversion between two units of fixed size.
    extract_how_many_in_intent,
    # "What is this temperature in Fahrenheit scale?": one quantity, one unit to give it in.
    extract_worded_conversion,
    # "2 hr + 20 min + 60 sec are equal to how many minutes?"
    extract_quantity_sum,
    # "I bought 3 notebooks at $2.40 each ... I paid with a $20 bill. how much change".
    extract_change_intent,
)
# Domain, range, inverse and composition are not ordinary calculus command words,
# so they route only when the dedicated extractor consumes the whole ask.
_FUNCTION_ANALYSIS_CUES = ("domain of", "range of", "inverse function", "inverse of", "compose")
_CRITICAL_POINT_CUES = ("critical point", "extrema", "local max", "local min")


def an_extractor_reads(cleaned: str, lower: str) -> bool:
    """True when one of the gate's extractors reads the prepared line."""
    if any(read(reader, cleaned) is not None for reader in _ALWAYS_ASKED):
        return True
    # "Let x = 5. What is x + 2?"
    if "=" in cleaned and substituted_eval_expr(cleaned) is not None:
        return True
    if word_index(lower, "square") != -1 and read(_extract_square_intent, cleaned) is not None:
        return True
    if (
        any(cue in lower for cue in _FUNCTION_ANALYSIS_CUES)
        and read(_extract_function_analysis_intent, cleaned) is not None
    ):
        return True
    if any(cue in lower for cue in _CRITICAL_POINT_CUES):
        critical = read(_extract_critical_points_intent, cleaned)
        if critical is not None and critical.expr:
            return True
    # Percent change from 40 to 50, the price before a 20% discount, ...
    return (
        any(ch.isdigit() for ch in cleaned)
        and read(extract_arithmetic_formulas, cleaned) is not None
    )

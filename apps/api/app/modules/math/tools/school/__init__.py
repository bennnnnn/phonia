"""School extractors and verified blocks. Registry order is the behavior."""

from __future__ import annotations

from collections.abc import Callable

from app.core.config import Settings
from app.modules.math.schemas import MathIntent
from app.modules.math.tools.block import VerifiedMathBlock
from app.modules.math.tools.extractors.fractions import extract_fraction_intent
from app.modules.math.tools.extractors.teaching import extract_teaching_intent
from app.modules.math.tools.school.algebra_facts import extract_algebra_fact_intent
from app.modules.math.tools.school.arithmetic import (
    _extract_arithmetic_intent,
    _verified_block_arithmetic,
)
from app.modules.math.tools.school.calculus import (
    _extract_taylor_or_ode,
    apply_calculus_extension,
)
from app.modules.math.tools.school.complex import (
    _extract_complex_intent,
    _verified_block_complex,
)
from app.modules.math.tools.school.coordinate import (
    _extract_coord_intent,
    _verified_block_coord,
)
from app.modules.math.tools.school.equation_features import extract_equation_feature_intent
from app.modules.math.tools.school.function_value import extract_function_value_intent
from app.modules.math.tools.school.geometry_facts import extract_geometry_fact_intent
from app.modules.math.tools.school.geometry_measures import extract_geometry_measure_intent
from app.modules.math.tools.school.number_facts import extract_number_fact_intent
from app.modules.math.tools.school.probability import (
    _extract_probability_intent,
    _verified_block_probability,
)
from app.modules.math.tools.school.statistics import _extract_z_score_intent
from app.modules.math.tools.school.trig import _extract_trig_intent, _verified_block_trig
from app.modules.math.tools.school.units import _extract_unit_intent, _verified_block_unit
from app.modules.math.tools.school.vectors import (
    _extract_vector_intent,
    _verified_block_vector,
)

__all__ = [
    "SCHOOL_BLOCK_BUILDERS",
    "SCHOOL_EXTRACTORS",
    "_extract_unit_intent",
    "apply_calculus_extension",
]

_SchoolBlockBuilder = Callable[[MathIntent, Settings, list[str]], VerifiedMathBlock | None]

SCHOOL_EXTRACTORS: list[Callable[[str], MathIntent | None]] = [
    extract_teaching_intent,
    # Before anything reads ``f(x) = ...`` as an equation to solve.
    extract_function_value_intent,
    extract_geometry_fact_intent,
    extract_geometry_measure_intent,
    extract_number_fact_intent,
    extract_algebra_fact_intent,
    # Before an equation is solved for x: "find the vertex of y = ..." asks
    # for the vertex.
    extract_equation_feature_intent,
    _extract_unit_intent,
    _extract_coord_intent,
    _extract_vector_intent,
    _extract_z_score_intent,
    _extract_taylor_or_ode,
    _extract_trig_intent,
    _extract_probability_intent,
    _extract_complex_intent,
    extract_fraction_intent,
    _extract_arithmetic_intent,
]

SCHOOL_BLOCK_BUILDERS: dict[str, _SchoolBlockBuilder] = {
    "arithmetic": _verified_block_arithmetic,
    "trig": _verified_block_trig,
    "coord": _verified_block_coord,
    "vector": _verified_block_vector,
    "probability": _verified_block_probability,
    "complex": _verified_block_complex,
    "unit": _verified_block_unit,
}

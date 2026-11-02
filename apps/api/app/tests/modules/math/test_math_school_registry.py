"""School registries keep the order that decides which extractor wins."""

from __future__ import annotations

from app.modules.math.tools.school import SCHOOL_BLOCK_BUILDERS, SCHOOL_EXTRACTORS


def test_school_extractor_order_and_builder_keys() -> None:
    assert [extractor.__qualname__ for extractor in SCHOOL_EXTRACTORS] == [
        "extract_teaching_intent",
        "extract_function_value_intent",
        "extract_geometry_fact_intent",
        "extract_geometry_measure_intent",
        "extract_number_fact_intent",
        "extract_algebra_fact_intent",
        "extract_equation_feature_intent",
        "_extract_unit_intent",
        "_extract_coord_intent",
        "_extract_vector_intent",
        "_extract_z_score_intent",
        "_extract_taylor_or_ode",
        "_extract_trig_intent",
        "_extract_probability_intent",
        "_extract_complex_intent",
        "extract_fraction_intent",
        "_extract_arithmetic_intent",
    ]
    assert list(SCHOOL_BLOCK_BUILDERS) == [
        "arithmetic",
        "trig",
        "coord",
        "vector",
        "probability",
        "complex",
        "unit",
    ]

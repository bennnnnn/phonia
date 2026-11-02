"""Every physics variable declares the dimension the unit check uses.

The catalog is that list. A param that reaches a solver without a declaration
can be converted by Pint into the wrong dimension: lowercase ``pa`` is a
petayear, ``t`` is a tonne, and ``c`` is the speed of light.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app.modules.physics.catalog import CATALOG
from app.modules.physics.schemas import PhysicsIntent
from app.modules.physics.solvers.si import PARAM_SI_DIMENSIONS
from app.services.units import get_unit_registry
from app.tests.modules.physics.support import extract_physics_intent

_TESTS = Path(__file__).resolve().parent


def _pinned_questions() -> list[str]:
    """Every string the physics suites pin, including the school-extension rows."""
    questions: list[str] = []
    for path in sorted(_TESTS.glob("test_physics_*.py")):
        if path.name == Path(__file__).name:
            continue
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                questions.append(node.value)
    return questions


def _solved_questions() -> list[str]:
    solved: list[str] = []
    for text in _pinned_questions():
        intent = extract_physics_intent(text)
        if isinstance(intent, PhysicsIntent) and intent.physics_op:
            solved.append(text)
    return solved


def test_the_corpus_covers_the_school_extension_suites() -> None:
    solved = _solved_questions()
    assert len(solved) > 200
    ops = set()
    for text in solved:
        intent = extract_physics_intent(text)
        assert intent is not None and intent.physics_op is not None
        ops.add(intent.physics_op)
    assert "poiseuille_flow" in ops
    assert "angular_displacement_rate" in ops
    assert "angular_velocity" in ops


def test_every_catalog_variable_declares_a_real_dimension() -> None:
    ureg = get_unit_registry()
    broken: list[tuple[str, str]] = []
    for spec in CATALOG.values():
        assert spec.variables, f"{spec.id} declares no variables"
        for variable in spec.variables:
            if variable.dimensionless:
                assert variable.dimension is None
                continue
            assert variable.dimension is not None
            try:
                ureg(variable.dimension)
            except Exception:
                broken.append((f"{spec.id}.{variable.name}", variable.dimension))
    assert not broken, f"unparseable dimension specs: {broken}"


def test_unit_checks_read_dimensions_from_the_catalog() -> None:
    for spec in CATALOG.values():
        for variable in spec.variables:
            dimension = "dimensionless" if variable.dimensionless else variable.dimension
            assert PARAM_SI_DIMENSIONS[variable.name] == dimension


@pytest.mark.parametrize("text", _solved_questions())
def test_solved_intent_params_are_declared_on_the_operation(text: str) -> None:
    intent = extract_physics_intent(text)
    assert isinstance(intent, PhysicsIntent)
    assert intent.physics_op is not None
    declared = {variable.name for variable in CATALOG[intent.physics_op].variables}
    undeclared = [key for key in (intent.physics_params or {}) if key not in declared]
    assert not undeclared, f"{intent.physics_op} does not declare {undeclared}"

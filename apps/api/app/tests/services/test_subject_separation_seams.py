"""Static and behavioral seams that keep math and physics as peer subjects."""

from __future__ import annotations

import ast
import subprocess
import sys
import typing
from pathlib import Path

import pytest

from app.modules.math.schemas import MathIntent
from app.modules.physics.schemas import PhysicsIntent
from app.services.subjects.dispatch import detect_subject

_APP_DIR = Path(__file__).resolve().parents[2]
_MATH_PATHS = (_APP_DIR / "modules" / "math", _APP_DIR / "models" / "schemas" / "math")
_PHYSICS_DIR = _APP_DIR / "modules" / "physics"

# Physics trajectories reuse the same native graph transport as mathematical
# plots. This is a renderer primitive, not math extraction or solving logic.
_ALLOWED_PHYSICS_IMPORTS_FROM_MATH = frozenset({("app.modules.math.schemas", "GraphBlockSpec")})


def _imports_below(path: Path, package: str) -> set[tuple[str, str]]:
    found: set[tuple[str, str]] = set()
    tree = ast.parse(path.read_text(), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            if node.module == package or node.module.startswith(f"{package}."):
                found.update((node.module, alias.name) for alias in node.names)
        elif isinstance(node, ast.Import):
            found.update(
                (alias.name, "*")
                for alias in node.names
                if alias.name == package or alias.name.startswith(f"{package}.")
            )
    return found


def test_math_package_has_no_physics_dependency() -> None:
    offenders: dict[str, set[tuple[str, str]]] = {}
    for root in _MATH_PATHS:
        for path in sorted(root.rglob("*.py")):
            imports = _imports_below(path, "app.modules.physics") | _imports_below(
                path, "app.modules.physics.schemas"
            )
            if imports:
                offenders[str(path.relative_to(_APP_DIR))] = imports
    assert offenders == {}


def test_physics_imports_only_the_shared_graph_transport_from_math() -> None:
    offenders: dict[str, set[tuple[str, str]]] = {}
    for path in sorted(_PHYSICS_DIR.rglob("*.py")):
        imports = _imports_below(path, "app.modules.math") | _imports_below(
            path, "app.modules.math.schemas"
        )
        unexpected = imports - _ALLOWED_PHYSICS_IMPORTS_FROM_MATH
        if unexpected:
            offenders[str(path.relative_to(_APP_DIR))] = unexpected
    assert offenders == {}


def test_math_prompt_has_no_physics_policy() -> None:
    from app.modules.math.reply_policy import MATH_SOLVER_HINT

    assert "physics" not in MATH_SOLVER_HINT.lower()
    assert "projectile" not in MATH_SOLVER_HINT.lower()
    assert "simulation" not in MATH_SOLVER_HINT.lower()


def test_math_and_physics_intent_kinds_are_disjoint() -> None:
    math_kinds = set(typing.get_args(MathIntent.model_fields["kind"].annotation))
    physics_kinds = set(typing.get_args(PhysicsIntent.model_fields["kind"].annotation))
    assert math_kinds.isdisjoint(physics_kinds)


def test_subject_registries_exactly_cover_their_own_kind_spaces() -> None:
    from app.modules.math.tools.block import _BLOCK_BUILDERS
    from app.modules.math.tools.school import SCHOOL_BLOCK_BUILDERS
    from app.modules.physics.catalog import CATALOG

    math_kinds = set(typing.get_args(MathIntent.model_fields["kind"].annotation))
    physics_kinds = set(typing.get_args(PhysicsIntent.model_fields["kind"].annotation))
    assert math_kinds == set(_BLOCK_BUILDERS) | set(SCHOOL_BLOCK_BUILDERS)
    assert physics_kinds == {spec.kind for spec in CATALOG.values()}


@pytest.mark.parametrize(
    "text, expected",
    [
        ("solve 2x + 3 = 11", "math"),
        ("differentiate x^3", "math"),
        ("find the average speed for 100 m in 20 s", "physics"),
        ("find the force on a 2 kg mass accelerating at 3 m/s^2", "physics"),
    ],
)
def test_subject_detection_routes_directly_to_one_peer(text: str, expected: str) -> None:
    assert detect_subject(text) == expected


def test_neutral_solving_module_does_not_build_math_blocks() -> None:
    source = (_APP_DIR / "services" / "solving.py").read_text()
    assert "def _finish_with_answer" not in source
    assert "def _diagram_block" not in source
    assert "def _answer_canonical" not in source


@pytest.mark.parametrize(
    "module",
    [
        "app.services.solving",
        "app.services.subjects.registry",
        "app.services.subjects.dispatch",
        "app.services.symbolic_text",
        "app.services.unit_text",
        "app.modules.math.schemas",
        "app.modules.physics.schemas",
        "app.modules.math.tools.extract",
        "app.modules.physics.extract",
        "app.modules.math.subject",
        "app.modules.physics.subject",
        "app.modules.chemistry.subject",
    ],
)
def test_subject_and_neutral_modules_import_cold(module: str) -> None:
    result = subprocess.run(  # noqa: S603 - fixed argv and parametrized literals
        [sys.executable, "-c", f"import {module}"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"{module} failed to import cold:\n{result.stderr}"

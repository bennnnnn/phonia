"""A constant with one home is never typed as a number anywhere else in the app.

The Celsius offset is ``services.units.CELSIUS_OFFSET_K``, and 25 °C and 100 °C are written
from it; c, e and mₑ are Pint's, read once in ``physics.constants``. A typed copy can drift
from its source or round differently.
"""

from __future__ import annotations

import ast

from .boundary_support import APP_ROOT

# Each value, with the one file allowed to write it (None: only Pint does).
_OWNED: dict[float, str | None] = {
    273.15: "services/units.py",
    298.15: None,
    373.15: None,
    299792458.0: None,
    1.602176634e-19: None,
    9.1093837015e-31: None,
}


def test_no_module_types_a_constant_that_has_a_home() -> None:
    typed: list[str] = []
    for path in sorted(APP_ROOT.rglob("*.py")):
        relative = path.relative_to(APP_ROOT).as_posix()
        if relative.startswith("tests/"):
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Constant) or isinstance(node.value, bool):
                continue
            if isinstance(node.value, int | float):
                home = _OWNED.get(float(node.value), relative)
                if home != relative:
                    typed.append(f"{relative}:{node.lineno} {node.value!r}")
    assert not typed, typed

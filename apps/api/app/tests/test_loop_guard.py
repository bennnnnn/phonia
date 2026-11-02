"""The loop guard (``loop_guard.py``) sees SymPy run on the event loop by production code."""

from __future__ import annotations

from typing import Any

from app.tests import loop_guard


async def test_sympy_on_the_loop_from_production_code_is_recorded() -> None:
    namespace: dict[str, Any] = {"__name__": "app.modules.fake_turn"}
    exec(  # noqa: S102 - a coroutine whose frames carry a production module name
        "import sympy\nasync def prepare():\n    return sympy.sympify('1 + 1')\n",
        namespace,
    )
    await namespace["prepare"]()

    found, loop_guard.found[:] = list(loop_guard.found), []
    # ``sympify`` parses with ``parse_expr``: both entry points saw it.
    assert found == [
        "sympy.sympify from app.modules.fake_turn.prepare",
        "sympy.parse_expr from app.modules.fake_turn.prepare",
    ]


async def test_a_test_running_sympy_itself_is_not_a_finding() -> None:
    import sympy

    sympy.sympify("1 + 1")
    assert loop_guard.found == []


def test_sympy_off_the_loop_is_not_a_finding() -> None:
    import sympy

    sympy.sympify("1 + 1")
    assert loop_guard.found == []

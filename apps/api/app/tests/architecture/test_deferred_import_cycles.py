"""A cycle through deferred imports may only shrink.

``test_import_cycles`` allows no cycle among the imports that run at load time. An
import deferred into a function fixes the load order but leaves the dependency: the two
modules still need each other. Counting those imports too, today's cycles are recorded
in ``import_cycle_baseline.json``: each one's modules and how many imports run between
them. No new cycle may form, none may take in more modules or more imports, and two may
not join. The fix for a cycle is shared code moved below both modules, not another
deferred import.

When a cycle shrinks, or a module in one is renamed or moved (the same number of modules,
no more imports), rerun with ``UPDATE_IMPORT_CYCLES=1``: it records the cycles as they
are and prints each changed one. It never records a larger cycle.

``importlib.import_module("app.x")`` counts as an import of ``app.x``. One whose name is
computed (``f"app.modules.chat.{name}"``, a lazy package's ``__getattr__``) cannot be
followed, so each is listed below by hand: a new one fails until it is reviewed and listed.
"""

from __future__ import annotations

import ast
import json
import os
from dataclasses import asdict, dataclass
from functools import cache
from pathlib import Path

import pytest

from .boundary_support import (
    _import_cycles,
    _import_graph,
    _module_imports,
    _named_dynamic_imports,
    computed_dynamic_imports,
    computed_import_keys,
)

_BASELINE = Path(__file__).with_name("import_cycle_baseline.json")


@dataclass(frozen=True)
class _Cycle:
    modules: list[str]
    imports: int


def _cycles_of(graph: dict[str, set[str]]) -> list[_Cycle]:
    """Each cycle's modules, and the imports that run between them."""
    cycles = []
    for members in sorted(_import_cycles(graph)):
        inside = set(members)
        cycles.append(_Cycle(members, sum(len(graph[module] & inside) for module in members)))
    return cycles


@cache
def _cycles() -> tuple[_Cycle, ...]:
    """Modules that reach one another through any import that can run."""
    return tuple(_cycles_of(_import_graph(_module_imports(load_time=False, runtime=True))))


def _changed_home(cycle: _Cycle, home: _Cycle) -> tuple[str | None, str | None]:
    """(how ``cycle`` grew past its recorded ``home``, how it changed without growing)."""
    size = len(home.modules)
    gained = sorted(set(cycle.modules) - set(home.modules))
    if len(cycle.modules) > size:
        return f"the cycle of {size} grew to {len(cycle.modules)}, taking in " + ", ".join(
            gained
        ), None
    if cycle.imports > home.imports:
        return (
            f"the cycle of {size} holding {home.modules[0]} has {cycle.imports} imports among"
            f" its modules, {home.imports} recorded"
        ), None
    if gained:
        lost = sorted(set(home.modules) - set(cycle.modules))
        return (
            None,
            f"the cycle of {size} now holds {', '.join(gained)} instead of {', '.join(lost)}",
        )
    if cycle != home:
        return None, (
            f"the cycle of {size} holding {home.modules[0]} is down to {len(cycle.modules)}"
            f" modules and {cycle.imports} imports"
        )
    return None, None


def _compare(cycles: tuple[_Cycle, ...], recorded: list[_Cycle]) -> tuple[list[str], list[str]]:
    """(cycles that grew, cycles that changed without growing)."""
    grown: list[str] = []
    changed: list[str] = []
    for cycle in cycles:
        homes = [known for known in recorded if set(cycle.modules) & set(known.modules)]
        if not homes:
            grown.append(f"a new cycle of {len(cycle.modules)}: " + ", ".join(cycle.modules))
        elif len(homes) > 1:
            sizes = " and ".join(str(len(known.modules)) for known in homes)
            grown.append(
                f"a cycle of {len(cycle.modules)} joins modules of the recorded cycles of"
                f" {sizes}: " + ", ".join(cycle.modules)
            )
        else:
            growth, change = _changed_home(cycle, homes[0])
            grown.extend([growth] if growth else [])
            changed.extend([change] if change else [])
    current = [set(cycle.modules) for cycle in cycles]
    for known in recorded:
        if not any(members & set(known.modules) for members in current):
            changed.append(f"the cycle of {len(known.modules)} holding {known.modules[0]} is gone")
    return grown, changed


def _recorded(cycles: tuple[_Cycle, ...]) -> list[_Cycle]:
    recorded = [_Cycle(**entry) for entry in json.loads(_BASELINE.read_text())]
    grown, changed = _compare(cycles, recorded)
    if os.environ.get("UPDATE_IMPORT_CYCLES") and not grown and changed:
        print("recorded import cycles that changed without growing:\n  " + "\n  ".join(changed))
        recorded = list(cycles)
        _BASELINE.write_text(json.dumps([asdict(cycle) for cycle in recorded], indent=2) + "\n")
    return recorded


def test_compare_names_grown_and_changed_cycles() -> None:
    recorded = [_Cycle(["a", "b", "c"], 3), _Cycle(["d", "e"], 2)]
    assert _compare((_Cycle(["a", "b", "c"], 3), _Cycle(["d", "e"], 2)), recorded) == ([], [])
    assert _compare((_Cycle(["x", "y"], 2),), recorded)[0] == ["a new cycle of 2: x, y"]
    assert _compare((_Cycle(["a", "b", "c", "z"], 4),), recorded)[0] == [
        "the cycle of 3 grew to 4, taking in z"
    ]
    assert _compare((_Cycle(["a", "b", "c"], 4),), recorded)[0] == [
        "the cycle of 3 holding a has 4 imports among its modules, 3 recorded"
    ]
    assert _compare((_Cycle(["c", "d"], 2),), recorded)[0] == [
        "a cycle of 2 joins modules of the recorded cycles of 3 and 2: c, d"
    ]
    renamed = _compare((_Cycle(["a", "b", "c2"], 3), _Cycle(["d", "e"], 2)), recorded)
    assert renamed == ([], ["the cycle of 3 now holds c2 instead of c"])
    assert _compare((_Cycle(["a", "b"], 2),), recorded) == (
        [],
        [
            "the cycle of 3 holding a is down to 2 modules and 2 imports",
            "the cycle of 2 holding d is gone",
        ],
    )


def test_no_deferred_import_cycle_forms_or_grows() -> None:
    cycles = _cycles()
    grown, _ = _compare(cycles, _recorded(cycles))
    assert grown == [], (
        "the import graph got more tangled. Move the code both modules need into a module"
        " below them instead of deferring an import; UPDATE_IMPORT_CYCLES=1 never records"
        " growth.\n  " + "\n  ".join(grown)
    )


def test_the_recorded_cycles_are_current() -> None:
    cycles = _cycles()
    _, changed = _compare(cycles, _recorded(cycles))
    assert changed == [], (
        "the cycles changed without growing (smaller, or a module renamed or moved): rerun"
        " this test with UPDATE_IMPORT_CYCLES=1 to record them.\n  " + "\n  ".join(changed)
    )


# Lazy packages' ``__getattr__`` (each imports only the names its own table lists) and the
# prompt-rule reader's walk over its rule homes.
_COMPUTED_DYNAMIC_IMPORTS = frozenset(
    {
        "modules/billing/__init__.py: f'app.modules.billing.{module_name}'",
        "modules/billing/__init__.py: f'app.modules.billing.{name}'",
        "modules/chat/__init__.py: f'app.modules.chat.{module_name}'",
        "modules/chat/__init__.py: f'app.modules.chat.{name}'",
        "modules/chat/prompt_rule_text.py: f'{home.__name__}.{name}'",
        "modules/chat/turn_prep/__init__.py: f'app.modules.chat.turn_prep.{module}'",
        "modules/math/__init__.py: f'app.modules.math.{module_name}'",
        "modules/memory/__init__.py: f'app.modules.memory.{module}'",
        "modules/memory/__init__.py: f'app.modules.memory.{name}'",
        "modules/notifications/__init__.py: f'app.modules.notifications.{module_name}'",
        "modules/physics/__init__.py: f'app.modules.physics.{module_name}'",
        "modules/todos/__init__.py: f'app.modules.todos.{module_name}'",
        "modules/web_search/__init__.py: f'app.modules.web_search.{module}'",
        "modules/web_search/__init__.py: f'app.modules.web_search.{name}'",
    }
)


def test_every_computed_dynamic_import_is_listed() -> None:
    found = computed_dynamic_imports()
    new = sorted(found - _COMPUTED_DYNAMIC_IMPORTS)
    gone = sorted(_COMPUTED_DYNAMIC_IMPORTS - found)
    assert not new, (
        "a dynamic import the import graph cannot follow (its cycles stay hidden): import "
        "the module by name, or review it and list it here:\n  " + "\n  ".join(new)
    )
    assert not gone, "listed dynamic imports no longer found; remove them:\n  " + "\n  ".join(gone)


def test_a_dynamic_import_by_name_is_an_edge() -> None:
    tree = ast.parse(
        "import importlib\nfrom importlib import import_module\n"
        "def f():\n    importlib.import_module('app.a')\n    import_module('app.b')\n"
        "    import_module(f'app.c.{x}')\n"
    )
    assert _named_dynamic_imports(tree) == {"app.a", "app.b"}


# 2026-11-01: each of these imported a module by name past the graph.
@pytest.mark.parametrize(
    ("source", "named"),
    [
        ("from importlib import import_module\nimport_module(name='app.x')", {"app.x"}),
        ("from importlib import import_module as load\nload('app.x')", {"app.x"}),
        ("import importlib as il\nil.import_module('app.x')", {"app.x"}),
        ("__import__('app.x')", {"app.x"}),
        ("import builtins\nbuiltins.__import__('app.x')", {"app.x"}),
        (
            "from importlib import import_module\nimport_module('.x', package='app.pkg')",
            {"app.pkg.x"},
        ),
        ("from importlib import import_module\nimport_module('..y', 'app.pkg.sub')", {"app.pkg.y"}),
        (
            "from importlib import import_module\nimport_module('.x', package=__package__)",
            {"app.own.x"},
        ),
        ("from importlib import import_module\nimport_module('.x')", set()),
        ("__import__('x', globals(), None, [], 1)", set()),
    ],
)
def test_every_spelling_of_a_dynamic_import_is_read(source: str, named: set[str]) -> None:
    assert _named_dynamic_imports(ast.parse(source), "app.own") == named


def test_two_computed_imports_in_one_file_are_listed_apart() -> None:
    tree = ast.parse(
        "from importlib import import_module as load\n"
        "def f(n):\n    load(f'app.{n}')\n    load('app.fixed')\n    return load(f'app.{n}')\n"
    )
    assert computed_import_keys("x.py", tree) == {"x.py: f'app.{n}'", "x.py: f'app.{n}' #2"}

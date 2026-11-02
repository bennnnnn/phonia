"""Production code has no import cycles: they are eliminated, not ignored.

The graph holds the imports that run when a module loads. One inside a function is
left out, since deferring an import is the accepted way to break a load-order cycle,
and so is one under ``if TYPE_CHECKING``, which never runs.
"""

import ast

from .boundary_support import _import_cycles, _import_graph, _load_time_imports, _module_imports


def test_load_time_imports_skip_functions_and_type_checking() -> None:
    tree = ast.parse(
        "from typing import TYPE_CHECKING\n"
        "import app.a\n"
        "try:\n    import app.b\nexcept ImportError:\n    import app.c\n"
        "if TYPE_CHECKING:\n    import app.d\nelse:\n    import app.e\n"
        "class Model:\n    import app.f\n"
        "def later():\n    import app.g\n"
    )
    found = [alias.name for node in _load_time_imports(tree.body) for alias in node.names]
    assert found == ["TYPE_CHECKING", "app.a", "app.b", "app.c", "app.e", "app.f"]


def test_import_cycles_are_the_components_of_more_than_one_module() -> None:
    graph = {"a": {"b"}, "b": {"c"}, "c": {"a"}, "d": {"a", "e"}, "e": {"d"}, "f": set()}
    assert _import_cycles(graph) == [["a", "b", "c"], ["d", "e"]]
    assert _import_cycles({"a": {"b"}, "b": set()}) == []


def test_production_code_has_no_import_cycles() -> None:
    cycles = _import_cycles(_import_graph(_module_imports(load_time=True)))
    assert not cycles, "\n\n".join(
        f"{len(cycle)} modules import one another at load time:\n  " + "\n  ".join(cycle)
        for cycle in cycles
    )

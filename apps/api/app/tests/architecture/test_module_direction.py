"""Modules depend one way; every import that runs upward is named (code-health audit ARCH-11).

The cycle test reads files at load time, so a cycle between modules hid behind imports
in functions, and nothing said which way modules may depend. Here every import that can
run counts, inside a function too (one under ``if TYPE_CHECKING`` does not), collapsed
to the components it joins (``modules.<name>``, ``services.<name>``), in four layers:

0. the shared leaves in ``services/``;
1. the subjects: maths, physics, chemistry;
2. the product features, and the subjects' registry, order and dispatcher;
3. chat, which runs a turn over all of them.

A component imports its own layer or a lower one. An import that runs upward is listed
below with why it stays; the list only shrinks, and without it the graph has no cycle.
"""

from __future__ import annotations

from .boundary_support import _import_cycles, _import_graph, _module_imports

_SUBJECTS = frozenset({"math", "physics", "chemistry"})
# The subjects' registry, the order between them (ST-05) and the dispatcher that asks them
# (ST-07, ``services/subjects/``) sit over the subjects they send a message to, under chat.
# The readers of a message are leaves: they import only services, so a subject may ask
# them too (ST-04).
_LAYER_OF = {
    "services.subjects": 2,
    "modules.turn_reading": 0,
}
# A composition root wires every module together (test_outside_modules.py).
_ROOTS = frozenset({"app.services.mcp"})

# Upward imports, each with why it stays. Take one off when its import goes.
_UPWARD = {
    ("modules.account", "modules.chat"): "deletion drops chat's cached follow-up questions",
    ("modules.images", "modules.chat"): "a picture turn sets off chat's post-turn jobs; a cut cue",
    ("modules.physics", "modules.chat"): "a direct reply is presented as chat presents one",
    (
        "modules.speech",
        "modules.chat",
    ): "a voice turn sets off chat's post-turn jobs and presentation",
    ("services.quota", "modules.billing"): "a daily budget is the plan's number (entitlements)",
}


def _component(module: str) -> str | None:
    parts = module.split(".")
    if len(parts) >= 3 and parts[1] in {"modules", "services"}:
        return f"{parts[1]}.{parts[2]}"
    return None


def _layer(component: str) -> int:
    if component in _LAYER_OF:
        return _LAYER_OF[component]
    kind, name = component.split(".", 1)
    if kind == "services":
        return 0
    if name in _SUBJECTS:
        return 1
    return 3 if name == "chat" else 2


def _edges() -> set[tuple[str, str]]:
    edges: set[tuple[str, str]] = set()
    for source, targets in _import_graph(_module_imports(load_time=False, runtime=True)).items():
        start = _component(source)
        if start is None or source in _ROOTS:
            continue
        for target in targets:
            end = _component(target)
            if end is not None and end != start:
                edges.add((start, end))
    return edges


def test_every_upward_import_is_named() -> None:
    upward = {edge for edge in _edges() if _layer(edge[0]) < _layer(edge[1])}
    new = sorted(upward - set(_UPWARD))
    assert not new, f"these import upward: depend downward, or name them with a reason: {new}"
    gone = sorted(set(_UPWARD) - upward)
    assert not gone, f"these imports are gone: take them off the list: {gone}"


def _subject_module(module: str, subjects: frozenset[str] = _SUBJECTS) -> bool:
    parts = module.split(".")
    return len(parts) >= 3 and parts[1] == "modules" and parts[2] in subjects


def test_the_dispatcher_asks_a_subject_only_through_its_adapter() -> None:
    """The dispatcher reaches a subject through the registry (ST-07), never directly."""
    imports = _module_imports(load_time=False, runtime=True)
    dispatcher = "app.services.subjects.dispatch"
    assert dispatcher in imports
    assert any(_subject_module(target) for target in imports["app.services.subjects.registry"])
    assert sorted(filter(_subject_module, imports[dispatcher])) == []


def test_chat_imports_no_subject() -> None:
    """Chat asks a subject, and money beside them, through the registry (ST-07), never
    directly: every import counts, one for an annotation too."""
    peers = _SUBJECTS | {"money"}
    reached = sorted(
        f"{module} imports {target}"
        for module, targets in _module_imports(load_time=False).items()
        if module.startswith("app.modules.chat")
        for target in targets
        if _subject_module(target, peers)
    )
    assert reached == []


def test_without_the_named_imports_the_modules_form_no_cycle() -> None:
    graph: dict[str, set[str]] = {}
    for start, end in _edges() - set(_UPWARD):
        graph.setdefault(start, set()).add(end)
        graph.setdefault(end, set())
    assert _import_cycles(graph) == []

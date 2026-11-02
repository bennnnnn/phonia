"""Direct callers of the readers behind a turn's decisions are listed, with why (ST-05).

These tests police who calls a reader, not how often a turn reads it. A call is found
through the file's own imports: a bare name bound by ``from <module> import name`` (aliases
too) or defined in the module itself, and ``alias.name`` where ``alias`` is the module.

Small talk is decided once per turn, in its place, by ``turn_prep.mode.classify_turn_mode``
(``_TurnMode.lightweight`` and its reason, carried as ``ctx.lightweight_turn``): a short
reply to an offer or a clarify card is an answer, not a greeting. Calling the reader on the
turn's message again elsewhere decides it a second time, without that place.

Whether the message asks to be taught is the turn's reading (``TurnReading.teaching``, read
by ``read_turn``); code asks ``turn_reading.turn.teaching_of``, which answers from the
reading for the turn's message and reads any other text on its own.

The message's subject is read in the pool and kept on the reading (``TurnReading.subject``
and the step of the subject order that decided it); chat code asks
``chat.turn_prep.reading.subject_of``, which answers from the reading for the turn's
message read with the turn's flags and reads anything else as before.

Every other caller reads some other text, or composes the reader into a reader of its own;
each function is listed with how many times it calls and why, and the lists only shrink.
"""

from __future__ import annotations

import ast
from collections import Counter

from .boundary_support import APP_ROOT

_ROUTING = "app.modules.turn_reading.routing"
_TEACHING = "app.modules.turn_reading.teaching"
_SUBJECTS = "app.services.subjects.dispatch"
_SUBJECT_READERS = {"detect_subject", "read_subject", "_subject_of_text"}
_SUBJECT_ORDER = "app.services.subjects.order"

# "path::function" -> (calls, why).
_LIGHTWEIGHT_CALLERS: dict[str, tuple[int, str]] = {
    # The owner: the turn's small-talk decision, read alone and then in its place.
    "modules/chat/turn_prep/mode.py::_light_reason": (2, "owner"),
    # Precedence questions (docs/STRUCTURE_TICKETS.md, ST-05): these ask about the turn's
    # own message without its place, so "no" after an offer reads as small talk here and
    # as an answer to the turn's mode. Choosing is a behaviour change of its own.
    "modules/chat/model_routing/route.py::_looks_like_smart_continuation": (
        1,
        "routing runs in the pool, before the window",
    ),
    "modules/chat/answer_photo_offer.py::offers_answer_photo": (1, "the bare query"),
    # Readers of other text, or readers built from this reader.
    "modules/chat/continuation_subject.py::is_pure_continuation": (1, "any line"),
    "modules/chat/follow_up_thread.py::_continues_thread": (1, "any line"),
    "modules/chat/prompt_constants/writing.py::is_bare_writing_line": (1, "a pasted fragment"),
    "modules/chat/related_questions.py::general_question": (1, "a suggested question"),
    "modules/chat/related_questions.py::_asks": (1, "a suggested question"),
    "modules/math/followup.py::open_math_problem": (1, "a fragment against its equation"),
    "modules/speech/live_talk_tools.py::execute_tool": (1, "live talk's spoken query"),
    "modules/turn_reading/personal.py::needs_rich_context": (1, "a reader built on it"),
    "modules/turn_reading/writing.py::_answers_draft_question": (1, "a reader built on it"),
    "modules/web_search/detection.py::web_search_skip": (1, "a reader with its own offer check"),
}

# "path::function" -> (calls of is_teaching_request or teaching_reason, why).
_TEACHING_CALLERS: dict[str, tuple[int, str]] = {
    "modules/chat/turn_prep/reading.py::read_turn": (1, "owner: the turn's reading"),
    "modules/turn_reading/turn.py::teaching_of": (1, "owner: any text that is not the turn's"),
    "modules/turn_reading/teaching.py::is_teaching_request": (1, "the reader's yes/no"),
    "modules/chat/lesson_progress.py::lesson_progress": (1, "the chat's earlier user lines"),
    "modules/turn_reading/lesson_flow.py::outline_awaits_pick": (1, "the line before the reply"),
}

# "path::function" -> (calls of a subject reader, why).
_SUBJECT_CALLERS: dict[str, tuple[int, str]] = {
    # The reader and the turn's subject: read in the pool, kept on the reading.
    "services/subjects/dispatch.py::detect_subject": (1, "the reader"),
    "services/subjects/dispatch.py::_subject_of_text": (1, "the reader"),
    "modules/chat/turn_prep/reading.py::ask_turn_readings": (4, "the pool's reads of the turn"),
    "modules/chat/turn_prep/reading.py::subject_of": (1, "owner: any text or flags not the turn's"),
    # A place or weather ask beside homework: its own subject, read in the pool
    # (``web_search.homework``).
    "modules/chat/turn_prep/reading.py::_read_place_requests": (1, "a request's own text"),
    # Routing runs in the pool, before the turn's reading is kept (see ST-05's precedence
    # note): it reads the line with the chemistry setting and no attachment flag.
    "modules/chat/model_routing/route.py::_routed_line": (1, "the lane, read in the pool"),
    "modules/chat/turn_prep/followups.py::read_prompt_inputs": (
        1,
        "the pool's reads for the prompt",
    ),
    # The subject fetch: the turn's subject with its image extract, off the loop.
    "modules/chat/turn_prep/augment.py::gather_and_inject": (1, "the turn's subject fetch"),
    "modules/chat/prompt_builder.py::fetch_subject": (1, "the prompt's subject fetch"),
    "services/subjects/dispatch.py::build_subject_augmentation": (1, "a fetch with no subject"),
    # Readers of other text.
    "modules/chat/turn_prep/intents.py::part_kind": (1, "a request's own text"),
    "modules/chat/turn_prep/intents.py::_continues_solve": (1, "the earlier request"),
    # A problem's setup and each question about it, read in the pool with the plan.
    "modules/chat/turn_prep/intents.py::_Problem.of": (1, "the setup by its own words"),
    "modules/chat/turn_prep/intents.py::_Problem.carries": (2, "a question, then with its setup"),
    "modules/chat/continuation_subject.py::classify_presentation_subject": (1, "any line"),
    "modules/chat/continuation_subject.py::blocks_math_followup": (1, "an earlier line"),
    "modules/chat/follow_up_thread.py::subject_for_related": (1, "a related question"),
    # Images reads a send before any chat turn (and may not import chat).
    "modules/images/gen_intent.py::stem_subject": (1, "a picture request's subject"),
    "modules/images/intent.py::composer_intent_for_chat": (1, "the composer's send"),
}


def _dotted(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _dotted(node.value)
        return f"{base}.{node.attr}" if base else None
    return None


def callers(names: set[str], module: str, tree: ast.AST, path: str) -> Counter[str]:
    """Each call of a function in ``names`` that ``module`` defines, by enclosing function."""
    module_path = module.removeprefix("app.").replace(".", "/") + ".py"
    parent, _, leaf = module.rpartition(".")
    functions: dict[str, str] = {}
    modules = {module}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == module:
            functions.update(
                {
                    alias.asname or alias.name: alias.name
                    for alias in node.names
                    if alias.name in names
                }
            )
        elif isinstance(node, ast.ImportFrom) and node.module == parent:
            modules.update(alias.asname or alias.name for alias in node.names if alias.name == leaf)
        elif isinstance(node, ast.Import):
            modules.update(
                alias.asname for alias in node.names if alias.name == module and alias.asname
            )
        elif (
            path == module_path
            and isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
            and node.name in names
        ):
            functions[node.name] = node.name
    found: Counter[str] = Counter()

    def visit(node: ast.AST, scope: str) -> None:
        for child in ast.iter_child_nodes(node):
            inner = scope
            if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                inner = f"{scope}.{child.name}" if scope else child.name
            if isinstance(child, ast.Call):
                func = child.func
                bare = isinstance(func, ast.Name) and func.id in functions
                qualified = (
                    isinstance(func, ast.Attribute)
                    and func.attr in names
                    and _dotted(func.value) in modules
                )
                if bare or qualified:
                    found[f"{path}::{scope or '<module>'}"] += 1
            visit(child, inner)

    visit(tree, "")
    return found


def _production_callers(names: set[str], module: str) -> Counter[str]:
    found: Counter[str] = Counter()
    for path in sorted(APP_ROOT.rglob("*.py")):
        relative = path.relative_to(APP_ROOT).as_posix()
        if not relative.startswith("tests/"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            found += callers(names, module, tree, relative)
    return found


def _check(found: Counter[str], listed: dict[str, tuple[int, str]], advice: str) -> None:
    recorded = {caller: calls for caller, (calls, _why) in listed.items()}
    more = sorted(
        f"{caller}: {calls}" for caller, calls in found.items() if calls > recorded.get(caller, 0)
    )
    assert not more, f"{more} call the reader directly: {advice}"
    fewer = sorted(caller for caller, calls in recorded.items() if found.get(caller, 0) < calls)
    assert not fewer, f"{fewer} call it less now: lower or remove them in the list"


def test_callers_resolves_the_files_imports() -> None:
    tree = ast.parse(
        f"from {_TEACHING} import is_teaching_request as itr, teaching_reason\n"
        "from app.modules.turn_reading import teaching as t\n"
        f"import {_TEACHING} as tt\n"
        "import app.modules.turn_reading.teaching\n"
        "from elsewhere import is_teaching_request as other\n"
        "def a(x):\n    return itr(x)\n"
        "class B:\n    def c(self, x):\n        return t.teaching_reason(x) and tt.is_teaching_request(x)\n"
        f"def d(x):\n    return {_TEACHING}.is_teaching_request(x) or teaching_reason(x)\n"
        "def e(x):\n    return other(x) or unknown.is_teaching_request(x)\n"
    )
    names = {"is_teaching_request", "teaching_reason"}
    assert callers(names, _TEACHING, tree, "f.py") == {"f.py::a": 1, "f.py::B.c": 2, "f.py::d": 2}


def test_callers_counts_a_module_calling_its_own_reader() -> None:
    tree = ast.parse(
        "def teaching_reason(x):\n    return x\n"
        "def is_teaching_request(x):\n    return teaching_reason(x) == 'teach'\n"
    )
    names = {"is_teaching_request", "teaching_reason"}
    found = callers(names, _TEACHING, tree, "modules/turn_reading/teaching.py")
    assert found == {"modules/turn_reading/teaching.py::is_teaching_request": 1}


def test_direct_callers_of_the_small_talk_reader_are_listed() -> None:
    _check(
        _production_callers({"is_lightweight_chat_turn"}, _ROUTING),
        _LIGHTWEIGHT_CALLERS,
        "read the turn's mode (ctx.lightweight_turn), or, for another text, list it with why",
    )


def test_direct_callers_of_the_teaching_reader_are_listed() -> None:
    _check(
        _production_callers({"is_teaching_request", "teaching_reason"}, _TEACHING),
        _TEACHING_CALLERS,
        "ask teaching_of(text), or, for another text, list it with why",
    )


def test_direct_callers_of_the_subject_readers_are_listed() -> None:
    _check(
        _production_callers(_SUBJECT_READERS, _SUBJECTS)
        + _production_callers({"read_subject_reason"}, _SUBJECT_ORDER),
        _SUBJECT_CALLERS,
        "ask subject_of(text, …) (chat.turn_prep.reading), or, for another text, list it with why",
    )

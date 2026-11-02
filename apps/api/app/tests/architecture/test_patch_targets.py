"""String patches only go down (code-health audit TEST-05).

A test that patches ``"app.modules.chat.turn_settle.SessionLocal"`` is tied to that
module's imports: moving one breaks the test, or leaves the patch on a name the code no
longer reads, so the real dependency runs. A chat turn takes a ``ChatTurnDeps``
(``modules/chat/turn_deps.py``) for this; a test passes fakes in it instead.

- Patches into ``app.modules.chat`` and patches of a private name (``_name``) are held
  at their count. Lower the number when a change removes some.
- A patch of a library name through an app module (``"app.x.asyncio.sleep"``,
  ``"app.x.time.time"``) replaces it for the whole process: the event loop, other
  threads and every other module. None is allowed; patch the module's own seam.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterator
from pathlib import Path

from .boundary_support import APP_ROOT

_TESTS = APP_ROOT / "tests"
# Library modules an app module imports whole; a patch through one reaches everyone,
# as a string (``"app.x.asyncio.sleep"``) or as ``patch.object(x.asyncio, "sleep")``.
_SHARED_MODULE = re.compile(
    r"(^|\.)(asyncio|time|datetime|random|os|uuid|json|socket|httpx|logging|secrets|"
    r"subprocess|shutil|tempfile|threading|concurrent)\.[A-Za-z_]+$"
)
# What is left; lower these when a change removes some.
_CHAT_PATCHES = 409
_PRIVATE_PATCHES = 98


def patch_targets(*, setattr_objects: bool = False) -> Iterator[tuple[str, str]]:
    """``(file:line, target)`` for each string patch and each ``patch.object`` attribute.

    With ``setattr_objects``, ``monkeypatch.setattr(module.asyncio, "sleep", ...)`` too.
    """
    for path in sorted(_TESTS.rglob("*.py")):
        if path.resolve() == Path(__file__).resolve():
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            name = ast.unparse(node.func)
            first = node.args[0]
            where = f"{path.relative_to(_TESTS)}:{node.lineno}"
            if name.endswith(("patch", "setattr", "patch.dict")) and isinstance(
                first, ast.Constant
            ):
                if isinstance(first.value, str) and first.value.startswith("app."):
                    yield where, first.value
            elif (
                name.endswith("patch.object") or (setattr_objects and name.endswith("setattr"))
            ) and len(node.args) > 1:
                attribute = node.args[1]
                if isinstance(attribute, ast.Constant) and isinstance(attribute.value, str):
                    yield where, f"{ast.unparse(first)}.{attribute.value}"


def _private(target: str) -> bool:
    leaf = target.rsplit(".", 1)[-1]
    return leaf.startswith("_") and not leaf.startswith("__")


def test_no_patch_of_a_library_name_through_an_app_module() -> None:
    through = [
        f"{where} {target}"
        for where, target in patch_targets(setattr_objects=True)
        if _SHARED_MODULE.search(target)
    ]
    assert through == [], "this patches the library for the whole process"


def test_string_patches_into_chat_and_private_names_only_go_down() -> None:
    targets = [target for _where, target in patch_targets()]
    chat = sum(target.startswith("app.modules.chat.") for target in targets)
    private = sum(_private(target) for target in targets)
    assert chat <= _CHAT_PATCHES, (
        "a new string patch into app.modules.chat: pass ChatTurnDeps fakes"
    )
    assert private <= _PRIVATE_PATCHES, "a new patch of a private name: patch a public seam"
    assert (chat, private) == (_CHAT_PATCHES, _PRIVATE_PATCHES), (
        f"fewer patches now: set _CHAT_PATCHES = {chat} and _PRIVATE_PATCHES = {private}"
    )

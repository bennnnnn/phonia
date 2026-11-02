"""Tests check which prompt text a turn gets, not its wording (code-health audit TEST-06).

An assert that pastes a prompt's words (``assert "Never use decorative headings" in
system``) turns red on every rewording of that prompt, and its fix is pasting the new
words, so it pins copy rather than behaviour. Assert the constant instead
(``assert EMAIL_DRAFT_HINT in system``), or use the golden test's ``@NAME`` tokens
(``modules/chat/test_prompt_golden.py``).

A phrase that must survive any rewording, a safety promise such as "Never say you
sent", stays literal with ``# safety phrase`` on its line. The rest are counted here
and may only go down.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterator

from .boundary_support import APP_ROOT

_TESTS = APP_ROOT / "tests"
_PLACEHOLDER = re.compile(r"(?<!\{)\{[A-Za-z_0-9!:.]*\}(?!\})")
# Literal prompt-copy asserts left; lower this when a change replaces some.
_PINNED = 98


def _prompt_texts() -> list[str]:
    """Every module-level string constant in app/ long enough to be prompt copy."""
    texts: list[str] = []
    for path in APP_ROOT.rglob("*.py"):
        if _TESTS in path.parents:
            continue
        for node in ast.parse(path.read_text()).body:
            value = node.value if isinstance(node, ast.Assign | ast.AnnAssign) else None
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                if len(value.value) >= 40 and not _PLACEHOLDER.search(value.value):
                    texts.append(value.value)
    return texts


def _pinned_copy() -> Iterator[str]:
    texts = _prompt_texts()
    lowered = [text.lower() for text in texts]
    for path in sorted(_TESTS.rglob("test_*.py")):
        source = path.read_text()
        lines = source.splitlines()
        for node in ast.walk(ast.parse(source)):
            if not (isinstance(node, ast.Assert) and isinstance(node.test, ast.Compare)):
                continue
            left = node.test.left
            if not (isinstance(left, ast.Constant) and isinstance(left.value, str)):
                continue
            phrase = left.value
            if len(phrase) < 25 and len(phrase.split()) < 4:
                continue
            if any("# safety phrase" in line for line in lines[node.lineno - 1 : node.end_lineno]):
                continue
            haystack = lowered if phrase == phrase.lower() else texts
            if any(phrase in text for text in haystack):
                yield f"{path.relative_to(_TESTS)}:{node.lineno} {phrase[:60]!r}"


def test_prompt_copy_asserts_only_go_down() -> None:
    pinned = list(_pinned_copy())
    assert len(pinned) <= _PINNED, "assert the prompt constant, not its words:\n" + "\n".join(
        pinned
    )
    assert len(pinned) == _PINNED, f"fewer pinned phrases now: set _PINNED = {len(pinned)}"

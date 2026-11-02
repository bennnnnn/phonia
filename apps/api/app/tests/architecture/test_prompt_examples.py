"""A prompt's example of the user's own facts names no real company.

Live: a new account with no memory asked "what can you do?" and was offered help
"reviewing your Uber-related projects". The privacy rule, in every prompt, said "if
memory says the user works at Uber …", and the next line let the model use memory for
examples of their work, so the example read as a fact about them. Such an example
uses a placeholder ("Company A").
"""

from __future__ import annotations

import ast
import re

from .boundary_support import APP_ROOT

_TESTS = APP_ROOT / "tests"
_USER_WORKS_AT = re.compile(
    r"\b(?:the user|user|they|she|he)\s+(?:works?|worked|is employed)\s+(?:at|for)\s+"
    r"(?!Company\s+[A-Z]\b)[A-Z][\w&.-]+"
)


def _prompt_texts() -> list[str]:
    """Every module-level string constant in app/ (prompt copy lives in these)."""
    texts: list[str] = []
    for path in APP_ROOT.rglob("*.py"):
        if _TESTS in path.parents:
            continue
        for node in ast.parse(path.read_text()).body:
            value = node.value if isinstance(node, ast.Assign | ast.AnnAssign) else None
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                texts.append(value.value)
    return texts


def test_an_example_of_the_user_s_job_uses_a_placeholder() -> None:
    offenders = [hit.group(0) for text in _prompt_texts() for hit in _USER_WORKS_AT.finditer(text)]
    assert offenders == []

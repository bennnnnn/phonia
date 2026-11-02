"""One retry policy for background work, owned by ``core/jobs``.

The worker's "3 tries, 2 s x n" was copied into the memory-lock retries (linked by a
comment) and the history scan (not linked at all), so a change to the job retry
policy reached them only if someone found the copies.
"""

from __future__ import annotations

import ast
import re

from .boundary_support import APP_ROOT

_BACKOFF_NAME = re.compile(r"BACKOFF", re.IGNORECASE)


def test_no_retry_backoff_constant_outside_core_jobs() -> None:
    copies = []
    for path in sorted(APP_ROOT.rglob("*.py")):
        relative = path.relative_to(APP_ROOT).as_posix()
        if relative.startswith(("tests/", "core/jobs/")):
            continue
        for node in ast.parse(path.read_text(encoding="utf-8")).body:
            targets = node.targets if isinstance(node, ast.Assign) else []
            if isinstance(node, ast.AnnAssign):
                targets = [node.target]
            for target in targets:
                if isinstance(target, ast.Name) and _BACKOFF_NAME.search(target.id):
                    copies.append(f"{relative}:{node.lineno} {target.id}")
    assert not copies, "import the retry policy from app.core.jobs instead:\n" + "\n".join(copies)

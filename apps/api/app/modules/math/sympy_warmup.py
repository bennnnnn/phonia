"""Warm a SymPy worker on the real verified-math path.

The process bootstrap hands this to ``app.core.sympy_executor.warm_sympy_pool``
so the pool stays subject-neutral infrastructure. It runs in a spawned worker,
so it must stay a picklable top-level function with no arguments.
"""

from __future__ import annotations


def warm_math_worker() -> None:
    from app.core.config import Settings
    from app.modules.math.schemas import MathIntent
    from app.modules.math.tools.block import _build_verified_block

    _build_verified_block(
        MathIntent(kind="arithmetic", school_op="eval", expr="1+1", operation="solve"),
        Settings.model_validate({}),
    )

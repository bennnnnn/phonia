"""Physics — a subject domain in its own right, not a corner of math.

Physics asks (kinematics, projectile, force, energy) are detected, solved and
rendered by the four modules here:

- ``solver``  — SymPy solves for the unknown and builds trajectory graph specs
- ``extract`` — recognizes a physics ask and produces a ``PhysicsIntent``
- ``direct``  — decides a complete literal ask may show its verified result
- ``block``   — builds the verified system-prompt block for the chat turn

Physics has its own intent, extraction, verified block, prompt augmentation,
direct presentation, and fence finalization. Only canonical solve transport
and text normalization are shared with other subjects.

The package surface is lazy, so importing a name loads only its module.
Other modules import only the names in ``_EXPORTS``.
"""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.modules.physics.block import (
        build_verified_physics_block as build_verified_physics_block,
    )
    from app.modules.physics.extract import (
        extract_physics_intent as extract_physics_intent,
    )
    from app.modules.physics.extract import (
        needs_physics as needs_physics,
    )
    from app.modules.physics.solver import (
        solve_physics as solve_physics,
    )
    from app.modules.physics.symbol_givens import (
        is_symbol_givens_request as is_symbol_givens_request,
    )

_EXPORTS = {
    "build_verified_physics_block": ("block", "build_verified_physics_block"),
    "extract_physics_intent": ("extract", "extract_physics_intent"),
    "is_symbol_givens_request": ("symbol_givens", "is_symbol_givens_request"),
    "needs_physics": ("extract", "needs_physics"),
    "solve_physics": ("solver", "solve_physics"),
}

__all__ = list(_EXPORTS)


def __getattr__(name: str) -> Any:
    target = _EXPORTS.get(name)
    if target is None:
        raise AttributeError(name)
    module_name, attribute = target
    value = getattr(import_module(f"app.modules.physics.{module_name}"), attribute)
    globals()[name] = value
    return value


# Seams the chat turn uses: question detection.
# ``subject``: physics as the subject registry (services/subjects/registry) asks it: its
# verified block, its direct reply, its prompt copy, its follow-ups and its fences.
# ``model_read``: the laws a model reader chooses from, and the intent its read binds to.
_MODULE_EXPORTS = ("extract", "model_read", "subject")

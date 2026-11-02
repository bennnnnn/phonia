"""Math — the symbolic pipeline, from raw user text to a verified answer.

Three stages, each its own subpackage:

- ``match``  — cheap text scanning: does this look like math, and what kind
- ``tools``  — intent extraction, direct-reply decisions, verified block and
               prompt augmentation (the stage that decides what to hand the model)
- ``solve``  — SymPy evaluation: actually compute the answer

Alongside them: ``fence`` (post-stream fence correction), ``school``,
``followup``, ``ocr`` / ``image_extract`` (math from photos), ``reply_policy``
and ``sympy_warmup`` (the solve that warms the shared SymPy pool in
``app.core.sympy_executor``).

Physics is a peer subject, not a corner of this package — see
``app.modules.physics``.

The package surface stays lazy so importing a matcher does not eagerly load the
symbolic solver stack. Other modules import only the names in ``_EXPORTS``.
"""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.modules.math.unit_conversion import (
        get_unit_registry as get_unit_registry,
    )

_EXPORTS = {"get_unit_registry": ("unit_conversion", "get_unit_registry")}

__all__ = list(_EXPORTS)


def __getattr__(name: str) -> Any:
    target = _EXPORTS.get(name)
    if target is None:
        raise AttributeError(name)
    module_name, attribute = target
    value = getattr(import_module(f"app.modules.math.{module_name}"), attribute)
    globals()[name] = value
    return value


# What other modules may import besides the package: chat reaches maths only through its
# adapter (``subject``, services/subjects/registry).
_MODULE_EXPORTS = (
    # The verified block's types (services/solving).
    "response_intent",
    "solve.key_steps",
    "subject",
    # The subject order (services/subjects/order): maths' cue, its intent, and a curve
    # physics cannot read.
    "tools.extract",
    "tools.prompt",
    "tools.school.curve_points",
    # The model reader (modules/model_reader) keeps maths' own typed read.
    "tools.llm_extract",
)

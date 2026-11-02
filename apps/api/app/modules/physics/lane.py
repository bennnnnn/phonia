"""Auto routing's physics lane: verified physics stays fast, uncovered homework goes smart.

Physics' read of a line for model routing (chat's ``model_routing/route``), asked through
its adapter (``services/subjects/registry``). ``_physics_solves`` is a reading
(``core/readings.py``): the turn reads it in the SymPy pool with the rest of its message,
so routing never runs the physics solver on the event loop.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from app.core.readings import reading

logger = logging.getLogger(__name__)

# Homework physics the verified solver does not cover (incline, momentum,
# escape velocity, …). needs_symbolic stays the solver gate so we don't
# inject fake verified fences; Auto still escalates so a weak model isn't
# left to invent F=ma on an incline. Bare "physics" must not match.
#
# Deliberately a separate list from `modules.physics.registry.PHYSICS_CUES` /
# `has_supported_physics_cue`, not a duplicate of it: that one gates "the
# solver's extractors might handle this text," which has grown to twenty
# kinds. This one gates "escalate Auto to the smarter model," which some
# entries here now overlap with a covered kind (momentum, simple harmonic,
# centripetal) — kept anyway, since a smarter model's surrounding
# explanation is still worth it even when the number itself is guaranteed.
# If that stops being true for a given phrase, prune it here; don't point
# this at `has_supported_physics_cue` — inverting the gate would escalate
# exactly the questions the solver already has covered, and stop escalating
# the ones it doesn't, which is backwards from this function's purpose.
_PHYSICS_HOMEWORK_CUES = (
    "frictionless",
    "incline",
    "inclined plane",
    "momentum",
    "escape velocity",
    "centripetal",
    "simple harmonic",
    "coefficient of friction",
    "normal force",
    "pendulum",
    "projectile motion",
    "free body",
    "atwood",
)
# Formula / conceptual asks that are hard even without a printed number.
_PHYSICS_FORMULA_CUES = (
    "escape velocity",
    "simple harmonic",
    "pendulum",
    "atwood",
    "projectile motion",
)


def _looks_like_physics_homework(content: str) -> bool:
    """Hard physics asks the solver templates don't cover.

    Requires a quantity (a digit) for everyday words like "momentum", so
    "the project has momentum" stays on the fast model. Formula phrases
    (escape velocity, pendulum, …) escalate even without a number.
    """
    lower = content.lower()
    if not any(cue in lower for cue in _PHYSICS_HOMEWORK_CUES):
        return False
    if any(ch.isdigit() for ch in content):
        return True
    return any(cue in lower for cue in _PHYSICS_FORMULA_CUES)


@reading(declined=False)
@lru_cache(maxsize=128)
def _physics_solves(content: str) -> bool:
    """Whether the verified solver finishes this line's physics template.

    Routing asks this of the current line and again of a prior one, every
    turn; the answer only depends on the text. Any failure is a decline: the
    strong model answers it, and the turn never fails for a routing hint.
    """
    from app.modules.physics import extract_physics_intent, solve_physics
    from app.services.solving import SolveServiceError

    intent = extract_physics_intent(content)
    if intent is None:
        return False
    try:
        solve_physics(intent)
    except SolveServiceError:
        return False
    except Exception:
        logger.warning(
            "physics routing solve failed kind=%s op=%s",
            intent.kind,
            intent.physics_op,
            exc_info=True,
        )
        return False
    return True


def physics_fast_lane(content: str, *, tools_on: bool) -> bool | None:
    """Verified physics stays on the fast model (True). Uncovered homework goes to the
    strong one (False). None when the line is no physics.

    The fast tier is only for a template the solver actually finishes, and only while
    math tools are on. Otherwise the strong model answers it.
    """
    homework = _looks_like_physics_homework(content)
    from app.modules.physics import extract_physics_intent, needs_physics

    if not homework and not needs_physics(content):
        return None
    if extract_physics_intent(content) is None:
        return False if homework else None
    return tools_on and _physics_solves(content)

"""Closed school templates, keyed by operation.

Kind solvers do not see these operations. ``solve_physics`` claims each id once.
"""

from __future__ import annotations

from collections.abc import Callable

from app.modules.physics.solvers.results import PhysicsResult
from app.modules.physics.solvers.school_ac import AC_SOLVERS
from app.modules.physics.solvers.school_circuits import CIRCUIT_SOLVERS
from app.modules.physics.solvers.school_fields import FIELD_SOLVERS
from app.modules.physics.solvers.school_matter import MATTER_SOLVERS

SCHOOL_SOLVERS: dict[str, Callable[[dict[str, float]], PhysicsResult]] = {
    **CIRCUIT_SOLVERS,
    **FIELD_SOLVERS,
    **AC_SOLVERS,
    **MATTER_SOLVERS,
}

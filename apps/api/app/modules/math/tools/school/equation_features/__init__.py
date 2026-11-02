"""A feature of one stated equation: vertex, intercepts, discriminant, roots, lines.

"find the vertex of y = x^2 - 6x + 5" used to be solved for x, and the
verified card read ``x = 3 - sqrt(y + 4) or ...``. The same happened to the
y-intercept, the axis of symmetry, the discriminant, the sum of the roots,
"find k so that ... has exactly one solution", and the line through a point
parallel to another. Each rule here reads one asked feature and the one
equation it is about, and the whole request has to be read: anything left
over, a second feature, or an equation of the wrong shape verifies nothing,
and the model answers. ``request_consumption`` refuses the equation solver
for the same words, so a declined feature never falls through to "solve".

``extract`` reads the request into one intent. ``solvers`` works it: ``forms``
reads the equation as a function, a line or a quadratic and writes the TeX, and
the features are solved in ``quadratics``, ``lines`` and ``sinusoids``.
"""

from app.modules.math.tools.school.equation_features.extract import (
    FEATURE_OPS,
    extract_equation_feature_intent,
)
from app.modules.math.tools.school.equation_features.solvers import equation_feature_block

__all__ = [
    "FEATURE_OPS",
    "equation_feature_block",
    "extract_equation_feature_intent",
]

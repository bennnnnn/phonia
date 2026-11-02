"""Properties of the physics solvers' shared arithmetic (Hypothesis; audit TEST-08).

``quadratic_roots`` answers every projectile, braking and kinematics quadratic. Its
roots must solve the equation they came from, in ascending order, and there must be
as many as the discriminant says.
"""

from __future__ import annotations

import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st

from app.modules.physics.solvers.arithmetic import quadratic_roots

# What a question gives: zero, or a size from a micrometre to a megametre either way.
# Near 1e-300, b² and 4ac underflow before the formula starts; no question goes there.
_SIZE = st.floats(min_value=1e-6, max_value=1e6, allow_nan=False, allow_infinity=False)
_COEFFICIENT = st.integers(min_value=-200, max_value=200).map(float) | st.builds(
    lambda size, sign: size * sign, _SIZE, st.sampled_from([-1.0, 1.0])
)


@given(a=_COEFFICIENT, b=_COEFFICIENT, c=_COEFFICIENT)
@example(a=1.0, b=-2.0, c=1.0)  # a double root
@example(a=-4.9, b=20.0, c=1.5)  # a thrown ball's height
@example(a=1.0, b=1e3, c=1e-3)  # the cancellation the closed form avoids
@settings(max_examples=300, deadline=None)
def test_each_root_solves_its_quadratic(a: float, b: float, c: float) -> None:
    roots = quadratic_roots(a, b, c)
    assert list(roots) == sorted(roots)
    for root in roots:
        scale = abs(a) * root * root + abs(b) * abs(root) + abs(c)
        assert a * root * root + b * root + c == pytest.approx(0.0, abs=1e-9 * max(scale, 1.0))
    if a == 0:
        return
    discriminant = b * b - 4 * a * c
    margin = 1e-9 * (b * b + abs(4 * a * c))
    if discriminant > margin:
        assert len(roots) == 2
    elif discriminant < -margin:
        assert roots == ()

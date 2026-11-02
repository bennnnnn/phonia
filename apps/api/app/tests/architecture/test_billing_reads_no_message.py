"""Billing keeps pools; which model a message needs is chat's (code-health audit ARCH-02).

Picking a model went ``chat.turn_load -> billing.plan -> services.routing`` and from there
into chat's cues, maths' matchers and the physics solver, so billing depended on chat and
the subjects. Routing is ``modules/chat/model_routing`` now, and billing reads no message.
"""

from __future__ import annotations

import os
import subprocess
import sys

from .boundary_support import APP_ROOT


def test_billing_plan_loads_no_chat_math_or_physics() -> None:
    # A fresh interpreter: this process has already imported every module.
    code = (
        "import sys\n"
        "import app.modules.billing.plan\n"
        "prefixes = ('app.modules.chat', 'app.modules.math', 'app.modules.physics')\n"
        "print(sorted(name for name in sys.modules if name.startswith(prefixes)))\n"
    )
    result = subprocess.run(  # noqa: S603 - fixed argv: this interpreter and a literal script
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=APP_ROOT.parent,
        env={**os.environ, "PYTHONPATH": str(APP_ROOT.parent)},
        check=True,
    )
    assert result.stdout.strip() == "[]", result.stdout

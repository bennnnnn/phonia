"""Whether the user's memory is on: the Settings → Memory switch.

Every reader asks here (code-health audit CLAR-11). Chat read the column with a default
of on and live talk with a default of off, so a reply could recall what a voice turn
in the same account would not.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.orm import User


def memory_switch_on(user: User | None) -> bool:
    """The switch; an account the turn has not loaded counts as on.

    So does a row built in code and not saved yet: its ``None`` takes the column's
    default, on.
    """
    return user is None or user.memory_enabled is not False

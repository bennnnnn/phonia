"""Plan and store-billing surface.

The package stays lazy so importing it does not load RevenueCat or the webhook.
"""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.modules.billing.entitlements import (
        allowance as allowance,
    )
    from app.modules.billing.entitlements import (
        can_use as can_use,
    )
    from app.modules.billing.entitlements import (
        is_paid as is_paid,
    )
    from app.modules.billing.entitlements import (
        plan_of as plan_of,
    )

_EXPORTS = {
    "allowance": ("entitlements", "allowance"),
    "can_use": ("entitlements", "can_use"),
    "is_paid": ("entitlements", "is_paid"),
    "plan_of": ("entitlements", "plan_of"),
}
# Account reads plan policy and syncs a purchase; both are billing's to own.
_MODULE_EXPORTS = ("entitlements", "plan", "subscription")
__all__ = list(_EXPORTS) + list(_MODULE_EXPORTS)


def __getattr__(name: str) -> Any:
    if name in _MODULE_EXPORTS:
        value = import_module(f"app.modules.billing.{name}")
        globals()[name] = value
        return value
    target = _EXPORTS.get(name)
    if target is None:
        raise AttributeError(name)
    module_name, attribute = target
    value = getattr(import_module(f"app.modules.billing.{module_name}"), attribute)
    globals()[name] = value
    return value

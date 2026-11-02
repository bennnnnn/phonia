"""Notification delivery services.

The package stays lazy so importing it does not load the push sender.
"""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.modules.notifications.jobs import (
        enqueue_purchase_receipt as enqueue_purchase_receipt,
    )
    from app.modules.notifications.jobs import (
        enqueue_welcome_email as enqueue_welcome_email,
    )
    from app.modules.notifications.push import (
        enqueue_push_receipts as enqueue_push_receipts,
    )

_EXPORTS = {
    "enqueue_push_receipts": ("push", "enqueue_push_receipts"),
    "enqueue_welcome_email": ("jobs", "enqueue_welcome_email"),
    "enqueue_purchase_receipt": ("jobs", "enqueue_purchase_receipt"),
}
# The schedulers in background/ run these: due reminders by push, and by email.
_MODULE_EXPORTS = ("push", "reminder_email")
__all__ = [*_EXPORTS, *_MODULE_EXPORTS]


def __getattr__(name: str) -> Any:
    target = _EXPORTS.get(name)
    if target is None:
        raise AttributeError(name)
    module_name, attribute = target
    value = getattr(import_module(f"app.modules.notifications.{module_name}"), attribute)
    globals()[name] = value
    return value

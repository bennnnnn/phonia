"""Allow the chat_ttft and chat_turn_outcome product events.

Revision ID: 0113_product_event_names
Revises: 0112_ai_data_consent

chat_ttft joined the API's allowlist without this constraint, so every batch
carrying it failed at commit and none was stored. Widening the check is an
expand: the old release writes a subset of these names.
"""

from collections.abc import Sequence
from typing import Union

from alembic import op

revision: str = "0113_product_event_names"
down_revision: Union[str, None] = "0112_ai_data_consent"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_CONSTRAINT = "ck_product_events_name"
_BEFORE = (
    "paywall_viewed",
    "purchase_started",
    "purchase_succeeded",
    "purchase_failed",
    "push_permission",
)
_ADDED = ("chat_ttft", "chat_turn_outcome")


def _check(names: tuple[str, ...]) -> str:
    return f"name IN {names!r}"


def upgrade() -> None:
    op.drop_constraint(_CONSTRAINT, "product_events", type_="check")
    op.create_check_constraint(_CONSTRAINT, "product_events", _check(_BEFORE + _ADDED))


def downgrade() -> None:
    names = ", ".join(f"'{name}'" for name in _ADDED)
    op.execute(f"DELETE FROM product_events WHERE name IN ({names})")
    op.drop_constraint(_CONSTRAINT, "product_events", type_="check")
    op.create_check_constraint(_CONSTRAINT, "product_events", _check(_BEFORE))

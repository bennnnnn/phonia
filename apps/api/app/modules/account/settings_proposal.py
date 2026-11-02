"""Confirm-then-apply theme changes (a card the user taps to apply).

The theme (light, dark or the system's) is the one setting a chat line changes, and
only when the user taps the card: the chat path stores the change in Redis, and the
confirm hands it to the phone, which keeps the theme. Every other setting (model,
tone, language, memory) is changed by hand in Settings.
"""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID, uuid4

from redis.asyncio import Redis

from app.exceptions import DomainError
from app.models.orm import User
from app.modules.account.settings_intent import SettingsChange

logger = logging.getLogger(__name__)

PROPOSAL_TTL_SECONDS = 900
_APPEARANCE_LABELS = {"light": "Light", "dark": "Dark", "system": "System"}
# "Default"/"auto" mean "follow the system theme", the product default; without
# them "switch to the default theme" could not undo a light or dark choice.
_APPEARANCE_ALIASES: dict[str, str] = {
    "default": "system",
    "auto": "system",
    "automatic": "system",
}


class SettingsProposalError(DomainError):
    """A settings card that can no longer be confirmed."""


def _proposal_key(user_id: UUID, proposal_id: str) -> str:
    return f"settings:proposal:{user_id}:{proposal_id}"


def change_label(value: str) -> str:
    return _APPEARANCE_LABELS.get(value, value)


def validate_changes(changes: list[SettingsChange]) -> list[SettingsChange]:
    """The theme changes a card may apply; any other field is never applied."""
    apply: list[SettingsChange] = []
    for change in changes:
        value = _APPEARANCE_ALIASES.get(change.value, change.value)
        if change.field == "appearance" and value in _APPEARANCE_LABELS:
            apply.append(SettingsChange("appearance", value))
    return apply


def format_proposal_reply(*, proposal_id: str, apply: list[SettingsChange]) -> str:
    summary = "; ".join(f"Appearance → {change_label(item.value)}" for item in apply)
    payload = {
        "proposal_id": proposal_id,
        "changes": [
            {"field": item.field, "value": item.value, "label": change_label(item.value)}
            for item in apply
        ],
    }
    fence = json.dumps(payload, ensure_ascii=False)
    return f"I can switch that for you: {summary}.\n\n```settings_proposal\n{fence}\n```"


async def store_proposal(
    redis: Redis, user_id: UUID, proposal_id: str, changes: list[SettingsChange]
) -> None:
    payload = [{"field": item.field, "value": item.value} for item in changes]
    await redis.set(
        _proposal_key(user_id, proposal_id), json.dumps(payload), ex=PROPOSAL_TTL_SECONDS
    )


async def load_proposal(
    redis: Redis, user_id: UUID, proposal_id: str
) -> list[SettingsChange] | None:
    raw = await redis.get(_proposal_key(user_id, proposal_id))
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, list):
        return None
    changes = [
        SettingsChange("appearance", item["value"])
        for item in data
        if isinstance(item, dict)
        and item.get("field") == "appearance"
        and isinstance(item.get("value"), str)
    ]
    return changes or None


async def materialize_settings_reply(
    redis: Redis, user: User, changes: list[SettingsChange]
) -> str | None:
    apply = validate_changes(changes)
    if not apply:
        return None
    proposal_id = str(uuid4())
    await store_proposal(redis, user.id, proposal_id, apply)
    return format_proposal_reply(proposal_id=proposal_id, apply=apply)


async def confirm_proposal(redis: Redis, user: User, proposal_id: str) -> dict[str, Any]:
    changes = await load_proposal(redis, user.id, proposal_id)
    if changes is None:
        raise SettingsProposalError("Proposal expired or not found.")

    lock_key = _proposal_key(user.id, proposal_id) + ":confirm"
    if not await redis.set(lock_key, "1", ex=120, nx=True):
        raise SettingsProposalError("Update already in progress.")

    try:
        claimed = await redis.getdel(_proposal_key(user.id, proposal_id))
        if claimed is None:
            raise SettingsProposalError("Proposal expired or not found.")
        apply = validate_changes(changes)
        if not apply:
            raise SettingsProposalError("I couldn't change that setting.")
        return {
            "user": user,
            "appearance": apply[-1].value,
            "applied": [
                {"field": item.field, "value": item.value, "label": change_label(item.value)}
                for item in apply
            ],
        }
    finally:
        try:
            await redis.delete(lock_key)
        except Exception:
            logger.exception(
                "Settings confirm lock release failed user_id=%s proposal_id=%s",
                user.id,
                proposal_id,
            )

"""A reminder change from chat is saved when the user taps its card.

The chat turn records what it would write (``write_log``), stores that here
for a day, and the reply carries a ``reminder_proposal`` fence the phone draws
as a card. ``confirm_proposal`` makes the writes once; a second tap on the
same card is answered as already saved. The saved card is marked in the chat
so it reads "Saved" after a reload.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ValidationError
from redis.asyncio import Redis
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timezone import resolve_timezone
from app.exceptions import DomainError
from app.modules.conversation import service as conversation_service
from app.modules.todos import repository as todos_repo
from app.modules.todos.models import TodoItem
from app.modules.todos.recurrence import completed_fields, next_recurring_due
from app.modules.todos.write_log import PlannedWrite
from app.services.md_fence_scan import map_fence_blocks, strip_closed_fences

logger = logging.getLogger(__name__)

PROPOSAL_TTL_SECONDS = 24 * 60 * 60
FENCE_LANG = "reminder_proposal"
_MESSAGE_SCAN_LIMIT = 30
# Only these row fields are ever written from a stored proposal.
_WRITABLE = frozenset(
    {
        "content",
        "topic",
        "chat_id",
        "due_at",
        "recurrence_rule",
        "sort_order",
        "checked",
        "notification_sent_at",
        "email_sent_at",
    }
)
_TIMES = frozenset({"due_at", "notification_sent_at", "email_sent_at"})

CardAction = Literal["add", "complete", "uncheck", "delete", "set_due", "clear_due", "move"]


class ProposalError(DomainError):
    """A reminder card that can no longer be confirmed."""


class CardItem(BaseModel):
    """One line on the card: what tapping it will do."""

    action: CardAction
    title: str
    due_at: datetime | None = None
    repeat: str | None = None
    topic: str | None = None
    when: str | None = None


class _StoredWrite(BaseModel):
    kind: Literal["create", "update", "delete"]
    todo_id: UUID
    title: str
    fields: dict[str, Any]


class _Stored(BaseModel):
    chat_id: UUID
    user_timezone: str | None = None
    writes: list[_StoredWrite]
    items: list[CardItem]


def _key(user_id: UUID, proposal_id: str) -> str:
    return f"todos:proposal:{user_id}:{proposal_id}"


def _saved_key(user_id: UUID, proposal_id: str) -> str:
    return f"{_key(user_id, proposal_id)}:saved"


def card_action(write: PlannedWrite) -> CardAction:
    if write.kind == "create":
        return "add"
    if write.kind == "delete":
        return "delete"
    fields = write.fields
    if "checked" in fields:
        return "complete" if fields["checked"] else "uncheck"
    if "topic" in fields and "due_at" not in fields:
        return "move"
    if "due_at" in fields and fields["due_at"] is None:
        return "clear_due"
    return "set_due"


def card_item(write: PlannedWrite, user_timezone: str | None) -> CardItem:
    from app.modules.todos.reminder_writes import format_schedule_when

    action = card_action(write)
    shows_time = action in {"add", "set_due", "move"} and write.due_at is not None
    return CardItem(
        action=action,
        title=write.title.strip(),
        due_at=write.due_at if shows_time else None,
        repeat=write.repeat if shows_time else None,
        topic=write.topic if action == "move" else None,
        when=(
            format_schedule_when(write.due_at, user_timezone, write.repeat)
            if shows_time and write.due_at is not None
            else None
        ),
    )


def _json_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    return value


async def propose(
    redis: Redis,
    *,
    user_id: UUID,
    chat_id: UUID,
    writes: list[PlannedWrite],
    user_timezone: str | None,
) -> str:
    """Store the writes and return the card fence for the reply."""
    proposal_id = str(uuid4())
    items = [card_item(write, user_timezone) for write in writes]
    stored = {
        "chat_id": str(chat_id),
        "user_timezone": user_timezone,
        "writes": [
            {
                "kind": write.kind,
                "todo_id": str(write.todo_id),
                "title": write.title,
                "fields": {
                    key: _json_value(value)
                    for key, value in write.fields.items()
                    if key in _WRITABLE
                },
            }
            for write in writes
        ],
        "items": [item.model_dump(mode="json") for item in items],
    }
    await redis.set(_key(user_id, proposal_id), json.dumps(stored), ex=PROPOSAL_TTL_SECONDS)
    card = {
        "proposal_id": proposal_id,
        # The zone the user's words were read in: the phone shows the card's
        # time there, and names it when the phone is in another zone.
        "tz": resolve_timezone(user_timezone).key,
        "items": [item.model_dump(mode="json", exclude_none=True) for item in items],
    }
    return f"```{FENCE_LANG}\n{json.dumps(card, ensure_ascii=False)}\n```"


def _row_fields(raw: dict[str, Any]) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    for key, value in raw.items():
        if key not in _WRITABLE:
            continue
        if key in _TIMES and isinstance(value, str):
            value = datetime.fromisoformat(value)
        elif key == "chat_id" and isinstance(value, str):
            value = UUID(value)
        fields[key] = value
    return fields


def _upcoming(fields: dict[str, Any], user_timezone: str | None) -> dict[str, Any]:
    """A repeating time that passed moves to its next turn; a one-off one is refused."""
    due = fields.get("due_at")
    if not isinstance(due, datetime) or fields.get("checked"):
        return fields
    now = datetime.now(UTC)
    if due > now:
        return fields
    rule = fields.get("recurrence_rule")
    if not rule:
        raise ProposalError("That time has passed. Ask again with a new time.", status_code=409)
    return {**fields, "due_at": next_recurring_due(due, rule, now=now, timezone=user_timezone)}


@dataclass(frozen=True)
class ConfirmedProposal:
    """What a tap saved: the card's lines, and the rows it wrote and deleted, which the
    phone applies instead of reading its whole list again (code-health audit NET-16).
    ``rows`` is None for a tap that found the card already saved (another device)."""

    items: list[CardItem]
    rows: list[TodoItem] | None = None
    deleted_ids: list[UUID] = field(default_factory=list)


async def _apply(
    session: AsyncSession, user_id: UUID, stored: _Stored
) -> tuple[list[UUID], list[UUID]]:
    """Make the writes; the ids written and the ids deleted."""
    written: list[UUID] = []
    deleted: list[UUID] = []
    for write in stored.writes:
        fields = _row_fields(write.fields)
        if write.kind == "create":
            fields = _upcoming(fields, stored.user_timezone)
            try:
                # A savepoint, so an open reminder already saved at that time
                # (a second device, an earlier tap) skips only this row.
                async with session.begin_nested():
                    created = await todos_repo.create(
                        session, user_id=user_id, commit=False, **fields
                    )
                written.append(created.id)
            except IntegrityError as exc:
                if not todos_repo.is_open_content_due_conflict(exc):
                    raise
            continue
        row = await todos_repo.get_by_id(session, write.todo_id, user_id)
        if write.kind == "delete":
            if row is not None:
                await todos_repo.delete_by_id(session, write.todo_id, user_id, commit=False)
                deleted.append(write.todo_id)
            continue
        if row is None:
            raise ProposalError(f"{write.title} is no longer in your to-dos.", status_code=409)
        if "due_at" in fields:
            fields = _upcoming(fields, stored.user_timezone)
        fields = completed_fields(
            fields,
            due_at=fields.get("due_at", row.due_at),
            rule=fields.get("recurrence_rule", row.recurrence_rule),
            timezone=stored.user_timezone,
            now=datetime.now(UTC),
        )
        await todos_repo.update(session, row, commit=False, **fields)
        written.append(row.id)
    await session.commit()
    return written, deleted


def mark_saved(content: str, proposal_id: str) -> str:
    """The reply with this proposal's card marked saved."""

    def replace(body: str) -> str:
        try:
            card = json.loads(body)
        except json.JSONDecodeError:
            card = None
        if isinstance(card, dict) and card.get("proposal_id") == proposal_id:
            card["status"] = "saved"
            body = json.dumps(card, ensure_ascii=False)
        return f"```{FENCE_LANG}\n{body.strip()}\n```"

    return map_fence_blocks(content, lambda _fence, body: replace(body), lang=FENCE_LANG)


async def _mark_saved_in_chat(session: AsyncSession, chat_id: UUID, proposal_id: str) -> None:
    await conversation_service.edit_recent_reply(
        session,
        chat_id,
        containing=proposal_id,
        edit=lambda content: mark_saved(content, proposal_id),
        scan=_MESSAGE_SCAN_LIMIT,
    )


async def confirm_proposal(
    session: AsyncSession,
    redis: Redis,
    *,
    user_id: UUID,
    proposal_id: str,
) -> ConfirmedProposal:
    """Make the card's writes. A second tap returns the same items."""
    key = _key(user_id, proposal_id)
    lock_key = f"{key}:confirm"
    if not await redis.set(lock_key, "1", ex=60, nx=True):
        raise ProposalError("Already saving.", status_code=409)
    try:
        raw = await redis.getdel(key)
        if raw is None:
            saved = await redis.get(_saved_key(user_id, proposal_id))
            if saved is not None:
                return ConfirmedProposal(
                    items=[CardItem.model_validate(item) for item in json.loads(saved)]
                )
            raise ProposalError("This expired. Ask again.", status_code=410)
        try:
            stored = _Stored.model_validate_json(raw)
        except ValidationError as exc:
            raise ProposalError("This expired. Ask again.", status_code=410) from exc
        try:
            written, deleted = await _apply(session, user_id, stored)
        except ProposalError:
            await session.rollback()
            raise
        except Exception:
            await session.rollback()
            # Nothing was saved: the same card can be tapped again.
            await redis.set(key, raw, ex=PROPOSAL_TTL_SECONDS)
            raise
        rows = await todos_repo.list_by_ids(session, user_id, written)
        items_json = json.dumps([item.model_dump(mode="json") for item in stored.items])
        await redis.set(_saved_key(user_id, proposal_id), items_json, ex=PROPOSAL_TTL_SECONDS)
        try:
            await _mark_saved_in_chat(session, stored.chat_id, proposal_id)
        except Exception:
            await session.rollback()
            logger.exception("Could not mark reminder card saved proposal_id=%s", proposal_id)
        return ConfirmedProposal(items=stored.items, rows=rows, deleted_ids=deleted)
    finally:
        try:
            await redis.delete(lock_key)
        except Exception:
            logger.exception("Reminder confirm lock release failed proposal_id=%s", proposal_id)


def strip_cards(text: str) -> str:
    """Drop cards from model output: only the server writes one, with a stored id."""
    if f"```{FENCE_LANG}" not in text:
        return text
    return re.sub(r"\n{3,}", "\n\n", strip_closed_fences(text, FENCE_LANG)).strip()


def reminder_cards_as_text(content: str) -> str:
    """A past reply's cards as the app's result lines, for the model's history.

    The model never sees card JSON it could copy. A card not yet tapped says so, and
    that nothing is saved: "Card offered, not tapped, so nothing is saved — Set: gym —
    Thursday, 6:00 PM." Read as "Card offered, not yet tapped — Added: …", the change
    looked made: asked what was on the list, a reply named the untapped item
    (2026-10-25).
    """
    if f"```{FENCE_LANG}" not in content:
        return content
    from app.modules.todos.reminder_writes import result_prefix

    def replace(body: str) -> str:
        try:
            card = json.loads(body)
            items = [CardItem.model_validate(item) for item in card.get("items", [])]
        except (json.JSONDecodeError, ValidationError, AttributeError):
            return ""
        lines = []
        for item in items:
            detail = item.when or (item.topic and f"to {item.topic}") or ""
            line = f"{result_prefix(item.action)}: {item.title}"
            lines.append(f"{line} — {detail}." if detail else f"{line}.")
        text = "\n".join(lines)
        if card.get("status") == "saved":
            return text
        return f"Card offered, not tapped, so nothing is saved — {text}"

    return map_fence_blocks(content, lambda _fence, body: replace(body), lang=FENCE_LANG)


def is_card_line(line: str, writes: list[PlannedWrite]) -> bool:
    """A result line the card replaces: "Set: gym — Thursday, 6:00 PM."."""
    from app.modules.todos.reminder_writes import OK_PREFIXES

    text = line.strip()
    if not text.startswith(OK_PREFIXES):
        return False
    lowered = text.lower()
    return any(write.title.strip().lower() in lowered for write in writes if write.title.strip())

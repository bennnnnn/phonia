"""Keyset pages: a cursor names the last row read (code-health audit CLAR-12).

An offset counts rows, so a row added or removed while a client pages shifts the next
page: one repeats or goes missing. A keyset cursor carries the last row's sort key
(its time, then ids that break ties), and the next page reads the rows after it.
Clients pass the cursor back unread.
"""

from __future__ import annotations

import binascii
import json
from base64 import urlsafe_b64decode, urlsafe_b64encode
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import ColumnElement, literal, tuple_
from sqlalchemy.orm import QueryableAttribute

from app.exceptions import DomainError


class InvalidCursorError(DomainError):
    """A cursor this API did not write; 422 ``invalid_cursor``."""

    status_code = 422
    default_code = "invalid_cursor"

    def __init__(self) -> None:
        super().__init__("This page link is no longer valid. Load the list again.")


def encode_cursor(at: datetime, *ids: UUID) -> str:
    """The cursor after a row sorted by ``at``, then ``ids``; a naive ``at`` is UTC."""
    if at.tzinfo is None:
        at = at.replace(tzinfo=UTC)
    raw = json.dumps([at.isoformat(), *(str(row_id) for row_id in ids)])
    return urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def decode_cursor(cursor: str, *, ids: int) -> tuple[datetime, list[UUID]]:
    """The sort key a cursor names; ``InvalidCursorError`` if it is not one of ours."""
    try:
        values = json.loads(urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
        at = datetime.fromisoformat(values[0])
        row_ids = [UUID(value) for value in values[1:]]
    except (binascii.Error, IndexError, KeyError, TypeError, ValueError) as exc:
        raise InvalidCursorError() from exc
    if at.tzinfo is None or len(row_ids) != ids:
        raise InvalidCursorError()
    return at, row_ids


def after(
    columns: Sequence[ColumnElement[Any] | QueryableAttribute[Any]],
    at: datetime,
    ids: Sequence[UUID],
) -> ColumnElement[bool]:
    """Rows after the cursor in a newest-first order over ``columns``.

    Each value binds as its column's type, so a UUID compares as one on every engine.
    """
    values = [
        literal(value, type_=column.type) for column, value in zip(columns, (at, *ids), strict=True)
    ]
    return tuple_(*columns) < tuple_(*values)


def page_of[T](
    rows: Sequence[T], limit: int, cursor_after: Callable[[T], str]
) -> tuple[list[T], str | None]:
    """The page from ``limit + 1`` rows read, and the cursor after its last row.

    The extra row only says another page exists; ``None`` means this is the last.
    """
    page = list(rows[:limit])
    if len(rows) <= limit or not page:
        return page, None
    return page, cursor_after(page[-1])

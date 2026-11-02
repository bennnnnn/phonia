"""Keyset cursors round-trip, refuse what the API did not write, and end on the last page."""

from __future__ import annotations

import json
from base64 import urlsafe_b64encode
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.repositories.keyset import InvalidCursorError, decode_cursor, encode_cursor, page_of

_AT = datetime(2026, 10, 1, 9, 30, tzinfo=UTC)
# A fixed id: a parameter made at collection time must be the same in every xdist worker.
_ID = str(UUID("0b6c2d4e-8f10-4a2b-9c3d-5e6f7a8b9c0d"))


def test_keyset_cursor_round_trips() -> None:
    first, second = uuid4(), uuid4()
    assert decode_cursor(encode_cursor(_AT, first, second), ids=2) == (_AT, [first, second])


def test_keyset_cursor_reads_a_naive_time_as_utc() -> None:
    row_id = uuid4()
    naive = _AT.replace(tzinfo=None)
    assert decode_cursor(encode_cursor(naive, row_id), ids=1) == (_AT, [row_id])


def _raw(values: object) -> str:
    return urlsafe_b64encode(json.dumps(values).encode()).decode().rstrip("=")


@pytest.mark.parametrize(
    "cursor",
    [
        "not-a-cursor",
        "",
        _raw([]),
        _raw(["yesterday", _ID]),
        _raw([_AT.isoformat(), "not-an-id"]),
        _raw([_AT.replace(tzinfo=None).isoformat(), _ID]),
        _raw([_AT.isoformat()]),
        _raw({"at": _AT.isoformat()}),
    ],
)
def test_keyset_cursor_refuses_what_the_api_did_not_write(cursor: str) -> None:
    with pytest.raises(InvalidCursorError):
        decode_cursor(cursor, ids=1)


@pytest.mark.parametrize(
    ("read", "limit", "page", "has_next"),
    [([1, 2, 3], 2, [1, 2], True), ([1, 2], 2, [1, 2], False), ([], 2, [], False)],
)
def test_page_of_names_the_last_row_only_when_another_page_exists(
    read: list[int], limit: int, page: list[int], has_next: bool
) -> None:
    rows, cursor = page_of(read, limit, lambda row: f"after-{row}")
    assert rows == page
    assert cursor == (f"after-{page[-1]}" if has_next else None)

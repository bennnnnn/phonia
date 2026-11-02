"""Tests for time-ordered UUID helpers."""

from uuid import UUID

from app.core.ids import uuid7


def test_uuid7_is_version_7_and_rfc_variant():
    u = uuid7()
    assert isinstance(u, UUID)
    assert u.version == 7
    assert u.variant == "specified in RFC 4122"


def test_uuid7_same_ms_sequence_is_monotonic():
    """Rapid inserts in one ms must sort by id in generation order."""
    ids = [uuid7() for _ in range(64)]
    assert ids == sorted(ids)
    assert len(set(ids)) == 64


def test_uuid7_distinct_across_calls():
    a, b = uuid7(), uuid7()
    assert a != b

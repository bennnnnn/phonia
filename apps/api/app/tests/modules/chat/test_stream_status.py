"""Stream status helpers."""

from typing import get_args

from app.modules.chat.stream_status import (
    STATUS_DETAIL_MAX_CHARS,
    StreamStatusPhase,
    clip_status_detail,
    status_phase_for_subject,
)


def test_phases_include_activity_specific_entries():
    for phase in ("remembering", "reading_files", "searching", "calculating", "chemistry"):
        assert phase in get_args(StreamStatusPhase)


def test_each_subject_has_its_own_status_phase() -> None:
    assert status_phase_for_subject("math") == "calculating"
    assert status_phase_for_subject("physics") == "physics"
    assert status_phase_for_subject("chemistry") == "chemistry"


def test_clip_status_detail_flattens_whitespace():
    assert clip_status_detail("  weather \n in   berlin ") == "weather in berlin"


def test_clip_status_detail_none_and_blank():
    assert clip_status_detail(None) is None
    assert clip_status_detail("   \n ") is None


def test_clip_status_detail_bounds_length():
    clipped = clip_status_detail("a" * 500)
    assert clipped is not None
    assert len(clipped) <= STATUS_DETAIL_MAX_CHARS
    assert clipped.endswith("…")

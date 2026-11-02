"""Tests for post-generation quality detection (R-API-001 v1)."""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

from app.modules.chat.quality import detect_quality_issues


def _ctx(
    *,
    rich_context_turn: bool = True,
    lightweight_turn: bool = False,
    skip_memory_jobs: bool = False,
    instant_reply: str | None = None,
    terminal_image_content: str | None = None,
    model: str = "free-chat",
) -> MagicMock:
    ctx = MagicMock()
    ctx.user_id = uuid4()
    ctx.chat_id = uuid4()
    ctx.model = model
    ctx.rich_context_turn = rich_context_turn
    ctx.lightweight_turn = lightweight_turn
    ctx.skip_memory_jobs = skip_memory_jobs
    ctx.instant_reply = instant_reply
    ctx.terminal_image_content = terminal_image_content
    return ctx


def test_detect_quality_no_issues_for_normal_reply():
    """A normal rich-context reply has no quality signals."""
    ctx = _ctx()
    report = detect_quality_issues(
        ctx, "Here is a detailed answer to your question about photosynthesis."
    )
    assert not report.has_issues


def test_detect_quality_refusal_pattern():
    """A reply starting with 'I can't' is flagged as a refusal pattern."""
    ctx = _ctx()
    report = detect_quality_issues(ctx, "I can't help with that request.")
    assert report.has_issues
    assert any(s.code == "refusal_pattern" for s in report.signals)


def test_detect_quality_refusal_as_ai():
    """A reply starting with 'As an AI' is flagged as a refusal pattern."""
    ctx = _ctx()
    report = detect_quality_issues(ctx, "As an AI language model, I cannot browse the web.")
    assert report.has_issues
    assert any(s.code == "refusal_pattern" for s in report.signals)


def test_detect_quality_no_refusal_false_positive():
    """A reply that contains 'I can't' mid-sentence is NOT flagged (pattern
    is anchored to the start)."""
    ctx = _ctx()
    report = detect_quality_issues(
        ctx, "You can't use that API directly, but here's an alternative approach."
    )
    assert not report.has_issues


def test_detect_quality_short_rich_reply():
    """A rich-context turn with a very short reply (< 40 chars) is flagged."""
    ctx = _ctx(rich_context_turn=True)
    report = detect_quality_issues(ctx, "Yes.")
    assert report.has_issues
    assert any(s.code == "short_rich_reply" for s in report.signals)


def test_detect_quality_short_reply_skipped_for_lightweight():
    """A lightweight turn (greeting/ack) with a short reply is NOT flagged."""
    ctx = _ctx(rich_context_turn=True, lightweight_turn=True)
    report = detect_quality_issues(ctx, "Hi!")
    assert not report.has_issues


def test_detect_quality_short_reply_skipped_for_quiz_turn():
    """A quiz answer turn (skip_memory_jobs=True) with brief feedback is NOT
    flagged — brief quiz feedback is expected."""
    ctx = _ctx(rich_context_turn=True, skip_memory_jobs=True)
    report = detect_quality_issues(ctx, "Correct!")
    assert not report.has_issues


def test_detect_quality_short_reply_skipped_for_instant_reply():
    """An instant reply (canned time/location) is NOT flagged."""
    ctx = _ctx(rich_context_turn=True, instant_reply="It's 3 PM.")
    report = detect_quality_issues(ctx, "It's 3 PM.")
    assert not report.has_issues


def test_detect_quality_short_reply_skipped_for_image_gen():
    """An image gen turn (terminal_image_content set) is NOT flagged — the
    '[Image: …]' row is always short."""
    ctx = _ctx(rich_context_turn=True, terminal_image_content="[Image: cat.png]")
    report = detect_quality_issues(ctx, "[Image: cat.png]")
    assert not report.has_issues


def test_detect_quality_short_reply_skipped_for_non_rich():
    """A non-rich-context turn with a short reply is NOT flagged — casual
    chat can legitimately be brief."""
    ctx = _ctx(rich_context_turn=False)
    report = detect_quality_issues(ctx, "No.")
    assert not report.has_issues


def test_detect_quality_empty_reply_no_crash():
    """An empty reply does not crash and does not flag short_rich_reply
    (the ModelUnavailableError path handles truly empty replies)."""
    ctx = _ctx()
    report = detect_quality_issues(ctx, "")
    assert not report.has_issues


def test_detect_quality_both_refusal_and_short():
    """A reply that is both a refusal and short flags both signals."""
    ctx = _ctx(rich_context_turn=True)
    report = detect_quality_issues(ctx, "I can't.")
    assert report.has_issues
    codes = {s.code for s in report.signals}
    assert "refusal_pattern" in codes
    assert "short_rich_reply" in codes


def test_detect_quality_duplicate_answer():
    ctx = _ctx(rich_context_turn=False)
    report = detect_quality_issues(
        ctx,
        "The value is 12.\n```answer\n12\n```",
    )
    assert any(s.code == "duplicate_answer" for s in report.signals)


def test_detect_quality_trailing_sources_is_not_raw_in_body():
    ctx = _ctx(rich_context_turn=False)
    report = detect_quality_issues(
        ctx,
        'Latest news.\n```sources\n[{"title": "A", "url": "https://a.example"}]\n```',
    )
    assert not any(s.code == "raw_sources_in_body" for s in report.signals)


def test_detect_quality_sources_mid_body():
    ctx = _ctx(rich_context_turn=False)
    report = detect_quality_issues(
        ctx,
        'Intro.\n```sources\n[{"title": "A", "url": "https://a.example"}]\n```\nMore prose.',
    )
    assert any(s.code == "raw_sources_in_body" for s in report.signals)


def test_detect_quality_unclosed_rich_fence():
    ctx = _ctx(rich_context_turn=False)
    report = detect_quality_issues(ctx, 'Plot:\n```graph\n{"type":"function"')
    assert any(s.code == "unclosed_rich_fence" for s in report.signals)


def test_detect_quality_malformed_json_fence():
    ctx = _ctx(rich_context_turn=False)
    report = detect_quality_issues(ctx, "```graph\n{bad json\n```")
    assert any(s.code == "malformed_json_fence" for s in report.signals)


def test_detect_quality_flags_instructions_inside_draft_fence():
    ctx = _ctx(rich_context_turn=False)
    report = detect_quality_issues(
        ctx,
        "I'll craft a message for you.\n"
        "```message\n"
        "fence!\n(Or paste their number if SMS and you want it formatted for texting.)\n"
        "```",
    )
    assert any(s.code == "invalid_draft_fence" for s in report.signals)


def test_detect_quality_allows_real_multilingual_draft_fence():
    ctx = _ctx(rich_context_turn=False)
    report = detect_quality_issues(
        ctx,
        "```message\nመልካም ልደት! ደስታና ፍቅር የተሞላ ቀን እመኛለሁ።\n```",
    )
    assert not any(s.code == "invalid_draft_fence" for s in report.signals)

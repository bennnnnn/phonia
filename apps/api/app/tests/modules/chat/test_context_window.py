"""Tests for token estimation + token-budget window selection."""

import pytest

from app.modules.chat.context_window import (
    cap_summary,
    compute_history_split,
    estimate_tokens,
    messages_within_token_budget,
    select_recent_window,
    should_run_compression,
    trim_message_for_summary,
    unsummarized_gap_bounds,
)


class _M:
    def __init__(self, content: str):
        self.content = content


def test_estimate_tokens():
    assert estimate_tokens("") == 1
    assert estimate_tokens("a" * 400) == 111


def test_estimate_tokens_non_latin_is_one_per_char() -> None:
    amharic = "ፕሮጀክቶችፕሮጀክቶችፕሮጀክቶች"
    assert estimate_tokens(amharic) == len(amharic)
    cyrillic = "проекты" * 8
    assert estimate_tokens(cyrillic) == len(cyrillic)


def test_estimate_tokens_vision_content_list():
    """Finalize fallback must not crash when vision turns use list content."""
    parts = [
        {"type": "text", "text": "what is in this image?"},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc"}},
    ]
    assert estimate_tokens(parts) >= 85
    assert estimate_tokens([{"type": "image_url", "image_url": {"url": "x"}}]) == 85
    assert estimate_tokens([]) == 1


def test_estimate_tokens_code_heavier():
    plain = "a" * 400
    code = "```python\n" + ("x = 1\n" * 40) + "```"
    assert estimate_tokens(code) > estimate_tokens(plain)


def test_select_keeps_all_when_under_budget():
    msgs = [_M("hi"), _M("there"), _M("friend")]
    assert select_recent_window(msgs, budget=1000, max_count=40) == 3


def test_select_respects_max_count():
    msgs = [_M("x") for _ in range(50)]
    assert select_recent_window(msgs, budget=10_000, max_count=40) == 40


def test_select_trims_to_budget():
    msgs = [_M("a" * 400) for _ in range(10)]
    assert select_recent_window(msgs, budget=250, max_count=40, min_count=2) == 2


def test_select_keeps_min_even_when_over_budget():
    msgs = [_M("a" * 1000), _M("a" * 1000), _M("a" * 1000)]
    assert select_recent_window(msgs, budget=50, max_count=40, min_count=2) == 2


def test_compute_history_split():
    msgs = [_M("a" * 400) for _ in range(40)]
    split = compute_history_split(60, msgs, budget=6000, max_count=40)
    # All 40 recent messages fit the budget, so the 20 older ones are summarized.
    assert split.summarized_count == 20


def test_should_run_compression_batch():
    split = compute_history_split(60, [_M("x")] * 40, budget=6000, max_count=40)
    # summarized_count = 20; pending = 20 - 0 = 20 >= batch(10) → run
    assert should_run_compression(split, already_summarized=0, batch=10) is True
    # pending = 20 - 18 = 2 < urgent_min_pending(3) → wait (small gap amortizes)
    assert should_run_compression(split, already_summarized=18, batch=10) is False


def test_should_run_compression_urgent_without_token_pressure():
    """H5: a gap >= urgent_min_pending must compress even without token
    pressure — otherwise the middle-history hole drops messages that are
    neither in the summary nor in the recent window."""
    msgs = [_M("x")] * 40
    split = compute_history_split(60, msgs, budget=6000, max_count=40)
    # No token pressure: the whole recent window is kept.
    assert split.summarized_count == 20
    assert should_run_compression(split, already_summarized=0, batch=10, urgent_min_pending=3)


def test_should_run_compression_urgent_under_token_pressure():
    msgs = [_M("a" * 400) for _ in range(40)]
    split = compute_history_split(60, msgs, budget=250, max_count=40)
    # Token pressure: the budget trims the window to its 2-message minimum.
    assert split.summarized_count == 58
    assert should_run_compression(split, already_summarized=0, batch=10, urgent_min_pending=3)


def test_should_run_compression_small_gap_waits():
    """A 1-2 message gap is too small to justify an LLM summarization call;
    wait for it to grow to urgent_min_pending."""
    split = compute_history_split(60, [_M("x")] * 40, budget=6000, max_count=40)
    # summarized_count = 60 - 40 = 20; already = 18 → pending = 2
    assert (
        should_run_compression(split, already_summarized=18, batch=10, urgent_min_pending=3)
        is False
    )


def test_unsummarized_gap_bounds_takes_the_hole_before_the_window():
    # 100 messages, summary covers 70, window holds the last 20 → indexes 70..80.
    assert unsummarized_gap_bounds(total=100, summarized=70, loaded=20) == (70, 10)


def test_unsummarized_gap_bounds_caps_a_long_hole_at_the_newest_messages():
    assert unsummarized_gap_bounds(total=100, summarized=0, loaded=20, max_messages=10) == (70, 10)


def test_gap_messages_stop_when_the_token_budget_is_spent():
    short = _M("hi")
    long = _M("a" * 400)
    fitted = messages_within_token_budget([long, short], budget=20, max_messages=10)
    assert fitted == [short]
    assert messages_within_token_budget([long], budget=0, max_messages=10) == []


def test_unsummarized_gap_bounds_empty_when_summary_reaches_the_window():
    assert unsummarized_gap_bounds(total=100, summarized=80, loaded=20) is None
    assert unsummarized_gap_bounds(total=15, summarized=0, loaded=15) is None


def test_trim_and_cap_summary():
    long = "word " * 500
    trimmed = trim_message_for_summary(long, max_chars=100)
    assert "[truncated]" in trimmed
    assert len(trimmed) <= 100
    capped = cap_summary("x" * 7000, max_chars=100)
    assert capped.endswith("...")


_CV = "Here is my CV:\n" + "Led backend projects in Go; shipped payment systems. " * 30


@pytest.mark.parametrize(
    ("message", "kept"),
    [
        # The ask after a paste is what the summary must hold.
        (f"{_CV}\nI'm applying to Stripe for the senior role, deadline Friday.", "Stripe"),
        # So is the instruction before one.
        (f"Rewrite this for a Stripe application, keep it to one page.\n{_CV}", "Stripe"),
    ],
)
def test_a_long_message_keeps_its_start_and_end_for_the_summary(message, kept):
    trimmed = trim_message_for_summary(message)
    assert len(trimmed) <= 1200 < len(message)
    assert kept in trimmed
    assert "[truncated]" in trimmed


# ── estimate_tokens — O(1) ────────────────────────────────────────────────────


def test_estimate_tokens_empty():
    from app.modules.chat.context_window import estimate_tokens

    assert estimate_tokens("") == 1


def test_estimate_tokens_short():
    from app.modules.chat.context_window import estimate_tokens

    # "hello" → len=5 // 4 = 1, max(1,1)=1
    assert estimate_tokens("hello") == 1


def test_estimate_tokens_long():
    from app.modules.chat.context_window import estimate_tokens

    text = "a" * 400
    assert estimate_tokens(text) == 111

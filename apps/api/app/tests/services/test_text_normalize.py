"""Tests for shared text normalization helpers."""

from app.services.text_normalize import cap_text_head_tail, collapse_ws, straighten_apostrophes


def test_collapse_ws():
    assert collapse_ws("  a \n b\t c  ") == "a b c"


def test_collapse_ws_strips_zero_width():
    assert collapse_ws("hi\u200b") == "hi"
    assert collapse_ws("\ufeffok") == "ok"


def test_straighten_apostrophes_folds_both_curly_quotes():
    assert straighten_apostrophes("What\u2019s it \u2018like\u2019") == "What's it 'like'"
    assert straighten_apostrophes('say "hi" \u201cok\u201d') == 'say "hi" \u201cok\u201d'


def test_cap_text_head_tail_short_passthrough():
    assert cap_text_head_tail("hello", 4000) == "hello"


def test_cap_text_head_tail_keeps_ends():
    text = "A" * 1000 + "MIDDLE" + "Z" * 1000
    out = cap_text_head_tail(text, max_chars=100)
    assert len(out) == 100
    assert out.startswith("A")
    assert out.endswith("Z")
    assert "…" in out
    assert "MIDDLE" not in out

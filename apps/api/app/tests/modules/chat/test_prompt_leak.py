"""Prompt scaffolding must never survive into a user-visible reply.

`[BEGIN VERIFIED MATH]` / `[END VERIFIED MATH]` wrap the block injected into
the prompt on every verified math turn. The model is instructed never to
mention a system block — but instruction is not enforcement, and this class of
leak has already reached a user once: `*Couldn't verify this with SymPy.*`
appeared under an anatomy answer (fixed separately).

Every other test touching these markers asserts they are *present in the
prompt*. These assert they are absent from what the user sees.
"""

from __future__ import annotations

import pytest

from app.services.solving import (
    VERIFIED_MATH_BEGIN,
    VERIFIED_MATH_END,
    VERIFIED_PHYSICS_END,
    strip_verified_solve_markers,
    wrap_verified_math,
)


@pytest.mark.parametrize(
    "reply",
    [
        f"{VERIFIED_MATH_BEGIN}\nVerified result: 2.02 s\n{VERIFIED_MATH_END}",
        f"The ball falls for:\n\n{VERIFIED_MATH_BEGIN}\nVerified result: 2.02 s\n"
        f"{VERIFIED_MATH_END}\n\nSo about 2 seconds.",
        f"As the {VERIFIED_MATH_BEGIN} block says, t = 2.02 s",
        f"{VERIFIED_MATH_BEGIN}\nt = 2.02 s",
        f"t = 2.02 s\n{VERIFIED_MATH_END}",
    ],
)
def test_markers_never_survive(reply: str) -> None:
    out = strip_verified_solve_markers(reply)

    assert VERIFIED_MATH_BEGIN not in out
    assert VERIFIED_MATH_END not in out
    assert "BEGIN VERIFIED" not in out
    assert VERIFIED_PHYSICS_END not in out


def test_the_answer_between_the_markers_is_kept() -> None:
    """Strip the scaffolding, not the reply.

    A model that echoed the block usually put the real answer inside it. An
    empty reply is worse than a slightly formal one.
    """
    out = strip_verified_solve_markers(
        f"The ball falls for:\n\n{VERIFIED_MATH_BEGIN}\nVerified result: 2.02 s\n"
        f"{VERIFIED_MATH_END}\n\nSo about 2 seconds."
    )

    assert "Verified result: 2.02 s" in out
    assert "The ball falls for:" in out
    assert "So about 2 seconds." in out


def test_a_clean_reply_is_returned_unchanged() -> None:
    """No marker, no work — the common case must not be reformatted."""
    reply = "The ball falls for about 2.02 s.\n\nThat is $t = \\sqrt{2h/g}$."

    assert strip_verified_solve_markers(reply) is reply


def test_wrap_then_strip_round_trips() -> None:
    body = "Verified result: 2.02 s"

    assert strip_verified_solve_markers(wrap_verified_math(body)) == body


def test_removing_a_marker_line_leaves_no_blank_gap() -> None:
    out = strip_verified_solve_markers(
        f"Answer:\n{VERIFIED_MATH_BEGIN}\nt = 2.02 s\n{VERIFIED_MATH_END}\nDone."
    )

    assert "\n\n\n" not in out
    assert out.startswith("Answer:")
    assert out.endswith("Done.")

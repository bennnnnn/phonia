"""Shared prompt-message injection helpers."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any


def inject_before_last_user(messages: list[dict[str, str]], block: str) -> list[dict[str, str]]:
    """Insert a system block immediately before the last user message."""
    augmented = list(messages)
    insert_at = len(augmented)
    for index in range(len(augmented) - 1, -1, -1):
        if augmented[index].get("role") == "user":
            insert_at = index
            break
    augmented.insert(insert_at, {"role": "system", "content": block})
    return augmented


def append_after_history(messages: list[dict[str, str]], block: str) -> list[dict[str, str]]:
    """Add a system block after the history: just before the turn's own line when the
    prompt ends with it, else at the end, so it never splits an earlier question from
    its reply."""
    augmented = list(messages)
    at = len(augmented) - 1 if augmented and augmented[-1].get("role") == "user" else None
    augmented.insert(len(augmented) if at is None else at, {"role": "system", "content": block})
    return augmented


def conversation_turns(messages: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """A built prompt's user and assistant turns, in order.

    Its system messages are left out: the rules before the history, and the turn's
    context, contracts and results between the history and the user's line. A reader
    of the last exchange then finds the reply right before that line.
    """
    return [message for message in messages if message.get("role") in {"user", "assistant"}]

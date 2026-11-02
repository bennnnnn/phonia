"""A subject's reply policy is stated once per prompt, in its last place.

The policy reached one prompt two or three times by accident: it closes the subject's
style pack, a maths follow-up adds it again, the verified-solve block before the user
turn closes with it, and a SymPy tool round appends it after its results. Each extra
copy costs tokens on every turn and tells the model nothing new, so only the copy
closest to the user turn stays.

Other repeats are on purpose and stay: a lesson or plan contract is restated beside
the user turn for small models (``NEARBY_CONTRACTS``), and the disclosure contract
closes the system prompt after its exclusive pack.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from app.modules.chat.prompt_subjects import SUBJECT_HINTS

# Every subject's reply policy: a solve block and the tool loop repeat it.
REPLY_POLICIES: tuple[str, ...] = tuple(
    policy for hints in SUBJECT_HINTS.values() for policy in hints.closing
)


def last_policy_parts(*groups: Sequence[str]) -> list[list[str]]:
    """The groups' parts in order, a reply policy that comes again later left out."""
    later: set[str] = set()
    kept: list[list[str]] = []
    for group in reversed(groups):
        parts: list[str] = []
        for part in reversed(group):
            if part in REPLY_POLICIES:
                if part in later:
                    continue
                later.add(part)
            parts.append(part)
        kept.append(parts[::-1])
    return kept[::-1]


def policies_once(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """``messages`` with each reply policy left only in the last system message stating it.

    Only system messages count and change: a user who pastes a policy keeps their
    words, and the system copies stay. A system message left empty is dropped. The
    messages are not changed in place.
    """
    out = list(messages)
    for policy in REPLY_POLICIES:
        holders = [index for index, message in enumerate(out) if policy in _system_text(message)]
        for index in reversed(holders[:-1]):
            content = _without(_system_text(out[index]), policy)
            if content:
                out[index] = {**out[index], "content": content}
            else:
                del out[index]
    return out


def _system_text(message: dict[str, Any]) -> str:
    content = message.get("content")
    return content if message.get("role") == "system" and isinstance(content, str) else ""


def _without(text: str, part: str) -> str:
    """``text`` without every copy of ``part``, each with the space that joined it on."""
    while part in text:
        start = text.index(part)
        before, after = text[:start], text[start + len(part) :]
        head, tail = before.rstrip(), after.lstrip()
        text = f"{head}{before[len(head) :]}{tail}" if head and tail else head or tail
    return text

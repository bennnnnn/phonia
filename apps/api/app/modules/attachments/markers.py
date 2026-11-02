"""``[Image: …]`` and ``[File: …]`` markers in stored message text.

Linear line scans, no regex on message bodies.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

_ATTACH_ID_PREFIX = "/attachments/"
_ATTACH_ID_SUFFIX = "/file"
VISION_REHYDRATE_LIMIT = 2
_IMAGE_UNAVAILABLE_NOTE = (
    "The earlier image is not available to look at again. "
    "Do not guess from a prior description; say you cannot see it. "
    "Do not call it a placeholder or a failed generation."
)


def image_marker(attachment_id: UUID | str) -> str:
    """The ``[Image: /attachments/{uuid}/file]`` line a message stores for a picture."""
    return f"[Image: {_ATTACH_ID_PREFIX}{attachment_id}{_ATTACH_ID_SUFFIX}]"


def _is_image_marker_line(line: str) -> bool:
    s = line.strip()
    return s.startswith("[Image:") and s.endswith("]") and len(s) > len("[Image:]")


def _is_file_ref_line(line: str) -> bool:
    s = line.strip()
    return s.startswith("[File:") and s.endswith("]") and len(s) > len("[File:]")


def image_attachment_ids_from_text(content: str) -> list[UUID]:
    """Parse ``[Image: /attachments/{uuid}/file]`` markers with a linear scan."""
    found: list[UUID] = []
    seen: set[UUID] = set()
    for line in content.splitlines():
        stripped = line.strip()
        if not _is_image_marker_line(stripped):
            continue
        inner = stripped[len("[Image:") : -1].strip()
        start = inner.find(_ATTACH_ID_PREFIX)
        if start < 0:
            continue
        id_start = start + len(_ATTACH_ID_PREFIX)
        id_end = inner.find(_ATTACH_ID_SUFFIX, id_start)
        if id_end < 0:
            continue
        raw = inner[id_start:id_end]
        try:
            uid = UUID(raw)
        except ValueError:
            continue
        if uid in seen:
            continue
        seen.add(uid)
        found.append(uid)
    return found


def _content_as_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                text = part.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts)
    return ""


def prior_image_attachment_ids(
    messages: list[dict[str, Any]],
    *,
    limit: int = VISION_REHYDRATE_LIMIT,
) -> list[UUID]:
    """Most recent prior-turn image ids (newest first), excluding the last user turn."""
    if limit <= 0:
        return []
    last_user: int | None = None
    for index in range(len(messages) - 1, -1, -1):
        if messages[index].get("role") == "user":
            last_user = index
            break
    start = last_user - 1 if last_user is not None else len(messages) - 1
    ordered: list[UUID] = []
    seen: set[UUID] = set()
    for index in range(start, -1, -1):
        for uid in image_attachment_ids_from_text(_content_as_text(messages[index].get("content"))):
            if uid in seen:
                continue
            seen.add(uid)
            ordered.append(uid)
            if len(ordered) >= limit:
                return ordered
    return ordered


def previous_user_turn_has_image(messages: list[dict[str, Any]]) -> bool:
    """True when the user message before the last one carried an ``[Image: …]`` marker."""
    user_turns = [message for message in messages if message.get("role") == "user"]
    if len(user_turns) < 2:
        return False
    return bool(image_attachment_ids_from_text(_content_as_text(user_turns[-2].get("content"))))


def append_image_unavailable_note(prompt_messages: list[dict[str, Any]]) -> None:
    """Tell the model it cannot see a prior image — do not guess from a caption."""
    for index in range(len(prompt_messages) - 1, -1, -1):
        msg = prompt_messages[index]
        if msg.get("role") != "user":
            continue
        content = msg.get("content")
        if isinstance(content, str):
            msg["content"] = f"{content}\n\n{_IMAGE_UNAVAILABLE_NOTE}"
            return
        if isinstance(content, list):
            content.append({"type": "text", "text": _IMAGE_UNAVAILABLE_NOTE})
            return
        msg["content"] = _IMAGE_UNAVAILABLE_NOTE
        return


def strip_attachment_from_content(content: str, attachment_id: UUID) -> str:
    """Remove this attachment's markers (and a following file excerpt) from a message.

    Linear scan — no regex. Empty result means the caller should delete the row.
    """
    needle = str(attachment_id)
    kept: list[str] = []
    skipping_file_block = False
    for line in content.split("\n"):
        stripped = line.strip()
        if skipping_file_block:
            if _is_image_marker_line(stripped) or _is_file_ref_line(stripped):
                skipping_file_block = False
            else:
                continue
        if needle in stripped and (_is_image_marker_line(stripped) or _is_file_ref_line(stripped)):
            skipping_file_block = _is_file_ref_line(stripped)
            continue
        kept.append(line)
    return "\n".join(kept).strip()


def _strip_image_markers(text: str) -> str:
    lines = [line for line in text.splitlines() if not _is_image_marker_line(line)]
    return "\n".join(lines).strip()

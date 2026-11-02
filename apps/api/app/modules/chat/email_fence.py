"""Rewrite a stored ```email fence from structured draft fields."""

from app.services.md_fence_scan import replace_first_closed_fence_body


def format_email_fence_body(*, to: str | None, subject: str | None, body: str) -> str:
    """Match mobile `fullEmailText`: To / Subject / blank / body."""
    parts: list[str] = []
    if to:
        parts.append(f"To: {to}")
    if subject:
        parts.append(f"Subject: {subject}")
    if parts:
        parts.append("")
    parts.append(body)
    return "\n".join(parts)


def rewrite_first_email_fence(
    content: str,
    *,
    to: str | None,
    subject: str | None,
    body: str,
) -> str | None:
    """Replace the first closed ```email fence body, or None if there is none."""
    return replace_first_closed_fence_body(
        content,
        "email",
        format_email_fence_body(to=to, subject=subject, body=body),
    )

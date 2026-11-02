"""Shared pieces of the hosted legal pages: the effective date, contact line and renderer."""

# The inline page stylesheet is one long line.
# ruff: noqa: E501

from __future__ import annotations

import html
import logging
import re

from app.core.config import Settings

logger = logging.getLogger(__name__)

# Shown at the top of the privacy policy and terms. Change it with any edit to their text.
LEGAL_EFFECTIVE_DATE = "October 29, 2026"

# Without SUPPORT_EMAIL (local dev) the pages still render; production boot warns.
_NO_EMAIL_CONTACT = "use the support link on Recall's app-store listing"
_PLAIN_EMAIL = re.compile(r"[^@\s()<>\[\]]+@[^@\s()<>\[\]]+\.[^@\s()<>\[\]]+")

_BOLD = re.compile(r"\*\*(.+?)\*\*")
# Only https, mailto and same-site paths become links.
_LINK = re.compile(r"\[([^\]]+)\]\(((?:https://|mailto:|/)[^\s)]+)\)")
_ORDERED_ITEM = re.compile(r"^\d+\.\s+")


def contact_markdown(support_email: str) -> str:
    """How to reach us, as a phrase that completes "To contact us, ...": a mailto link."""
    email = support_email.strip()
    if not _PLAIN_EMAIL.fullmatch(email):
        return _NO_EMAIL_CONTACT
    return f"email [{email}](mailto:{email})"


def warn_if_no_support_email(settings: Settings) -> None:
    """Production boot: the store listings link pages that need a real contact address."""
    if settings.environment == "production" and not settings.support_email.strip():
        logger.warning(
            "SUPPORT_EMAIL is empty: the privacy policy, terms and account-deletion pages "
            "have no contact address. Set it before submitting to the stores."
        )


def _inline(raw: str) -> str:
    escaped = html.escape(raw)
    linked = _LINK.sub(r'<a href="\2">\1</a>', escaped)
    return _BOLD.sub(r"<strong>\1</strong>", linked)


def markdown_to_html(markdown: str, *, page_title: str) -> str:
    """Minimal markdown → HTML for legal pages (headings, lists, paragraphs, bold, links)."""
    body_parts: list[str] = []
    open_list: str | None = None
    for raw_line in markdown.strip().split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("- "):
            kind, item = "ul", line[2:]
        elif _ORDERED_ITEM.match(line):
            kind, item = "ol", _ORDERED_ITEM.sub("", line, count=1)
        else:
            kind, item = None, line
        if open_list and open_list != kind:
            body_parts.append(f"</{open_list}>")
            open_list = None
        if kind:
            if open_list is None:
                body_parts.append(f"<{kind}>")
                open_list = kind
            body_parts.append(f"<li>{_inline(item)}</li>")
        elif line.startswith("# "):
            body_parts.append(f"<h1>{html.escape(line[2:])}</h1>")
        elif line.startswith("## "):
            body_parts.append(f"<h2>{html.escape(line[3:])}</h2>")
        else:
            body_parts.append(f"<p>{_inline(line)}</p>")
    if open_list:
        body_parts.append(f"</{open_list}>")

    html_body = "\n".join(body_parts)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{html.escape(page_title)}</title>
  <style>
    body {{ font-family: system-ui, sans-serif; line-height: 1.55; max-width: 42rem; margin: 2rem auto; padding: 0 1rem; color: #111; }}
    h1 {{ font-size: 1.75rem; margin-bottom: 0.5rem; }}
    h2 {{ font-size: 1.15rem; margin-top: 1.5rem; }}
    p, li {{ font-size: 1rem; }}
    ul, ol {{ padding-left: 1.25rem; }}
    a {{ color: #1d4ed8; }}
  </style>
</head>
<body>
{html_body}
</body>
</html>"""

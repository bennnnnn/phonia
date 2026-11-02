"""Finalize pass: on a searched turn, a link is a source only if the search found it.

The search hint asks for ``[Name](url)`` links, and a model can write one for a
page no result returned: a made-up source that reads as a citation. On a turn
with search results, an inline markdown link stays a link when its page was
among this turn's results (or the user's own message), when it is the home page
of a site a result came from, or when it is a Google Maps search for a place.
Any other link keeps its words and loses its URL.

It runs after ``untrusted_media``, which turns a model's image into a link: the
image's own address is not a source claim, so those links stay. Fenced and
inline code are copied as written, so a code sample's links are untouched.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from app.modules.chat.inline_code import escaped_at, read_inline_code_span
from app.modules.chat.markdown_regions import map_prose_outside_fences

if TYPE_CHECKING:
    from app.modules.chat.finalize_passes import FinalizeState

_USER_URL = re.compile(r"https?://[^\s<>()\[\]\"']+", re.IGNORECASE)
_IMAGE_SOURCE = re.compile(
    r"!\[[^\]\n]*\]\(\s*<?([^\s)>]+)|<img\b[^>]*\bsrc\s*=\s*[\"']?([^\"'\s>]+)", re.IGNORECASE
)
_MAPS_HOSTS = frozenset({"google.com", "maps.google.com"})


def _key(url: str) -> tuple[str, str] | None:
    """Host (no ``www.``) and path (no trailing slash) with its query: what a link opens."""
    try:
        parts = urlsplit(url.strip().strip("<>"))
    except ValueError:
        return None
    if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
        return None
    host = parts.hostname.lower().removeprefix("www.")
    path = parts.path.rstrip("/")
    return host, f"{path}?{parts.query}" if parts.query else path


class _Allowed:
    """The pages this turn may link: its results, the user's links and the model's images."""

    def __init__(self, urls: list[str]) -> None:
        keys = [key for url in urls if (key := _key(url)) is not None]
        self.pages = set(keys)
        self.hosts = {host for host, _path in keys}

    def __contains__(self, url: str) -> bool:
        key = _key(url)
        if key is None:
            return False
        host, path = key
        if key in self.pages or (path == "" and host in self.hosts):
            return True
        return host in _MAPS_HOSTS and path.startswith("/maps")


def unlink_unretrieved_links(state: FinalizeState) -> str:
    """Pass entry: a searched turn's links point only at what the search returned."""
    ctx = state.ctx
    if state.server_text or not ctx.search_sources:
        return state.text
    images = [next(g for g in match.groups() if g) for match in _IMAGE_SOURCE.finditer(state.raw)]
    allowed = _Allowed(
        [hit.url for hit in ctx.search_sources]
        + _USER_URL.findall(ctx.user_message_content or "")
        + images
    )
    return unlink_except(state.text, allowed)


def unlink_except(text: str, allowed: _Allowed) -> str:
    if "](" not in text:
        return text
    return map_prose_outside_fences(text, lambda prose: _rewrite_links(prose, allowed))


def _link_at(prose: str, start: int) -> tuple[int, str, str] | None:
    """The inline link whose ``[`` is at ``start``: its end, its words and its URL."""
    close = prose.find("]", start + 1)
    if close < 0 or "\n\n" in prose[start:close] or not prose.startswith("(", close + 1):
        return None
    depth = 0
    index = close + 1
    while index < len(prose):
        char = prose[index]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                break
        elif char == "\n":
            return None
        index += 1
    else:
        return None
    target = prose[close + 2 : index].strip()
    url = target.split(maxsplit=1)[0].strip("<>") if target else ""
    return index + 1, prose[start + 1 : close], url


def _plain(words: str) -> str:
    """A dropped link's words; a URL as its words becomes the site's name."""
    key = _key(words)
    return words if key is None else key[0]


def _rewrite_links(prose: str, allowed: _Allowed) -> str:
    out: list[str] = []
    index = 0
    while index < len(prose):
        char = prose[index]
        if char == "`" and (code_end := read_inline_code_span(prose, index)) is not None:
            out.append(prose[index:code_end])
            index = code_end
            continue
        # An image's "[" opens its alt text, not a link.
        image = char == "!" and prose.startswith("[", index + 1)
        if char == "[" and not escaped_at(prose, index):
            link = _link_at(prose, index)
            if link is not None and _key(link[2]) is not None and link[2] not in allowed:
                end, words, _url = link
                out.append(_plain(words))
                index = end
                continue
        out.append(prose[index : index + 2] if image else char)
        index += 2 if image else 1
    return "".join(out)

"""Finalize pass: nothing the model wrote loads a URL by itself.

Text an attacker planted in a web result, an uploaded PDF or a photo's OCR can
tell the model to put the user's memory, schedule or location into a URL.
Whatever a client fetches without a tap would then send it to the attacker: a
markdown image, an ``[Image: …]`` line (the app's attachment marker), the
favicon chips of a ``sources`` fence. The server's own pictures are always
Recall attachments (``[Image: /attachments/<id>/file]``), added after this pass
by the photo pass or before it by the image tools (whose turns skip
finalizing), and its chips come from ``add_search_sources``. So on model text,
before those passes, this one:

- drops an ``[Image: …]`` line unless it is an attachment marker (those load
  only from Recall's own API, as the signed-in user);
- turns a markdown image or HTML ``<img>`` whose source could reach another
  host into a link, labelled with its alt text or host: a tap opens it,
  nothing loads (inside a link's text, the label alone stays);
- drops a ``sources`` fence on a turn the server did not search.

Fenced code and inline code are copied byte for byte, so a markdown lesson's
``![alt](url)`` example stays as written. Saved history then auto-loads
nothing for the web client or an older app; the phone refuses untrusted
images itself while a reply streams (``apps/mobile/lib/images/imageUriPolicy.ts``).
"""

from __future__ import annotations

import html
import json
import re
import string
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from app.modules.chat.finalize_subjects import fallback_text
from app.modules.chat.inline_code import escaped_at, read_inline_code_span
from app.modules.chat.markdown_regions import map_prose_outside_fences
from app.services.md_fence_scan import iter_fences

if TYPE_CHECKING:
    from app.modules.chat.finalize_passes import FinalizeState

_ATTACHMENT_MARKER = re.compile(
    r"\[Image: /attachments/[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}/file\]"
)
_IMAGE_MARKER_HEAD = "[Image:"
# RFC 3986: a scheme is a letter, then letters, digits, "+", "." or "-", up to the first ":".
_SCHEME_FIRST = frozenset(string.ascii_letters)
_SCHEME_REST = frozenset(string.ascii_letters + string.digits + "+.-")
# Browsers drop tabs, newlines and control characters from URLs: "ht\ttps:" is https.
_URL_IGNORED_CHARS = re.compile(r"[\x00-\x20\x7f]")
_BACKSLASH_ESCAPE = re.compile(r"\\([!-/:-@\[-`{-~])")
_REFERENCE_DEFINITION = re.compile(
    r"^ {0,3}\[((?:[^\]\\\n]|\\.){1,999})\]:[ \t]*(<[^>\n]*>|\S+)", re.MULTILINE
)
_HTML_IMG = re.compile(r"<img\b[^>]*>", re.IGNORECASE)
_HTML_ATTR = r"\b{name}\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s>]+))"
_IMAGE_FALLBACK_LABEL = "image"


def neutralize_untrusted_media(state: FinalizeState) -> str:
    """The model's reply with no picture or chip that loads without a tap.

    A changed reply commits, so a later pass's failure keeps it (ES-03)."""
    if state.server_text:
        return state.text
    text = neutralize_media(state.text, searched=bool(state.ctx.search_sources))
    if text != state.text:
        state.committed = fallback_text(text, server_text=False)
    return text


def drop_media_lines(text: str) -> str:
    """What stands in when neutralizing fails: every line that could load a picture or
    a chip goes, in code too, and so does any ``sources`` fence. A Recall attachment
    marker alone on its line stays."""
    kept: list[str] = []
    for line in without_source_fences(text).split("\n"):
        lower = line.lower()
        loads = "![" in line or "<img" in lower or _IMAGE_MARKER_HEAD.lower() in lower
        if not loads or _ATTACHMENT_MARKER.fullmatch(line.strip()):
            kept.append(line)
    return "\n".join(kept)


def without_source_fences(text: str) -> str:
    """No closed fence the phone makes favicon chips of: a ``sources`` one, however it
    is spelled, or an unlabeled one whose body reads as source rows
    (``apps/mobile/lib/searchSources.ts``)."""
    if "```" not in text and "~~~" not in text:
        return text
    pieces: list[str] = []
    cursor = 0
    for fence in iter_fences(text):
        body = text[fence.body_start : fence.body_end]
        unlabeled = not fence.opener.info.strip()
        if fence.closed and (fence.lang == "sources" or (unlabeled and _source_rows(body))):
            pieces.append(text[cursor : fence.start])
            cursor = fence.end
    if not cursor:
        return text
    pieces.append(text[cursor:])
    return "".join(pieces).rstrip()


def _source_rows(body: str) -> bool:
    """A JSON list with a row that has a title or a URL: what the phone reads as chips."""
    if not body.lstrip().startswith("["):
        return False
    try:
        rows = json.loads(body)
    except (ValueError, RecursionError):
        return False
    return isinstance(rows, list) and any(
        isinstance(row, dict)
        and any(str(row[key]).strip() for key in ("title", "url") if row.get(key) is not None)
        for row in rows
    )


def neutralize_media(text: str, *, searched: bool) -> str:
    """See the module docstring. ``searched``: the server's chips replace any sources fence."""
    if not searched:
        text = without_source_fences(text)
    if "[Image:" not in text and "![" not in text and "<img" not in text.lower():
        return text
    definitions: dict[str, str] = {}

    def collect(prose: str) -> str:
        for match in _REFERENCE_DEFINITION.finditer(prose):
            definitions.setdefault(_label_key(match.group(1)), match.group(2).strip("<>"))
        return prose

    map_prose_outside_fences(text, collect)
    return map_prose_outside_fences(
        text, lambda prose: _rewrite_images(_drop_image_markers(prose), definitions)
    )


def _drop_image_markers(prose: str) -> str:
    """Drop ``[Image: …]`` lines that are not a Recall attachment marker."""
    if _IMAGE_MARKER_HEAD not in prose:
        return prose
    kept: list[str] = []
    for line in prose.split("\n"):
        marker = line.strip()
        is_marker = marker.startswith(_IMAGE_MARKER_HEAD) and marker.endswith("]")
        if is_marker and not _ATTACHMENT_MARKER.fullmatch(marker):
            continue
        kept.append(line)
    return "\n".join(kept)


def _label_key(label: str) -> str:
    return " ".join(label.split()).lower()


def _clean_url(raw: str) -> str:
    """The URL a client would fetch: entities and backslash escapes resolved."""
    return _URL_IGNORED_CHARS.sub("", _BACKSLASH_ESCAPE.sub(r"\1", html.unescape(raw)))


def loads_nothing(raw: str) -> bool:
    """An image source no client fetches from another host: inline data or a plain relative path."""
    url = _clean_url(raw)
    if not url or url.lower().startswith("data:"):
        return True
    if url.startswith(("//", "\\", "/\\")):
        return False
    return not _starts_with_scheme(url)


def _starts_with_scheme(url: str) -> bool:
    """``scheme:`` at the start, read in one pass: the URL is the model's, of any length."""
    head, colon, _rest = url.partition(":")
    return bool(colon and head) and head[0] in _SCHEME_FIRST and set(head) <= _SCHEME_REST


def _label(alt: str, url: str) -> str:
    alt = alt.strip()
    if alt:
        return alt
    try:
        host = urlsplit(_clean_url(url)).hostname
    except ValueError:
        host = None
    return host or _IMAGE_FALLBACK_LABEL


def _bracket_end(text: str, start: int) -> int | None:
    """Index of the ``]`` closing the ``[`` at ``start`` (nested, escaped, one paragraph)."""
    depth = 0
    index = start
    while index < len(text):
        char = text[index]
        if char == "\\":
            index += 2
            continue
        if char == "\n" and text.startswith("\n", index + 1):
            return None
        if char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                return index
        index += 1
    return None


def _skip_space(text: str, index: int) -> int:
    newline_seen = False
    while index < len(text) and text[index] in " \t\n":
        if text[index] == "\n":
            if newline_seen:
                break
            newline_seen = True
        index += 1
    return index


def _destination(text: str, index: int) -> tuple[str, int] | None:
    """The inline link destination at ``index`` and the index after it."""
    if text.startswith("<", index):
        close = text.find(">", index)
        if close < 0 or "\n" in text[index:close]:
            return None
        return text[index + 1 : close], close + 1
    depth = 0
    start = index
    while index < len(text):
        char = text[index]
        if char == "\\":
            index += 2
            continue
        if char.isspace() or ord(char) < 0x20:
            break
        if char == "(":
            depth += 1
        elif char == ")":
            if depth == 0:
                break
            depth -= 1
        index += 1
    return text[start:index], index


def _inline_tail_end(text: str, index: int) -> tuple[str, int] | None:
    """``(dest "title")`` from its ``(`` at ``index``: the destination and the end."""
    found = _destination(text, _skip_space(text, index + 1))
    if found is None:
        return None
    url, index = found
    index = _skip_space(text, index)
    if index < len(text) and text[index] in "\"'(":
        closer = ")" if text[index] == "(" else text[index]
        index += 1
        while index < len(text) and text[index] != closer:
            index += 2 if text[index] == "\\" else 1
        index = _skip_space(text, index + 1)
    if index >= len(text) or text[index] != ")":
        return None
    return url, index + 1


def _image_at(text: str, start: int, definitions: dict[str, str]) -> tuple[int, str, str] | None:
    """For the image whose ``![`` is at ``start``: its end, alt text and source."""
    alt_end = _bracket_end(text, start + 1)
    if alt_end is None:
        return None
    alt = text[start + 2 : alt_end]
    after = alt_end + 1
    if text.startswith("(", after):
        inline = _inline_tail_end(text, after)
        return None if inline is None else (inline[1], alt, inline[0])
    if text.startswith("[", after):
        ref_end = _bracket_end(text, after)
        if ref_end is None:
            return None
        label = text[after + 1 : ref_end] or alt
        url = definitions.get(_label_key(label))
        return None if url is None else (ref_end + 1, alt, url)
    url = definitions.get(_label_key(alt))
    return None if url is None else (after, alt, url)


def _rewrite_images(prose: str, definitions: dict[str, str]) -> str:
    """Markdown images and ``<img>`` tags that could reach a host become links."""
    out: list[str] = []
    depth = 0  # open "[" of a link's text around the scan position
    index = 0
    while index < len(prose):
        char = prose[index]
        if char == "`" and (code_end := read_inline_code_span(prose, index)) is not None:
            out.append(prose[index:code_end])
            index = code_end
            continue
        if char == "!" and prose.startswith("[", index + 1) and not escaped_at(prose, index):
            image = _image_at(prose, index, definitions)
            if image is not None and not loads_nothing(image[2]):
                end, alt, url = image
                label = _label(alt, url)
                # Inside a link's text a second link would not render: keep the words.
                out.append(label if depth else f"[{label}]{prose[index + 2 + len(alt) + 1 : end]}")
                index = end
                continue
        if char == "<" and (tag := _HTML_IMG.match(prose, index)) is not None:
            out.append(_img_tag_as_link(tag.group(0)))
            index = tag.end()
            continue
        if char in "[]" and not escaped_at(prose, index):
            depth = depth + 1 if char == "[" else max(0, depth - 1)
        out.append(char)
        index += 1
    return "".join(out)


def _html_attr(tag: str, name: str) -> str | None:
    match = re.search(_HTML_ATTR.format(name=name), tag, re.IGNORECASE)
    if match is None:
        return None
    return next(group for group in match.groups() if group is not None)


def _img_tag_as_link(tag: str) -> str:
    src = _html_attr(tag, "src") or ""
    if loads_nothing(src):
        return tag
    url = html.unescape(src).strip()
    for raw, encoded in ((" ", "%20"), ("(", "%28"), (")", "%29"), ("<", "%3C"), (">", "%3E")):
        url = url.replace(raw, encoded)
    return f"[{_label(html.unescape(_html_attr(tag, 'alt') or ''), url)}]({url})"

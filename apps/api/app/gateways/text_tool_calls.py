"""Tool calls a model writes as reply text, read as the calls they are.

GLM 5.2 sent its search as text on 2026-10-24, and the bubble showed it with no answer:
``<tool_call>web_search<arg_key>query</arg_key><arg_value>Ethiopia population …
</arg_value></tool_call>``. Text from ``<tool_call>`` to ``</tool_call>`` never streams
now. When the request offered tools, it is read as a call, in GLM's form (the name,
then ``<arg_key>``/``<arg_value>`` pairs, a closing ``</arg_key>`` sometimes left out)
or the JSON one (``{"name": …, "arguments": {…}}``), and the reply's search runs. When
it offered none (the search already ran), the call is dropped: a reply that was only
the call is empty, and the next model writes the answer. Text between the tags that is
no call (prose about the tag) is shown as written.
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.gateways.stream_tool_calls import StreamedToolCalls

CALL_OPEN = "<tool_call>"
CALL_CLOSE = "</tool_call>"
_ARGUMENT = re.compile(
    r"<arg_key>\s*([^<]+?)\s*(?:</arg_key>)?\s*<arg_value>(.*?)</arg_value>", re.DOTALL
)
# The longest text held back while a call may still close.
_MAX_CALL = 8_192


def _value(raw: str) -> Any:
    """A JSON object or list as one; anything else as the text it is. A query of "2024"
    stays a string, as the tool's schema wants."""
    text = raw.strip()
    if text[:1] in {"{", "["}:
        try:
            return json.loads(text)
        except ValueError:
            return text
    return text


def read_text_call(body: str) -> tuple[str, dict[str, Any]] | None:
    """The name and arguments in a call's text (what came between the tags), or None."""
    text = body.strip()
    if text.startswith("{"):
        try:
            parsed = json.loads(text)
        except ValueError:
            return None
        name = parsed.get("name") if isinstance(parsed, dict) else None
        arguments = parsed.get("arguments", parsed.get("parameters", {}))
        if isinstance(arguments, str):
            arguments = _value(arguments)
        if isinstance(name, str) and name and isinstance(arguments, dict):
            return name, arguments
        return None
    name = text.split("<", 1)[0].strip()
    if not name or not re.fullmatch(r"[A-Za-z_][\w.-]*", name):
        return None
    return name, {key: _value(value) for key, value in _ARGUMENT.findall(text)}


def _tag_start_at_end(text: str) -> int:
    """Where a ``<tool_call>`` cut off at the end of ``text`` begins, or -1."""
    for size in range(min(len(CALL_OPEN) - 1, len(text)), 0, -1):
        if CALL_OPEN.startswith(text[-size:]):
            return len(text) - size
    return -1


class TextToolCalls:
    """Holds a call written as text out of the stream; ``calls`` gets it when offered."""

    def __init__(self, calls: StreamedToolCalls | None) -> None:
        self._calls = calls
        self._buf = ""
        self.found = False

    def _take(self, body: str) -> bool:
        """Read ``body`` as a call; False when it is none (prose that names the tag)."""
        read = read_text_call(body)
        if read is None:
            return False
        if self._calls is not None:
            self._calls.add(read[0], json.dumps(read[1], ensure_ascii=False))
        self.found = True
        return True

    def feed(self, text: str) -> str:
        """The text to show from this piece; a call, and a tag still arriving, are held."""
        self._buf += text
        out: list[str] = []
        while self._buf:
            start = self._buf.find(CALL_OPEN)
            if start < 0:
                cut = _tag_start_at_end(self._buf)
                if cut < 0:
                    out.append(self._buf)
                    self._buf = ""
                else:
                    out.append(self._buf[:cut])
                    self._buf = self._buf[cut:]
                break
            out.append(self._buf[:start])
            end = self._buf.find(CALL_CLOSE, start)
            if end < 0:
                if len(self._buf) - start > _MAX_CALL:
                    # Not a call after all: let it through rather than hold the reply.
                    out.append(self._buf[start:])
                    self._buf = ""
                else:
                    self._buf = self._buf[start:]
                break
            whole = self._buf[start : end + len(CALL_CLOSE)]
            if not self._take(whole[len(CALL_OPEN) : -len(CALL_CLOSE)]):
                out.append(whole)
            self._buf = self._buf[end + len(CALL_CLOSE) :]
        return "".join(out)

    def flush(self) -> str:
        """The end of the stream: a call left open is still a call; prose that only named
        the tag ("The `<tool_call>` tag opens a call …") and a cut tag are text."""
        rest, self._buf = self._buf, ""
        if rest.startswith(CALL_OPEN) and self._take(rest[len(CALL_OPEN) :]):
            return ""
        return rest

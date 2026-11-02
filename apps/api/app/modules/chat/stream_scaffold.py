"""Keep prompt scaffolding and text-written tool calls out of the live token stream.

The finalize passes strip ``[BEGIN VERIFIED MATH]``-style markers
(``services.solving.strip_verified_solve_markers``) and ``!function_call:{…}``
blobs (``math.fence.convert_function_call_text``) from the saved reply, but the
tokens the phone draws while the reply streams came straight from the model, so
the scaffolding showed until ``done``. ``ScaffoldFilter`` removes the same text
from each token as it streams. Like the think stripper, it holds back a short
tail that could still grow into a marker, so a marker split across chunks never
goes out in pieces.
"""

from __future__ import annotations

from app.services.solving import (
    VERIFIED_MATH_BEGIN,
    VERIFIED_MATH_END,
    VERIFIED_PHYSICS_BEGIN,
    VERIFIED_PHYSICS_END,
)

# What a model writes when it types a tool call instead of making one; the
# finalize twin is math.fence.convert_function_call_text.
FUNCTION_CALL_MARKER = "!function_call:"
# Text between markers is kept: a model that echoed the block usually put the
# real answer inside it (strip_verified_solve_markers keeps it too).
_SOLVE_MARKERS = (
    VERIFIED_MATH_BEGIN,
    VERIFIED_MATH_END,
    VERIFIED_PHYSICS_BEGIN,
    VERIFIED_PHYSICS_END,
)
_MARKERS = (*_SOLVE_MARKERS, FUNCTION_CALL_MARKER)
# A text-written tool call is a small JSON object. One that has not closed by
# this length is not one: it is shown, as the finalize pass would keep it.
MAX_HELD_CALL_CHARS = 8_192


# Every marker opens with one of these: only a tail that starts with one can still grow
# into a marker, so most chunks need no comparison at all.
_MARKER_OPENERS = tuple(sorted({marker[0] for marker in _MARKERS}))
_LONGEST_PARTIAL = max(len(marker) for marker in _MARKERS) - 1


def _partial_marker_len(text: str) -> int:
    """Length of the longest tail of ``text`` that a marker could still start with."""
    start = max(0, len(text) - _LONGEST_PARTIAL)
    while True:
        openers = [at for at in (text.find(char, start) for char in _MARKER_OPENERS) if at >= 0]
        if not openers:
            return 0
        start = min(openers)
        tail = text[start:]
        if any(len(tail) < len(marker) and marker.startswith(tail) for marker in _MARKERS):
            return len(tail)
        start += 1


class ScaffoldFilter:
    """Stateful filter over a reply's tokens; ``feed`` each one, then ``flush``."""

    def __init__(self) -> None:
        self._buf = ""
        # The text after a FUNCTION_CALL_MARKER, held until its JSON object closes.
        self._call: str | None = None
        self._depth = 0
        self._in_string = False
        self._escaped = False

    def feed(self, chunk: str) -> str:
        self._buf += chunk
        out: list[str] = []
        while self._buf:
            if self._call is not None:
                if not self._consume_call(out):
                    break
                continue
            found = self._first_marker()
            if found is None:
                safe = len(self._buf) - _partial_marker_len(self._buf)
                out.append(self._buf[:safe])
                self._buf = self._buf[safe:]
                break
            index, marker = found
            out.append(self._buf[:index])
            self._buf = self._buf[index + len(marker) :]
            if marker == FUNCTION_CALL_MARKER:
                self._start_call()
        return "".join(out)

    def flush(self) -> str:
        """The held text once the stream ends: a marker that never completed is
        text, and an unclosed call keeps its object as the finalize pass does."""
        held = self._buf
        if self._call is not None:
            held = self._call.lstrip() + held
        self._buf = ""
        self._call = None
        return held

    def _first_marker(self) -> tuple[int, str] | None:
        best: tuple[int, str] | None = None
        for marker in _MARKERS:
            index = self._buf.find(marker)
            if index != -1 and (best is None or index < best[0]):
                best = (index, marker)
        return best

    def _start_call(self) -> None:
        self._call = ""
        self._depth = 0
        self._in_string = False
        self._escaped = False

    def _consume_call(self, out: list[str]) -> bool:
        """Read the held call; True once it ended and normal text resumes."""
        held = self._call or ""
        for index, char in enumerate(self._buf):
            if self._depth == 0:
                if char.isspace():
                    continue
                if char != "{":
                    # The marker alone, with no object after it: drop the marker.
                    self._buf = self._buf[index:]
                    self._call = None
                    return True
            self._track(char)
            if self._depth == 0:
                self._buf = self._buf[index + 1 :]
                self._call = None
                return True
        held += self._buf
        self._buf = ""
        self._call = held
        if len(held) > MAX_HELD_CALL_CHARS:
            out.append(held.lstrip())
            self._call = None
        return False

    def _track(self, char: str) -> None:
        if self._in_string:
            if self._escaped:
                self._escaped = False
            elif char == "\\":
                self._escaped = True
            elif char == '"':
                self._in_string = False
        elif char == '"':
            self._in_string = True
        elif char == "{":
            self._depth += 1
        elif char == "}":
            self._depth -= 1

"""A turn's reply text as it streams, and what a Stop keeps of it.

The finalize passes read what the client was sent (``shown``: the model's text
with its scaffolding removed), so a saved reply never holds text the phone did
not draw. A user's Stop also cuts it to what the client says it drew, so the
saved reply and the stopped bubble are the same text and nothing streams on
into it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

# How a reply ended: whole, cut short (provider, length or a server stop), or stopped
# by its user. ``done`` sends the last two as ``completion``.
Completion = Literal["complete", "interrupted", "user_stop"]

# A client's report of how much it drew is a UTF-16 length (a JS string's).
_UTF16 = "utf-16-le"


def utf16_prefix(text: str, units: int) -> str:
    """The first ``units`` UTF-16 code units of ``text``, never half a character."""
    encoded = text.encode(_UTF16)
    if units * 2 >= len(encoded):
        return text
    return encoded[: max(0, units) * 2].decode(_UTF16, errors="ignore")


@dataclass
class StreamAccum:
    # The model's text as it arrived.
    parts: list[str] = field(default_factory=list)
    # The text the client was sent: scaffolding removed (``ScaffoldFilter``).
    shown: list[str] = field(default_factory=list)
    was_cancelled: bool = False
    completion: Completion = "complete"
    # A first answer taken back to ask again with search (``tool_loop.live_denial``).
    # The phone drew it, so ``done`` carries the reply that replaces it, and a turn
    # that ends with nothing in its place keeps it.
    retracted: str = ""
    retracted_parts: str = ""
    # The reply stopped extending what the client was sent (a ```worked block laid out
    # again when a record came out of order, ``worked_stream``): ``done`` carries it.
    rewritten: bool = False

    def retract(self, parts_from: int, shown_from: int) -> None:
        self.retracted = "".join(self.shown[shown_from:])
        self.retracted_parts = "".join(self.parts[parts_from:])
        del self.parts[parts_from:], self.shown[shown_from:]

    def restore_retracted(self) -> None:
        """A stop or a failure left nothing in the retracted answer's place: it stays."""
        if self.retracted and not "".join(self.shown).strip():
            self.parts.append(self.retracted_parts)
            self.shown.append(self.retracted)
            self.retracted = self.retracted_parts = ""

    def mark_user_stop(self) -> None:
        self.was_cancelled = True
        if self.completion == "complete":
            self.completion = "user_stop"

    def mark_interrupted(self) -> None:
        self.was_cancelled = True
        if self.completion == "complete":
            self.completion = "interrupted"

    def mark_truncated(self) -> None:
        if self.completion == "complete":
            self.completion = "interrupted"

    def mark_server_stop(self) -> None:
        """The server stopped the reply (shutdown), whatever the stop looked like."""
        self.was_cancelled = True
        self.completion = "interrupted"

    def reply_text(self, client_shown_chars: int | None = None) -> str:
        """The text to finalize: what the client was sent, so the saved reply is
        the one the phone drew. After the user's Stop it is cut to the length the
        client says it drew; tokens still in flight then were never seen."""
        shown = "".join(self.shown)
        # After a rewrite the client's count is of other text: the reply is kept whole,
        # and ``done`` carries it (``rewritten``).
        stopped = self.completion == "user_stop" and not self.rewritten
        if stopped and client_shown_chars is not None:
            # The client counted the retracted answer it drew before this one.
            drawn = client_shown_chars - len(self.retracted.encode(_UTF16)) // 2
            shown = utf16_prefix(shown, max(0, drawn))
        return shown.strip()

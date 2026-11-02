"""Strip inline think fences from a streamed reply."""

from __future__ import annotations

# DeepSeek-R1 (and similar) emit inline think fences in `content`, plus a
# separate `reasoning_content` delta. Hex-encode the tags so a source rewrite
# cannot turn this filter into a no-op. Strip the fences from tokens; do not
# forward `reasoning_content` to the client (the chat UI must not show CoT).
THINK_OPEN = "\x3cthink\x3e"
THINK_CLOSE = "\x3c/think\x3e"
# Hold an unclosed think block this long while streaming. R1 CoT on even a
# short ask is often >4k chars; giving up early leaked the rest into the bubble.
THINK_MAX_OPEN_BUFFER = 65_536
# How much of a reply's start to hold for a model that has ended untagged
# reasoning with a lone closing tag ("Simple question.</think>2 + 2 = 4"): text
# before such a tag, inside this window, is that reasoning and is dropped. The
# leak happens when the provider did not split the reasoning off, so once
# reasoning arrives on its own channel ahead of any text, the text that follows
# is most likely the answer and only its first sentence or two is held
# (``reasoning_streamed``): a provider that split only part of it off still
# leaks the rest there.
STRAY_THINK_LEAD_HOLD = 400
STRAY_THINK_SHORT_HOLD = 160
# Held back at the end of the buffer so a tag split across chunks cannot leak.
_TAG_TAIL = len(THINK_CLOSE) - 1


class ThinkStripper:
    """Stateful filter that removes inline think fences from a token stream.

    Handles open/close tags split across chunks. Emits text outside think blocks
    unchanged; discards text inside. An unclosed think block is dropped on flush.
    A closing tag with no opening one is never shown; before any visible text
    has gone out, the text ahead of it is reasoning and is dropped too.
    ``lead_hold`` holds that many characters of the reply's start so a lone
    closing tag can still arrive in time; ``reasoning_streamed`` shortens it.
    """

    def __init__(self, *, lead_hold: int = 0) -> None:
        self._buf = ""
        self._in_think = False
        self._lead_hold = lead_hold
        self._released = False

    def _emit(self, out: list[str], text: str) -> None:
        if text:
            out.append(text)
            if text.strip():
                self._released = True

    @property
    def holding_thought(self) -> bool:
        """Text is held as reasoning: inside a think block, or a reply's start
        that a lone closing tag could still turn into reasoning."""
        if self._in_think:
            return True
        return not self._released and self._lead_hold > 0 and bool(self._buf.strip())

    def reasoning_streamed(self) -> None:
        """The provider sent reasoning on its own channel.

        Before any text, the text to come is most likely the answer: its hold
        shrinks to ``STRAY_THINK_SHORT_HOLD``, still long enough to catch the end
        of reasoning the provider did not split off. Text already held came
        before that reasoning and keeps the whole hold.
        """
        if not self._released and not self._buf.strip():
            self._lead_hold = min(self._lead_hold, STRAY_THINK_SHORT_HOLD)

    def feed(self, chunk: str) -> str:
        # Inside a think block the held text was already searched for its close: only one
        # that ends in this chunk can be new. Searching all of it again on every chunk
        # was quadratic in the block (a 60k-character one cost 180 ms of event loop).
        searched = max(0, len(self._buf) - _TAG_TAIL)
        self._buf += chunk
        out: list[str] = []
        while True:
            if self._in_think:
                idx = self._buf.find(THINK_CLOSE, searched)
                if idx == -1:
                    if len(self._buf) > THINK_MAX_OPEN_BUFFER:
                        # Model forgot to close — give up on this block.
                        self._buf = ""
                        self._in_think = False
                    break
                self._buf = self._buf[idx + len(THINK_CLOSE) :]
                self._in_think = False
                searched = 0
                continue
            open_idx = self._buf.find(THINK_OPEN)
            close_idx = self._buf.find(THINK_CLOSE)
            if close_idx != -1 and (open_idx == -1 or close_idx < open_idx):
                if self._released:
                    self._emit(out, self._buf[:close_idx])
                self._buf = self._buf[close_idx + len(THINK_CLOSE) :]
                continue
            if open_idx == -1:
                if not self._released and len(self._buf) < self._lead_hold:
                    break
                safe = len(self._buf) - _TAG_TAIL
                if safe > 0:
                    self._emit(out, self._buf[:safe])
                    self._buf = self._buf[safe:]
                break
            self._emit(out, self._buf[:open_idx])
            self._buf = self._buf[open_idx + len(THINK_OPEN) :]
            self._in_think = True
            searched = 0
        return "".join(out)

    def flush(self) -> str:
        if self._in_think:
            self._buf = ""
            self._in_think = False
            return ""
        out = self._buf
        self._buf = ""
        return out

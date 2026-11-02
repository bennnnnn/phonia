"""The reply's tokens on their way to the phone: scaffolding out, a ```worked block laid out.

A turn whose calculation no solver checked asks the model for its solution as a ```worked
block of records (``worked_solution``). ``WorkedFilter`` reads the block as it streams and
puts out the layout instead (``worked_render``): each record is laid out as soon as its
line ends, so the reply streams as it did, section by section, never as raw records. The
text around the block passes through unchanged. A block with no valid record is shown as
the model wrote it; a model that writes no block gets today's reply.

``ReplyFilter`` chains the scaffold filter and this one for ``stream_paths``. The text the
phone was sent stays a prefix of the reply: a record out of order (a given after the
substitution) would move what was drawn, so the saved reply takes the corrected text, and
``done`` carries it (``StreamAccum.rewritten``).
"""

from __future__ import annotations

import logging

from app.modules.chat.stream_accum import StreamAccum
from app.modules.chat.stream_scaffold import ScaffoldFilter
from app.modules.chat.worked_render import WorkedLayout, render_worked
from app.modules.chat.worked_solution import RecordModel, assemble, read_record
from app.services.md_fence_scan import FenceMarker, read_fence_marker

logger = logging.getLogger(__name__)

_LANG = "worked"
_OPENERS = tuple(run * 3 + _LANG for run in "`~")
# A block that never closes is cut off here, so a runaway reply is not held forever.
MAX_BLOCK_CHARS = 16_000


def _may_open(partial: str) -> bool:
    """Whether a line still being written could become the block's opener."""
    compact = partial.replace(" ", "").replace("\t", "").lower()
    # Spaces alone may still lead to it; they are held too, so nothing drawn moves.
    return bool(partial) and any(opener.startswith(compact) for opener in _OPENERS)


class WorkedFilter:
    """Reads a reply as it streams; ``text`` is the reply with its block laid out."""

    def __init__(self, layout: WorkedLayout) -> None:
        self._layout = layout
        # The finished text: prose and closed blocks.
        self._done = ""
        self._line = ""
        # The open block: its fence, its records, its lines as written.
        self._fence: FenceMarker | None = None
        self._records: list[RecordModel] = []
        self._raw: list[str] = []
        self._raw_chars = 0
        # The open block as last laid out, by how many records it had.
        self._shown: tuple[int, str] = (0, "")
        # A block closed at the length cap: its own closer line is dropped when it comes.
        self._cut_off: FenceMarker | None = None
        self.blocks = 0

    @property
    def text(self) -> str:
        if self._fence is not None:
            if self._shown[0] != len(self._records):
                self._shown = (len(self._records), self._render(streaming=True))
            return self._done + self._shown[1]
        return self._done if _may_open(self._line) else self._done + self._line

    def feed(self, chunk: str) -> None:
        self._line += chunk
        while "\n" in self._line:
            line, self._line = self._line.split("\n", 1)
            self._take(line)
        if self._fence is not None and self._raw_chars > MAX_BLOCK_CHARS:
            # Its own closer, when it comes, would open a code block that swallows the rest.
            self._cut_off = self._fence
            self._close()

    def close(self) -> None:
        """The stream ended: a line left open is read, and an open block closes."""
        if self._line:
            line, self._line = self._line, ""
            if self._fence is not None or not _may_open(line):
                self._take(line, last=True)
            else:
                self._done += line
        if self._fence is not None:
            self._close()

    def _take(self, line: str, *, last: bool = False) -> None:
        end = "" if last else "\n"
        marker = read_fence_marker(line)
        if self._fence is None and self._cut_off is not None and marker is not None:
            if marker.closes(self._cut_off):
                self._cut_off = None
                return
        if self._fence is None:
            if marker is None or marker.lang != _LANG or marker.info.strip().lower() != _LANG:
                self._done += line + end
                return
            self._fence = marker
            if self._done.strip() and not self._done.endswith("\n\n"):
                self._done += "\n" if self._done.endswith("\n") else "\n\n"
            return
        if marker is not None and marker.closes(self._fence):
            self._close()
            return
        self._raw.append(line)
        self._raw_chars += len(line) + 1
        record = read_record(line)
        if record is not None:
            self._records.append(record)

    def _render(self, *, streaming: bool) -> str:
        if not self._records:
            # Nothing read yet: while it streams, nothing to show; at its end, the model's
            # own lines (it wrote no records).
            return "" if streaming else "\n".join(self._raw).strip()
        try:
            return render_worked(assemble(self._records), self._layout, streaming=streaming)
        except Exception:
            logger.exception("worked block failed to render; showing its lines")
            return "" if streaming else "\n".join(self._raw).strip()

    def _close(self) -> None:
        rendered = self._render(streaming=False)
        # A blank line after it: prose that follows is a paragraph of its own.
        self._done += f"{rendered}\n\n" if rendered else ""
        if self._records:
            self.blocks += 1
            logger.info("worked block laid out records=%d", len(self._records))
        else:
            logger.info("worked block had no records; shown as written")
        self._fence = None
        self._records = []
        self._raw = []
        self._raw_chars = 0
        self._shown = (0, "")


class ReplyFilter:
    """The scaffold filter, then the worked block's layout when the turn asks for one.

    ``feed`` and ``flush`` return what to send next. Everything this filter returns is
    appended to ``accum.shown`` from ``start`` on, so when the reply's text stops
    extending what was sent, ``accum.shown`` from there is set to the text itself.
    """

    def __init__(self, accum: StreamAccum, layout: WorkedLayout | None) -> None:
        self._scaffold = ScaffoldFilter()
        self._worked = WorkedFilter(layout) if layout is not None else None
        self._accum = accum
        self._start = len(accum.shown)
        self._sent = ""

    @property
    def worked_blocks(self) -> int:
        return self._worked.blocks if self._worked is not None else 0

    def feed(self, token: str) -> str:
        visible = self._scaffold.feed(token)
        if self._worked is None:
            return visible
        self._worked.feed(visible)
        return self._delta(self._worked.text)

    def flush(self) -> str:
        tail = self._scaffold.flush()
        if self._worked is None:
            return tail
        self._worked.feed(tail)
        self._worked.close()
        return self._delta(self._worked.text)

    def _delta(self, text: str) -> str:
        if text.startswith(self._sent):
            delta, self._sent = text[len(self._sent) :], text
            return delta
        # What was sent is no longer the reply's start: the reply is the text, and done
        # carries it to the phone. The list keeps its length, so a round's index into it
        # (a retract) still points where it did.
        replaced = len(self._accum.shown) - self._start
        self._accum.shown[self._start :] = [text, *([""] * max(0, replaced - 1))]
        self._accum.rewritten = True
        self._sent = text
        return ""

"""A real photo above an answer about something worth seeing.

The model opens such a reply with a ```photo fence holding a short image
search ("Ethiopia location map", "capybara"). The search starts as soon as
that fence closes, while the rest of the answer streams. When the reply is
done the fence becomes the app's ``[Image: …]`` marker, or disappears when
no photo was found. The phone hides the fence until then.
"""

from __future__ import annotations

import asyncio
import logging
from uuid import UUID

from app.core.config import Settings
from app.models.orm import User
from app.modules.attachments.markers import image_marker
from app.modules.images import search as image_search
from app.services.md_fence_scan import iter_fences

logger = logging.getLogger(__name__)

# The fence holds one short line: what to look up.
_QUERY_CHARS = 120
# The fence opens the reply; a late one is still honored when the reply ends.
_WATCH_CHARS = 600
# The search usually finishes while the answer streams; never hold a reply long.
_WAIT_SECONDS = 6.0


def _photo_fences(text: str) -> list[tuple[int, int, str]]:
    """Each closed ```photo fence holding one short line: (start, end, query). The end
    takes the blank lines after the fence."""
    found: list[tuple[int, int, str]] = []
    for fence in iter_fences(text):
        if not fence.closed or fence.lang != "photo":
            continue
        query = text[fence.body_start : fence.body_end].strip()
        if not query or len(query) > _QUERY_CHARS or "\n" in query or "`" in query:
            continue
        end = fence.end
        while (newline := text.find("\n", end)) >= 0 and not text[end:newline].strip():
            end = newline + 1
        found.append((fence.start, end, query))
    return found


def _replace_photo_fences(content: str, marker: str = "") -> str:
    """The reply with its first photo fence as ``marker`` and every other one gone."""
    pieces: list[str] = []
    cursor = 0
    for index, (start, end, _query) in enumerate(_photo_fences(content)):
        pieces.append(content[cursor:start])
        if index == 0 and marker:
            pieces.append(f"{marker}\n\n")
        cursor = end
    pieces.append(content[cursor:])
    return "".join(pieces).strip()


class AnswerPhoto:
    """Starts the photo search for one reply and swaps its fence for the photo."""

    def __init__(self, settings: Settings, user: User) -> None:
        self._settings = settings
        self._user = user
        self._task: asyncio.Task[list[UUID]] | None = None
        self._watching = True

    @property
    def watching(self) -> bool:
        """True until the reply's opening is past (or its photo search started)."""
        return self._watching

    def _start(self, query: str) -> asyncio.Task[list[UUID]]:
        self._task = asyncio.create_task(
            image_search.photos_for_answer(self._settings, user=self._user, query=query),
            name="answer_photo",
        )
        return self._task

    def feed(self, text: str) -> None:
        """Look at the reply so far; start the search once its photo fence closes."""
        if not self._watching:
            return
        found = _photo_fences(text[:_WATCH_CHARS])
        if found:
            self._watching = False
            self._start(found[0][2])
        elif len(text) >= _WATCH_CHARS:
            self._watching = False

    async def attach(self, content: str) -> tuple[str, list[UUID]]:
        """The reply with its photo marker in place of the fence, and the photo ids."""
        found = _photo_fences(content)
        if not found:
            self.cancel()
            return content, []
        task = self._task or self._start(found[0][2])
        ids: list[UUID] = []
        try:
            ids = await asyncio.wait_for(asyncio.shield(task), timeout=_WAIT_SECONDS)
        except TimeoutError:
            # Stopped, not left to finish: a late photo was stored unlinked for the reaper,
            # after costing a lookup. Its cleanup (bytes, allowance) runs as the reply goes.
            logger.info("Answer photo took too long; sending the reply without it")
            task.add_done_callback(_log_late_photo)
            task.cancel()
        except Exception:
            logger.exception("Answer photo failed")
        marker = "\n".join(image_marker(attachment_id) for attachment_id in ids)
        return _replace_photo_fences(content, marker), ids

    def cancel(self) -> None:
        """Drop a search the reply no longer needs (stopped, failed, or no fence left)."""
        if self._task is not None and not self._task.done():
            self._task.cancel()


def _log_late_photo(task: asyncio.Task[list[UUID]]) -> None:
    # A search that finished storing before its cancel arrived leaves an unlinked photo;
    # the attachment reaper removes it.
    if not task.cancelled() and task.exception() is not None:
        logger.warning("Late answer photo failed", exc_info=task.exception())


def strip_photo_fences(content: str) -> str:
    """The reply without any photo fence (when photos are off or the reply failed)."""
    return _replace_photo_fences(content)

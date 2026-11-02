"""One shape for every list the API pages (code-health audit CLAR-12)."""

from __future__ import annotations

from pydantic import BaseModel


class Page[T](BaseModel):
    """A page of rows, and where the next one starts.

    Pass ``next_cursor`` back as ``cursor`` for the next page; ``None`` means this
    was the last. The cursor names the last row read (``repositories/keyset.py``), so
    rows added or removed while a client pages neither repeat nor go missing.
    """

    items: list[T]
    next_cursor: str | None = None

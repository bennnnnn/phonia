"""Each extractor reads a line once: the math gate's readings are the extraction step's.

The gate (``match/needs.py``) asks some extractors whether they read a line, and
when it says yes, extraction (``tools/extract.py``) walks its registry over the
same prepared line. Both, and the extractors that call one another, read through
here, so a turn runs each extractor on a line once.

An extractor is a pure function of the text: it reads no settings, clock, user or
request (the extractor packages are held off infrastructure by
``tests/architecture/test_pure_solvers.py``). So the key is the extractor and the
text alone, and the cache is shared rather than passed through each turn. Every
caller gets its own copy of the intent, so none can change what the next reads.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import lru_cache

from app.modules.math.schemas import MathIntent

Reader = Callable[[str], MathIntent | None]

# One line is read by up to about 80 extractors; this keeps roughly the last 100
# lines, enough for the gate and the extraction of every turn in flight.
_CACHE_SIZE = 8192


@lru_cache(maxsize=_CACHE_SIZE)
def _read(reader: Reader, text: str) -> MathIntent | None:
    return reader(text)


def read(reader: Reader, text: str) -> MathIntent | None:
    """What ``reader`` reads in ``text``, run once per line."""
    intent = _read(reader, text)
    return None if intent is None else intent.model_copy(deep=True)

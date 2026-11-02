"""User text that Postgres can store.

Postgres ``text`` rejects U+0000 and UTF-8 cannot encode a lone surrogate, so
either one passed request validation and then failed at the insert, after the
model had already answered (a chat turn's user row is saved in the background
while the prompt builds). A NUL is refused with a clear message; nobody types
one. A lone surrogate is half of an emoji pair a client cut in two, so it is
replaced with U+FFFD instead of failing the user's send.
"""

import re
from typing import Annotated

from pydantic import BeforeValidator

NUL_REJECTED_MESSAGE = "Text can't contain a null character (U+0000)."

# A Python str holds a valid pair as one code point, so any code point in the
# surrogate block is unpaired.
_LONE_SURROGATE = re.compile("[\ud800-\udfff]")


def storable_text(value: str) -> str:
    """``value`` as Postgres can store it; raises ``ValueError`` on a NUL."""
    if "\x00" in value:
        raise ValueError(NUL_REJECTED_MESSAGE)
    return _LONE_SURROGATE.sub("�", value)


def _storable_input(value: object) -> object:
    # Before str parsing: pydantic refuses a lone surrogate in a required str
    # ("unable to parse raw data as a unicode string") but not in an optional one.
    return storable_text(value) if isinstance(value, str) else value


# Every request field whose text reaches the database is this type.
UserText = Annotated[str, BeforeValidator(_storable_input)]

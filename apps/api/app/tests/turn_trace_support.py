"""The tests' check on a turn's trace line (``modules/chat/turn_trace.py``)."""

from collections.abc import Mapping
from typing import Any

from app.modules.chat.turn_trace import _token


def plain_record(record: Mapping[str, Any]) -> bool:
    """True when every value is a number, a bool, None, an identifier, or a list or map
    of them: what a turn's line may hold."""

    def plain(value: object) -> bool:
        if value is None or isinstance(value, bool | int | float):
            return True
        if isinstance(value, str):
            return _token(value) is not None
        if isinstance(value, list | tuple):
            return all(plain(item) for item in value)
        if isinstance(value, Mapping):
            return all(_token(key) is not None and plain(item) for key, item in value.items())
        return False

    return plain(record)

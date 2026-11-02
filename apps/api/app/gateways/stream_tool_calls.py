"""The tool calls a streamed reply makes, put back together from their pieces.

A provider streams each call in deltas: the first delta for an index carries the
call's id and name, later ones add to its arguments. Some providers repeat the name
in every delta, so a name is set, never appended. ``calls`` gives the finished calls
in the shape a message list takes back.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4


def _field(source: Any, name: str) -> Any:
    if source is None:
        return None
    if isinstance(source, dict):
        return source.get(name)
    return getattr(source, name, None)


class StreamedToolCalls:
    """The calls of one streamed reply, folded delta by delta."""

    def __init__(self) -> None:
        self._calls: list[dict[str, str]] = []
        self._open: dict[int, dict[str, str]] = {}

    def fold(self, deltas: Any) -> bool:
        """Add one chunk's ``delta.tool_calls``; True when the chunk carried any."""
        if not isinstance(deltas, list | tuple) or not deltas:
            return False
        for position, delta in enumerate(deltas):
            index = _field(delta, "index")
            key = index if isinstance(index, int) else position
            call_id = str(_field(delta, "id") or "")
            entry = self._open.get(key)
            # A new id at an index already in use is another call (one provider
            # numbers every call 0).
            if entry is None or (call_id and entry["id"] and call_id != entry["id"]):
                entry = {"id": call_id, "name": "", "arguments": ""}
                self._open[key] = entry
                self._calls.append(entry)
            elif call_id:
                entry["id"] = call_id
            function = _field(delta, "function")
            name = _field(function, "name")
            if name:
                entry["name"] = str(name)
            arguments = _field(function, "arguments")
            if arguments:
                entry["arguments"] += str(arguments)
        return True

    def add(self, name: str, arguments: str) -> None:
        """A whole call the model wrote as text (``text_tool_calls``)."""
        self._calls.append({"id": "", "name": name, "arguments": arguments})

    def calls(self) -> list[dict[str, Any]]:
        """The finished calls, in order; a call that never got a name is dropped."""
        return [
            {
                "id": entry["id"] or f"call_{uuid4().hex[:24]}",
                "type": "function",
                "function": {"name": entry["name"], "arguments": entry["arguments"] or "{}"},
            }
            for entry in self._calls
            if entry["name"]
        ]

"""A bare plot command, read literally: "plot the point (2, 3)" and nothing more.

Extraction reads the whole request once; the direct reply skips the model only
when plotting is all the request asks.
"""

from __future__ import annotations

import math

_MAX_REQUEST = 1000
_MAX_NUMBER = 64
_PLOT_VERBS = ("plot ", "graph ", "mark ", "show ", "draw ", "sketch ")


def literal_number(value: object) -> float | None:
    """A finite number, written plainly or stored as one."""
    if isinstance(value, bool) or not isinstance(value, str | int | float):
        return None
    if isinstance(value, str) and len(value) > _MAX_NUMBER:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def literal_pair(text: str) -> tuple[float, float] | None:
    """``(2, 3)`` or ``2, 3``: exactly two plain numbers, no expressions."""
    value = text.strip()
    if value.startswith("(") and value.endswith(")"):
        value = value[1:-1]
    parts = value.split(",")
    if len(parts) != 2:
        return None
    x, y = (literal_number(part.strip()) for part in parts)
    return (x, y) if x is not None and y is not None else None


def plot_command_object(text: str) -> str | None:
    """What a bare plot command draws: "Please graph the line x=0" is "line x=0"."""
    if len(text) > _MAX_REQUEST:
        return None
    request = " ".join(text.split()).replace("\u2212", "-")
    if request.lower().startswith("please "):
        request = request[7:].lstrip()
    for verb in _PLOT_VERBS:
        if request.lower().startswith(verb):
            request = request[len(verb) :].strip().rstrip(".?")
            break
    else:
        return None
    return request[4:] if request.lower().startswith("the ") else request


def literal_plot_point(text: str) -> tuple[float, float] | None:
    """The point a request names when plotting that one point is all it asks."""
    request = plot_command_object(text)
    if request is None or not request.lower().startswith("point "):
        return None
    return literal_pair(request[6:])

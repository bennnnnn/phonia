"""Whole single conversions may use the existing verified quantity directly."""

from __future__ import annotations

import math
import re

from app.services.number_text import bounded_decimal
from app.services.text_match import word_index

_NUMBER = bounded_decimal(24)
_UNIT = r"[A-Za-zµμ°][A-Za-z0-9µμ°*/^._-]{0,63}"
_CONVERSION = re.compile(rf"({_NUMBER})\s*({_UNIT})\s+to\s+({_UNIT})", re.IGNORECASE)


def unit_direct_request(text: str) -> bool | None:
    """Require the whole request and existing extractor to agree, preserving case."""
    request = " ".join(text.split())
    if word_index(request.lower(), "convert") == -1:
        # "Whats 72 fahrenheit in celsius": that grammar reads the whole request.
        from app.modules.math.match.units import asked_conversion

        return True if asked_conversion(request) is not None else None
    if len(text) > 1000:
        return False
    if request.endswith((".", "?")):
        request = request[:-1].rstrip()
    if request.lower().startswith("please "):
        request = request[7:]
    if request.lower().endswith(" please"):
        request = request[:-7]
    if not request.lower().startswith("convert "):
        return False
    match = _CONVERSION.fullmatch(request[8:])
    if match is None:
        return False
    value = float(match.group(1))
    if not math.isfinite(value):
        return False
    # This is syntax/identity validation only. The existing Pint-backed solve
    # has already produced the canonical quantity; do not convert it again.
    from app.modules.math.match import prepare
    from app.modules.math.tools.school import _extract_unit_intent

    cleaned = prepare(request)
    if cleaned is None:
        return False
    intent = _extract_unit_intent(cleaned)
    return bool(
        intent is not None
        and intent.kind == "unit"
        and intent.percent_base == value
        and intent.unit_from == match.group(2)
        and intent.unit_to == match.group(3)
    )

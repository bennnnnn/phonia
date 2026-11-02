"""Whole-request eligibility for an already verified descriptive statistic."""

from __future__ import annotations

import math
import re

from app.modules.math.match.discrete import _STATS_WORDS, stats_signal
from app.modules.math.match.scan import strip_command_lead
from app.services.number_text import bounded_decimal
from app.services.text_match import word_index

_NUMBER = bounded_decimal(24, exponent_digits=4)
_VALUE = re.compile(rf"({_NUMBER})(?:\s*/\s*({_NUMBER}))?")
_CLOSING = {"[": "]", "(": ")", "{": "}"}


def _complete_data(text: str) -> list[float] | None:
    """Read each scalar once, with complete separators and paired outer brackets."""
    data = text.strip()
    if data and data[0] in _CLOSING:
        if data[-1] != _CLOSING[data[0]]:
            return None
        data = data[1:-1].strip()
    values: list[float] = []
    index = 0
    while index < len(data):
        match = _VALUE.match(data, index)
        if match is None:
            return None
        try:
            value = float(match.group(1))
            if match.group(2) is not None:
                value /= float(match.group(2))
        except (ValueError, ZeroDivisionError):
            return None
        if not math.isfinite(value):
            return None
        values.append(value)
        if len(values) > 200:
            return None
        index = match.end()
        if index == len(data):
            break
        end = index
        while index < len(data) and data[index].isspace():
            index += 1
        separated = index > end
        if index < len(data) and data[index] in ",;":
            index += 1
            separated = True
            while index < len(data) and data[index].isspace():
                index += 1
        if separated and data.startswith("and ", index):
            index += 4
            separated = True
        if not separated or index == len(data):
            return None
    return values if len(values) >= 2 else None


def statistics_direct_request(text: str) -> bool | None:
    """None means another family; False retains the model for an incomplete ask.

    A recognized statistics family must pass this grammar before the generic
    direct-answer check. Qualifiers never become globally allowed prose words.
    The existing statistics extractor must agree with the exact operation/data.
    """
    request = " ".join(text.lower().split())
    if not any(word_index(request, phrase) != -1 for phrase, _ in _STATS_WORDS):
        return None
    if len(text) > 1000:
        return False
    if request.endswith((".", "?")):
        request = request[:-1].rstrip()
    if request.startswith("please "):
        request = request[7:]
    request = strip_command_lead(request)
    for phrase, operation in _STATS_WORDS:
        if not request.startswith(phrase + " "):
            continue
        data = request[len(phrase) + 1 :]
        if data.startswith("of "):
            data = data[3:]
        values = _complete_data(data)
        return values is not None and stats_signal(request) == (operation, values)
    return False

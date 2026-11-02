"""Reading a stated value and its unit from the question: by keyword, by label, in order."""

from __future__ import annotations

import re
from bisect import bisect_left, bisect_right

from app.modules.physics.extractors.unit_patterns import NUMBER

VALUE_UNIT_RE = re.compile(
    rf"({NUMBER})\s*"
    r"(m/s\^?2|m/s2|m/s|m\^?2/s\^?2|km/h|mph|miles\s+per\s+hour|cm/s|mm/s|"
    r"kilometers?|centimeters?|millimeters?|"
    r"miles?|minutes?|milliseconds?|seconds?|hours?|"
    r"meters?|metres?|inches?|yards?|feet|"
    r"km|cm|mm|mi|ft|yd|in|"
    r"kg|mg|lb|lbs|oz|"
    r"N|J|W|Pa|Hz|"
    r"s|ms|sec|min|hr|h|"
    r"deg|degrees|°|rad|radians)?"
    r"(?![A-Za-z0-9/^])",
    re.IGNORECASE,
)


def find_value_with_unit(text: str, keywords: tuple[str, ...]) -> tuple[float, str] | None:
    """Find the first number near a keyword (e.g. "height of 20m", "20m high").

    Returns (value, unit) where unit is "" if no unit was found. The unit is
    not validated here — the solver runs it through Pint.
    """
    lower = text.lower()
    for kw in keywords:
        idx = lower.find(kw)
        if idx == -1:
            continue
        # Search a window after the keyword for a number (the common case:
        # "height of 20m", "velocity 15 m/s"). Also search a small window
        # *before* the keyword ("20m high", "15 m/s initial velocity").
        after = text[idx + len(kw) : idx + len(kw) + 40]
        m = VALUE_UNIT_RE.match(after.strip())
        if m:
            val = float(m.group(1))
            unit = (m.group(2) or "").strip()
            return val, unit
        before = text[max(0, idx - 40) : idx]
        m = VALUE_UNIT_RE.search(before)
        if m:
            val = float(m.group(1))
            unit = (m.group(2) or "").strip()
            return val, unit
    return None


def find_value_after_keyword(text: str, keywords: tuple[str, ...]) -> tuple[float, str] | None:
    """Number immediately after a keyword — never the window before it.

    ``What`` / a preceding height must not bind as v0.
    """
    lower = text.lower()
    for kw in keywords:
        idx = lower.find(kw)
        if idx == -1:
            continue
        after = text[idx + len(kw) : idx + len(kw) + 40]
        m = VALUE_UNIT_RE.match(after.strip())
        if m:
            return float(m.group(1)), (m.group(2) or "").strip()
    return None


def keyword_spans(
    text: str, keywords: tuple[str, ...], *, whole_words: bool = True
) -> list[tuple[int, int]]:
    """Where each keyword appears, as a whole word or anywhere in a word."""
    lower = text.lower()
    spans: list[tuple[int, int]] = []
    for keyword in keywords:
        if whole_words:
            spans.extend(
                (found.start(), found.end())
                for found in re.finditer(rf"\b{re.escape(keyword.lower())}\b", lower)
            )
            continue
        start = 0
        while (idx := lower.find(keyword.lower(), start)) != -1:
            spans.append((idx, idx + len(keyword)))
            start = idx + len(keyword)
    return spans


# Words that sit between a label and the number it names: "distance of 1.50 m",
# "image height is 6.00 cm". "and" is not one of them, so "2 cm object and 6 cm"
# does not hand the second length to the first label. One punctuation mark per
# repeat: ``[\s,:=.]+`` inside the ``*`` could split a run of commas 2^n ways, and
# a failed fullmatch tried them all (22 commas took 0.3 s, each one doubled it).
_LABEL_GAP = re.compile(
    r"(?:[\s,:=.]|(?:of|is|are|was|were|a|an|the|height|distance|equal|to)\b)*",
    re.IGNORECASE,
)


def _value_the_keyword_names(
    text: str,
    matches: list[re.Match[str]],
    spans: list[tuple[int, int]],
) -> re.Match[str] | None:
    """The value a keyword introduces, when only a label sits between them.

    Character distance ties "screen distance of 1.50 m" with the length written
    just before that label, and the earlier length won. The label names the
    number that follows it.
    """
    named: list[tuple[int, int, re.Match[str]]] = []
    for candidate in matches:
        gap: int | None = None
        for _start, end in spans:
            if end > candidate.start():
                continue
            if any(
                other.start() >= end and other.end() <= candidate.start()
                for other in matches
                if other.start() != candidate.start()
            ):
                continue
            if _LABEL_GAP.fullmatch(text[end : candidate.start()]) is None:
                continue
            size = candidate.start() - end
            if gap is None or size < gap:
                gap = size
        if gap is not None:
            named.append((gap, candidate.start(), candidate))
    if not named:
        return None
    named.sort()
    return named[0][2]


def find_value_with_specific_unit(
    text: str,
    unit_pattern: str,
    keywords: tuple[str, ...] = (),
    *,
    require_keyword: bool = False,
    whole_words: bool = False,
) -> tuple[float, str] | None:
    """Find a number followed by a specific unit (e.g. "20 N", "5 kg").

    When keywords are present in the text, prefer the unit-bearing value
    nearest one of them; otherwise use the first matching value. This avoids
    binding an earlier unrelated quantity to the requested mass/force/etc.

    ``require_keyword`` (projectile h0): if none of the keywords appear, return
    None instead of the first unlabeled length (``wall is 15 m away``).
    Kinematics unlabeled ``free fall 20 m`` still binds.

    ``whole_words`` matches a keyword only as a word: ``in`` is not the start of
    ``inductor``.
    """
    matches = [
        m
        for m in re.finditer(
            rf"({NUMBER})\s*({unit_pattern})(?![A-Za-z0-9/^])",
            text,
            re.IGNORECASE,
        )
        if not part_label(text, m)
    ]
    if not matches:
        return None

    match = matches[0]
    if keywords:
        spans = keyword_spans(text, keywords, whole_words=whole_words)
        if require_keyword and not spans:
            return None
        if spans:
            starts = sorted(start for start, _ in spans)
            ends = sorted(end for _, end in spans)

            def distance_to_keyword(candidate: re.Match[str]) -> int:
                # Every span lies wholly after the value, wholly before it, or
                # overlaps it. Sorted ends and starts give the nearest of the
                # first two in log time, where comparing every pair grew with
                # the square of a long question's values and keywords.
                after = bisect_left(starts, candidate.end())
                before = bisect_right(ends, candidate.start())
                if before + len(starts) - after < len(starts):
                    return 0
                distances = []
                if after < len(starts):
                    distances.append(starts[after] - candidate.end())
                if before:
                    distances.append(candidate.start() - ends[before - 1])
                return min(distances)

            named = _value_the_keyword_names(text, matches, spans)
            match = named if named is not None else min(matches, key=distance_to_keyword)
        elif require_keyword:
            return None

    return float(match.group(1)), match.group(2)


def labeled_value(text: str, label: str, unit: str) -> tuple[float, str] | None:
    """The value a label names, with its unit: ``initial speed of 4 m/s`` → ``(4.0, "m/s")``."""
    match = re.search(
        rf"\b(?:{label})(?:\s+of)?\s+({NUMBER})\s*({unit})\b",
        text,
        re.IGNORECASE,
    )
    if match is None:
        return None
    return float(match.group(1)), match.group(2)


def part_label(text: str, match: re.Match[str]) -> bool:
    """A one-letter unit closed by ")" or "." outside any bracket, with the next part's label
    after it, is that part's label: "… 9.7, 12.6 a) Draw the circuit … b) Copy" read as 12.6 A
    certified a 12 V bulb's resistance as 0.952 Ω (2026-10-30). "a current (2 A)" and
    "supplies 3 A) to the lamp" keep their unit."""
    unit = match.group(2).lower()
    if len(unit) != 1 or text[match.end() : match.end() + 1] not in (")", "."):
        return False
    before = text[: match.start()]
    if before.rfind("(") > before.rfind(")"):
        return False
    following = ("ii", "j") if unit == "i" else (chr(ord(unit) + 1),)
    after = text[match.end() + 1 :]
    # The next label as "b)", "(b)" or "b. ".
    return any(
        re.search(rf"(?<!\w)\(?{label}\)|(?<!\w){label}\.\s", after, re.IGNORECASE)
        for label in following
    )


def ordered_values(text: str, unit_pattern: str) -> list[tuple[float, str]]:
    """Every number carrying one of these units, left to right.

    Collisions need two masses and two velocities *in the order written* —
    "a 2 kg ball at 3 m/s hits a 1 kg ball at rest" binds m1=2, v1=3, m2=1.
    The keyword-nearest search the other extractors use cannot express that.
    """
    return [
        (float(m.group(1)), m.group(2))
        for m in re.finditer(
            rf"({NUMBER})\s*({unit_pattern})(?![A-Za-z0-9/^])",
            text,
            re.IGNORECASE,
        )
        if not part_label(text, m)
    ]


def positioned_values(text: str, unit_pattern: str) -> list[tuple[int, float, str]]:
    """Like ``ordered_values`` but keeps each match's offset.

    Torque balance needs to know *which* force a distance belongs to, which
    written order alone cannot say.
    """
    return [
        (m.start(), float(m.group(1)), m.group(2))
        for m in re.finditer(
            rf"({NUMBER})\s*({unit_pattern})(?![A-Za-z0-9/^])",
            text,
            re.IGNORECASE,
        )
        if not part_label(text, m)
    ]

"""A worked solution states its result once, after the working, never as a guess above it.

Told to answer first, a model opened worked replies with a number it had not worked yet:
"The ratio of fuel used … is **5 : 7**" over working and a card that found 4 : 5, and
"The car covers **290 m**" over a sum of 310 m (a Class 9 book, 2026-10-30); the prompt
saying a calculation opens with its working did not hold. In a reply with a worked section
(Given, Working, Solution, Required, Formula, Substitution or Steps) and an answer card below
it, a short lead above the section stating a number the working never reaches is that guess,
and goes: a lead the working agrees with stays.
A heading, a photo or a lead without a number stays, and so does a long lead, which may be
an answer of its own.
"""

from __future__ import annotations

import re

from app.services.md_fence_scan import iter_fences, line_fences
from app.services.workout import REQUIRED_PATTERN

# The first label of the working, as a heading or a bare line: **Given**, **Working**,
# ## Solution, "Given". Replies label it several ways; the guess sits above any of them.
_GIVEN = re.compile(
    rf"^[^\S\n]*(?:#{{1,4}}[^\S\n]+)?(?:\*\*)?(?:Given|Working|Solution|{REQUIRED_PATTERN}|Formula"
    r"|Substitution|Steps)(?:\*\*)?:?(?:\*\*)?[^\S\n]*$",
    re.I | re.M,
)
# A heading: "## Stage 1", "**Atomic structure of Mg**"; a bold sentence ("**The ratio is
# 1 : 5.**") is a statement.
_HEADING = re.compile(r"^\s*(?:#{1,6}\s|\*\*[^*]*[^*.!?\s]\*\*\s*$)")
# Not a stated result: a photo, an image, a list, a table, display maths, a part's label,
# a note or a warning.
_KEEP = re.compile(
    r"^\s*(?:\[Image:|!\[|[-*+]\s|\d+[.)]\s|\||\$\$|\\\[|\(?[a-h]\)|\(?[ivx]+\)|\*\*\s*(?:part|\(?[a-h]\))"
    r"|(?:\*\*)?(?:note|warning|tip|remember|caution|assume|assumption)s?\b)",
    re.I,
)
_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
# "4 : 5", "4/5", "\frac{4}{5}": a ratio is its pair, not two numbers any working holds.
_RATIO = re.compile(r"(\d+)\s*[:/]\s*(\d+)|\\[dt]?frac\{(\d+)\}\{(\d+)\}")
# "(15 milliseconds)": the same value in another unit, which the working need not reach.
_ASIDE = re.compile(r"\([^()]*\)")
_MOST_WORDS = 60


def _paragraphs(lead: str) -> list[tuple[int, int]]:
    """Each paragraph's (start, end) in ``lead``."""
    spans: list[tuple[int, int]] = []
    start = 0
    for gap in re.finditer(r"\n[^\S\n]*\n", lead):
        spans.append((start, gap.start()))
        start = gap.end()
    spans.append((start, len(lead)))
    return [(begin, end) for begin, end in spans if lead[begin:end].strip()]


def _numbers(text: str) -> set[str]:
    """The numbers ``text`` states, each ratio as one ("4:5")."""
    ratios = {
        f"{match.group(1) or match.group(3)}:{match.group(2) or match.group(4)}"
        for match in _RATIO.finditer(text)
    }
    plain = {number.replace(",", "") for number in _NUMBER.findall(_RATIO.sub(" ", text))}
    return ratios | plain


def _a_guess(
    lead: str, span: tuple[int, int], fenced: list[tuple[int, int]], worked: set[str]
) -> bool:
    """Prose stating a number the working never reaches: "**5 : 7**" over working that
    found 4 : 5. A lead whose numbers the working holds agrees with it and stays, and so
    does a heading, a photo, a fence (a photo's query), a list, a part or a note."""
    begin, end = span
    if any(begin < fence_end and fence_start < end for fence_start, fence_end in fenced):
        return False
    stripped = lead[begin:end].strip()
    if _HEADING.match(stripped) or _KEEP.match(stripped):
        return False
    return bool(_numbers(_ASIDE.sub(" ", stripped)) - worked)


def drop_guessed_lead(text: str) -> str:
    """``text`` without a short lead above its working that states a number the working
    and its card never reach."""
    given = _GIVEN.search(text)
    if given is None:
        return text
    if not any(
        fence.lang == "answer" and fence.start > given.start() for fence in iter_fences(text)
    ):
        return text
    # A Given inside a fence (an example in code) is not the reply's.
    if line_fences(text)[text.count("\n", 0, given.start())] is not None:
        return text
    lead = text[: given.start()]
    if len(lead.split()) > _MOST_WORDS or not lead.strip():
        return text
    fenced = [(fence.start, fence.end) for fence in iter_fences(lead)]
    spans = _paragraphs(lead)
    rest = text[given.start() :]
    worked = _numbers(rest) | {number.replace(",", "") for number in _NUMBER.findall(rest)}
    kept = [span for span in spans if not _a_guess(lead, span, fenced, worked)]
    if len(kept) == len(spans):
        return text
    head = "\n\n".join(lead[begin:end].strip("\n") for begin, end in kept)
    return f"{head}\n\n{text[given.start() :]}" if head else text[given.start() :]

"""Does the reply ask instead of answering?

A reply that asks for missing information gets no verified answer pinned
under it. Plain numbers are compared as numbers in
``app.services.answer_check``; the string check here covers expressions that
are not plain values.
"""

from __future__ import annotations

import re

from app.services.answer_check import asks_without_answering


def _normalize_answer_token(text: str) -> str:
    """Strip math/markup noise so we can test whether prose already states a value."""
    cleaned = (
        text.replace("$", "")
        .replace("`", "")
        .replace("\u2009", "")
        .replace("\u00a0", "")
        .replace("\u2212", "-")
        .replace("\\", "")
    )
    return "".join(cleaned.split()).lower()


def _answer_numeric_core(answer_body: str) -> str:
    """Strip a leading ``x=`` and trailing latin unit so ``2.02 s`` → ``2.02``."""
    token = _normalize_answer_token(answer_body)
    equals = token.rfind("=")
    if equals >= 0:
        token = token[equals + 1 :]
    end = len(token)
    while end > 0 and token[end - 1].isalpha():
        end -= 1
    return token[:end]


def _math_spans(prose: str) -> list[str]:
    """Read complete dollar or TeX-delimited formulas in one forward scan."""
    spans: list[str] = []
    index = 0
    while index < len(prose):
        if prose.startswith((r"\(", r"\["), index):
            closer = r"\)" if prose[index + 1] == "(" else r"\]"
            start = index + 2
        elif prose[index] == "\\":
            # Escaped dollars and literal backslashes are not math openers.
            index += 2
            continue
        elif prose[index] == "$":
            closer = "$$" if prose.startswith("$$", index) else "$"
            start = index + len(closer)
        else:
            index += 1
            continue
        end = prose.find(closer, start)
        if end < 0:
            break
        spans.append(prose[start:end])
        index = end + len(closer)
    return spans


def _contains_value(haystack: str, needle: str) -> bool:
    """``needle`` in ``haystack`` as a whole value: ``12.75`` is not in ``112.75`` or ``12.755``."""
    start = haystack.find(needle)
    while start >= 0:
        end = start + len(needle)
        before = haystack[start - 1] if start > 0 else ""
        after = haystack[end : end + 2]
        number_start = needle[:1].isdigit() or needle[:1] in ".-"
        number_end = needle[-1:].isdigit()
        clipped_before = number_start and (before.isdigit() or before == ".")
        clipped_after = number_end and (
            after[:1].isdigit() or (after[:1] == "." and after[1:2].isdigit())
        )
        if not clipped_before and not clipped_after:
            return True
        start = haystack.find(needle, start + 1)
    return False


def _span_states_short_int(span: str, core: str) -> bool:
    compact = _normalize_answer_token(span)
    return compact == core or compact.endswith("=" + core)


def _normalize_math_answer_expression(text: str) -> str:
    """Compare harmless TeX spelling differences, preserving grouped powers."""
    # Remove spacing commands before whitespace/command slashes are stripped.
    # Word boundaries keep \quad from binding inside a different command name.
    spaced = re.sub(r"\\(?:qquad|quad)(?![A-Za-z])", "", text)
    for spacing in (r"\,", r"\;", r"\:", r"\!", "\\ "):
        spaced = spaced.replace(spacing, "")
    # Upright unit lettering is presentation only, but unit case is semantic:
    # mJ and MJ must never compare equal. Keep this fallback case-sensitive.
    spaced = re.sub(r"\\mathrm\{([A-Za-z°]{1,24})\}", r"\1", spaced)
    cleaned = (
        spaced.replace(r"\left", "")
        .replace(r"\right", "")
        .replace("$", "")
        .replace("\u2212", "-")
        .replace("\\", "")
    )
    compact = "".join(cleaned.split())
    # Only one literal atom: x^{12} and x^12 are different TeX expressions,
    # as are x^{1/6} and x^1/6. Never remove arbitrary grouping braces.
    return re.sub(r"\^\{([A-Za-z0-9])\}", r"^\1", compact)


def prose_already_states_answer(content: str, answer_body: str) -> bool:
    """True when the verified value is already visible in the assistant prose.

    Short integers (1-2 digits) must appear as a whole math result (``$2$`` or
    a span ending in ``=2``) so a digit inside ``$x^2$`` does not suppress the
    pill. Longer values (``2.02 s``, ``x = 12``) use a normalized substring.
    """
    body = answer_body.strip()
    if not body:
        return False
    core = _answer_numeric_core(body)
    if core.isdigit() and len(core) <= 2:
        return any(_span_states_short_int(span, core) for span in _math_spans(content))
    needle = _normalize_answer_token(body)
    if len(needle) < 2:
        return False
    if r"\mathrm{" not in body and _contains_value(_normalize_answer_token(content), needle):
        return True
    # Formatting equivalence applies to complete math results only. A looser
    # substring check would find canonical x^{1} inside the different x^12.
    expression = _normalize_math_answer_expression(body)
    for span in _math_spans(content):
        stated = _normalize_math_answer_expression(span)
        if stated == expression or stated.endswith("=" + expression):
            return True
    return False


# Emphasis and code ticks trailing the question mark: "**...?**", "...?*".
_TRAILING_MARKUP = "*_`~ \t"


def _line_asks(line: str) -> bool:
    return line.rstrip(_TRAILING_MARKUP).endswith("?")


def reply_asks_instead_of_answering(content: str, answer_body: str | None) -> bool:
    """True when the reply requests information rather than giving a result.

    The fences below are solver-owned — the model is told not to emit them, so
    they are attached whenever they are missing. "Missing" was read as "the
    model forgot", because nothing here could tell that apart from a reply that
    deliberately has no answer in it. So when the model correctly answered a 2D
    collision with *"Which ball's final path is at 30°?"*, the pipeline pinned a
    verified ``0.79 m`` and a trajectory chart underneath the question.

    Both halves are needed, and the second is the one that keeps this safe. A
    question mark alone proves nothing: *"The range is about 35.31 m. Would you
    like the maximum height?"* answers first and asks second, and must keep its
    chart. It is the *absence* of an answer beside the question that makes a
    reply a request for more information.

    Position, on the other hand, proves nothing either way, which the incident
    itself showed: its question is the opening line and its closing line is a
    plain statement, so "the reply ends with a question" would have missed the
    very case this exists for. Any line that asks counts.

    A solver that produced no answer at all is the third case, and it is not
    this one. Angles alone fix a triangle's shape but not its size, so the
    solver returns a diagram, no number, and the reply asks for a side length —
    a question and no stated answer, yet the diagram is exactly right. What
    makes the incident wrong is a *verified answer* being pinned to a reply that
    does not make it, so with no such answer there is nothing to withhold.

    "States an answer" means any final value, right or wrong: "Subtract 5,
    then divide: x = 7. Want to try a harder one?" answered (wrongly) and then
    offered more, so it keeps the verified card and gets a correction.
    """
    if not answer_body:
        return False
    numeric = asks_without_answering(content, answer_body)
    if numeric is not None:
        return numeric and not prose_already_states_answer(content, answer_body)
    if not any(_line_asks(line) for line in content.splitlines()):
        return False
    return not prose_already_states_answer(content, answer_body)

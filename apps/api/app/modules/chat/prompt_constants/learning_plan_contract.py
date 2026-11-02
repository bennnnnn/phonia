"""The day-by-day contract a bounded learning roadmap ("a 30 day Python plan") follows."""

from __future__ import annotations

import re

from app.modules.turn_reading.teaching import programming_tag
from app.services.text_normalize import collapse_ws

_DAY_COUNT = re.compile(r"\b(\d{1,3})[\s-]?days?\b", re.IGNORECASE)


def learning_plan_daily_contract(text: str) -> str:
    """Return an exact day-label contract for bounded daily roadmaps."""
    match = _DAY_COUNT.search(collapse_ws(text))
    if match is None:
        return ""
    count = int(match.group(1))
    if count < 2 or count > 90:
        return ""
    labels = " | ".join(f"Day {day}" for day in range(1, count + 1))
    programming_rule = ""
    # Production experience is a software engineer's: a Spanish or calculus plan ended on
    # "Production experience takes longer than this roadmap" too.
    closing = "`### Checkpoints and milestones` and `### Daily routine`."
    tag = programming_tag(text)
    if tag:
        checkpoints = sorted({max(1, round(count * fraction / 5)) for fraction in range(1, 6)})
        locations = ", ".join(f"Day {day}" for day in checkpoints)
        programming_rule = (
            f"\n- Include exactly five short runnable ```{tag} code blocks total, placed after "
            f"{locations}. Inline snippets do not count."
        )
        closing = (
            "`### Checkpoints and milestones`, `### Daily routine`, and "
            "`### Production-experience note`. Under the last heading, write the exact sentence "
            "`Production experience takes longer than this roadmap.` before briefly explaining why."
        )
    return (
        f"HARD DAILY-COVERAGE CONTRACT FOR THIS {count}-DAY PLAN:\n"
        f"- The daily breakdown must contain exactly {count} separate Markdown lines, one per day.\n"
        "- Every line must begin with one bold day label in this shape: "
        "`- **Day N — Topic:** Learn → Practice/build → Done when ...`.\n"
        "- Do not combine days, skip a number, or use a day range in the daily breakdown.\n"
        f"- Required labels, in order: {labels}.\n"
        f"- Keep every day line compact so Day {count} and all closing sections fit.\n"
        f"- After the daily lines, include these exact headings: {closing}{programming_rule}"
    )

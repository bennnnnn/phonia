"""A first answer that says it can't see live data is asked again, with search offered.

"Perfect. totally unrelated but did the bears win today" was answered "I can't check live
scores" (live chat, 2026-10-25): the word rules read the line as a statement, so neither
the tool loop nor the reply's own call could search. Two rules that read the user's words
caught everyday statements ("went to the gym today but was too tired") in review. The
reply decides instead. When the first call carried no tool and its answer opens a
sentence with such a denial, the answer is taken back and the model is asked again with
``web_search`` offered; it searches, or answers without (a heart rate, a camera feed).
The tool-loop path offers the retry only when nothing searched and the spend cap allows
tools (``StreamContext.denial_retry_tools``).
"""

from __future__ import annotations

import re
from typing import Any

from app.modules.chat.clock_denial import model_denies_clock
from app.modules.chat.stream_accum import StreamAccum
from app.modules.chat.turn_prep import StreamContext
from app.modules.web_search import asks_only_whether_it_searches
from app.modules.web_search.subject import collect_prior_user_messages, last_assistant_content
from app.services.text_normalize import collapse_ws, straighten_apostrophes

_MAX_LEN = 600
_LIVE = r"(?:live|real-time|realtime|current|up-to-date|today's|the\s+latest)"
# The denial opens its sentence, after bold and a softener ("I'm sorry, but I can't…", "As
# an AI, I don't…"): a quoted or mid-sentence one is talk about it.
_SOFTENER = r"(?:(?:i'm\s+)?sorry|unfortunately|honestly|hmm+|ah|as\s+an\s+ai)[,\s\u2014\u2013-]+(?:but\s+)?"
_OPENS = rf"(?:^|(?<=[.!?])\s+)[*_]*(?:{_SOFTENER})?"
_DENIAL = re.compile(
    rf"{_OPENS}i(?:\s+can't|\s+cannot|\s+can\s+not|'m\s+unable\s+to|\s+am\s+unable\s+to|"
    r"'m\s+not\s+able\s+to|\s+am\s+not\s+able\s+to|"
    r"\s+don't\s+have\s+(?:a\s+way|the\s+ability)\s+to)\s+"
    rf"(?:check|access|look\s+up|see|get|pull\s+up|browse|confirm|track)\s+{_LIVE}\b"
    rf"|{_OPENS}i\s+(?:don't|do\s+not)\s+have\s+(?:access\s+to\s+)?"
    rf"{_LIVE}\s+(?:\w+\s+)?(?:data|information|info|results|scores|access|updates|news|stats)\b"
    rf"|{_OPENS}i\s+(?:can't|cannot)\s+browse\s+the\s+(?:web|internet)\b",
    re.IGNORECASE,
)


def denies_live_data(reply: str) -> bool:
    """A short reply that opens a sentence with "I can't check live scores" and the like."""
    cleaned = straighten_apostrophes(collapse_ws(reply))
    return bool(cleaned) and len(cleaned) <= _MAX_LEN and _DENIAL.search(cleaned) is not None


def _asks_only_whether_it_searches(ctx: StreamContext) -> bool:
    """ "Can you search the web?" with nothing in the chat to search asks about Recall: a
    retry offering search could search whatever the chat said before it."""
    asked = ctx.user_message_content
    if not isinstance(asked, str):
        return False
    prompt = ctx.prompt_messages if isinstance(ctx.prompt_messages, list) else []
    return asks_only_whether_it_searches(
        asked,
        prior_user_messages=collect_prior_user_messages(prompt, asked) or None,
        prior_assistant=last_assistant_content(prompt),
    )


def asks_again(
    ctx: StreamContext, calls: list[dict[str, Any]], accum: StreamAccum, written: int
) -> bool:
    """The first call's answer, with no tool call, denies live data: ask again."""
    if calls or accum.was_cancelled or ctx.search_sources:
        return False
    if _asks_only_whether_it_searches(ctx):
        return False
    reply = "".join(accum.parts[written:])
    # "What time is it" denied gets the clock (``finalize_text.fix_clock``).
    return denies_live_data(reply) and not model_denies_clock(reply, ctx.user_message_content)

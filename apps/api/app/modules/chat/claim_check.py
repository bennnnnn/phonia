"""Finalize pass: on a searched turn, a claim the sources never made is cut.

The search hint tells the model to ground its answer in the results, and a model can
still add what no result says. In one study chat (2026-10-26) a reply told a user a
broker "has been reinstated and is fully operational, so you can use them safely" under
five sources that were its own research pages, and a fee table carried a "CSTA levy"
credited to the regulator that no source named.

A cheap model lists the claims the evidence does not support: a figure, a legal or
regulatory status, a named organisation said to do something, an attribution. The evidence
is this turn's search results and the user's own words; an earlier reply of the assistant
is where an invention starts, so it is not evidence. Each quote must be found in the reply.
The pass removes the table row or sentence that holds it, outside fences, and adds one line
saying what was left out. A check that fails, times out or flags most of the reply
changes nothing: it never costs the user an answer.
"""

from __future__ import annotations

import logging
import re
import string
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from app.gateways.structured_completion import complete_structured
from app.models.routing_lanes import ROUTING
from app.modules.chat.markdown_regions import map_prose_outside_fences
from app.modules.chat.stream_status import announced_if_slow
from app.services.text_normalize import collapse_ws

if TYPE_CHECKING:
    from app.modules.chat.finalize_passes import FinalizeState

logger = logging.getLogger(__name__)

# A reply shorter than this holds no table of figures or status claims worth a model call.
_MIN_REPLY_CHARS = 120
_MAX_HITS = 8
_HIT_CHARS = 700
_EARLIER_USER_MESSAGES = 4
_MAX_MEMORY = 20
_USER_CHARS = 600
_REPLY_CHARS = 7000
# More than this share of the reply flagged: the check is wrong; the user keeps the reply.
_MAX_CUT_SHARE = 0.5
_MAX_CLAIMS = 12
_SEARCH_BLOCK_MARK = "Web search results"

# A reply citing a result's headline was once cut as unsupported: the checker read only the
# text under it.
HEADLINE_IS_EVIDENCE = "a headline that states a fact supports it"

_SYSTEM = (
    "You check an assistant reply against the evidence it had, and list every claim the "
    "evidence does not support.\n\n"
    "A claim is: a figure (rate, fee, price, percentage, date, count); a legal or "
    "regulatory status (licensed, banned, approved, reinstated, safe to use); a named "
    "organisation, product or person said to offer or do something; or an attribution "
    "to a named source or authority.\n\n"
    "Evidence is ONLY the web results (each one's title, address and text all count; "
    + HEADLINE_IS_EVIDENCE
    + ") and the user's own messages and saved memory. "
    "Earlier assistant replies are NOT evidence. A figure within rounding of one in the evidence is "
    "supported, and so is arithmetic done on supported or user-given figures.\n\n"
    "Not a claim to list: advice, opinions, definitions, general explanations of how "
    "something works, steps for doing something, hedged estimates the reply calls "
    "estimates, and what the reply says it could not find.\n\n"
    'Return JSON: {"unsupported": [{"quote": ..., "topic": ...}], "note": ...}. '
    "quote is the shortest span copied exactly from the reply that holds the claim. "
    "topic is 2 to 8 words naming what was claimed. note is one short sentence, in the "
    "language of the reply, saying you could not confirm those details from the sources "
    "found and left them out. Use an empty list and an empty note when every claim is "
    "supported."
)


class _Claim(BaseModel):
    quote: str = Field(min_length=3, max_length=300)
    topic: str = Field(default="", max_length=100)


class _Verdict(BaseModel):
    unsupported: list[_Claim] = Field(default_factory=list, max_length=_MAX_CLAIMS)
    note: str = Field(default="", max_length=240)


def _evidence(state: FinalizeState) -> str:
    ctx = state.ctx
    hits = [
        f"[{n}] {hit.title}\n{hit.url}\n{hit.snippet[:_HIT_CHARS]}"
        for n, hit in enumerate(ctx.search_sources[:_MAX_HITS], 1)
    ]
    earlier = [
        m["content"][:_USER_CHARS]
        for m in ctx.prompt_messages[:-1]
        if m.get("role") == "user"
        and isinstance(m.get("content"), str)
        and _SEARCH_BLOCK_MARK not in m["content"]
    ][-_EARLIER_USER_MESSAGES:]
    said = [*earlier, (ctx.user_message_content or "")[:_USER_CHARS]]
    remembered = "\n".join(f"- {hint[:_USER_CHARS]}" for hint in ctx.memory_hints[:_MAX_MEMORY])
    memory = f"\n\nWHAT THE USER ASKED US TO REMEMBER:\n{remembered}" if remembered else ""
    return (
        "WEB RESULTS:\n"
        + "\n\n".join(hits)
        + "\n\nTHE USER'S MESSAGES (oldest first):\n"
        + "\n".join(f"- {message}" for message in said)
        + memory
    )


_TABLE_ROW = re.compile(r"^\s*\|")
# Linear checks: a reply is untrusted text, and overlapping `\s*`/`\s+` groups backtrack.
_TABLE_RULE_CHARS = re.compile(r"[\s:|-]*")
_SENTENCE_END = re.compile(r"[.!?]")
_SENTENCE_OPENERS = frozenset(string.ascii_uppercase + string.digits + "*_[(\"'")
_ONLY_MARKUP = re.compile(r"^[\s>*_\-•\d.)#]*$")


_MARKUP = re.compile(r"[*_`~|]+")
_WORD = re.compile(r"[\w.%]+")
# A re-typed quote still names a line when this share of its words are the line's own.
_MIN_OVERLAP = 0.8


def _plain(text: str) -> str:
    """Words only: emphasis, code ticks, tildes and pipes do not tell two lines apart."""
    return collapse_ws(_MARKUP.sub(" ", text)).casefold()


def _contains(line: str, needle: str) -> bool:
    """``needle`` as whole words: ``5%`` is not in ``15%``, nor ``KES 50`` in ``KES 500``."""
    return re.search(rf"(?<![\w.]){re.escape(needle)}(?!\w)", _plain(line)) is not None


def _find_line(lines: list[str], quote: str) -> int | None:
    needle = _plain(quote)
    if not needle:
        return None
    for index, line in enumerate(lines):
        if _contains(line, needle):
            return index
    words = set(_WORD.findall(needle))
    figures = {w for w in words if any(c.isdigit() for c in w)}
    best: tuple[float, int] | None = None
    for index, line in enumerate(lines):
        have = set(_WORD.findall(_plain(line)))
        if not have or len(words) < 3 or figures - have:
            continue
        overlap = len(words & have) / len(words)
        if overlap >= _MIN_OVERLAP and (best is None or overlap > best[0]):
            best = (overlap, index)
    return None if best is None else best[1]


_LIST_MARKER = re.compile(r"^\s*(?:[-*+\u2022]|\d+[.)])\s+")
# A table row the cut took out: it keeps its place, so its table can be tidied as one.
_CUT_ROW = "\x00cut"


def _is_table_rule(row: str) -> bool:
    """A table's rule row, "|---|:--|": only pipes, dashes, colons and spaces, with a pipe
    after the first character."""
    return _TABLE_RULE_CHARS.fullmatch(row) is not None and "|" in row[1:]


def _sentences(line: str) -> list[str]:
    """``line`` split after each ``.``, ``!`` or ``?`` that whitespace and then a capital,
    digit, markup or quote follow; the whitespace goes."""
    parts: list[str] = []
    start = 0
    for end in _SENTENCE_END.finditer(line):
        stop = gap = end.end()
        while gap < len(line) and line[gap].isspace():
            gap += 1
        if stop < gap < len(line) and line[gap] in _SENTENCE_OPENERS:
            parts.append(line[start:stop])
            start = gap
    parts.append(line[start:])
    return parts


def _cut_from_line(line: str, quote: str) -> str | None:
    """The line without the sentence holding ``quote``; ``_CUT_ROW`` for a table row, None
    when nothing is left, the line itself when it cannot tell which sentence was meant."""
    if _TABLE_ROW.match(line):
        return _CUT_ROW
    needle = _plain(quote)
    sentences = _sentences(line)
    kept = [s for s in sentences if not _contains(s, needle)]
    if len(kept) == len(sentences):
        # Named by its words, not copied: one sentence has nothing else to keep, and with
        # several there is no telling which one it meant.
        return None if len(sentences) == 1 else line
    rest = " ".join(kept).rstrip()
    if _ONLY_MARKUP.match(rest):
        return None
    marker = _LIST_MARKER.match(line)
    return rest if marker is None or _LIST_MARKER.match(rest) else f"{marker.group()}{rest}"


_TOTAL_ROW = re.compile(r"^\s*\|[\s*_]*(?:grand\s+)?(?:total|sum)\b", re.IGNORECASE)


def _tidy_tables(lines: list[str | None]) -> list[str]:
    """A table that lost rows: its total no longer adds up, so that goes too; a table that
    lost its header, or every row, leaves nothing to show. Other tables are left as written."""
    out: list[str] = []
    run: list[str] = []

    def flush() -> None:
        if _CUT_ROW not in run:
            out.extend(run)
        else:
            rows = [row for row in run if not _is_table_rule(row)]
            header_cut = rows[0] == _CUT_ROW
            body = [row for row in rows[1:] if row != _CUT_ROW and not _TOTAL_ROW.match(row)]
            if not header_cut and body:
                rule = [row for row in run[1:2] if _is_table_rule(row)]
                out.extend([rows[0], *rule, *body])
        run.clear()

    for line in lines:
        if line is not None and (line == _CUT_ROW or _TABLE_ROW.match(line)):
            run.append(line)
            continue
        flush()
        if line is not None:
            out.append(line)
    flush()
    return out


_ORDERED = re.compile(r"^(?P<indent>\s*)(?P<number>\d+)(?P<mark>[.)])(?=\s)")


@dataclass
class _ListRun:
    indent: int
    start: int
    lost: bool = False
    items: list[tuple[int, re.Match[str]]] = field(default_factory=list)


def _renumber_lists(lines: list[str | None], cut: dict[int, tuple[str, int]]) -> list[str | None]:
    """A numbered list that lost a whole item counts on without the gap.

    A searched reply's "1. … 2. … 3." lost item 1 to the cut and showed as a list
    starting at 2 (2026-10-29). ``cut`` maps a removed item's line to its indent and
    number: the list still starts at its first number, and lists that lost nothing keep
    theirs. A list nested under an item is its own, and the outer one goes on after it.
    """
    out = list(lines)
    open_runs: list[_ListRun] = []  # outermost first

    def close_from(depth: int) -> None:
        """Ends every open list at ``depth`` or deeper."""
        while open_runs and open_runs[-1].indent >= depth:
            run = open_runs.pop()
            if run.lost:
                for offset, (index, match) in enumerate(run.items):
                    rest = (out[index] or "")[match.end() :]
                    out[index] = f"{match['indent']}{run.start + offset}{match['mark']}{rest}"

    def run_at(depth: int, number: int) -> _ListRun:
        close_from(depth + 1)
        if not open_runs or open_runs[-1].indent != depth:
            open_runs.append(_ListRun(depth, number))
        return open_runs[-1]

    for index, line in enumerate(lines):
        if line is None:
            if index in cut:
                indent, number = cut[index]
                run_at(len(indent), number).lost = True
            continue
        match = _ORDERED.match(line)
        if match is not None:
            run_at(len(match["indent"]), int(match["number"])).items.append((index, match))
        elif line.strip():
            # A paragraph ends every list at its own depth or deeper.
            close_from(len(line) - len(line.lstrip()))
    close_from(0)
    return out


def cut_claims(text: str, quotes: list[str]) -> tuple[str, int]:
    """``text`` without the sentence or table row of each quote found in its prose,
    and how many quotes it took out."""
    handled: set[str] = set()

    def rewrite(prose: str) -> str:
        lines: list[str | None] = [*prose.split("\n")]
        cut_items: dict[int, tuple[str, int]] = {}
        for quote in quotes:
            if quote in handled:
                continue
            index = _find_line([line or "" for line in lines], quote)
            if index is None:
                continue
            before = lines[index]
            after = _cut_from_line(before or "", quote)
            if after != before:
                lines[index] = after
                handled.add(quote)
                item = _ORDERED.match(before or "")
                if after is None and item is not None:
                    cut_items[index] = (item["indent"], int(item["number"]))
        return "\n".join(_tidy_tables(_renumber_lists(lines, cut_items)))

    return map_prose_outside_fences(text, rewrite), len(handled)


async def _verdict(state: FinalizeState) -> _Verdict | None:
    settings = state.settings
    messages = [
        {"role": "system", "content": _SYSTEM},
        {
            "role": "user",
            "content": f"{_evidence(state)}\n\nASSISTANT REPLY TO CHECK:\n{state.text[:_REPLY_CHARS]}",
        },
    ]
    return await announced_if_slow(
        complete_structured(
            settings=settings,
            model_alias=ROUTING.background,
            messages=messages,
            schema=_Verdict,
            max_tokens=600,
            timeout_seconds=settings.claim_check_timeout_seconds,
            usage=state.usage,
            allow_fallback=False,
        ),
        state.on_status,
        "checking",
        then="finishing",
    )


def _prose_chars(text: str) -> int:
    total = 0

    def count(prose: str) -> str:
        nonlocal total
        total += len(prose)
        return prose

    map_prose_outside_fences(text, count)
    return total


async def cut_unsupported_claims(state: FinalizeState) -> str:
    """Pass entry: a searched reply keeps only what its sources or the user said."""
    ctx = state.ctx
    text = state.text
    if (
        not state.settings.claim_check_enabled
        or not ctx.search_sources
        or state.server_text
        or state.was_cancelled
        or ctx.verified_subject is not None
        or ctx.money is not None
        or len(text) < _MIN_REPLY_CHARS
    ):
        return text
    verdict = await _verdict(state)
    if verdict is None or not verdict.unsupported:
        return text
    quotes = [claim.quote for claim in verdict.unsupported]
    cut, found = cut_claims(text, quotes)
    if not found:
        return text
    before = _prose_chars(text)
    if before and (before - _prose_chars(cut)) / before > _MAX_CUT_SHARE:
        logger.warning("claim_check flagged most of a reply; left it as written")
        return text
    topics = "; ".join(dict.fromkeys(c.topic.strip() for c in verdict.unsupported if c.topic))
    logger.info("claim_check cut %d unsupported claim(s): %s", found, topics)
    note = verdict.note.strip() or (
        f"I couldn't confirm these from the sources I found, so I left them out: {topics}."
        if topics
        else "I left out details the sources I found did not confirm."
    )
    return f"{cut.rstrip()}\n\n*{note.strip('*_ ')}*"

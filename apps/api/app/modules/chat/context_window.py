"""Token estimation + token-budget windowing for prompt context.

Pure helpers (no app imports but the pure fence scanner) so both the chat service
and the background compaction job can share them without import cycles.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.md_fence_scan import iter_fences

_SUMMARY_MAX_CHARS = 6000
_SUMMARY_MESSAGE_MAX_CHARS = 1200
_TRIM_MARK = " … [truncated] … "

# An invented "Open: user considering sleeping 6-7 hours" later came back as something the
# assistant had asked.
NO_INVENTED_PLAN = "never invent a plan or a question nobody voiced"
# Two figures for one thing: the summary keeps the newer, dated, so an old one is not read
# as current.
NEWEST_FIGURE_RULE = (
    "When two figures for the same thing differ, keep the most recent one with its date. "
)

SUMMARY_SYSTEM_PROMPT = (
    "You compress a conversation into a concise running summary so an assistant can "
    "continue it later. Merge the existing summary with the new messages.\n\n"
    "Format (plain text, no markdown headings):\n"
    "Facts: durable preferences, names, numbers, decisions\n"
    "Topics: one short line per topic in the order it was discussed (oldest first), "
    "with its outcome\n"
    "Open: questions the user left unanswered or next steps they asked for; write None when "
    "there are none, and " + NO_INVENTED_PLAN + "\n\n"
    "Keep the whole summary under 300 words: shorten older topic lines as new ones arrive, "
    "never drop a topic, and always finish every section. "
    + NEWEST_FIGURE_RULE
    + "Keep durable facts and decisions; drop greetings and filler. Preserve uncertainty: "
    "if someone is considering an option or has not decided, do not upgrade that into a "
    "decision (e.g. keep 'considering Postgres', never 'uses Postgres'). Reply with the "
    "summary only."
)


# Flat estimate for a vision ``image_url`` part when provider usage is missing.
_VISION_IMAGE_PART_TOKENS = 85


def estimate_tokens(text: str | list[Any]) -> int:
    """Rough token count — blends word/char heuristics; code blocks count denser.

    Accepts OpenAI-style multimodal ``content`` lists (vision turns) so finalize
    fallbacks do not crash when provider usage is absent.
    """
    if isinstance(text, list):
        total = 0
        for part in text:
            if isinstance(part, str):
                total += estimate_tokens(part)
            elif isinstance(part, dict):
                part_type = part.get("type")
                if part_type == "text" and isinstance(part.get("text"), str):
                    total += estimate_tokens(part["text"])
                elif part_type == "image_url":
                    total += _VISION_IMAGE_PART_TOKENS
        return max(1, total)

    stripped = text.strip()
    if not stripped:
        return 1

    latin_letters = 0
    other_letters = 0
    for char in stripped:
        if not char.isalpha():
            continue
        if "A" <= char <= "Z" or "a" <= char <= "z":
            latin_letters += 1
        else:
            other_letters += 1
    letter_total = latin_letters + other_letters
    if letter_total > 0 and other_letters / letter_total >= 0.4:
        # CJK / Amharic / Cyrillic pack ~1 token per character; the Latin
        # word heuristic undercounts and lets the window grow too large.
        return max(1, len(stripped))

    dense_chars = sum(fence.end - fence.start for fence in iter_fences(stripped))
    plain_len = max(0, len(stripped) - dense_chars)
    words = len(stripped.split())
    char_est = plain_len / 3.6 + dense_chars / 2.5
    word_est = words * 1.35
    return max(1, int(max(char_est, word_est)))


def select_recent_window(
    messages: list[Any],
    budget: int,
    max_count: int,
    min_count: int = 2,
) -> int:
    """How many of the most recent messages to keep verbatim.

    Walks newest → oldest, accumulating estimated tokens. Keeps messages until
    the token budget or `max_count` is hit, but always keeps at least
    `min_count` (so the latest exchange is never dropped, even if it alone
    exceeds the budget). Returns the count of trailing messages to keep.
    """
    kept = 0
    tokens = 0
    for msg in reversed(messages):
        if kept >= max_count:
            break
        cost = estimate_tokens(msg.content)
        if kept >= min_count and tokens + cost > budget:
            break
        tokens += cost
        kept += 1
    return kept


@dataclass(frozen=True)
class HistorySplit:
    summarized_count: int


def compute_history_split(
    total_message_count: int,
    recent_messages: list[Any],
    budget: int,
    max_count: int,
    min_count: int = 2,
) -> HistorySplit:
    """Split a chat into verbatim tail vs messages eligible for summarization."""
    keep = select_recent_window(recent_messages, budget, max_count, min_count)
    return HistorySplit(summarized_count=max(0, total_message_count - keep))


def should_run_compression(
    split: HistorySplit,
    already_summarized: int,
    batch: int,
    *,
    urgent_min_pending: int = 3,
) -> bool:
    """Whether the background job should fold more messages into the summary.

    The gap between ``already_summarized`` and ``split.summarized_count`` is
    dropped from the prompt entirely — those messages are older than the
    recent window and not yet in the summary. Run compaction whenever that
    gap reaches ``urgent_min_pending`` (not only under token pressure) so the
    hole never grows past a few messages. The larger ``batch`` threshold
    amortizes LLM cost on long, low-pressure threads.
    """
    pending = split.summarized_count - already_summarized
    if pending <= 0:
        return False
    if pending >= batch:
        return True
    if pending >= urgent_min_pending:
        return True
    return False


# How many messages between the stored summary and the loaded recent window
# the prompt may include verbatim. Compression folds the rest later.
UNSUMMARIZED_GAP_MAX_MESSAGES = 10


def unsummarized_gap_bounds(
    *,
    total: int,
    summarized: int,
    loaded: int,
    max_messages: int = UNSUMMARIZED_GAP_MAX_MESSAGES,
) -> tuple[int, int] | None:
    """Oldest-first offset and count of messages in neither the summary nor the window.

    ``loaded`` is the trailing window already fetched for the prompt. The
    newest ``max_messages`` of that hole are the ones worth showing; older
    ones wait for the summary job.
    """
    if total <= 0 or loaded < 0 or summarized < 0 or max_messages <= 0:
        return None
    window_start = max(0, total - loaded)
    gap_end = window_start
    gap_start = min(max(0, summarized), gap_end)
    pending = gap_end - gap_start
    if pending <= 0:
        return None
    if pending > max_messages:
        gap_start = gap_end - max_messages
    return gap_start, gap_end - gap_start


def messages_within_token_budget(
    messages: list[Any],
    budget: int,
    *,
    max_messages: int,
) -> list[Any]:
    """Newest messages that still fit ``budget``, oldest first.

    Each body is measured after the summary trim, matching what the prompt
    will send. A full recent window leaves no room, so the gap stays empty.
    """
    if budget <= 0 or max_messages <= 0:
        return []
    chosen: list[Any] = []
    used = 0
    for message in reversed(messages):
        if len(chosen) >= max_messages:
            break
        content = getattr(message, "content", "")
        text = content if isinstance(content, str) else ""
        cost = estimate_tokens(trim_message_for_summary(text))
        if used + cost > budget:
            break
        used += cost
        chosen.append(message)
    chosen.reverse()
    return chosen


def trim_message_for_summary(content: str, max_chars: int = _SUMMARY_MESSAGE_MAX_CHARS) -> str:
    """A long message keeps its start and its end: a pasted CV, then the ask after it."""
    text = content.strip()
    if len(text) <= max_chars:
        return text
    keep = max(0, max_chars - len(_TRIM_MARK))
    head = keep // 2
    return f"{text[:head].rstrip()}{_TRIM_MARK}{text[len(text) - (keep - head) :].lstrip()}"


def cap_summary(text: str, max_chars: int = _SUMMARY_MAX_CHARS) -> str:
    trimmed = text.strip()
    if len(trimmed) <= max_chars:
        return trimmed
    return f"{trimmed[: max_chars - 3].rstrip()}..."

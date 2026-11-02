"""What one extraction pass writes, from the model's ops and the user's own words.

No IO: ``extraction_workflow`` reads the snapshot and the lines under the user's write
lock, asks the model, and applies what ``compose_writes`` returns.
"""

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.modules.memory.commands import (
    forget_requests,
    is_explicit_forget_command,
    is_explicit_memory_command,
    is_explicit_mute_command,
    is_memory_correction,
    memory_reset_request,
    mute_requests,
    remember_requests,
)
from app.modules.memory.fact_quality import FactView, is_one_off_schedule_fact, texts_to_drop
from app.modules.memory.facts import should_skip_sensitive_persist
from app.modules.memory.forget_match import names_nothing, phrase_names_fact
from app.modules.memory.name_claim import is_unclaimed_user_name
from app.modules.memory.ops import EXPLICIT_IMPORTANCE, MODEL_IMPORTANCE_MAX, normalize_memory_text
from app.modules.memory.schemas import MemoryFactOp
from app.modules.memory.self_facts import stated_fact_writes
from app.modules.memory.text import classify_memory_sensitivity
from app.modules.memory.topics import is_area, parse_topic, topic_memory_type
from app.modules.memory.user_name import as_chosen_name
from app.modules.memory.writes_repository import MemoryFactWrite

logger = logging.getLogger(__name__)

_MATCH_ONLY_OPS = frozenset({"delete", "mute"})


@dataclass(frozen=True)
class MemorySnapshot:
    memory_enabled: bool
    include_sensitive: bool
    existing_facts: dict[UUID, str]
    prompt_facts: list[dict[str, str]]
    prompt_areas: list[dict[str, str]]
    # When the user last removed or changed memory by hand.
    edited_at: datetime | None = None
    active_facts: tuple[FactView, ...] = ()
    # Their zone: "next Friday" is saved as the date it means on their calendar.
    user_timezone: str | None = None
    # The account name: a name they give that differs is saved as the one they go by.
    profile_name: str | None = None


@dataclass(frozen=True)
class Asks:
    """What the lines ask of memory in the user's own words."""

    forget: bool
    mute: bool
    # A correction changes a saved fact by the user's word, like a hand edit.
    correction: bool
    remember: bool

    @classmethod
    def of(cls, lines: str) -> "Asks":
        forget = is_explicit_forget_command(lines)
        return cls(
            forget=forget,
            mute=is_explicit_mute_command(lines),
            correction=is_memory_correction(lines),
            remember=is_explicit_memory_command(lines) and not forget,
        )


def compose_writes(
    snapshot: MemorySnapshot,
    lines: str,
    asks: Asks,
    ops: list[MemoryFactOp],
    *,
    chat_id: UUID,
    from_history: bool,
    min_confidence: float,
    earlier: str = "",
) -> tuple[list[MemoryFactWrite], int]:
    """Every write a pass makes, from the model's ops and the user's own words; no IO.

    ``earlier`` is the exchange before ``lines``: a lone "forget that" drops what the
    line before it asked to remember.
    """
    writes, skipped = writes_from_ops(
        ops,
        chat_id=chat_id,
        explicit_remember=asks.remember,
        include_sensitive=snapshot.include_sensitive,
        min_confidence=min_confidence,
        transcript=lines,
        existing_texts=snapshot.existing_facts.values(),
        profile_name=snapshot.profile_name,
    )
    if asks.forget and not from_history and not any(write.op == "delete" for write in writes):
        writes.extend(
            named_forget_deletes(lines, existing_facts=snapshot.existing_facts, chat_id=chat_id)
            or _forget_points_back(lines, earlier, snapshot.existing_facts, chat_id)
        )
    if asks.mute and not from_history and not any(write.op == "mute" for write in writes):
        writes.extend(
            named_mute_ops(lines, existing_facts=snapshot.existing_facts, chat_id=chat_id)
        )
    if not asks.forget:
        writes.extend(
            stated_fact_writes(
                lines,
                chat_id=chat_id,
                existing_facts=(
                    (str(fact["type"]), str(fact["text"])) for fact in snapshot.prompt_facts
                ),
                already=writes,
                include_sensitive=snapshot.include_sensitive,
                explicit_remember=asks.remember,
                model_ops=ops,
            )
        )
    if from_history:
        return [write for write in writes if write.op == "add"], skipped
    return writes + _stale_fact_deletes(snapshot, writes), skipped


def _stale_fact_deletes(
    snapshot: MemorySnapshot, writes: list[MemoryFactWrite]
) -> list[MemoryFactWrite]:
    """Deletes for saved facts gone stale (``texts_to_drop``) that no write covers yet."""
    already = {
        normalize_memory_text(write.match_text or "") for write in writes if write.op == "delete"
    }
    fresh = {
        normalize_memory_text(write.text) for write in writes if write.op != "delete" and write.text
    }
    deletes: list[MemoryFactWrite] = []
    for text in texts_to_drop(snapshot.active_facts):
        key = normalize_memory_text(text)
        if key in already or key in fresh:
            continue
        already.add(key)
        deletes.append(
            MemoryFactWrite(op="delete", type="fact", text="", confidence=1.0, match_text=text)
        )
    return deletes


def writes_from_ops(
    result_ops: list[MemoryFactOp],
    *,
    chat_id: UUID | None,
    explicit_remember: bool,
    include_sensitive: bool,
    min_confidence: float,
    transcript: str,
    existing_texts: Iterable[str] = (),
    profile_name: str | None = None,
) -> tuple[list[MemoryFactWrite], int]:
    writes: list[MemoryFactWrite] = []
    skipped = 0
    for op in result_ops:
        confidence = float(op.confidence)
        if confidence < min_confidence:
            skipped += 1
            continue
        text = normalize_memory_text(op.text or "")
        sensitivity = op.sensitivity or classify_memory_sensitivity(text)
        if should_skip_sensitive_persist(
            sensitivity=sensitivity,
            text=text or op.match_text or "",
            explicit_remember=explicit_remember,
            include_sensitive=include_sensitive,
        ) and op.op in {"add", "update", "supersede"}:
            logger.info(
                "Skipping sensitive memory persist op=%s sensitivity=%s",
                op.op,
                sensitivity,
            )
            skipped += 1
            continue
        # A delete or mute names an existing fact by match_text; it writes no text.
        writes_text = op.op not in _MATCH_ONLY_OPS
        if writes_text and not text:
            skipped += 1
            continue
        if writes_text and is_unclaimed_user_name(text, transcript, existing_texts=existing_texts):
            logger.info("Skipping memory name the user did not claim")
            skipped += 1
            continue
        if writes_text and is_one_off_schedule_fact(text):
            logger.info("Skipping one-off reminder stored as memory")
            skipped += 1
            continue
        if writes_text:
            # "Call me Sam", or "My name is Bill" on an account named William, is
            # the name they go by, kept beside the profile name.
            text = as_chosen_name(text, transcript, profile_name)
        # No valid topic keeps a matched fact where it is; a new fact then gets
        # the default document for its type.
        topic = parse_topic(op.topic)
        writes.append(
            MemoryFactWrite(
                op=op.op,
                # The document decides the type, so the two never disagree.
                type=topic_memory_type(topic) if topic else op.type,
                text=text,
                confidence=confidence,
                sensitivity=sensitivity,
                # What the user asked to keep is never pushed out by the fact cap.
                importance=EXPLICIT_IMPORTANCE
                if explicit_remember and writes_text
                else min(float(op.importance), MODEL_IMPORTANCE_MAX),
                match_text=op.match_text,
                source_chat_id=chat_id,
                topic=topic,
                area_title=op.topic_title if topic and is_area(topic) else None,
                area_summary=op.topic_summary if topic and is_area(topic) else None,
            )
        )
    return writes, skipped


def named_forget_deletes(
    transcript: str,
    *,
    existing_facts: dict[UUID, str],
    chat_id: UUID | None,
) -> list[MemoryFactWrite]:
    """Delete stored facts the user named when the model returned no delete."""
    return _named_fact_ops("delete", forget_requests(transcript), existing_facts, chat_id)


def _forget_points_back(
    lines: str, earlier: str, existing_facts: dict[UUID, str], chat_id: UUID
) -> list[MemoryFactWrite]:
    """ "Remember I'm vegetarian", then "Actually, forget that": delete what it remembered.

    Only for one line that names nothing; a line that names a fact the store lacks
    ("forget my old address") deletes nothing. The earlier line must be the remember
    and nothing else: after "Remember I'm vegetarian, and suggest a dinner", "that" may
    be the dinner, and the model decides.
    """
    said = [line for line in lines.splitlines() if line.strip()]
    if len(said) != 1 or not all(names_nothing(phrase) for phrase in forget_requests(lines)):
        return []
    asked: list[str] = []
    for line in earlier.splitlines():
        if not line.startswith("User:"):
            continue
        body = line.removeprefix("User:").strip().rstrip(" .!")
        asked.extend(
            phrase
            for phrase in remember_requests(body)
            if body.casefold().endswith(phrase.casefold())
        )
    return _named_fact_ops("delete", asked, existing_facts, chat_id)


def named_mute_ops(
    transcript: str,
    *,
    existing_facts: dict[UUID, str],
    chat_id: UUID | None,
) -> list[MemoryFactWrite]:
    """Mute stored facts the user named ("stop mentioning my job") when the model did not."""
    return _named_fact_ops("mute", mute_requests(transcript), existing_facts, chat_id)


def _named_fact_ops(
    op: str,
    phrases: list[str],
    existing_facts: dict[UUID, str],
    chat_id: UUID | None,
) -> list[MemoryFactWrite]:
    return [
        MemoryFactWrite(
            op=op,
            type="fact",
            text="",
            confidence=1.0,
            match_text=fact_text,
            source_chat_id=chat_id,
        )
        for fact_text in existing_facts.values()
        if any(phrase_names_fact(phrase, fact_text) for phrase in phrases)
    ]


def without_reset_requests(transcript: str) -> str:
    """Drop "forget everything you know about me" lines: a card the user taps does that."""
    lines = [
        line
        for line in transcript.splitlines()
        if memory_reset_request(line.removeprefix("User:").strip()) is None
    ]
    return "\n".join(lines).strip()

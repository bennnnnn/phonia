"""Durable first-person facts taken from the user's own lines.

The memory model often returns no ops for "I am working on …". Those
statements are still saved here, without storing story characters.
"""

from __future__ import annotations

from collections.abc import Iterable
from uuid import UUID

from app.modules.memory.fact_quality import is_one_off_schedule_fact
from app.modules.memory.facts import should_skip_sensitive_persist
from app.modules.memory.ops import normalize_memory_text
from app.modules.memory.text import classify_memory_sensitivity
from app.modules.memory.writes_repository import MemoryFactWrite

_MAX_FACTS = 5
_MAX_OBJECT_CHARS = 200

# Longest prefixes first so "currently working on" wins over "working on".
_PREFIXES: tuple[tuple[str, str, str], ...] = (
    ("i am currently working on ", "project", "User is working on {object}"),
    ("i'm currently working on ", "project", "User is working on {object}"),
    ("i am working on ", "project", "User is working on {object}"),
    ("i'm working on ", "project", "User is working on {object}"),
    ("im working on ", "project", "User is working on {object}"),
    ("am working on ", "project", "User is working on {object}"),
    ("i am currently building ", "project", "User is building {object}"),
    ("i'm currently building ", "project", "User is building {object}"),
    ("i am building ", "project", "User is building {object}"),
    ("i'm building ", "project", "User is building {object}"),
    ("im building ", "project", "User is building {object}"),
    ("my main project is called ", "project", "User's project is {object}"),
    ("my current project is called ", "project", "User's project is {object}"),
    ("my project is called ", "project", "User's project is {object}"),
    ("my main project is ", "project", "User's project is {object}"),
    ("my current project is ", "project", "User's project is {object}"),
    ("my project is ", "project", "User's project is {object}"),
    ("my current focus is ", "focus", "User's current focus is {object}"),
    ("my current priority is ", "focus", "User's current focus is {object}"),
    ("i am focusing on ", "focus", "User's current focus is {object}"),
    ("i'm focusing on ", "focus", "User's current focus is {object}"),
)

_BARE_AM_PREFIX = "am working on "

_PRONOUNS = frozenset(
    {"it", "this", "that", "them", "these", "those", "something", "anything", "nothing", "stuff"}
)
_SKIP_PREFIXES = (
    "the problem",
    "this problem",
    "a problem",
    "my problem",
    "the question",
    "this question",
    "a question",
    "the equation",
    "this equation",
    "the math",
    "this math",
    "the homework",
    "my homework",
    "homework",
)
_REQUEST_MARKERS = (
    " can you ",
    " could you ",
    " please ",
    " help me ",
    " how do i ",
    " how can i ",
)
# Words before the prefix that make it a condition or someone else's report.
_NON_ASSERTION_WORDS = frozenset(
    {
        "if",
        "whether",
        "asked",
        "ask",
        "asks",
        "told",
        "tell",
        "said",
        "says",
        "suppose",
        "supposing",
        "unless",
        "wonder",
        "wondering",
        "wondered",
    }
)


def _fold(text: str) -> str:
    return text.replace("\u2019", "'").replace("\u2018", "'").casefold()


def _user_lines(transcript: str) -> list[str]:
    labeled = False
    lines: list[str] = []
    for raw in (transcript or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        folded = _fold(line)
        if folded.startswith("assistant:"):
            labeled = True
            continue
        if folded.startswith("user:"):
            labeled = True
            line = line.split(":", 1)[1].strip()
        elif labeled:
            continue
        if line:
            lines.append(line)
    return lines


def _cut_object(rest: str) -> str:
    folded = _fold(rest)
    end = len(rest)
    for index, char in enumerate(rest):
        if char in ".?!":
            end = index
            break
    request_at = end
    for marker in _REQUEST_MARKERS:
        found = folded.find(marker)
        if found >= 0 and found < request_at:
            request_at = found
    if request_at < end:
        end = request_at
    comma = rest.find(",")
    if 0 <= comma < end:
        tail = _fold(rest[comma + 1 :]).lstrip()
        if tail.startswith(("can ", "could ", "please", "help ", "how ", "what ", "why ")):
            end = comma
    return " ".join(rest[:end].strip(" \"'").split())


def _skip_object(obj: str) -> bool:
    folded = _fold(obj)
    if len(folded) < 2 or len(folded) > _MAX_OBJECT_CHARS:
        return True
    if folded in _PRONOUNS:
        return True
    for prefix in _SKIP_PREFIXES:
        if folded == prefix or folded.startswith(prefix + " "):
            return True
    return False


def _match_prefix(line: str) -> tuple[str, str, str] | None:
    folded = _fold(line)
    best: tuple[int, str, str, str] | None = None
    for prefix, kind, template in _PREFIXES:
        if prefix == _BARE_AM_PREFIX:
            if not folded.startswith(prefix):
                continue
            index = 0
        else:
            index = folded.find(prefix)
            if index < 0:
                continue
            if index > 0 and folded[index - 1] not in ".!? ":
                continue
            if not _is_direct_assertion(folded, index):
                continue
        if best is None or index < best[0] or (index == best[0] and len(prefix) > len(best[1])):
            best = (index, prefix, kind, template)
    if best is None:
        return None
    return best[1], best[2], best[3]


def stated_self_facts(transcript: str) -> list[tuple[str, str, str]]:
    """Return ``(type, text, object)`` for work the user said they are doing."""
    found: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for line in _user_lines(transcript):
        matched = _match_prefix(line)
        if matched is None:
            continue
        prefix, kind, template = matched
        folded = _fold(line)
        index = 0 if prefix == _BARE_AM_PREFIX else folded.find(prefix)
        obj = _cut_object(line[index + len(prefix) :])
        if _skip_object(obj):
            continue
        text = template.format(object=obj)
        key = normalize_memory_text(text).casefold()
        if key in seen:
            continue
        seen.add(key)
        found.append((kind, text, obj))
    if len(found) > _MAX_FACTS:
        return found[-_MAX_FACTS:]
    return found


def stated_fact_writes(
    transcript: str,
    *,
    chat_id: UUID,
    existing_facts: Iterable[tuple[str, str]],
    already: Iterable[MemoryFactWrite],
    include_sensitive: bool,
    explicit_remember: bool = False,
    model_ops: Iterable[object] = (),
) -> list[MemoryFactWrite]:
    known = [
        (kind, normalize_memory_text(text).casefold()) for kind, text in existing_facts if text
    ]
    known.extend(
        (write.type, normalize_memory_text(write.text).casefold())
        for write in already
        if write.op != "delete" and write.text
    )
    ops = list(model_ops)
    writes: list[MemoryFactWrite] = []
    for kind, text, obj in stated_self_facts(transcript):
        sensitivity = _model_sensitivity(obj, ops) or classify_memory_sensitivity(text)
        if should_skip_sensitive_persist(
            sensitivity=sensitivity,
            text=text,
            explicit_remember=explicit_remember,
            include_sensitive=include_sensitive,
        ):
            continue
        sentence = normalize_memory_text(text).casefold()
        if _already_stored(kind, sentence, obj.casefold(), known):
            continue
        if is_one_off_schedule_fact(text):
            continue
        writes.append(
            MemoryFactWrite(
                op="add",
                type=kind,
                text=text,
                confidence=0.9,
                sensitivity=sensitivity,
                importance=0.7,
                source_chat_id=chat_id,
            )
        )
        known.append((kind, sentence))
    return writes


def _is_direct_assertion(folded: str, index: int) -> bool:
    start = index
    while start > 0 and folded[start - 1] not in ".!?":
        start -= 1
    words = {word.strip("\"'(),") for word in folded[start:index].split()}
    return words.isdisjoint(_NON_ASSERTION_WORDS)


def _model_sensitivity(obj: str, model_ops: Iterable[object]) -> str | None:
    """Use the model's sensitivity when it already judged this same work."""
    folded_obj = obj.casefold()
    words = [word for word in folded_obj.split() if len(word) >= 5]
    for op in model_ops:
        label = str(getattr(op, "sensitivity", None) or "normal")
        if label == "normal":
            continue
        op_text = str(getattr(op, "text", "") or "").casefold()
        if not op_text:
            continue
        if folded_obj in op_text or any(word in op_text for word in words):
            return label
    return None


def _already_stored(
    kind: str,
    sentence: str,
    obj: str,
    known: list[tuple[str, str]],
) -> bool:
    for item_type, item in known:
        if item == sentence:
            return True
        if item_type == kind and kind in {"project", "focus"} and len(obj) >= 4 and obj in item:
            return True
    return False

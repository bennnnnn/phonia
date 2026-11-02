"""A sentence that tells the user about the prompt's own parts comes off a reply.

An investing answer opened: "The memory block contains details that don't match this
conversation. It names a different person and preferences that conflict with what
you've told me, so I'm setting it aside and answering from what you've shared, Dev."
(live chat, 2026-10-25). The prompt asks for no such line (``PRIVACY_HINT``, the saved
memory preamble); this pass removes the ones a model writes anyway.

It is deliberately narrow. A sentence goes only when it names an internal part from a
closed list: a label only Recall's prompt uses ("[Chemistry note]", "saved memory
block", "BEGIN UNTRUSTED CONTENT"), or a word that also has an everyday meaning
("memory block" in C, "system prompt" in prompt writing) together with words about
this user's chat with Recall ("this conversation", "what you've told me", "your … on
file"; not a bare "your name" or "about you", which an answer about a CMS or an LLM
uses). The sentence after it goes too when it points back ("It names a different
person…"). Never inside a code fence, an inline code span, a table, a heading or a
quote, never the whole reply, and never on a turn whose recent messages name these
parts or prompt writing, or whose message asks about language models or Recall's memory.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Set as AbstractSet
from functools import cache
from typing import TYPE_CHECKING

from app.modules.chat.prompt_rule_text import prompt_rule_text
from app.services.md_fence_scan import line_fences
from app.services.text_normalize import straighten_apostrophes

if TYPE_CHECKING:
    from app.modules.chat.finalize_passes import FinalizeState

logger = logging.getLogger(__name__)

# Labels and wrappers only Recall's prompt writes.
_PROMPT_LABEL = re.compile(
    r"\[(?:chemistry|physics|math) (?:note|context)\]|\bsaved[- ]memory block\b"
    r"|\bknown[- ]facts block\b|\b(?:begin|end) (?:untrusted content|verified (?:math|physics))\b"
    # "No verified block is present": "each verified block is added to the chain" is bitcoin.
    r"|\bverified (?:math|physics|chemistry) block\b|\bno verified block\b"
    r"|\bverified block (?:is|was) (?:present|given|shown|provided|attached)\b",
    re.IGNORECASE,
)
# An instruction copied from the prompt's rules: "Do not describe the work as math,
# algebra, or solving equations." opened a Class 8 speed answer (2026-10-30). Read only
# against the fixed rules (``prompt_rule_text``), never a turn's memory, to-dos or
# documents, and only in an instruction's shape.
_INSTRUCTION = re.compile(
    r"(?:do not|don't|never|always|when|if no|use|copy|put|give|state)\b", re.IGNORECASE
)
_WORDS = re.compile(r"[a-z0-9']+")
# Names with an everyday meaning too: internal only beside words about this user.
_PROMPT_PART = re.compile(
    r"\b(?:memory|profile) block\b|\bsystem (?:prompt|message)\b", re.IGNORECASE
)
_ABOUT_THIS_USER = re.compile(
    r"\b(?:this|our) (?:conversation|chat)\b|\bwhat you(?:'ve| have)? (?:told|shared with) me\b"
    r"|\byou(?:'ve| have) told me\b|\byour? \w+(?: \w+)? on file\b"
    r"|\b(?:a )?different person\b|\bset(?:ting)? (?:it|that|this|them) aside\b",
    re.IGNORECASE,
)
# A sentence that goes on about the one before it.
_POINTS_BACK = re.compile(r"(?:it|this|that|they|these|those)\b", re.IGNORECASE)
# The user's latest messages name these parts or ask about prompt writing.
_ASKED_ABOUT_PARTS = re.compile(
    r"\bmemory block|\bsystem (?:message|prompt)|\bknown[- ]facts|\bchemistry note"
    r"|\buntrusted content|\bprompt (?:engineering|injection|templates?)\b"
    r"|\b(?:user|good|better|my) prompts?\b|\bprompts? (?:for|to) (?:chatgpt|gpts?|an? (?:ai|llm))"
    r"|\bverified block",
    re.IGNORECASE,
)
# This message asks about language models or about what Recall remembers. Only this
# one: "I asked ChatGPT earlier" two messages back says nothing about this reply.
_ASKED_ABOUT_MODELS = re.compile(
    r"\bllms?\b|\bgpts?\b|\bchatgpt\b|\bchat ?bots?\b|\blanguage models?\b"
    r"|\bai (?:agents?|assistants?|models?)\b|\byour memory\b|\byou remember\b"
    r"|\b(?:know|remember) about me\b",
    re.IGNORECASE,
)
# How many of the user's latest messages say what the chat is about.
_RECENT_USER_MESSAGES = 4
_INLINE_CODE = re.compile(r"`[^`\n]*`")
_SENTENCE_BREAK = re.compile(r"(?<=[.!?…]) +")
# A line's list marker, kept when its sentences change.
_LEAD = re.compile(r"[ \t]*(?:(?:[-*+]|\d{1,3}[.)])[ \t]+)?")
_SKIPPED_STARTS = ("|", "#", ">", "    ", "\t")


def drop_prompt_leaks_pass(state: FinalizeState) -> str:
    """The finalize pass: a model reply loses sentences about the prompt's parts."""
    if state.server_text:
        return state.text
    return drop_prompt_leaks(state.text, *_recent_user_lines(state), rules=_rule_grams())


def drop_prompt_lines(text: str) -> str:
    """What stands in when the pass fails: every line with a sentence that names a part
    of the prompt or copies one of its rules goes, in code and quotes too."""
    try:
        rules: AbstractSet[str] = _rule_grams()
    except Exception:
        logger.exception("prompt rules unreadable; dropping only lines that name its parts")
        rules = frozenset()
    return "\n".join(line for line in text.split("\n") if not _leaking_line(line, rules))


def _leaking_line(line: str, rules: AbstractSet[str]) -> bool:
    lead = _LEAD.match(line.lstrip(" \t>#|"))
    body = line.lstrip(" \t>#|")[lead.end() if lead else 0 :]
    for sentence in _SENTENCE_BREAK.split(body):
        prose = straighten_apostrophes(_INLINE_CODE.sub(" ", sentence))
        if _leaks(prose) or (rules and _copies(prose, rules)):
            return True
    return False


@cache
def _rule_grams() -> frozenset[str]:
    return frozenset(_grams(prompt_rule_text(), 4))


def _recent_user_lines(state: FinalizeState) -> list[str]:
    """The message and the user's messages just before it."""
    earlier = [
        content
        for message in getattr(state.ctx, "prompt_messages", None) or []
        if message.get("role") == "user" and isinstance(content := message.get("content"), str)
    ]
    return [state.ctx.user_message_content or "", *earlier[-_RECENT_USER_MESSAGES:]]


def _grams(text: str, size: int) -> set[str]:
    words = _WORDS.findall(text.lower())
    return {" ".join(words[at : at + size]) for at in range(len(words) - size + 1)}


def drop_prompt_leaks(
    text: str,
    *asked: str | None,
    instructions: str = "",
    rules: frozenset[str] | None = None,
) -> str:
    """``text`` without sentences that name the prompt's internal parts or copy one of
    its ``instructions``, or unchanged.

    ``asked`` is what the user wrote this turn, then just before it.
    """
    prompt: AbstractSet[str] = rules if rules is not None else _grams(instructions, 4)
    # A leak copies a run of rules; one sentence that matches is advice the reply gives
    # ("Never open with a rhetorical hook." in tips on blog intros, review 2026-10-30).
    if _copied_count(text, prompt) < 2:
        prompt = frozenset()
    if not text or not (_PROMPT_LABEL.search(text) or _PROMPT_PART.search(text) or prompt):
        return text
    if _asked_about(asked):
        return text
    lines = text.split("\n")
    owners = line_fences(text)
    out: list[str] = []
    dropped_line = False
    for index, line in enumerate(lines):
        kept = line if owners[index] is not None else _without_leaks(line, prompt)
        if kept is None:
            dropped_line = True
            continue
        # A paragraph that went entirely leaves one blank line, not two.
        if dropped_line and not kept.strip() and (not out or not out[-1].strip()):
            continue
        dropped_line = False
        out.append(kept)
    result = "\n".join(out)
    return result if result.strip() else text


def _asked_about(asked: tuple[str | None, ...]) -> bool:
    """The user asked about these parts lately, or about models or memory just now."""
    lines = [straighten_apostrophes(line) for line in asked if line]
    if any(_ASKED_ABOUT_PARTS.search(line) for line in lines):
        return True
    return bool(asked and asked[0] and _ASKED_ABOUT_MODELS.search(lines[0]))


def _copies(sentence: str, prompt: AbstractSet[str]) -> bool:
    """An instruction of six words or more, half its four-word runs the prompt's own."""
    grams = _grams(sentence, 4)
    return (
        len(grams) >= 3
        and _INSTRUCTION.match(sentence.lstrip("*_ -")) is not None
        and len(grams & prompt) * 2 >= len(grams)
    )


def _copied_count(text: str, prompt: AbstractSet[str]) -> int:
    if not prompt:
        return 0
    sentences = _SENTENCE_BREAK.split(text.replace("\n", " "))
    return sum(_copies(sentence, prompt) for sentence in sentences)


def _without_leaks(line: str, prompt: AbstractSet[str] | None = None) -> str | None:
    """The line without its leaking sentences; None when none of it is left."""
    if line.startswith(_SKIPPED_STARTS) or line.lstrip().startswith(("|", "#", ">")):
        return line
    lead_match = _LEAD.match(line)
    lead = lead_match.group(0) if lead_match else ""
    body = line[len(lead) :]
    sentences = _SENTENCE_BREAK.split(body)
    kept: list[str] = []
    after_leak = False
    copied = 0
    for sentence in sentences:
        prose = straighten_apostrophes(_INLINE_CODE.sub(" ", sentence))
        copy = bool(prompt) and _copies(prose, prompt or frozenset())
        copied += copy
        if _leaks(prose) or copy or (after_leak and _points_back(prose)):
            after_leak = True
            continue
        after_leak = False
        kept.append(sentence)
    if len(kept) == len(sentences):
        return line
    # A paragraph mostly copied from the prompt: its short pieces ("Do not recompute.")
    # are the prompt's too.
    if not kept or (copied >= 2 and copied * 2 >= len(sentences)):
        return None
    return lead + " ".join(kept)


def _leaks(prose: str) -> bool:
    if _PROMPT_LABEL.search(prose):
        return True
    return bool(_PROMPT_PART.search(prose) and _ABOUT_THIS_USER.search(prose))


def _points_back(prose: str) -> bool:
    return bool(_POINTS_BACK.match(prose.lstrip("*_ ")) and _ABOUT_THIS_USER.search(prose))

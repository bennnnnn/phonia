"""Turn reading — what a message says, read from its words alone.

The pure readers chat's prompt used to keep beside its copy (structure ticket ST-04): a
confirmation, a light turn, a locale cue, code, a chart, a lesson step, a school exercise,
whether the subject readers can read a question (``readable``: English, numbers as written).
``turn`` holds the turn's reading, built once from them (ST-05), and ``plan`` its requests.
Nothing here reaches a database, a cache, the network or a model, and nothing here is
prompt text; chat's ``prompt_constants`` keeps the copy these readers choose between.
Every module, chat included, imports a reader from here and never through chat.
"""

from __future__ import annotations

_MODULE_EXPORTS = (
    "answer_subject",
    "capabilities",
    "chart",
    "checklist",
    "clarify",
    "coding",
    "conversation",
    "diagrams",
    "format",
    "length",
    "lesson_flow",
    "locale_cues",
    "personal",
    "plan",
    "practice",
    "profile_ask",
    "question_kinds",
    "reactions",
    "readable",
    "routing",
    "school_question",
    "stuck",
    "teaching",
    "turn",
    "visuals",
    "writing",
    "writing_kind",
    "writing_locales",
    "writing_purpose",
)

__all__ = [*_MODULE_EXPORTS]

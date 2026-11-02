"""Recall's own prompt rules as one text: what a reply must never say back to the user.

Only the fixed rules (chat's prompt constants and each subject's hints), never a turn's
context: a saved memory, a to-do, a document or a search result is the user's own, and a
reply quoting "Use a heavy-based pan" from their recipe quotes them, not the prompt
(review, 2026-10-30).
"""

from __future__ import annotations

import importlib
import pkgutil
from functools import cache
from types import ModuleType

from app.modules import turn_reading
from app.modules.chat import prompt_constants
from app.modules.chat.prompt_subjects import SUBJECT_HINTS

# A rule is a sentence or more; a short constant is a label or a word list.
_MIN_RULE = 40


def _strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value] if len(value) >= _MIN_RULE else []
    if isinstance(value, tuple | list | frozenset | set):
        return [text for item in value for text in _strings(item)]
    if isinstance(value, dict):
        return [text for item in value.values() for text in _strings(item)]
    return []


# Where the rules' words live: chat's copy, the readers that left it (structure ticket
# ST-04: their word lists still read as the prompt's), and chemistry's fence hint, which
# went to its subject (its adapter's hints carry it, ``beside_visuals``). Read by module
# name, as one package was before.
_RULE_HOMES = (prompt_constants, turn_reading)
_BESIDE_MODULE = "visuals"


def _rule_sources() -> list[ModuleType | tuple[str, ...]]:
    """Each module whose rule constants count, and the subjects' copy beside chat's visuals."""
    homes = {
        home: {info.name for info in pkgutil.iter_modules(home.__path__)} for home in _RULE_HOMES
    }
    sources: list[ModuleType | tuple[str, ...]] = []
    for name in sorted(set().union(*homes.values())):
        sources += [
            importlib.import_module(f"{home.__name__}.{name}")
            for home, names in homes.items()
            if name in names
        ]
        if name == _BESIDE_MODULE:
            sources += [hints.beside_visuals for hints in SUBJECT_HINTS.values()]
    return sources


def _source_rules(source: ModuleType | tuple[str, ...]) -> list[str]:
    if not isinstance(source, ModuleType):
        return _strings(source)
    rules: list[str] = []
    for name, value in vars(source).items():
        if name.isupper() or (name.startswith("_") and name.lstrip("_").isupper()):
            rules += _strings(value)
    return rules


@cache
def prompt_rule_text() -> str:
    """Every fixed rule the chat prompt may carry, joined."""
    rules = [rule for source in _rule_sources() for rule in _source_rules(source)]
    for hints in SUBJECT_HINTS.values():
        for short in (False, True):
            rules += _strings(list(hints.presentation(short)))
        rules += _strings(hints.closing)
    return "\n".join(rules)

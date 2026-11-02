"""Memory's public surface: what other modules read from it, typed for mypy.

Importing ``modules.memory.models`` must not load the service graph, or SQLAlchemy's
model registry cycles on ``Memory``, so each export is resolved on access. The package
does not keep what it resolved: a test patches the module that defines a name
(``app.modules.memory.retrieval.get_memory_block``) and every caller sees it, and
nothing patches the package itself (code-health audit CLAR-05).
"""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.modules.memory.cache import invalidate_memory_block as invalidate_memory_block
    from app.modules.memory.commands import asks_to_remember as asks_to_remember
    from app.modules.memory.commands import (
        is_explicit_memory_command as is_explicit_memory_command,
    )
    from app.modules.memory.commands import memory_reset_request as memory_reset_request
    from app.modules.memory.crud import active_fact_texts as active_fact_texts
    from app.modules.memory.crud import areas_for_export as areas_for_export
    from app.modules.memory.crud import delete_all_memories as delete_all_memories
    from app.modules.memory.crud import facts_for_export as facts_for_export
    from app.modules.memory.fact_quality import asks_to_keep as asks_to_keep
    from app.modules.memory.facts import SECTION_LABELS as SECTION_LABELS
    from app.modules.memory.retrieval import MemoryLoadReport as MemoryLoadReport
    from app.modules.memory.retrieval import MemoryScope as MemoryScope
    from app.modules.memory.retrieval import get_memory_block as get_memory_block
    from app.modules.memory.text import (
        exclude_sensitive_for_query as exclude_sensitive_for_query,
    )
    from app.modules.memory.text import is_food_or_diet_query as is_food_or_diet_query
    from app.modules.memory.text import memory_extract_user_text as memory_extract_user_text
    from app.modules.memory.text import memory_extraction_due as memory_extraction_due

# Name -> the module that defines it.
_EXPORTS = {
    "MemoryLoadReport": "retrieval",
    "MemoryScope": "retrieval",
    "SECTION_LABELS": "facts",
    "active_fact_texts": "crud",
    "areas_for_export": "crud",
    "asks_to_keep": "fact_quality",
    "asks_to_remember": "commands",
    "delete_all_memories": "crud",
    "exclude_sensitive_for_query": "text",
    "facts_for_export": "crud",
    "get_memory_block": "retrieval",
    "invalidate_memory_block": "cache",
    "is_explicit_memory_command": "commands",
    "is_food_or_diet_query": "text",
    "memory_extract_user_text": "text",
    "memory_extraction_due": "text",
    "memory_reset_request": "commands",
}
# The chat turn answers "what do you know about me" from ``profile_reply``; every
# reader of the Settings → Memory switch asks ``switch``.
_MODULE_EXPORTS = ("profile_reply", "switch")
__all__ = [*_EXPORTS, *_MODULE_EXPORTS]


def __getattr__(name: str) -> Any:
    if name in _MODULE_EXPORTS:
        return import_module(f"app.modules.memory.{name}")
    module = _EXPORTS.get(name)
    if module is None:
        raise AttributeError(name)
    return getattr(import_module(f"app.modules.memory.{module}"), name)

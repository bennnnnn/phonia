"""Public, lazily loaded surface for the Todos domain.

Keeping this package initializer lazy lets the central SQLAlchemy metadata
registry import ``modules.todos.models`` without loading the service graph.
"""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.modules.todos.actions import (
        MAX_TODO_ACTIONS_PER_TURN as MAX_TODO_ACTIONS_PER_TURN,
    )
    from app.modules.todos.actions import (
        REMINDER_TOPIC as REMINDER_TOPIC,
    )
    from app.modules.todos.actions import (
        apply_todo_actions as apply_todo_actions,
    )
    from app.modules.todos.chat_language import (
        TODO_LINK_FENCE as TODO_LINK_FENCE,
    )
    from app.modules.todos.chat_language import (
        language_evidence as language_evidence,
    )
    from app.modules.todos.chat_language import (
        message_language as message_language,
    )
    from app.modules.todos.chat_language import (
        todo_screen_answer as todo_screen_answer,
    )
    from app.modules.todos.chat_language import (
        writes_todos_in_todo_screen as writes_todos_in_todo_screen,
    )
    from app.modules.todos.classification import (
        query_implies_todos as query_implies_todos,
    )
    from app.modules.todos.due_reminders import (
        EMAIL_REMINDERS as EMAIL_REMINDERS,
    )
    from app.modules.todos.due_reminders import (
        PUSH_REMINDERS as PUSH_REMINDERS,
    )
    from app.modules.todos.due_reminders import (
        advance_recurring_without_device as advance_recurring_without_device,
    )
    from app.modules.todos.due_reminders import (
        aged_out_unsent as aged_out_unsent,
    )
    from app.modules.todos.due_reminders import (
        due_reminder_page as due_reminder_page,
    )
    from app.modules.todos.due_reminders import (
        is_due_now as is_due_now,
    )
    from app.modules.todos.due_reminders import (
        mark_reminder_emailed as mark_reminder_emailed,
    )
    from app.modules.todos.due_reminders import (
        mark_reminder_pushed as mark_reminder_pushed,
    )
    from app.modules.todos.due_reminders import (
        reminder_page_key as reminder_page_key,
    )
    from app.modules.todos.occurrences import (
        TodoEmailSnapshot as TodoEmailSnapshot,
    )
    from app.modules.todos.offer_reply import (
        accepted_offer_in as accepted_offer_in,
    )
    from app.modules.todos.offer_reply import (
        follows_reminder_card as follows_reminder_card,
    )
    from app.modules.todos.prompt_context import (
        build_todos_system_section as build_todos_system_section,
    )
    from app.modules.todos.prompt_context import (
        format_todos_voice_block as format_todos_voice_block,
    )
    from app.modules.todos.prompt_context import (
        select_todos_for_prompt as select_todos_for_prompt,
    )
    from app.modules.todos.prompt_hint import (
        TODO_HINT as TODO_HINT,
    )
    from app.modules.todos.proposals import (
        reminder_cards_as_text as reminder_cards_as_text,
    )
    from app.modules.todos.reminder_fences import (
        materialize_reminder_fences as materialize_reminder_fences,
    )
    from app.modules.todos.reply_denials import (
        without_denials as without_denials,
    )
    from app.modules.todos.write_asks import (
        todo_screen_reply as todo_screen_reply,
    )

_EXPORTS = {
    "MAX_TODO_ACTIONS_PER_TURN": ("actions", "MAX_TODO_ACTIONS_PER_TURN"),
    "REMINDER_TOPIC": ("actions", "REMINDER_TOPIC"),
    "TODO_HINT": ("prompt_hint", "TODO_HINT"),
    "apply_todo_actions": ("actions", "apply_todo_actions"),
    "build_todos_system_section": ("prompt_context", "build_todos_system_section"),
    "format_todos_voice_block": ("prompt_context", "format_todos_voice_block"),
    "materialize_reminder_fences": ("reminder_fences", "materialize_reminder_fences"),
    "reminder_cards_as_text": ("proposals", "reminder_cards_as_text"),
    "without_denials": ("reply_denials", "without_denials"),
    "query_implies_todos": ("classification", "query_implies_todos"),
    "accepted_offer_in": ("offer_reply", "accepted_offer_in"),
    "follows_reminder_card": ("offer_reply", "follows_reminder_card"),
    "TODO_LINK_FENCE": ("chat_language", "TODO_LINK_FENCE"),
    "language_evidence": ("chat_language", "language_evidence"),
    "message_language": ("chat_language", "message_language"),
    "todo_screen_answer": ("chat_language", "todo_screen_answer"),
    "todo_screen_reply": ("write_asks", "todo_screen_reply"),
    "writes_todos_in_todo_screen": ("chat_language", "writes_todos_in_todo_screen"),
    "select_todos_for_prompt": ("prompt_context", "select_todos_for_prompt"),
    "TodoEmailSnapshot": ("occurrences", "TodoEmailSnapshot"),
    "EMAIL_REMINDERS": ("due_reminders", "EMAIL_REMINDERS"),
    "PUSH_REMINDERS": ("due_reminders", "PUSH_REMINDERS"),
    "advance_recurring_without_device": ("due_reminders", "advance_recurring_without_device"),
    "aged_out_unsent": ("due_reminders", "aged_out_unsent"),
    "due_reminder_page": ("due_reminders", "due_reminder_page"),
    "is_due_now": ("due_reminders", "is_due_now"),
    "mark_reminder_emailed": ("due_reminders", "mark_reminder_emailed"),
    "mark_reminder_pushed": ("due_reminders", "mark_reminder_pushed"),
    "reminder_page_key": ("due_reminders", "reminder_page_key"),
}

__all__ = list(_EXPORTS)


def __getattr__(name: str) -> Any:
    target = _EXPORTS.get(name)
    if target is None:
        raise AttributeError(name)
    module_name, attribute = target
    value = getattr(import_module(f"app.modules.todos.{module_name}"), attribute)
    globals()[name] = value
    return value

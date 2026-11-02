"""Conversation — the user's chats and their messages, stored and read.

Chat runs a turn and decides what a reply says; this module keeps the rows it writes and
the ones other modules read (structure ticket ST-03). Its repositories stay private:
other modules use ``history`` (reads), ``service`` (writes), ``turn_record`` (a turn
chat did not stream) and ``history_rag`` (past turns as prompt snippets).
"""

from __future__ import annotations

_MODULE_EXPORTS = ("history", "history_rag", "turn_record")

__all__ = [*_MODULE_EXPORTS]

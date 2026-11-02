"""The retired proactive-suggestions table.

Nothing writes it any more: the generator, its job and the ``/suggestions``
routes are gone (follow-ups arrive on the reply, ``modules/chat/related_prompts``).
Rows already stored are still exported and deleted with the account. A later
release drops the table (expand, then contract: docs/ROLLBACK.md).
"""

"""Nothing goes to outside AI services until the account agreed to it.

The phone's sign-in page says beside its buttons that continuing agrees to the
outside AI processing, and the tap records the agreement with the sign-in itself
(``ai_data_consent`` on ``/auth/google``, ``/auth/apple``, ``/auth/dev``). An
account with none (one from before that, one that withdrew, a client that sends no
flag such as the web) is asked after sign-in and agrees with ``PATCH /auth/me``
``ai_data_consent``. Either way the agreement is
``users.ai_data_consent_at``. The server holds the same line: a
chat turn, speech (transcribe, read aloud, a live talk key or tool), a scanned
problem's read-back, a picture and the composer's picture check, and a memory
edit are refused with ``consent_required`` until the account agrees, and again
after it withdraws; a file's indexing (OCR and embeddings) skips it. The phone
answers that code with its consent screen. It sits in ``core`` because every
feature module checks it, and account itself reads those modules.

A user cached by ``get_current_user`` trails an agreement made on another
machine only when that change's generation never reached Redis
(``core/user_cache``), so a refusal still re-reads the row first.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.deps import get_current_user
from app.core.user_cache import forget_user
from app.exceptions import ConsentRequiredError, DomainError
from app.models.orm import User

# What a refusal re-reads: a withdrawal elsewhere can change these for the next
# outside-AI call.
_PRIVACY_COLUMNS = ("ai_data_consent_at", "memory_enabled", "web_search_enabled")


def has_ai_data_consent(user: User) -> bool:
    """The account agreed to the outside-AI disclosure and has not withdrawn."""
    return user.ai_data_consent_at is not None


class ConsentRefusedError(DomainError):
    """403 ``consent_required``: the phone opens its consent screen."""

    status_code = 403
    default_code = ConsentRequiredError.code

    def __init__(self) -> None:
        super().__init__(ConsentRequiredError().message)


async def get_consented_user(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """The signed-in user, once they agreed; 403 ``consent_required`` otherwise.

    ``get_current_user`` serves a cached row only under the account's current
    generation, which a withdrawal made on another machine replaces
    (``core/user_cache``). A refusal still re-reads the row before anything is sent.
    """
    if has_ai_data_consent(user):
        return user
    await session.refresh(user, attribute_names=list(_PRIVACY_COLUMNS))
    await session.commit()  # the re-read's transaction ends here, as in get_current_user
    if not has_ai_data_consent(user):
        raise ConsentRefusedError()
    # The cached copy was stale; the next request reads the row again.
    forget_user(user.id)
    return user

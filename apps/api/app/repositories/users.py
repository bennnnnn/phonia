from typing import Any
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import object_session

from app.core.user_cache import forget_user, publish_change, remember_user
from app.models.orm import Chat, Message, PushToken, UsageDaily, User
from app.models.schemas.auth import chosen_model_id


async def get_by_id(session: AsyncSession, user_id: UUID) -> User | None:
    return await session.get(User, user_id)


async def refresh_for_update(session: AsyncSession, user: User) -> None:
    """Refresh stale profile fields and lock them until the caller commits."""
    await session.refresh(user, with_for_update=True)


async def get_by_google_sub(session: AsyncSession, google_sub: str) -> User | None:
    result = await session.execute(select(User).where(User.google_sub == google_sub))
    return result.scalar_one_or_none()


async def get_by_apple_sub(session: AsyncSession, apple_sub: str) -> User | None:
    result = await session.execute(select(User).where(User.apple_sub == apple_sub))
    return result.scalar_one_or_none()


async def get_by_email(session: AsyncSession, email: str) -> User | None:
    result = await session.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def list_ids_by_plan(
    session: AsyncSession,
    *,
    plan: str,
    after_id: UUID | None = None,
    limit: int = 25,
) -> list[UUID]:
    """Keyset page of user ids on *plan*, ordered by id. Never fetch-all."""
    stmt = select(User.id).where(User.plan == plan).order_by(User.id).limit(max(1, limit))
    if after_id is not None:
        stmt = stmt.where(User.id > after_id)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def create(
    session: AsyncSession,
    *,
    email: str,
    name: str | None,
    avatar_url: str | None,
    google_sub: str | None = None,
    apple_sub: str | None = None,
    commit: bool = True,
) -> User:
    """A new user row. With ``commit=False`` it is flushed (its id is set) and the
    caller commits."""
    if not google_sub and not apple_sub:
        raise ValueError("google_sub or apple_sub is required")
    user = User(
        google_sub=google_sub,
        apple_sub=apple_sub,
        email=email,
        name=name,
        avatar_url=avatar_url,
    )
    session.add(user)
    if commit:
        await session.commit()
    else:
        await session.flush()
    await session.refresh(user)
    return user


async def update(session: AsyncSession, user: User, *, commit: bool = True, **fields: Any) -> User:
    """Apply *fields* onto *user*.

    Keys present in *fields* are written as-is, including explicit ``None``
    (so nullable columns like ``custom_instructions`` / ``location`` can be
    cleared). Omit a key to leave that column unchanged.

    Committed here, the change is published to every machine's user cache
    (``core/user_cache``); a publish Redis refuses raises ``RedisUnavailableError``
    after the commit. With ``commit=False`` the caller commits, then awaits
    ``user_cache.publish_change(user.id)``.
    """
    if "enabled_models" in fields:
        # default_model is a stored copy of the chosen model, never set on its own.
        fields["default_model"] = chosen_model_id(fields["enabled_models"])
    bound = user
    # object_session returns the sync Session, not the AsyncSession wrapper.
    # Spec mocks in unit tests have no sync_session; mutate those users as-is.
    try:
        sync = session.sync_session
    except AttributeError:
        sync = None
    if sync is not None and object_session(user) is not sync:
        bound = await session.merge(user, load=False)
    for key, value in fields.items():
        if hasattr(bound, key):
            setattr(bound, key, value)
    if commit:
        user_id = bound.id  # before the commit, which may expire it
        await session.commit()
        # Every machine drops its copy before the row is read back, so the copy
        # kept here under the new generation already holds this write.
        generation = await publish_change(user_id)
        await session.refresh(bound)
        remember_user(bound, generation)
    else:
        await session.flush()
        # Not saved yet: the caller publishes after its commit.
        forget_user(bound.id)
    return bound


async def lock_for_delete(session: AsyncSession, user_id: UUID) -> None:
    """Lock the user row for an account delete: memory writers lock User before Memory,
    so the delete takes the same order before any module deletes its rows."""
    await session.execute(select(User.id).where(User.id == user_id).with_for_update())


async def delete_user(session: AsyncSession, user_id: UUID, *, commit: bool = True) -> None:
    """Hard-delete a user, their chats, messages, usage and push tokens, and commit
    (with ``commit=False`` the caller commits, then forgets the cached row).

    The modules' rows (memory, to-dos, suggestions, attachments) are gone already:
    ``account.lifecycle`` asks each module, under ``lock_for_delete``. Every row is
    deleted explicitly before the user row, so the delete succeeds even for a table
    whose FK to users.id has no ON DELETE CASCADE.
    """
    await lock_for_delete(session, user_id)
    await session.execute(delete(Message).where(Message.user_id == user_id))
    await session.execute(delete(UsageDaily).where(UsageDaily.user_id == user_id))
    await session.execute(delete(PushToken).where(PushToken.user_id == user_id))
    await session.execute(delete(Chat).where(Chat.user_id == user_id))
    user = await session.get(User, user_id)
    if user is not None:
        await session.delete(user)
    if commit:
        await session.commit()
        forget_user(user_id)
    else:
        await session.flush()

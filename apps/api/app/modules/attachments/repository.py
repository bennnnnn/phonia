import json
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

from sqlalchemy import String, and_, func, literal, or_, select
from sqlalchemy import cast as sql_cast
from sqlalchemy import delete as sa_delete
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
from sqlalchemy.sql.elements import ColumnElement

from app.models.orm import Attachment, Chat, Message, User
from app.repositories.keyset import after, decode_cursor, encode_cursor, page_of

# Library is the user's archive. Reference-photo lookup copies (`search`)
# stay on the chat and are never listed.
_LIBRARY_SOURCES = ("upload", "generated")


def _never_sent_upload() -> ColumnElement[bool]:
    """An upload no message ever linked: a composer draft, not a Library item.

    One whose chat was deleted has ``linked_at`` and stays in Library.
    """
    return and_(
        Attachment.source == "upload",
        Attachment.linked_at.is_(None),
        Attachment.message_id.is_(None),
    )


def _referenced_as_avatar() -> ColumnElement[bool]:
    return (
        select(User.id)
        .where(
            User.id == Attachment.user_id,
            User.avatar_url
            == literal("/attachments/") + sql_cast(Attachment.id, String) + literal("/file"),
        )
        .correlate(Attachment)
        .exists()
    )


async def hide_from_gallery(session: AsyncSession, row: Attachment) -> None:
    """The profile-save transaction owns the commit after claiming this photo."""
    row.library_visible = False
    await session.flush()


def _contains(column: Any, query: str) -> Any:
    """Case-insensitive substring match with LIKE wildcards escaped."""
    escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return column.ilike(f"%{escaped}%", escape="\\")


async def create_pending(
    session: AsyncSession,
    *,
    attachment_id: UUID,
    user_id: UUID,
    storage_key: str,
    content_type: str,
    size_bytes: int,
    source: str = "upload",
    original_filename: str | None = None,
    library_visible: bool = True,
    commit: bool = True,
) -> Attachment:
    row = Attachment(
        id=attachment_id,
        user_id=user_id,
        storage_key=storage_key,
        content_type=content_type,
        size_bytes=size_bytes,
        source=source,
        original_filename=original_filename,
        library_visible=library_visible,
    )
    session.add(row)
    if commit:
        await session.commit()
        await session.refresh(row)
    else:
        await session.flush()
    return row


async def insert_verified(
    session: AsyncSession,
    *,
    attachment_id: UUID,
    user_id: UUID,
    storage_key: str,
    content_type: str,
    size_bytes: int,
    source: str,
    original_filename: str | None,
    library_visible: bool,
    message_id: UUID | None,
) -> None:
    """A row for bytes the server stored and checked itself, on ``message_id`` if given.

    No commit: the caller's turn saves it with its messages.
    """
    now = datetime.now(UTC)
    session.add(
        Attachment(
            id=attachment_id,
            user_id=user_id,
            storage_key=storage_key,
            content_type=content_type,
            size_bytes=size_bytes,
            source=source,
            original_filename=original_filename,
            library_visible=library_visible,
            verified_at=now,
            message_id=message_id,
            linked_at=now if message_id is not None else None,
        )
    )
    await session.flush()


async def insert_verified_clone(
    session: AsyncSession,
    *,
    src: Attachment,
    new_id: UUID,
    storage_key: str,
    message_id: UUID | None = None,
) -> Attachment:
    """Copy of an item for a new chat send, on ``message_id`` if given. Hidden from gallery."""
    row = Attachment(
        id=new_id,
        user_id=src.user_id,
        storage_key=storage_key,
        content_type=src.content_type,
        size_bytes=src.size_bytes,
        source=src.source,
        original_filename=src.original_filename,
        verified_at=src.verified_at or datetime.now(UTC),
        library_visible=False,
        message_id=message_id,
        linked_at=datetime.now(UTC) if message_id is not None else None,
    )
    session.add(row)
    await session.flush()
    return row


async def get_by_id(
    session: AsyncSession,
    attachment_id: UUID,
    user_id: UUID,
    *,
    for_update: bool = False,
    owner_consented: bool = False,
) -> Attachment | None:
    statement = select(Attachment).where(
        Attachment.id == attachment_id, Attachment.user_id == user_id
    )
    if owner_consented:  # only while the owner has AI data consent (indexing OCRs and embeds)
        statement = statement.join(User).where(User.ai_data_consent_at.is_not(None))
    if for_update:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    result = await session.execute(statement)
    return result.scalar_one_or_none()


async def get_by_ids(
    session: AsyncSession, attachment_ids: list[UUID], user_id: UUID
) -> list[Attachment]:
    """Batched ``get_by_id``, scoped by ``user_id``, in one round-trip.

    Order is not guaranteed to match ``attachment_ids``; re-order by id if it matters.
    """
    if not attachment_ids:
        return []
    result = await session.execute(
        select(Attachment).where(Attachment.id.in_(attachment_ids), Attachment.user_id == user_id)
    )
    return list(result.scalars().all())


async def link_to_message(
    session: AsyncSession,
    *,
    user_id: UUID,
    attachment_ids: list[UUID],
    message_id: UUID,
    commit: bool = True,
) -> int:
    """Bulk-link a set of attachments to the message just created.

    Only rows owned by ``user_id`` and not already linked are updated, so a
    client can't relink another user's attachment or double-link. Returns the
    number of rows linked. Called from the chat send path right after the user
    message is persisted, so attachments stop being permanent orphans.
    """
    if not attachment_ids:
        return 0
    from sqlalchemy import update as sql_update

    # Profile saves lock the photo before changing the user's reference. Take
    # the same lock, then use a fresh statement snapshot to see that reference.
    await session.execute(
        select(Attachment.id)
        .where(Attachment.id.in_(attachment_ids), Attachment.user_id == user_id)
        .order_by(Attachment.id)
        .with_for_update()
    )
    result = cast(
        CursorResult[Any],
        await session.execute(
            sql_update(Attachment)
            .where(
                Attachment.id.in_(attachment_ids),
                Attachment.user_id == user_id,
                Attachment.message_id.is_(None),
                ~_referenced_as_avatar(),
            )
            .values(
                message_id=message_id,
                linked_at=func.coalesce(Attachment.linked_at, func.now()),
            )
        ),
    )
    if commit:
        await session.commit()
    return result.rowcount or 0


async def list_for_message_ids(session: AsyncSession, message_ids: list[UUID]) -> list[Attachment]:
    if not message_ids:
        return []
    result = await session.execute(select(Attachment).where(Attachment.message_id.in_(message_ids)))
    return list(result.scalars().all())


async def list_for_user(
    session: AsyncSession,
    user_id: UUID,
    *,
    limit: int | None = None,
) -> list[Attachment]:
    """Attachments owned by ``user_id`` (linked and pending) — account delete / export."""
    stmt = (
        select(Attachment)
        .where(Attachment.user_id == user_id)
        .order_by(Attachment.created_at.asc(), Attachment.id.asc())
    )
    if limit is not None:
        stmt = stmt.limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def list_for_gallery(
    session: AsyncSession,
    user_id: UUID,
    *,
    category: str | None = None,
    source: str | None = None,
    q: str | None = None,
    limit: int = 30,
    cursor: str | None = None,
) -> tuple[list[Attachment], str | None]:
    """One page of the gallery, newest first, and the cursor for the next (None: the last).

    ``category`` narrows by content family:

    * ``"images"`` — ``content_type LIKE 'image/%'``
    * ``"files"``  — ``content_type NOT LIKE 'image/%'``
    * ``None``     — uploads and generated files (not lookup photos)

    Optional ``source`` filter narrows to ``'upload'`` or ``'generated'``.
    Reference-photo lookup copies (``source='search'``) are never listed, nor
    uploads no message ever linked (composer drafts, reaped after a day).
    Verified items stay listed after their chat is deleted (``message_id``
    SET NULL); Open chat is omitted when no chat remains. Optional ``q``
    matches original filename, content type, the linked message body, or
    the previous user message in that chat (the draw prompt for generated
    images, which are linked to the assistant ``[Image: …]`` marker rather
    than the user prompt).
    """
    stmt = select(Attachment).where(
        Attachment.user_id == user_id,
        Attachment.verified_at.is_not(None),
        Attachment.library_visible.is_(True),
        Attachment.source.in_(_LIBRARY_SOURCES),
        ~_never_sent_upload(),
    )
    if category == "images":
        stmt = stmt.where(Attachment.content_type.like("image/%"))
    elif category == "files":
        stmt = stmt.where(Attachment.content_type.notlike("image/%"))
    if source in _LIBRARY_SOURCES:
        stmt = stmt.where(Attachment.source == source)
    if q:
        linked = aliased(Message)
        prev_user_content = (
            select(Message.content)
            .where(
                Message.chat_id == linked.chat_id,
                Message.role == "user",
                Message.created_at < linked.created_at,
            )
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(1)
            .correlate(linked)
            .scalar_subquery()
        )
        stmt = stmt.outerjoin(linked, Attachment.message_id == linked.id)
        stmt = stmt.where(
            or_(
                _contains(Attachment.original_filename, q),
                _contains(Attachment.content_type, q),
                _contains(linked.content, q),
                _contains(prev_user_content, q),
            )
        )
    if cursor is not None:
        at, ids = decode_cursor(cursor, ids=1)
        stmt = stmt.where(after((Attachment.created_at, Attachment.id), at, ids))
    stmt = stmt.order_by(Attachment.created_at.desc(), Attachment.id.desc())
    page_size = max(limit, 1)
    rows = list((await session.execute(stmt.limit(page_size + 1))).scalars().all())
    return page_of(rows, page_size, lambda row: encode_cursor(row.created_at, row.id))


async def chat_meta_for_message_ids(
    session: AsyncSession,
    message_ids: list[UUID],
) -> dict[UUID, tuple[UUID, str | None]]:
    """Map message id → (chat id, chat title) for gallery rows."""
    if not message_ids:
        return {}
    result = await session.execute(
        select(Message.id, Message.chat_id, Chat.title)
        .join(Chat, Chat.id == Message.chat_id)
        .where(Message.id.in_(message_ids))
    )
    return {row[0]: (row[1], row[2]) for row in result.all()}


async def list_orphans(
    session: AsyncSession,
    *,
    older_than_hours: int,
    pending_older_than_hours: int | None = None,
    limit: int = 100,
) -> list[Attachment]:
    """Pending uploads, never-sent uploads and hidden send-clones not linked to a message.

    Verified Library items that lost their chat (``message_id`` SET NULL,
    ``linked_at`` set, ``library_visible`` still true) are not orphans — they
    stay until the user deletes them from Library. Hidden copies (Library reuse
    clones, reference-photo lookups) are reaped once that chat is gone, and
    confirmed uploads no message ever linked once they are, after
    ``older_than_hours``. Unverified original uploads (``library_visible``
    true) use ``pending_older_than_hours`` (default same as
    ``older_than_hours``) so a same-day abandoned image can refund its
    daily slot.

    Bounded so one reap cannot load every orphan in the system; the scheduler
    re-runs and drains remaining rows over time.
    """
    now = datetime.now(UTC)
    clone_cutoff = now - timedelta(hours=older_than_hours)
    pending_hours = (
        older_than_hours if pending_older_than_hours is None else pending_older_than_hours
    )
    pending_cutoff = now - timedelta(hours=pending_hours)
    result = await session.execute(
        select(Attachment)
        .where(
            Attachment.message_id.is_(None),
            ~_referenced_as_avatar(),
            or_(
                and_(
                    Attachment.verified_at.is_(None),
                    Attachment.library_visible.is_(True),
                    Attachment.created_at < pending_cutoff,
                ),
                and_(
                    Attachment.library_visible.is_(False),
                    Attachment.created_at < clone_cutoff,
                ),
                and_(_never_sent_upload(), Attachment.created_at < clone_cutoff),
            ),
        )
        .order_by(Attachment.created_at.asc(), Attachment.id.asc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def set_index_coverage(
    session: AsyncSession,
    *,
    attachment_id: UUID,
    user_id: UUID,
    coverage: dict[str, Any],
    commit: bool = True,
) -> None:
    """Persist extract ceilings used for this file's RAG chunks."""
    from sqlalchemy import update as sql_update

    await session.execute(
        sql_update(Attachment)
        .where(Attachment.id == attachment_id, Attachment.user_id == user_id)
        .values(index_coverage_json=json.dumps(coverage))
    )
    if commit:
        await session.commit()


async def mark_verified(session: AsyncSession, attachment_id: UUID, *, commit: bool = True) -> None:
    """Record that stored bytes matched the declared type/size."""
    await mark_verified_many(session, [attachment_id], commit=commit)


async def mark_verified_many(
    session: AsyncSession, attachment_ids: list[UUID], *, commit: bool = True
) -> None:
    """Record, in one statement, that these uploads' bytes matched their type and size."""
    from sqlalchemy import update as sql_update

    if not attachment_ids:
        return
    await session.execute(
        sql_update(Attachment)
        .where(Attachment.id.in_(attachment_ids))
        .values(verified_at=datetime.now(UTC))
    )
    if commit:
        await session.commit()


async def delete_rows(
    session: AsyncSession,
    ids: list[UUID],
    *,
    commit: bool = True,
) -> int:
    """Delete attachment rows; callers remove stored bytes only after committing."""
    if not ids:
        return 0
    from sqlalchemy import delete as sql_delete

    result = cast(
        CursorResult[Any],
        await session.execute(sql_delete(Attachment).where(Attachment.id.in_(ids))),
    )
    if commit:
        await session.commit()
    return result.rowcount or 0


async def delete_unlinked_returning(
    session: AsyncSession, ids: list[UUID], *, orphan_only: bool = False
) -> list[str]:
    """Delete rows still eligible for cleanup; return committed storage keys."""
    if not ids:
        return []
    from sqlalchemy import delete as sql_delete

    # Wait for any in-flight profile save before checking the user's avatar in
    # the DELETE's fresh snapshot. A WHERE subquery alone can see the old user
    # row while waiting on an attachment lock and delete a newly claimed photo.
    await session.execute(
        select(Attachment.id)
        .where(Attachment.id.in_(ids))
        .order_by(Attachment.id)
        .with_for_update()
    )
    statement = sql_delete(Attachment).where(
        Attachment.id.in_(ids),
        Attachment.message_id.is_(None),
        ~_referenced_as_avatar(),
    )
    if orphan_only:
        statement = statement.where(
            or_(
                Attachment.verified_at.is_(None),
                Attachment.library_visible.is_(False),
                _never_sent_upload(),
            )
        )
    result = await session.execute(statement.returning(Attachment.storage_key))
    await session.commit()
    return [row[0] for row in result.all()]


async def delete_all_for_user(session: AsyncSession, user_id: UUID) -> None:
    """Every attachment row of the user, bytes or not; no commit."""
    await session.execute(sa_delete(Attachment).where(Attachment.user_id == user_id))

"""An account delete's attachment rows (``account.lifecycle``, through the service)."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orm import Attachment
from app.repositories.batch_delete import DELETE_BATCH


async def delete_all_for_user(
    session: AsyncSession, user_id: UUID, *, batch: int = DELETE_BATCH
) -> list[str]:
    """Every attachment row of the user, bytes or not, and the storage keys they named;
    no commit.

    In id batches (``repositories/batch_delete``), each returning only its keys: the
    account delete read every full row first just to collect them.
    """
    storage_keys: list[str] = []
    while True:
        batch_ids = select(Attachment.id).where(Attachment.user_id == user_id).limit(batch)
        result = await session.execute(
            delete(Attachment)
            .where(Attachment.id.in_(batch_ids))
            .returning(Attachment.storage_key)
            .execution_options(synchronize_session=False)
        )
        keys = [row[0] for row in result.all()]
        storage_keys.extend(keys)
        if len(keys) < batch:
            return storage_keys

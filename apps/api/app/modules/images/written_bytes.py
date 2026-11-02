"""Storage objects one picture turn wrote, deleted if the turn fails (``generation``)."""

from __future__ import annotations

import logging

from app.gateways.storage_gateway import StorageGateway
from app.modules.attachments import service as attachments_service

logger = logging.getLogger(__name__)


async def _rollback_written_bytes(gateway: StorageGateway, storage_key: str | None) -> None:
    """Delete an object that persisting never named (the reaper sees rows only), or queue it.

    Without this an object written before a failed persist leaked for ever.
    """
    if not storage_key:
        return
    try:
        await gateway.delete_bytes(storage_key)
    except Exception:
        logger.exception("Failed to delete orphaned generated image %s", storage_key)
        await attachments_service.queue_storage_deletes([storage_key])


class WrittenBytes:
    """Storage objects this turn wrote, deleted in write order if the turn fails."""

    def __init__(self, gateway: StorageGateway) -> None:
        self.gateway = gateway
        self.keys: list[str] = []

    async def write(self, storage_key: str, data: bytes) -> None:
        await self.gateway.write_bytes(storage_key, data)
        self.keys.append(storage_key)

    async def delete_all(self) -> None:
        for key in self.keys:
            await _rollback_written_bytes(self.gateway, key)

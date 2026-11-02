"""One turn per client message: a message the server already took never runs twice.

The phone names each message it sends (``client_message_id``) and keeps the name
on every later send of it: over a new socket after the old one went quiet, over
SSE, or from Retry. The first turn to claim the name runs. A later send is told
``duplicate`` (``stream_events.build_duplicate_event``) and the phone follows the
first turn by reloading the chat. A turn that ends with nothing saved gives the
name back, so a resend after a refusal (busy, quota) runs.

A claim holds its key with a token of its own (``core.redis_lock``), so a settle
never frees or extends a hold that is no longer this turn's. It is settled even
when the code that made it is cancelled: an SSE response body is cancelled at
every await once its client disconnects.
"""

from __future__ import annotations

import asyncio
import logging
import secrets
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.background_tasks import create_background_task
from app.core.redis_lock import refresh_lock, release_lock
from app.exceptions import RedisUnavailableError
from app.modules.chat.turn_outcome import TurnOutcome

logger = logging.getLogger(__name__)

# Held this long while the turn runs: a machine that dies mid-turn frees it then.
CLAIM_RUNNING_TTL_SECONDS = 15 * 60
# Kept this long once the turn saved something: a resend or Retry within a day
# of it is recognized.
CLAIM_SAVED_TTL_SECONDS = 24 * 60 * 60


def claim_key(user_id: UUID, chat_id: UUID, client_message_id: UUID) -> str:
    return f"chat:client_msg:{user_id}:{chat_id}:{client_message_id}"


@dataclass(frozen=True)
class ClientMessageClaim:
    """A turn's hold on its message's name; settle it once the turn ended.

    A message sent without a name (older clients, web) has no hold to settle.
    """

    redis: Redis | None = None
    key: str | None = None
    token: str = ""

    async def settle(self, outcome: TurnOutcome) -> None:
        """Keep the name for a day when the turn saved its message or a reply; else free it.

        The Redis call runs to the end even when the caller is cancelled meanwhile.
        """
        if self.redis is None or self.key is None:
            return
        work = create_background_task(
            self._settle(self.redis, self.key, outcome), name="client_message_settle"
        )
        await asyncio.shield(work)

    def settle_after(self, turn: asyncio.Future[Any] | None, outcome: TurnOutcome) -> None:
        """Settle once ``turn`` (the task running the turn) is done, on a task of its own.

        For a caller that may be cancelled before the turn ends or at any await of
        its own cleanup: a disconnected SSE response is.
        """
        if self.key is None:
            return

        async def settle_when_done() -> None:
            if turn is not None:
                await asyncio.wait({turn})
                if not turn.cancelled():
                    turn.exception()  # its owner reports it; this only waited
            await self.settle(outcome)

        create_background_task(settle_when_done(), name="client_message_settle")

    async def _settle(self, redis: Redis, key: str, outcome: TurnOutcome) -> None:
        try:
            if outcome.user_message_saved or outcome.message_id is not None:
                await refresh_lock(redis, key, self.token, CLAIM_SAVED_TTL_SECONDS)
            else:
                await release_lock(redis, key, self.token)
        except Exception:
            # The running TTL frees it; a lost settle only delays a resend's turn.
            logger.warning("Client message claim not settled key=%s", key, exc_info=True)


UNNAMED = ClientMessageClaim()


async def claim_client_message(
    redis: Redis,
    *,
    user_id: UUID,
    chat_id: UUID,
    client_message_id: UUID | None,
) -> ClientMessageClaim | None:
    """This turn's claim on its message; None when an earlier turn already took it.

    A named message fails closed: when Redis errors, ``RedisUnavailableError`` (the
    turn needs Redis for its lock and quota anyway), and whatever the SET stored
    before failing is freed. A caller cancelled while Redis answers frees it too.
    """
    if client_message_id is None:
        return UNNAMED
    key = claim_key(user_id, chat_id, client_message_id)
    claim = ClientMessageClaim(redis, key, secrets.token_hex(16))
    setting = asyncio.ensure_future(
        redis.set(key, claim.token, nx=True, ex=CLAIM_RUNNING_TTL_SECONDS)
    )
    try:
        claimed = await asyncio.shield(setting)
    except asyncio.CancelledError:
        claim.settle_after(setting, TurnOutcome())
        raise
    except (RedisError, OSError) as exc:
        logger.warning("Client message claim failed key=%s", key, exc_info=True)
        claim.settle_after(None, TurnOutcome())
        raise RedisUnavailableError() from exc
    return claim if claimed else None

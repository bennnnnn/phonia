"""Money as the subject registry names it beside the subjects (``services/subjects/registry``).

A money turn is no SymPy solve: its numbers are worked before the prompt (``prepare``) and its
calculator card lands after the reply (``finish``). The service is imported when a turn asks:
it loads the web search and the database models, which a SymPy pool worker that loads the
registry must not.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, TypeGuard

if TYPE_CHECKING:
    from redis.asyncio import Redis

    from app.core.config import Settings
    from app.models.orm import User
    from app.modules.money.service import MoneyTurn


@dataclass(frozen=True)
class MoneyPeer:
    async def prepare(
        self,
        text: str,
        settings: Settings,
        redis: Redis | None,
        *,
        user: User | None,
        location: str | None,
        earlier: Sequence[str | Sequence[str]],
        last_reply: str,
    ) -> MoneyTurn | None:
        from app.modules.money.service import prepare_money_turn

        return await prepare_money_turn(
            text,
            settings,
            redis,
            user=user,
            location=location,
            earlier=earlier,
            last_reply=last_reply,
        )

    async def prepare_standing(
        self,
        text: str,
        settings: Settings,
        redis: Redis | None,
        *,
        user: User | None,
        location: str | None,
        earlier: Sequence[str | Sequence[str]],
        last_reply: str,
    ) -> MoneyTurn | None:
        from app.modules.money.service import prepare_standing_turn

        return await prepare_standing_turn(
            text,
            settings,
            redis,
            user=user,
            location=location,
            earlier=earlier,
            last_reply=last_reply,
        )

    async def finish(self, turn: MoneyTurn, text: str, settings: Settings, *, english: bool) -> str:
        from app.modules.money.service import finish_money_reply

        return await finish_money_reply(turn, text, settings, english=english)

    def owns(self, value: object) -> TypeGuard[MoneyTurn]:
        from app.modules.money.service import MoneyTurn

        return isinstance(value, MoneyTurn)


MONEY_PEER = MoneyPeer()

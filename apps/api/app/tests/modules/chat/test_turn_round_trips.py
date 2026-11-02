"""The database and Redis round trips a chat turn makes before its reply starts.

Each one costs the user time before the first token: about 12 ms per Postgres round
trip from Fly to Neon, and about 1 ms per Redis command. This drives the real chat
paths (auth, rate limits, the turn, the mock model) for a few kinds of message, over
SSE from the request and over the WebSocket from the message frame, and counts until
the first token is sent: SQL statements, pool checkouts, transactions (each also a
BEGIN and a COMMIT or ROLLBACK on the wire), checkout pings (one round trip each;
none for a connection used moments ago, ``core/pool_liveness``) and Redis round
trips (a pipeline is one). That is everything before the model is called, plus the
user message's save, which the first token waits for. The app has one fake Redis,
as production has one Redis: a user-row write publishes its generation where the
next token check reads it (``core/user_cache``).

No timing assertions: counts only. One wait sits inside what is counted: the memory
read waits 0.75 s for its query's embedding, then matches facts by words instead, which
makes round trips of its own. A loaded CI machine ran past it (8 statements, not 7), so
the fixture gives the wait 30 s and fails a turn whose memory read fell back. Each
ceiling is the count when it was set. A change that lowers a count lowers its ceiling here in the same change, so
it stays down. A change that raises one fails this test: make the new round trip
unnecessary, overlap it with one already made, or, when it is worth the time,
raise the ceiling and say why in the change's description.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, MutableMapping
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import httpx
import pytest
from redis.asyncio.client import Pipeline
from sqlalchemy import event
from starlette.websockets import WebSocket

from app.core import access_tokens, pool_liveness, user_cache
from app.core import redis as core_redis
from app.core.background_tasks import drain_background_tasks
from app.core.cache_generation import bump_generation
from app.core.config import get_settings
from app.core.db import SessionLocal, engine
from app.gateways import storage_gateway
from app.models.orm import Memory, TodoItem, User
from app.modules.chat import stream_api, stream_events, ws_api, ws_turn
from app.modules.images import search as image_search
from app.services.quota import tokens as quota_tokens


@dataclass(frozen=True)
class Ceiling:
    sql: int
    checkouts: int
    transactions: int
    redis: int
    pings: int = 0


# Measured on the SSE path with the user, the chat and today's usage already known to
# the process and to Redis, as for every message after the day's first. A new chat
# each, so the history read finds nothing; the user message's save is one of each.
# To update: ``pytest -s`` on this file prints every count.
CEILINGS: dict[str, tuple[str, Ceiling]] = {
    # A greeting reads the chat's recent window like any message: one that skipped it
    # was greeted afresh after a "hi", since its prompt never saw the first one.
    "greeting": ("hi", Ceiling(sql=2, checkouts=2, transactions=2, redis=16)),
    "question": (
        "What's the capital of France?",
        Ceiling(sql=2, checkouts=2, transactions=2, redis=16),
    ),
    "reminder": (
        "Remind me to call mom tomorrow at 5pm",
        Ceiling(sql=7, checkouts=7, transactions=7, redis=21),
    ),
    "memory line": (
        "Remember that I'm allergic to peanuts",
        Ceiling(sql=7, checkouts=7, transactions=7, redis=22),
    ),
    # The lookup finds no usable photo, so the model answers in words.
    "photo lookup": (
        "Show me a photo of the Eiffel Tower",
        Ceiling(sql=3, checkouts=3, transactions=3, redis=21),
    ),
}
# The day's first message: Redis has no usage counter yet, so it is read back from
# the database before the turn reserves its tokens.
FIRST_OF_THE_DAY = ("hi", Ceiling(sql=3, checkouts=3, transactions=3, redis=17))
# Questions on one chat socket, from the message frame to the first token frame (the
# handshake and auth frame are the socket's, paid once). On a machine that has not
# read the user yet, the first turn reads the row; the next finds it in the process's
# cache, current by the generation its frame's token check read; after a change made
# on another machine, the generation moved and the row is read again.
WS_TURNS: dict[str, tuple[str, Ceiling]] = {
    "first on the socket": (
        "What's the capital of France?",
        Ceiling(sql=3, checkouts=3, transactions=3, redis=15),
    ),
    "next": ("And of Spain?", Ceiling(sql=2, checkouts=2, transactions=2, redis=15)),
    "after a change elsewhere": (
        "And of Italy?",
        Ceiling(sql=3, checkouts=3, transactions=3, redis=15),
    ),
}


@dataclass
class _Trips:
    counting: bool = False
    sql: int = 0
    checkouts: int = 0
    transactions: int = 0
    redis: int = 0
    pings: int = 0
    statements: list[str] = field(default_factory=list)

    def start(self) -> None:
        self.sql = self.checkouts = self.transactions = self.redis = self.pings = 0
        self.statements = []
        self.counting = True

    def seen(self) -> Ceiling:
        return Ceiling(self.sql, self.checkouts, self.transactions, self.redis, self.pings)


@dataclass
class _Turns:
    client: httpx.AsyncClient
    token: str
    user_id: UUID
    redis: Any
    trips: _Trips

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    @asynccontextmanager
    async def socket(self) -> AsyncIterator[_Socket]:
        """A chat socket on a new chat, authenticated; closed by the client on exit."""
        created = await self.client.post("/chats", json={}, headers=self.headers)
        chat_id = UUID(created.json()["id"])
        await drain_background_tasks()
        socket = _Socket(self.trips)
        websocket = WebSocket(socket.scope(chat_id), socket.receive, socket.send)
        served = asyncio.create_task(ws_api.chat_websocket(websocket, chat_id))
        try:
            await socket.connect(self.token)
            yield socket
        finally:
            await socket.inbox.put({"type": "websocket.disconnect", "code": 1000})
            async with asyncio.timeout(30):
                await served

    async def first_token_trips(self, content: str) -> Ceiling:
        """Send ``content`` in a new chat; the round trips until its first token."""
        created = await self.client.post("/chats", json={}, headers=self.headers)
        chat_id = created.json()["id"]
        # The previous turn's save and jobs run on their own tasks: finish them first.
        await drain_background_tasks()
        self.trips.start()
        response = await self.client.post(
            f"/chats/{chat_id}/messages/stream", json={"content": content}, headers=self.headers
        )
        self.trips.counting = False
        assert response.status_code == 200
        assert '"type":"token"' in response.text, response.text[-400:]
        return self.trips.seen()


@dataclass
class _Socket:
    """The app's chat WebSocket, served in this event loop: httpx speaks no WebSocket,
    and a TestClient would run the app on a loop of its own."""

    trips: _Trips
    inbox: asyncio.Queue[dict[str, Any]] = field(default_factory=asyncio.Queue)
    outbox: asyncio.Queue[MutableMapping[str, Any]] = field(default_factory=asyncio.Queue)

    @staticmethod
    def scope(chat_id: UUID) -> dict[str, Any]:
        return {
            "type": "websocket",
            "path": f"/ws/chats/{chat_id}",
            "headers": [(b"host", b"test")],
            "query_string": b"",
            "client": ("127.0.0.1", 50_000),
            "server": ("test", 80),
            "subprotocols": [],
        }

    async def receive(self) -> dict[str, Any]:
        """What the client sent (ASGI); a counted frame starts the count as it is read."""
        message = await self.inbox.get()
        if message.pop("count", False):
            self.trips.start()
        return message

    async def send(self, message: MutableMapping[str, Any]) -> None:
        """What the app sent (ASGI)."""
        await self.outbox.put(message)

    async def connect(self, token: str) -> None:
        await self.inbox.put({"type": "websocket.connect"})
        await self.inbox.put({"type": "websocket.receive", "text": json.dumps({"token": token})})
        async with asyncio.timeout(30):
            accepted = await self.outbox.get()
        assert accepted["type"] == "websocket.accept", accepted

    async def _until(self, kind: str) -> None:
        async with asyncio.timeout(30):
            while True:
                message = await self.outbox.get()
                assert message["type"] == "websocket.send", message
                frame = json.loads(message["text"])
                assert frame.get("type") != "error", frame
                if frame.get("type") == kind:
                    return

    async def first_token_trips(self, content: str) -> tuple[Ceiling, list[str]]:
        """Send ``content`` as a message frame; the round trips until its first token
        frame, and the statements among them. Returns once the turn is saved."""
        frame = json.dumps({"type": "message", "content": content})
        await self.inbox.put({"type": "websocket.receive", "text": frame, "count": True})
        await self._until("token")
        seen, statements = self.trips.seen(), list(self.trips.statements)
        await self._until("done")
        await drain_background_tasks()
        return seen, statements


async def _seed_user() -> UUID:
    """A free account with a remembered fact and an open to-do, as a turn would read."""
    async with SessionLocal() as session:
        user = User(email=f"{uuid4()}@example.com", name="Round Trips", google_sub=str(uuid4()))
        session.add(user)
        await session.flush()
        session.add_all(
            [
                Memory(
                    user_id=user.id,
                    type="project",
                    topic="recent-work",
                    text="User is building a chat app called Recall",
                    status="active",
                ),
                TodoItem(user_id=user.id, content="buy milk", topic="Groceries", sort_order=0),
            ]
        )
        await session.commit()
        return user.id


# Set while a fallback that only fakeredis runs stands in for a Lua script.
_IN_PLACE_OF_LUA: ContextVar[bool] = ContextVar("in_place_of_lua", default=False)


def _count(trips: _Trips, field: str) -> Any:
    def record(*_args: Any, **_kwargs: Any) -> None:
        if trips.counting and not _IN_PLACE_OF_LUA.get():
            setattr(trips, field, getattr(trips, field) + 1)

    return record


def _count_embed_fallbacks(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Each read that waited for its query's embedding and got none. Mock mode embeds every
    query, so here only a wait that ran out returns none, and that read matches by words."""
    from app.gateways import embedding_gateway

    fallbacks: list[str] = []
    embed = embedding_gateway.get_or_embed_query

    async def counted(*args: Any, **kwargs: Any) -> list[float] | None:
        vector = await embed(*args, **kwargs)
        query = args[2] if len(args) > 2 else kwargs.get("query", "")
        if vector is None and str(query).strip():
            fallbacks.append("query embedding missing")
        return vector

    monkeypatch.setattr(embedding_gateway, "get_or_embed_query", counted)
    return fallbacks


@pytest.fixture
async def turns(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, user_generation_redis: Any
) -> AsyncIterator[_Turns]:
    from app.main import create_app

    monkeypatch.setenv("MOCK_LLM_ENABLED", "true")
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    monkeypatch.setenv("STORAGE_LOCAL_PATH", str(tmp_path))
    # Production runs with the global spend cap on; a turn reads it.
    monkeypatch.setenv("DAILY_GLOBAL_SPEND_USD", "1000")
    # The memory read's wait for its query embedding: past it the read matches by words and
    # counts more round trips than the turn makes (see the module docstring).
    monkeypatch.setenv("MEMORY_QUERY_EMBED_TIMEOUT_SECONDS", "30")
    get_settings.cache_clear()
    storage_gateway._gateway_cache = None
    settings = get_settings()
    fallbacks = _count_embed_fallbacks(monkeypatch)
    # The client user-row writes publish to (conftest) is the app's Redis too.
    fake = user_generation_redis
    core_redis.get_redis_client.cache_clear()
    core_redis.get_jobs_redis_client.cache_clear()
    monkeypatch.setattr(core_redis, "_connect", lambda *_a, **_k: fake)
    assert user_cache.get_redis_client() is fake  # type: ignore[attr-defined]
    await engine.dispose(close=False)

    trips = _Trips()
    count_sql = _count(trips, "sql")

    def sql(_conn: Any, _cursor: Any, statement: str, *_args: Any) -> None:
        if trips.counting and not _IN_PLACE_OF_LUA.get():
            trips.statements.append(" ".join(statement.split())[:80])
        count_sql()

    listeners = [
        ("before_cursor_execute", sql),
        ("checkout", _count(trips, "checkouts")),
        ("begin", _count(trips, "transactions")),
    ]
    for name, listener in listeners:
        event.listen(engine.sync_engine, name, listener)
    ping = pool_liveness.ping

    def counted_ping(driver_connection: Any) -> None:
        _count(trips, "pings")()
        ping(driver_connection)

    monkeypatch.setattr(pool_liveness, "ping", counted_ping)
    # Every fake Redis counts: in production they are all the one Redis.
    fake_redis_class = type(fake)
    send = fake_redis_class.execute_command
    run_pipeline = Pipeline.execute

    async def counted_send(self: Any, *args: Any, **kwargs: Any) -> Any:
        _count(trips, "redis")()
        return await send(self, *args, **kwargs)

    async def counted_pipeline(self: Any, *args: Any, **kwargs: Any) -> Any:
        _count(trips, "redis")()
        return await run_pipeline(self, *args, **kwargs)

    monkeypatch.setattr(fake_redis_class, "execute_command", counted_send)
    monkeypatch.setattr(Pipeline, "execute", counted_pipeline)
    # fakeredis has no Lua, so the token reserve's script fails there and a WATCH
    # fallback takes the tokens. Production's Redis runs the script in the one EVAL
    # already counted: the fallback's commands are not.
    reserve_watched = quota_tokens._reserve_up_to_watched

    async def reserve_in_place_of_lua(*args: Any, **kwargs: Any) -> int:
        token = _IN_PLACE_OF_LUA.set(True)
        try:
            return await reserve_watched(*args, **kwargs)
        finally:
            _IN_PLACE_OF_LUA.reset(token)

    monkeypatch.setattr(quota_tokens, "_reserve_up_to_watched", reserve_in_place_of_lua)
    build_token_event = stream_events.build_token_event

    def first_token_stops_the_count(content: str) -> dict[str, Any]:
        trips.counting = False
        return build_token_event(content)

    monkeypatch.setattr(stream_api, "build_token_event", first_token_stops_the_count)
    monkeypatch.setattr(ws_turn, "build_token_event", first_token_stops_the_count)
    # No photo is fetched from the internet: a lookup finds none it can use.
    monkeypatch.setattr(image_search, "_fetch_candidates", AsyncMock(return_value=[]))

    user_id = await _seed_user()
    token = access_tokens.create_access_token(user_id, settings, session_id=str(uuid4()))
    app = create_app()
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            yield _Turns(client, token, user_id, fake, trips)
        assert not fallbacks, "a read's query embedding ran out; it matched facts by words"
    finally:
        await drain_background_tasks()
        for name, listener in listeners:
            event.remove(engine.sync_engine, name, listener)
        from app.modules.account import lifecycle

        async with SessionLocal() as session:
            await lifecycle.erase_user_rows(session, user_id)
        user_cache.forget_user(user_id)
        await engine.dispose(close=False)
        await fake.aclose()
        core_redis.get_redis_client.cache_clear()
        get_settings.cache_clear()
        storage_gateway._gateway_cache = None


def _within(seen: Ceiling, ceiling: Ceiling) -> list[str]:
    return [
        f"{name}: {getattr(seen, name)} > {getattr(ceiling, name)}"
        for name in ("sql", "checkouts", "transactions", "redis", "pings")
        if getattr(seen, name) > getattr(ceiling, name)
    ]


def _over(
    seen: dict[str, Ceiling], ceilings: dict[str, tuple[str, Ceiling]]
) -> dict[str, list[str]]:
    return {kind: _within(counts, ceilings[kind][1]) for kind, counts in seen.items()}


async def test_turn_round_trips_before_the_first_token_stay_under_their_ceilings(
    turns: _Turns,
) -> None:
    # Today's usage counter now exists, as for every message after the day's first.
    await turns.first_token_trips("hello")
    seen = {kind: await turns.first_token_trips(content) for kind, (content, _) in CEILINGS.items()}
    print("round trips before the first token:", seen)

    over = {kind: problems for kind, problems in _over(seen, CEILINGS).items() if problems}
    assert not over, over


async def test_the_days_first_turn_reads_back_usage_under_its_ceiling(turns: _Turns) -> None:
    content, ceiling = FIRST_OF_THE_DAY
    for key in await turns.redis.keys("usage:*"):
        await turns.redis.delete(key)

    seen = await turns.first_token_trips(content)
    print("round trips before the day's first token:", seen)

    assert not _within(seen, ceiling), seen


async def test_websocket_turns_stay_under_their_ceilings_and_reuse_the_user_until_it_changes(
    turns: _Turns,
) -> None:
    # Today's usage counter now exists, as for every message after the day's first.
    await turns.first_token_trips("hello")
    seen: dict[str, tuple[Ceiling, list[str]]] = {}

    async with turns.socket() as socket:
        # The socket landed on a machine that has not read this user yet.
        user_cache.forget_user(turns.user_id)
        for step, (content, _) in WS_TURNS.items():
            if step == "after a change elsewhere":
                # What another machine's settings change does to the one Redis.
                await bump_generation(turns.redis, user_cache.generation_key(turns.user_id))
            seen[step] = await socket.first_token_trips(content)
    print("round trips before each socket turn's first token:", seen)

    over = {step: _within(counts, WS_TURNS[step][1]) for step, (counts, _) in seen.items()}
    assert not any(over.values()), over
    user_reads = {step: len(_user_reads(statements)) for step, (_, statements) in seen.items()}
    assert user_reads == {"first on the socket": 1, "next": 0, "after a change elsewhere": 1}


def _user_reads(statements: list[str]) -> list[str]:
    return [statement for statement in statements if statement.startswith("SELECT users.")]

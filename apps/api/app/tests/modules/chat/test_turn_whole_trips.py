"""Everything one chat turn sends out of the process, from the request to its last job.

``test_turn_round_trips`` holds what a turn does before its first token. This drives a
whole turn of each common kind over SSE (the request, the reply's finalize and save,
its follow-up questions), then runs the jobs it queued as the worker would, and counts
what each part sent (``turn_ledger``): model calls, embedding requests, web and photo
searches, SQL statements, pool checkouts, transactions and Redis round trips (a
pipeline or a Lua script is one). The model, the embedder and the searches are fakes
at their provider seams, with mock mode off, so every call production makes is seen.

No timing assertions: counts only. The memory read's wait for its query embedding is the
one wait inside what is counted, so the harness gives it 30 s (past it the read matches by
words and makes round trips of its own). Each ceiling is the count when it was set. A change that lowers a count lowers its ceiling in the same change, so it stays
down. A change that raises one fails here: make the new call unnecessary, or raise
the ceiling and say why in the change's description. ``pytest -s`` prints each
part's calls, statements and Redis commands with the code that sent them.
"""

from __future__ import annotations

import itertools
import json
import re
import sys
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import FrameType
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from redis.asyncio.client import Pipeline
from redis.exceptions import ResponseError
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import access_tokens, user_cache
from app.core import redis as core_redis
from app.core.background_tasks import drain_background_tasks
from app.core.config import get_settings
from app.core.db import SessionLocal, engine
from app.core.jobs import JOBS_STREAM
from app.core.jobs.worker import _process_one_entry
from app.gateways import (
    embedding_gateway,
    image_gateway,
    image_search_gateway,
    litellm_gateway,
    storage_gateway,
    web_search_gateway,
)
from app.gateways.mcp import registry as mcp_registry
from app.gateways.mock_llm import mock_image_bytes
from app.models.orm import Attachment, Chat, Memory, Message, TodoItem, User
from app.services.mcp import setup_mcp_adapters
from app.services.quota import tokens as quota_tokens
from app.tests.modules.chat.turn_ledger import (
    APP_DIR,
    Counts,
    Ledger,
    callers,
    fake_acompletion,
    fake_aembedding,
)


@dataclass(frozen=True)
class Ceiling:
    """One kind of turn: what its request may send, what its jobs may, and which jobs."""

    turn: Counts
    jobs: Counts
    queued: tuple[str, ...]


# A chat's first reply is titled; compress runs only when the chat has messages out of
# its window, or when the turn cannot tell (a picture, a regenerate).
_FIRST = ("memory", "topic", "message_index")
_NEXT = ("memory", "message_index")
_FIRST_UNTOLD = ("memory", "topic", "compress", "message_index")
_NEXT_FOLDS = ("memory", "compress", "message_index")
# Measured with the user, today's usage and the chat already known to Redis, as for
# every message after the day's first. To update: ``pytest -s`` prints every count.
# A turn with follow-up questions reads what its chat already showed (one GET,
# ``related_prompts.shown_in_chat``) and writes both records in one pipeline.
CEILINGS: dict[str, Ceiling] = {
    "greeting": Ceiling(
        Counts(sql=5, checkouts=3, transactions=3, redis=21, models=1),
        Counts(sql=10, checkouts=4, transactions=4, redis=18, embeds=1),
        _FIRST,
    ),
    "question": Ceiling(
        Counts(sql=5, checkouts=3, transactions=3, redis=25, models=2),
        Counts(sql=12, checkouts=4, transactions=4, redis=21, models=2, embeds=1),
        _FIRST,
    ),
    "follow-up, short chat": Ceiling(
        Counts(sql=5, checkouts=3, transactions=3, redis=24, models=2),
        Counts(sql=11, checkouts=3, transactions=3, redis=16, models=1, embeds=1),
        _NEXT,
    ),
    "follow-up, long chat": Ceiling(
        Counts(sql=8, checkouts=5, transactions=5, redis=27, models=2),
        Counts(sql=17, checkouts=5, transactions=5, redis=23, models=2, embeds=1),
        _NEXT_FOLDS,
    ),
    "maths": Ceiling(
        Counts(sql=5, checkouts=3, transactions=3, redis=22, models=2),
        Counts(sql=12, checkouts=4, transactions=4, redis=21, models=2, embeds=1),
        _FIRST,
    ),
    # "Who won …?" is about now: a dated news search runs beside the general one, with
    # its own cache read, lock and write. A searched reply also gets one claim check (a
    # model call and its spend write) before it saves, so a claim no source made is cut.
    "web search": Ceiling(
        Counts(sql=5, checkouts=3, transactions=3, redis=35, models=3, searches=2),
        Counts(sql=12, checkouts=4, transactions=4, redis=21, models=2, embeds=1),
        _FIRST,
    ),
    "reminder": Ceiling(
        Counts(sql=10, checkouts=8, transactions=8, redis=31, models=1, embeds=1),
        Counts(sql=12, checkouts=4, transactions=4, redis=21, models=2, embeds=1),
        _FIRST,
    ),
    "photo lookup": Ceiling(
        Counts(sql=6, checkouts=4, transactions=4, redis=28, models=2, searches=1),
        Counts(sql=12, checkouts=4, transactions=4, redis=21, models=2, embeds=1),
        _FIRST,
    ),
    "picture": Ceiling(
        Counts(sql=8, checkouts=3, transactions=3, redis=16, models=1),
        Counts(sql=15, checkouts=5, transactions=5, redis=27, models=2, embeds=1),
        _FIRST_UNTOLD,
    ),
    "attachment question": Ceiling(
        Counts(sql=13, checkouts=8, transactions=8, redis=36, models=2, embeds=1),
        Counts(sql=13, checkouts=5, transactions=5, redis=25, models=2, embeds=1),
        ("attachment_index", *_FIRST),
    ),
    "regenerate": Ceiling(
        Counts(sql=10, checkouts=3, transactions=3, redis=28, models=2),
        Counts(sql=14, checkouts=4, transactions=4, redis=21, models=1, embeds=1),
        _NEXT_FOLDS,
    ),
    "clarify picks": Ceiling(
        Counts(sql=9, checkouts=7, transactions=7, redis=33, models=2, embeds=1),
        Counts(sql=11, checkouts=3, transactions=3, redis=16, models=1, embeds=1),
        _NEXT,
    ),
}
# The lists the app opens, each read in a fixed number of statements however many rows
# the user has (no read per row).
LIST_CEILINGS: dict[str, Counts] = {
    "/chats": Counts(sql=3, checkouts=2, transactions=2, redis=2),
    "/chats/{chat}/messages": Counts(sql=2, checkouts=2, transactions=2, redis=4),
    "/memories": Counts(sql=2, checkouts=1, transactions=1, redis=5),
    "/memories/documents": Counts(sql=3, checkouts=1, transactions=1, redis=4),
    "/todos/page": Counts(sql=1, checkouts=1, transactions=1, redis=2),
    "/attachments": Counts(sql=2, checkouts=1, transactions=1, redis=2),
    "/search?q=Paris": Counts(sql=1, checkouts=1, transactions=1, redis=2),
}

# A reply long enough to get follow-up questions (``related_questions``).
_LONG = (
    " It sits on the Seine in the north of the country and has been the seat of"
    " government for centuries. About two million people live in the city itself,"
    " and more than twelve million in the wider region. It is known for the Louvre,"
    " the Eiffel Tower and its cafes."
)
# What the follow-up call answers: each line names a word of ``_LONG``, so a turn keeps
# three. Each call answers five the run has not answered yet, so a chat's later replies
# get questions it has not shown (``follow_up_repeats``), as a model told what was shown
# would write.
_ANCHORS = ("Louvre", "Seine", "cafes", "government", "region", "centuries", "people", "north")
_TOPICS = ("history", "music", "trade", "schools", "parks", "bridges", "streets", "food")
_FOLLOW_UPS = [
    f"How did the {anchor} shape its {topic}?" for topic in _TOPICS for anchor in _ANCHORS
]


def _follow_up_answers() -> Callable[[], dict[str, list[str]]]:
    calls = itertools.count()

    def answer() -> dict[str, list[str]]:
        start = 5 * next(calls)
        return {"questions": [_FOLLOW_UPS[(start + i) % len(_FOLLOW_UPS)] for i in range(5)]}

    return answer


_PICKS_CARD = {
    "questions": [
        {
            "id": "priority",
            "label": "Main priority",
            "question": "What matters most to you?",
            "options": ["💰 Making money", "🌿 Quality of life", "🛡️ Safety"],
            "values": ["Making money", "Quality of life", "Safety"],
        }
    ],
    "request": "Recommend the best country for me.",
    "closing": "Compare the strongest options with practical pros and cons.",
    "submit": "Find my best country",
}


@dataclass
class _Seen:
    turn: Ledger
    jobs: dict[str, Ledger] = field(default_factory=dict)

    @property
    def jobs_total(self) -> Counts:
        return sum((job.counts() for job in self.jobs.values()), Counts())


@dataclass
class _Harness:
    client: httpx.AsyncClient
    token: str
    user_id: UUID
    redis: Any
    ledger: Ledger
    storage: Path

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    async def new_chat(self) -> UUID:
        created = await self.client.post("/chats", json={}, headers=self.headers)
        return UUID(created.json()["id"])

    async def turn(
        self, chat_id: UUID, content: str | None, attachment_ids: list[str] | None = None
    ) -> _Seen:
        """Send ``content`` (None regenerates the last reply), then run its jobs."""
        await self.run_jobs(count=False)
        self.ledger.start()
        if content is None:
            url, body = f"/chats/{chat_id}/regenerate/stream", {}
        else:
            url = f"/chats/{chat_id}/messages/stream"
            body = {"content": content, "attachment_ids": attachment_ids or []}
        response = await self.client.post(url, json=body, headers=self.headers)
        # The reply's save and the jobs' enqueue run on tasks of their own.
        await drain_background_tasks()
        seen = _Seen(self.ledger.stop())
        assert response.status_code == 200, response.text
        assert '"type":"done"' in response.text, response.text[-400:]
        seen.jobs = await self.run_jobs()
        return seen

    async def run_jobs(self, *, count: bool = True) -> dict[str, Ledger]:
        """Run each queued job once, as the worker does; each job's own count."""
        await drain_background_tasks()
        settings = get_settings()
        seen: dict[str, Ledger] = {}
        entries = await self.redis.xrange(JOBS_STREAM)
        await self.redis.delete(JOBS_STREAM)
        for entry_id, fields in entries:
            if count:
                self.ledger.start()
            await _process_one_entry(self.redis, settings, entry_id, fields)
            await drain_background_tasks()
            if count:
                # A second job of a type is its own entry: "topic", then "topic 2".
                name = fields["type"]
                seen[name if name not in seen else f"{name} {len(seen)}"] = self.ledger.stop()
        return seen


def _count_sql(ledger: Ledger, monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, Any]]:
    """Count statements, checkouts and transactions; each statement with the code that
    asked for it (the session call before it: the statement runs in a greenlet)."""
    asked = {"by": "?"}

    def attributed(method: Any) -> Any:
        async def run(self: Any, *args: Any, **kwargs: Any) -> Any:
            if ledger.counting:
                asked["by"] = callers(("gateways", "core", "repositories", "repository"), 2)
            return await method(self, *args, **kwargs)

        return run

    for name in ("execute", "scalar", "scalars", "get", "flush", "commit"):
        monkeypatch.setattr(AsyncSession, name, attributed(getattr(AsyncSession, name)))

    def statement(_conn: Any, _cursor: Any, text: str, *_args: Any) -> None:
        if ledger.counting:
            flat = re.sub(r"^SELECT .*? FROM ", "SELECT … FROM ", " ".join(text.split()))
            flat = re.sub(r"^INSERT INTO (\S+) \(.*?\) VALUES.*", r"INSERT INTO \1", flat)
            ledger.sql.append(f"{flat[:160]}  <- {asked['by']}")

    def counter(name: str) -> Any:
        def count(*_args: Any) -> None:
            if ledger.counting:
                setattr(ledger, name, getattr(ledger, name) + 1)

        return count

    listeners = [
        ("before_cursor_execute", statement),
        ("checkout", counter("checkouts")),
        ("begin", counter("transactions")),
    ]
    for name, listener in listeners:
        event.listen(engine.sync_engine, name, listener)
    return listeners


def _count_redis(ledger: Ledger, fake: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """Every fake Redis counts: in production they are the one Redis.

    fakeredis runs no Lua. A script it refuses has a fallback of plain commands in its
    caller; production's Redis ran the script in the one EVAL counted, so what that
    caller sends next for it is not counted.
    """
    send = type(fake).execute_command
    run_pipeline = Pipeline.execute
    lua_callers: list[Any] = []
    in_place_of_lua = {"on": False}

    def uncounted() -> bool:
        if in_place_of_lua["on"]:
            return True
        frame: FrameType | None = sys._getframe(2)
        while frame is not None:
            if any(frame is caller for caller in lua_callers):
                return True
            frame = frame.f_back
        return False

    async def counted_send(self: Any, *args: Any, **kwargs: Any) -> Any:
        command = str(args[0]).upper()
        if ledger.counting and not uncounted():
            key = "" if command == "EVAL" or len(args) < 2 else str(args[1]).split(":")[0]
            ledger.redis.append(f"{command} {key}  <- {callers(('gateways', 'core'))}")
        try:
            return await send(self, *args, **kwargs)
        except ResponseError:
            if command == "EVAL":
                frame: FrameType | None = sys._getframe(1)
                while frame is not None and not frame.f_code.co_filename.startswith(str(APP_DIR)):
                    frame = frame.f_back
                lua_callers.append(frame)
            raise

    async def counted_pipeline(self: Any, *args: Any, **kwargs: Any) -> Any:
        if ledger.counting and not uncounted():
            names = ",".join(str(command[0][0]) for command in self.command_stack)
            ledger.redis.append(f"PIPELINE {names}  <- {callers(('gateways', 'core'))}")
        return await run_pipeline(self, *args, **kwargs)

    monkeypatch.setattr(type(fake), "execute_command", counted_send)
    monkeypatch.setattr(Pipeline, "execute", counted_pipeline)
    # The token reserve's script falls back to a WATCH transaction under fakeredis.
    reserve_watched = quota_tokens._reserve_up_to_watched

    async def reserve_in_place_of_lua(*args: Any, **kwargs: Any) -> int:
        in_place_of_lua["on"] = True
        try:
            return await reserve_watched(*args, **kwargs)
        finally:
            in_place_of_lua["on"] = False

    monkeypatch.setattr(quota_tokens, "_reserve_up_to_watched", reserve_in_place_of_lua)


def _fake_providers(ledger: Ledger, monkeypatch: pytest.MonkeyPatch) -> None:
    """The model, the embedder, the picture model and the searches: counted fakes."""
    monkeypatch.setattr(litellm_gateway, "acompletion", fake_acompletion(ledger))
    monkeypatch.setattr(embedding_gateway, "aembedding", fake_aembedding(ledger))

    async def web(_settings: Any, query: str, max_results: int, **_kwargs: Any) -> list[Any]:
        if ledger.counting:
            ledger.searches.append(f"web <- {callers()}")
        hit = web_search_gateway.WebSearchHit(
            title="Result", url="https://example.com/result", snippet=f"About {query}."
        )
        return [hit][:max_results]

    async def photos(_settings: Any, _query: str, **_kwargs: Any) -> list[Any]:
        if ledger.counting:
            ledger.searches.append(f"photo <- {callers()}")
        return []

    async def picture(_settings: Any, **_kwargs: Any) -> tuple[bytes, str]:
        if ledger.counting:
            ledger.models.append(f"picture <- {callers()}")
        return mock_image_bytes(), "image/png"

    monkeypatch.setattr(web_search_gateway, "_search_tavily", web)
    monkeypatch.setattr(image_search_gateway, "search_images", photos)
    monkeypatch.setattr(image_gateway, "generate_via_openrouter", picture)


async def _seed_user() -> UUID:
    """A free account with a remembered fact and an open to-do, as a turn would read."""
    async with SessionLocal() as session:
        user = User(email=f"{uuid4()}@example.com", name="Whole Turns", google_sub=str(uuid4()))
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


@pytest.fixture
async def harness(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, user_generation_redis: Any
) -> AsyncIterator[_Harness]:
    from app.background import handlers as job_handlers
    from app.main import create_app
    from app.modules.account import lifecycle

    # A provider key turns mock mode off: each call goes to the counted fakes.
    monkeypatch.setenv("MOCK_LLM_ENABLED", "false")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("TAVILY_API_KEY", "test-key")
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    monkeypatch.setenv("STORAGE_LOCAL_PATH", str(tmp_path))
    # Production runs with the global spend cap on; a turn and each job read it.
    monkeypatch.setenv("DAILY_GLOBAL_SPEND_USD", "1000")
    # The memory read's wait for its query embedding (0.75 s in production): past it the
    # read matches facts by words, with round trips of its own, as a loaded CI run showed.
    monkeypatch.setenv("MEMORY_QUERY_EMBED_TIMEOUT_SECONDS", "30")
    get_settings.cache_clear()
    storage_gateway._gateway_cache = None
    settings = get_settings()
    fake = user_generation_redis
    core_redis.get_redis_client.cache_clear()
    core_redis.get_jobs_redis_client.cache_clear()
    monkeypatch.setattr(core_redis, "_connect", lambda *_a, **_k: fake)
    await engine.dispose(close=False)

    ledger = Ledger(structured={"RelatedQuestions": _follow_up_answers()})
    listeners = _count_sql(ledger, monkeypatch)
    _count_redis(ledger, fake, monkeypatch)
    _fake_providers(ledger, monkeypatch)
    # What the app's startup does: the worker's job types, the model's tools.
    job_handlers.register_all()
    setup_mcp_adapters(settings)

    user_id = await _seed_user()
    token = access_tokens.create_access_token(user_id, settings, session_id=str(uuid4()))
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=create_app()), base_url="http://test"
        ) as client:
            yield _Harness(client, token, user_id, fake, ledger, tmp_path)
    finally:
        await drain_background_tasks()
        mcp_registry.clear()
        for name, listener in listeners:
            event.remove(engine.sync_engine, name, listener)
        async with SessionLocal() as session:
            await lifecycle.erase_user_rows(session, user_id)
        user_cache.forget_user(user_id)
        await engine.dispose(close=False)
        core_redis.get_redis_client.cache_clear()
        get_settings.cache_clear()
        storage_gateway._gateway_cache = None


async def _seed_messages(user_id: UUID, chat_id: UUID, lines: list[tuple[str, str]]) -> None:
    start = datetime.now(UTC) - timedelta(hours=2)
    async with SessionLocal() as session:
        for index, (role, content) in enumerate(lines):
            model = "free-chat" if role == "assistant" else None
            session.add(
                Message(
                    chat_id=chat_id,
                    user_id=user_id,
                    role=role,
                    content=content,
                    model=model,
                    created_at=start + timedelta(minutes=index),
                )
            )
        await session.commit()


async def _upload_text(harness: _Harness, text: str) -> str:
    body = text.encode()
    presigned = await harness.client.post(
        "/attachments/presign",
        json={"content_type": "text/plain", "size_bytes": len(body), "filename": "plan.txt"},
        headers=harness.headers,
    )
    attachment_id = str(presigned.json()["attachment_id"])
    put = await harness.client.put(
        f"/attachments/{attachment_id}/upload",
        content=body,
        headers={**harness.headers, "Content-Type": "text/plain"},
    )
    assert put.status_code == 204, put.text
    confirmed = await harness.client.post(
        f"/attachments/{attachment_id}/confirm", headers=harness.headers
    )
    assert confirmed.status_code == 204, confirmed.text
    return attachment_id


async def _turns(harness: _Harness) -> dict[str, _Seen]:
    """One turn of each kind, each on the chat it needs."""
    ledger = harness.ledger
    seen: dict[str, _Seen] = {}

    async def turn(
        kind: str, content: str | None, reply: str, chat_id: UUID | None = None, **extra: Any
    ) -> UUID:
        ledger.reply = reply
        ledger.tool_call = extra.pop("tool_call", None)
        chat_id = chat_id or await harness.new_chat()
        seen[kind] = await harness.turn(chat_id, content, **extra)
        return chat_id

    paris = "The capital of France is **Paris**." + _LONG
    await turn("greeting", "hi", "Hi! What can I help you with today?")
    question = await turn("question", "What's the capital of France?", paris)
    population = "About 2.1 million people live in Paris proper." + _LONG
    await turn("follow-up, short chat", "And what's its population?", population, question)
    long_chat = await harness.new_chat()
    await _seed_messages(
        harness.user_id,
        long_chat,
        [
            line
            for i in range(20)
            for line in (
                ("user", f"Tell me fact number {i} about French cities."),
                ("assistant", f"Fact {i}: Lyon was founded as Lugdunum in 43 BC." + _LONG),
            )
        ],
    )
    oldest = "Marseille is the oldest, founded by Greek settlers around 600 BC." + _LONG
    await turn("follow-up, long chat", "Which of those cities is the oldest?", oldest, long_chat)
    await turn("maths", "Solve 2x + 3 = 11", "Subtract 3: 2x = 8. Divide by 2: **x = 4**.")
    await turn(
        "web search",
        "Who won the most recent Champions League final?",
        "Real Madrid won the most recent final." + _LONG,
        tool_call=("web_search", {"query": "Champions League final winner"}),
    )
    await turn(
        "reminder",
        "Remind me to call mom tomorrow at 5pm",
        "Sure, I'll remind you to call mom tomorrow at 5 pm.",
    )
    tower = "The Eiffel Tower is a wrought-iron lattice tower in Paris." + _LONG
    await turn("photo lookup", "Show me a photo of the Eiffel Tower", tower)
    await turn("picture", "Draw a picture of a cat wearing a hat", "Here is your cat.")
    plan = "Budget plan 2026. Rent 1200. Food 400. Transport 150. Savings 500. " * 20
    attachment = await _upload_text(harness, plan)
    await harness.run_jobs(count=False)
    savings = "The plan sets aside 500 a month for savings." + _LONG
    await turn(
        "attachment question",
        "What does this plan say about savings?",
        savings,
        attachment_ids=[attachment],
    )
    await turn("regenerate", None, paris, question)
    clarify_chat = await harness.new_chat()
    card = f"**Let me ask you one thing.**\n\n```clarify\n{json.dumps(_PICKS_CARD)}\n```"
    await _seed_messages(
        harness.user_id,
        clarify_chat,
        [("user", "What is the best country to live in?"), ("assistant", card)],
    )
    await turn(
        "clarify picks",
        "Recommend the best country for me. Main priority: Quality of life. "
        "Compare the strongest options with practical pros and cons.",
        "**Switzerland** fits a quality-of-life priority best." + _LONG,
        clarify_chat,
    )
    return seen


# Every kind of turn end to end, then its jobs: the suite's longest test, and on a CI worker
# sharing the machine with three others it ran past the one-minute hang limit. It counts and
# never times, so a longer limit changes no result.
@pytest.mark.timeout(240)
async def test_each_kind_of_turn_stays_under_its_ceilings_to_its_last_job(
    harness: _Harness,
) -> None:
    # Today's usage counter now exists, as for every message after the day's first.
    await harness.turn(await harness.new_chat(), "hello")
    seen = await _turns(harness)
    for kind, part in seen.items():
        print(f"=== {kind}: the request\n{part.turn.detail()}")
        for name, job in part.jobs.items():
            print(f"--- {kind}: job {name}\n{job.detail()}")
    print({kind: (part.turn.counts(), part.jobs_total) for kind, part in seen.items()})

    over = {
        kind: problems
        for kind, part in seen.items()
        if (
            problems := [
                *(f"request {p}" for p in part.turn.counts().over(CEILINGS[kind].turn)),
                *(f"jobs {p}" for p in part.jobs_total.over(CEILINGS[kind].jobs)),
            ]
        )
    }
    assert not over, over
    queued = {kind: tuple(part.jobs) for kind, part in seen.items()}
    assert queued == {kind: ceiling.queued for kind, ceiling in CEILINGS.items()}


async def test_a_page_read_before_the_title_job_makes_no_second_title_call(
    harness: _Harness,
) -> None:
    """The phone reads the newest page when it opens or refreshes the chat. Read between
    the first reply and its title job, the page queued a title job of its own, and the
    model was asked for the title twice."""
    harness.ledger.reply = "The capital of France is **Paris**." + _LONG
    chat_id = await harness.new_chat()
    await harness.run_jobs(count=False)
    response = await harness.client.post(
        f"/chats/{chat_id}/messages/stream",
        json={"content": "What's the capital of France?"},
        headers=harness.headers,
    )
    assert response.status_code == 200
    page = await harness.client.get(f"/chats/{chat_id}/messages", headers=harness.headers)
    assert page.status_code == 200

    jobs = await harness.run_jobs()
    titles = [call for job in jobs.values() for call in job.models if "titles" in call]
    assert len(titles) == 1, jobs.keys()


async def _seed_lists(harness: _Harness, n: int) -> UUID:
    """``n`` chats of one exchange, with a memory, a to-do and a photo for each."""
    now = datetime.now(UTC)
    chat_ids: list[UUID] = []
    async with SessionLocal() as session:
        for i in range(n):
            chat = Chat(user_id=harness.user_id, title=f"Paris {i}", pinned=i < 2)
            session.add(chat)
            await session.flush()
            chat_ids.append(chat.id)
            asked = Message(
                chat_id=chat.id,
                user_id=harness.user_id,
                role="user",
                content=f"Tell me about Paris landmark {i}",
                created_at=now - timedelta(minutes=2 * i + 1),
            )
            session.add(asked)
            session.add(
                Message(
                    chat_id=chat.id,
                    user_id=harness.user_id,
                    role="assistant",
                    content=f"Paris landmark {i} is lovely." + _LONG,
                    created_at=now - timedelta(minutes=2 * i),
                )
            )
            await session.flush()
            key = f"u/{harness.user_id}/{uuid4()}.png"
            (harness.storage / key).parent.mkdir(parents=True, exist_ok=True)
            (harness.storage / key).write_bytes(mock_image_bytes())
            session.add_all(
                [
                    Memory(
                        user_id=harness.user_id,
                        type="fact",
                        topic="interests",
                        text=f"User likes Paris landmark number {i}",
                        status="active",
                        source_chat_id=chat.id,
                        source_message_id=asked.id,
                    ),
                    TodoItem(
                        user_id=harness.user_id, content=f"Visit {i}", topic="Trip", sort_order=i
                    ),
                    Attachment(
                        user_id=harness.user_id,
                        message_id=asked.id,
                        storage_key=key,
                        content_type="image/png",
                        size_bytes=68,
                        verified_at=now,
                        linked_at=now,
                    ),
                ]
            )
        await session.commit()
    return chat_ids[0]


async def test_each_list_reads_in_the_same_statements_for_5_rows_and_for_50(
    harness: _Harness,
) -> None:
    seen: dict[int, dict[str, Counts]] = {}
    chat_id = await _seed_lists(harness, 5)
    # The process has read the user, as for every request after a session's first.
    await harness.client.get("/chats", headers=harness.headers)
    for rows in (5, 50):
        if rows == 50:
            await _seed_lists(harness, 45)
        seen[rows] = {}
        for path in LIST_CEILINGS:
            await drain_background_tasks()
            harness.ledger.start()
            response = await harness.client.get(path.format(chat=chat_id), headers=harness.headers)
            await drain_background_tasks()
            counted = harness.ledger.stop()
            assert response.status_code == 200, (path, response.text[:300])
            print(f"=== {path} over {rows} rows\n{counted.detail()}")
            seen[rows][path] = counted.counts()

    over = {
        f"{path} over {rows} rows": problems
        for rows, paths in seen.items()
        for path, counts in paths.items()
        if (problems := counts.over(LIST_CEILINGS[path]))
    }
    assert not over, over
    assert {p: c.sql for p, c in seen[50].items()} == {p: c.sql for p, c in seen[5].items()}

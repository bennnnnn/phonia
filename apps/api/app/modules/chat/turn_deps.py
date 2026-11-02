"""What a chat turn uses outside the chat module, handed to it explicitly.

``stream_entry`` and the stages behind it (``turn_resources``, ``turn_load``,
``turn_intercepts``, ``stream_pipeline``, ``stream_paths``, the finalize passes)
take a ``ChatTurnDeps``. The transports pass ``default_deps()``; a test passes one
with fakes for the database, quota, locks, the model or a service. Each field is a
protocol the real module satisfies, so mypy checks the wiring in ``default_deps``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable, Coroutine, Iterable, Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Any, Protocol
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import redis_lock
from app.core.config import Settings
from app.core.db import SessionLocal
from app.gateways import litellm_gateway
from app.models.orm import Chat, Message, User
from app.modules import todos, web_search
from app.modules.attachments import lifecycle as attachment_lifecycle
from app.modules.attachments import service as attachments_service
from app.modules.billing import plan
from app.modules.chat.model_routing import choice as model_choice
from app.modules.conversation import history as conversation_history
from app.modules.conversation import service as conversation_service
from app.modules.images import generation as image_generation
from app.modules.images import search as image_search
from app.repositories import usage, users
from app.services import conversation_reference, quota
from app.services.subjects.registry import subject_adapter

if TYPE_CHECKING:
    from app.gateways.stream_signals import StreamAttempt
    from app.gateways.web_search_gateway import WebSearchHit
    from app.modules.billing.entitlements import Feature
    from app.services.conversation_reference import ReferenceKind, Turn
    from app.services.subjects.registry import SubjectFence

SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]


class UsersRepo(Protocol):
    async def get_by_id(self, session: AsyncSession, user_id: UUID) -> User | None: ...


class ChatsRepo(Protocol):
    def peek_recent_chat(self, chat_id: UUID, user_id: UUID) -> Chat | None: ...

    async def get_by_id(
        self, session: AsyncSession, chat_id: UUID, user_id: UUID
    ) -> Chat | None: ...

    async def touch_by_id(
        self, session: AsyncSession, chat_id: UUID, *, commit: bool = ...
    ) -> None: ...


class MessagesRepo(Protocol):
    async def create(
        self,
        session: AsyncSession,
        *,
        chat_id: UUID,
        user_id: UUID,
        role: str,
        content: str,
        model: str | None = ...,
        input_tokens: int = ...,
        output_tokens: int = ...,
        commit: bool = ...,
        message_id: UUID | None = ...,
        completion: str | None = ...,
    ) -> Message: ...

    async def list_recent(
        self, session: AsyncSession, chat_id: UUID, *, limit: int
    ) -> list[Message]: ...

    async def count_for_chat(self, session: AsyncSession, chat_id: UUID) -> int: ...

    async def get_by_id(
        self, session: AsyncSession, message_id: UUID, chat_id: UUID
    ) -> Message | None: ...

    async def get_last_user(self, session: AsyncSession, chat_id: UUID) -> Message | None: ...

    async def delete_message(self, session: AsyncSession, message: Message) -> None: ...


class Quota(Protocol):
    """The daily chat budget in Redis, and the global spend cap."""

    def daily_limit_for_user(self, user: User, settings: Settings) -> int: ...

    async def has_daily_usage_key(
        self, redis: Redis, user_id: str, *, day: date | None = ...
    ) -> bool: ...

    async def reserve_usage_up_to(
        self, redis: Redis, user_id: str, wanted: int, *, daily_limit: int
    ) -> int: ...

    async def refund_usage(self, redis: Redis, user_id: str, amount: int) -> None: ...

    async def adjust_usage(
        self,
        redis: Redis,
        user_id: str,
        reserved: int,
        actual: int,
        *,
        daily_limit: int | None = ...,
    ) -> int: ...

    async def mark_usage_needs_heal(
        self, redis: Redis, user_id: str, *, day: date | None = ...
    ) -> None: ...

    async def global_spend_exceeded(self, redis: Redis, settings: Settings) -> bool: ...

    async def record_global_spend(
        self, redis: Redis, usd: float, *, day: date | None = ...
    ) -> int: ...


class UsageRepo(Protocol):
    """The day's usage row in the database, which reseeds Redis after an eviction."""

    async def add_tokens(
        self,
        session: AsyncSession,
        user_id: UUID,
        day: date,
        *,
        input_tokens: int,
        output_tokens: int,
        est_cost_usd: float = ...,
        commit: bool = ...,
    ) -> object: ...


class Plan(Protocol):
    def can_use(self, subject: User, feature: Feature, settings: Settings) -> bool: ...


class ModelChoice(Protocol):
    """The model a turn runs on (``model_routing.choice``): the user's pool, routed."""

    def resolve_user_model_override(
        self,
        user: User,
        model_alias: str | None,
        content: str,
        settings: Settings,
        *,
        prior_user: str | None = ...,
        prior_model: str | None = ...,
        lesson_active: bool = ...,
        unhealthy: frozenset[str] = ...,
    ) -> str: ...

    def resolve_regenerate_model(
        self,
        user: User,
        model_alias: str | None,
        content: str,
        prior_assistant_model: str | None,
        settings: Settings,
    ) -> str: ...


class TurnLocks(Protocol):
    async def acquire_lock(self, redis: Redis, key: str, ttl_seconds: int) -> str | None: ...

    async def refresh_lock(self, redis: Redis, key: str, token: str, ttl_seconds: int) -> bool: ...

    async def release_lock(self, redis: Redis, key: str, token: str) -> None: ...


class ChatModel(Protocol):
    """The streamed model reply (LiteLLM)."""

    def stream_chat_completion(
        self,
        *,
        settings: Settings,
        model_alias: str,
        messages: list[dict[str, Any]],
        max_tokens: int,
        usage: dict[str, int] | None = ...,
        fallback_aliases: list[str] | None = ...,
        stream_meta: dict[str, str] | None = ...,
        on_reasoning: Callable[[str], Awaitable[None]] | None = ...,
        thinking: bool | str | None = ...,
        attempts: list[StreamAttempt] | None = ...,
        on_thinking: Callable[[], Awaitable[None]] | None = ...,
        may_try: Callable[[str], Awaitable[bool]] | None = ...,
        tools: list[dict[str, Any]] | None = ...,
        tool_calls: list[dict[str, Any]] | None = ...,
    ) -> AsyncIterator[str]: ...


class ImageGeneration(Protocol):
    async def generate_for_chat(
        self,
        settings: Settings,
        *,
        user: User,
        chat_id: UUID,
        prompt: str,
        user_message_content: str | None = ...,
        create_user_message: bool = ...,
        reference_attachment_ids: list[UUID] | None = ...,
    ) -> tuple[Message, Message]: ...

    def image_reference_ids(self, content: str) -> list[UUID]: ...


class ImageSearch(Protocol):
    async def search_and_attach_for_chat(
        self,
        settings: Settings,
        *,
        user: User,
        chat_id: UUID,
        query: str,
        user_message_content: str | None = ...,
        create_user_message: bool = ...,
    ) -> tuple[Message, Message]: ...


class AttachmentCleanup(Protocol):
    async def purge_attachments_for_messages(
        self, session: AsyncSession, settings: Settings, message_ids: list[UUID]
    ) -> int: ...

    async def detach_attachments_for_messages(
        self, session: AsyncSession, message_ids: list[UUID], *, commit: bool = ...
    ) -> list[str]: ...

    async def delete_storage_keys(
        self, settings: Settings, storage_keys: list[str]
    ) -> list[str]: ...

    async def enqueue_failed_storage_deletes(self, keys: list[str]) -> None: ...


class AttachmentLinks(Protocol):
    """A reply's photo, stored while it streamed, joined to the saved reply."""

    async def link_to_message(
        self,
        session: AsyncSession,
        *,
        user_id: UUID,
        attachment_ids: list[UUID],
        message_id: UUID,
        commit: bool = ...,
    ) -> int: ...


class ConversationReferences(Protocol):
    """Who "her" or "it" is, read from the chat by a model."""

    def turns_from_rows(self, rows: Iterable[Any]) -> list[Turn]: ...

    async def resolve_reference(
        self,
        settings: Settings,
        *,
        kind: ReferenceKind,
        request: str,
        turns: Sequence[Turn],
    ) -> str | None: ...


class Todos(Protocol):
    """The reply's reminder changes (a card to tap, or To-do rows)."""

    async def materialize_reminder_fences(
        self,
        session: AsyncSession,
        *,
        user_id: UUID,
        chat_id: UUID,
        assistant_text: str,
        user_timezone: str | None,
        user_text: str | None = ...,
        prior_assistant: str | None = ...,
        prior_user: str | None = ...,
        redis: Redis | None = ...,
        confirm: bool = ...,
        window: Sequence[object] | None = ...,
    ) -> tuple[str, int]: ...


@dataclass(frozen=True)
class _PackageTodos:
    """``app.modules.todos`` exports these lazily, which a protocol check cannot see."""

    materialize_reminder_fences: Callable[..., Coroutine[Any, Any, tuple[str, int]]]


class _ConversationChats:
    """``ChatsRepo`` over conversation's operations: its repositories stay inside it."""

    peek_recent_chat = staticmethod(conversation_history.peek_recent_chat)
    get_by_id = staticmethod(conversation_history.get_chat)
    touch_by_id = staticmethod(conversation_service.touch_chat)


class _ConversationMessages:
    """``MessagesRepo`` over conversation's operations."""

    create = staticmethod(conversation_service.create_message)
    list_recent = staticmethod(conversation_history.recent_messages)
    count_for_chat = staticmethod(conversation_history.message_count)
    get_by_id = staticmethod(conversation_history.message_in_chat)
    get_last_user = staticmethod(conversation_history.last_user_message)
    delete_message = staticmethod(conversation_service.delete_message)


# One of each, so two turns' default deps compare equal.
CONVERSATION_CHATS = _ConversationChats()
CONVERSATION_MESSAGES = _ConversationMessages()


class WebSearchFences(Protocol):
    """Source chips and the places card under a searched reply."""

    def strip_sources_from_text(self, text: str) -> str: ...

    def sources_payload(self, hits: list[WebSearchHit]) -> list[web_search.SearchSource]: ...

    def format_sources_fence(self, hits: list[WebSearchHit]) -> str: ...

    def strip_duplicate_venue_list(self, text: str) -> str: ...

    def format_places_fence(self, hits: list[WebSearchHit]) -> str: ...


@dataclass(frozen=True)
class ChatTurnDeps:
    session_factory: SessionFactory
    users: UsersRepo
    chats: ChatsRepo
    messages: MessagesRepo
    usage: UsageRepo
    quota: Quota
    plan: Plan
    model_choice: ModelChoice
    locks: TurnLocks
    llm: ChatModel
    image_generation: ImageGeneration
    image_search: ImageSearch
    attachments: AttachmentCleanup
    attachment_links: AttachmentLinks
    references: ConversationReferences
    todos: Todos
    web_search: WebSearchFences
    # Maths' fence: it checks every reply no peer verified; tests swap it for a pass-through.
    math_fence: SubjectFence


def default_deps() -> ChatTurnDeps:
    """The real modules, as one turn uses them."""
    return ChatTurnDeps(
        session_factory=SessionLocal,
        users=users,
        chats=CONVERSATION_CHATS,
        messages=CONVERSATION_MESSAGES,
        usage=usage,
        quota=quota,
        plan=plan,
        model_choice=model_choice,
        locks=redis_lock,
        llm=litellm_gateway,
        image_generation=image_generation,
        image_search=image_search,
        attachments=attachment_lifecycle,
        attachment_links=attachments_service,
        references=conversation_reference,
        todos=_PackageTodos(
            materialize_reminder_fences=todos.materialize_reminder_fences,
        ),
        web_search=web_search,
        math_fence=subject_adapter("math").fence,
    )

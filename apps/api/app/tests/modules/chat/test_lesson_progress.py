from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.modules.chat.lesson_progress import lesson_progress
from app.modules.chat.post_turn import enqueue_post_turn_jobs
from app.modules.chat.prompt_constants.lesson_flow import lesson_continue_hint
from app.modules.chat.prompt_format import _style_format_hints
from app.modules.chat.turn_prep.context import StreamContext
from app.modules.turn_reading.lesson_flow import lesson_after_gap, lesson_titles, teach_subject

NOW = datetime(2026, 10, 18, 12, tzinfo=UTC)


def _lesson(number, topic):
    return f"Intro.\n\n### Lesson {number}: {topic}\n\n### 1. Idea\nText.\n\n```quiz\n{{}}\n```"


def _msg(role, content, at=NOW):
    return SimpleNamespace(role=role, content=content, created_at=at)


@pytest.mark.parametrize(
    "text, subject",
    [
        ("teach me python", "Python"),
        ("can you teach me Python, please", "Python"),
        ("I want to know American history", "American history"),
        ("help me learn english for work", "English for work"),
        ("Teach me python dictionaries step by step", "Python dictionaries"),
        ("I want to learn calculus because I failed", "Calculus"),
        ("give me a lesson on the French revolution", "The French revolution"),
        ("enséñame inglés", "Inglés"),
        ("teach me", None),
        ("what is python?", None),
    ],
)
def test_teach_subject(text, subject):
    assert teach_subject(text) == subject


def test_lesson_titles_read_number_and_topic():
    text = "### Lesson 3: Dictionaries\n...\n**Lesson 4: Loops**"
    assert lesson_titles(text) == [(3, "Dictionaries"), (4, "Loops")]


def test_lesson_progress_names_the_subject_lessons_and_chat():
    day = timedelta(days=1)
    progress = lesson_progress(
        [
            _msg("user", "teach me python", NOW - 3 * day),
            _msg("assistant", "1. **Variables** ... Pick a number?", NOW - 3 * day),
            _msg("user", "1", NOW - 2 * day),
            _msg("assistant", _lesson(1, "Variables"), NOW - 2 * day),
            _msg("user", "next", NOW - day),
            _msg("assistant", _lesson(2, "Lists and loops"), NOW - day),
            _msg("user", "why?", NOW),
            # Explained again under the same title: covered once.
            _msg("assistant", _lesson(2, "Lists and loops"), NOW),
        ],
        title="Python basics",
    )
    assert progress is not None
    assert progress.text == (
        'Learning Python: reached Lesson 2, Lists and loops (chat "Python basics"). '
        "Covered: Variables; Lists and loops"
    )
    assert progress.started_at == NOW - 2 * day


def test_lesson_progress_falls_back_to_the_chat_title():
    progress = lesson_progress(
        [_msg("user", "next"), _msg("assistant", _lesson(4, "Functions"))], title="Python"
    )
    assert progress is not None and progress.text.startswith("Learning Python: reached Lesson 4")


@pytest.mark.parametrize(
    "messages",
    [
        [_msg("user", "teach me python"), _msg("assistant", "1. **Variables** ... Pick one?")],
        [_msg("user", "what is 2+2"), _msg("assistant", "4")],
        [],
    ],
)
def test_lesson_progress_none_without_a_lesson(messages):
    assert lesson_progress(messages, title="Chat") is None


@pytest.mark.parametrize(
    "sent, expected",
    [
        (NOW - timedelta(days=7), True),
        (NOW - timedelta(hours=20), True),
        (NOW - timedelta(hours=2), False),
        (None, False),
    ],
)
def test_lesson_after_gap(sent, expected):
    messages = [_msg("user", "teach me x"), _msg("assistant", _lesson(1, "X"), sent)]
    assert lesson_after_gap(messages, now=NOW) is expected


def test_a_lesson_after_a_gap_opens_with_a_recap_and_a_warm_up():
    hint = lesson_continue_hint(3, after_gap=True)
    assert "LESSON 3 WAS OVER A DAY AGO" in hint and '"Warm-up"' in hint
    assert "`**Quick recap**`" in hint and "the number is 4" in hint
    assert "OVER A DAY AGO" not in lesson_continue_hint(3)
    hints = _style_format_hints(
        query_text="next",
        is_day_plan=False,
        minimal_personal_context=False,
        lesson=3,
        lesson_after_gap=True,
    )
    assert hint in hints


def _ctx(*, memory_enabled=True, skip=False):
    user = MagicMock()
    user.memory_enabled = memory_enabled
    return StreamContext(
        user_id=uuid4(),
        chat_id=uuid4(),
        model="free-chat",
        prompt_messages=[],
        run_title=False,
        user_message_content="next",
        reserved_tokens=10,
        max_output_tokens=100,
        assistant_message_id=uuid4(),
        skip_memory_jobs=skip,
        prior_count=4,
        user=user,
    )


async def _job_types(ctx, reply):
    with (
        patch("app.core.jobs.enqueue", AsyncMock()) as enqueue,
        patch(
            "app.modules.chat.post_turn.quota_service.global_spend_exceeded",
            AsyncMock(return_value=False),
        ),
    ):
        await enqueue_post_turn_jobs(
            AsyncMock(),
            Settings(history_compression_enabled=False, chat_history_rag_enabled=False),
            ctx,
            reply,
        )
    return [call.args[1] for call in enqueue.call_args_list]


@pytest.mark.asyncio
async def test_a_lesson_reply_queues_the_learning_line():
    ctx = _ctx()
    assert "lesson_progress" in await _job_types(ctx, _lesson(2, "Lists"))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "ctx, reply",
    [
        (_ctx(), "Paris is the capital of France."),
        (_ctx(memory_enabled=False), _lesson(2, "Lists")),
        (_ctx(skip=True), _lesson(2, "Lists")),
    ],
)
async def test_no_learning_line_without_a_lesson_or_memory(ctx, reply):
    assert "lesson_progress" not in await _job_types(ctx, reply)


@pytest.mark.asyncio
async def test_job_writes_the_line_and_retries_a_busy_memory():
    from app.background import handlers
    from app.modules.chat.lesson_progress import LessonProgress

    payload = {"user_id": str(uuid4()), "chat_id": str(uuid4()), "assistant_message_id": "m1"}
    progress = LessonProgress(text="Learning Python: reached Lesson 1, X", started_at=NOW)
    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    with (
        patch.object(handlers, "SessionLocal", lambda: session),
        patch.object(
            handlers.lesson_progress, "load_lesson_progress", AsyncMock(return_value=progress)
        ),
        patch.object(
            handlers.memory_learning,
            "record_learning_progress",
            AsyncMock(side_effect=[None, "skipped_lock"]),
        ) as record,
        patch.object(handlers, "_reenqueue_after_memory_lock", AsyncMock()) as retry,
    ):
        await handlers._handle_lesson_progress(Settings(), payload)
        retry.assert_not_awaited()
        await handlers._handle_lesson_progress(Settings(), payload)
    assert record.await_args.kwargs["text"] == progress.text
    assert retry.await_args.kwargs["job_type"] == "lesson_progress"

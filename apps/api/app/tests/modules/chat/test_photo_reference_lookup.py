"""Photo lookups that name someone earlier in the chat: "show me her image"."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.modules.chat.turn_outcome import TurnOutcome
from app.modules.images.lookup_intent import (
    extract_image_lookup_query,
    is_reference_subject,
    names_a_drawing,
)
from app.tests.fakes import make_user
from app.tests.modules.chat.chat_test_support import turn_deps


def _awaited(mock: AsyncMock) -> Any:
    """The last await of *mock*; fails the test when it was never awaited."""
    assert mock.await_args is not None
    return mock.await_args


_CALMENT_ROWS = [
    SimpleNamespace(id=uuid4(), role="user", content="Has anyone ever lived for 123 years?"),
    SimpleNamespace(
        id=uuid4(),
        role="assistant",
        content="No verified human has; the longest is Jeanne Calment, 122 years.",
        model="free-chat",
    ),
    SimpleNamespace(id=uuid4(), role="user", content="Where is she from"),
    SimpleNamespace(
        id=uuid4(),
        role="assistant",
        content="She was French, born in Arles, France.",
        model="free-chat",
    ),
]


@pytest.mark.parametrize(
    "text, subject",
    [
        ("Show me her image", "her"),
        ("show me a photo of her", "her"),
        ("can you show me her picture", "her"),
        ("show me his photo", "his"),
        ("what does she look like", "she"),
        ("show me what she looks like", "she"),
        ("please show me an ear", "ear"),
        ("send me a photo of the eiffel tower", "eiffel tower"),
        ("I'd like to see the Taj Mahal", "Taj Mahal"),
    ],
)
def test_lookup_reads_pronouns_and_polite_requests(text: str, subject: str) -> None:
    assert extract_image_lookup_query(text) == subject


@pytest.mark.parametrize(
    "text",
    ["show me my todos", "can you show me my todos", "find me a restaurant", "send me the notes"],
)
def test_lookup_leaves_app_content_alone(text: str) -> None:
    assert extract_image_lookup_query(text) is None


@pytest.mark.parametrize(
    "subject, expected",
    [
        ("her", True),
        ("she", True),
        ("it at night", True),
        ("another one", True),
        # A count with nothing counted names no one either.
        ("both", True),
        ("Both of them", True),
        ("all of them", True),
        ("other two", True),
        ("others", True),
        ("each one", True),
        ("either one", True),
        ("all three", True),
        # Fillers and how-to-show tails do not name anything either.
        ("both please", True),
        ("both pls", True),
        ("both again", True),
        ("both of em", True),
        ("both of 'em", True),
        ("both at night", True),
        ("all 3", True),
        ("3 of them", True),
        ("both side by side", True),
        ("all of them together, please", True),
        ("Jeanne Calment", False),
        ("ear", False),
        ("Eiffel Tower", False),
        # A count with a noun names what to search.
        ("both sides of the coin", False),
        ("all the planets", False),
        ("both crocodiles", False),
        ("two cats", False),
        ("other side of the moon", False),
        ("one direction", False),
        ("first one", False),
        ("3 cats", False),
        ("please", False),
    ],
)
def test_is_reference_subject(subject: str, expected: bool) -> None:
    assert is_reference_subject(subject) is expected


@pytest.mark.parametrize(
    "subject, drawn",
    [
        # The app draws these; they are no photo search.
        ("water and carbon dioxide molecules", True),
        ("H2O molecule", True),
        ("caffeine molecular structure", True),
        ("the graph of y = x^2", True),
        ("quadratic equation", True),
        # Resolved names that hit a typed-phrase word ("square", "i", "table") are photos.
        ("crocodile and alligator", False),
        ("Queen Elizabeth I", False),
        ("Times Square at night", False),
        ("Table Mountain", False),
        ("Red Square in Moscow", False),
        ("Manhattan Project scientists", False),
        ("human heart diagram", False),
        ("Formula 1 car", False),
        ("Similac infant formula", False),
    ],
)
def test_names_a_drawing(subject: str, drawn: bool) -> None:
    assert names_a_drawing(subject) is drawn


def _found(asst_id) -> AsyncMock:
    asst_msg = MagicMock()
    asst_msg.id = asst_id
    asst_msg.content = "[Image: /attachments/x/file]"
    asst_msg.model = "image-search-model"
    return AsyncMock(return_value=(MagicMock(), asst_msg))


@pytest.mark.asyncio
async def test_show_me_her_image_searches_the_person_from_the_chat() -> None:
    """The screenshot: "Show me her image" after a chat about Jeanne Calment."""
    from app.modules.chat.turn_intercepts import try_image_lookup_for_turn

    user = MagicMock()
    user.id = uuid4()
    search_and_attach = _found(uuid4())
    resolve = AsyncMock(return_value="Jeanne Calment")

    deps = turn_deps(
        image_search={"search_and_attach_for_chat": search_and_attach},
        references={"resolve_reference": resolve},
    )
    handled = await try_image_lookup_for_turn(
        deps,
        Settings(image_search_enabled=True),
        user=user,
        chat_id=uuid4(),
        content="Show me her image",
        outcome=TurnOutcome(),
        create_user_message=True,
        recent_messages=list(_CALMENT_ROWS),
    )

    assert handled is True
    assert _awaited(search_and_attach).kwargs["query"] == "Jeanne Calment"
    kwargs = _awaited(resolve).kwargs
    assert kwargs["kind"] == "photo"
    assert kwargs["request"] == "Show me her image"
    assert ("user", "Where is she from") in kwargs["turns"]


@pytest.mark.asyncio
async def test_unclear_reference_falls_through_to_the_model() -> None:
    from app.modules.chat.turn_intercepts import try_image_lookup_for_turn

    user = MagicMock()
    user.id = uuid4()
    search_and_attach = _found(uuid4())

    deps = turn_deps(
        image_search={"search_and_attach_for_chat": search_and_attach},
        references={"resolve_reference": AsyncMock(return_value=None)},
    )
    handled = await try_image_lookup_for_turn(
        deps,
        Settings(image_search_enabled=True),
        user=user,
        chat_id=uuid4(),
        content="show me her image",
        outcome=TurnOutcome(),
        create_user_message=True,
        recent_messages=[],
    )

    assert handled is False
    search_and_attach.assert_not_awaited()


@pytest.mark.asyncio
async def test_after_a_generated_picture_it_is_left_to_the_editor() -> None:
    """ "show it at night" after a generated cat edits the cat; no stock photo of "it"."""
    from app.modules.chat.turn_intercepts import try_image_lookup_for_turn

    user = MagicMock()
    user.id = uuid4()
    rows = [
        SimpleNamespace(id=uuid4(), role="user", content="Generate image: black cat"),
        SimpleNamespace(
            id=uuid4(),
            role="assistant",
            content="[Image: /attachments/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee/file]",
            model="image-gen-model",
        ),
    ]
    search_and_attach = _found(uuid4())
    resolve = AsyncMock()

    deps = turn_deps(
        image_search={"search_and_attach_for_chat": search_and_attach},
        references={"resolve_reference": resolve},
    )
    handled = await try_image_lookup_for_turn(
        deps,
        Settings(image_search_enabled=True),
        user=user,
        chat_id=uuid4(),
        content="Show it at night",
        outcome=TurnOutcome(),
        create_user_message=True,
        recent_messages=rows,
    )

    assert handled is False
    resolve.assert_not_awaited()
    search_and_attach.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_named_subject_needs_no_resolver() -> None:
    from app.modules.chat.turn_intercepts import try_image_lookup_for_turn

    user = MagicMock()
    user.id = uuid4()
    search_and_attach = _found(uuid4())
    resolve = AsyncMock()

    deps = turn_deps(
        image_search={"search_and_attach_for_chat": search_and_attach},
        references={"resolve_reference": resolve},
    )
    handled = await try_image_lookup_for_turn(
        deps,
        Settings(image_search_enabled=True),
        user=user,
        chat_id=uuid4(),
        content="can you show me a picture of Jeanne Calment",
        outcome=TurnOutcome(),
        create_user_message=True,
    )

    assert handled is True
    assert _awaited(search_and_attach).kwargs["query"] == "Jeanne Calment"
    resolve.assert_not_awaited()


@pytest.mark.asyncio
async def test_regenerating_a_reference_lookup_reads_history_without_the_old_photo() -> None:
    from app.modules.chat.turn_intercepts import try_image_lookup_for_turn

    user = MagicMock()
    user.id = uuid4()
    old_photo = SimpleNamespace(
        id=uuid4(), role="assistant", content="[Image: /a/file]", model="image-search-model"
    )
    rows = [*_CALMENT_ROWS, SimpleNamespace(id=uuid4(), role="user", content="Show me her image")]
    rows.append(old_photo)
    list_recent = AsyncMock(return_value=rows)
    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)
    resolve = AsyncMock(return_value="Jeanne Calment")
    search_and_attach = _found(uuid4())

    deps = turn_deps(
        session_factory=MagicMock(return_value=session),
        messages={"list_recent": list_recent, "get_by_id": AsyncMock(return_value=None)},
        references={"resolve_reference": resolve},
        image_search={"search_and_attach_for_chat": search_and_attach},
    )
    handled = await try_image_lookup_for_turn(
        deps,
        Settings(image_search_enabled=True),
        user=user,
        chat_id=uuid4(),
        content="Show me her image",
        outcome=TurnOutcome(),
        create_user_message=False,
        replace_assistant_id=old_photo.id,
    )

    assert handled is True
    turns = _awaited(resolve).kwargs["turns"]
    assert ("assistant", "[Image: /a/file]") not in turns
    assert _awaited(search_and_attach).kwargs["query"] == "Jeanne Calment"


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["photo", "picture"])
async def test_a_stop_held_for_the_users_row_cuts_off_a_photo_or_picture(kind: str) -> None:
    """A new message holds a Stop's hard cancel until its row is saved; a photo or a
    picture saves that row only with its reply, so the Stop reaches it before it runs."""
    from app.modules.chat.turn_intercepts import intercept_new_turn

    user = make_user()
    order: list[str] = []
    found = _found(uuid4())

    async def work(*_args: Any, **_kwargs: Any) -> Any:
        order.append(kind)
        return await found()

    outcome = TurnOutcome()
    outcome.hold_stops()
    outcome.stop_when_safe(lambda: order.append("stop"))
    deps = turn_deps(
        image_search={"search_and_attach_for_chat": work},
        image_generation={"generate_for_chat": work},
        plan={"can_use": MagicMock(return_value=True)},
    )
    content = "Show me a photo of the Eiffel Tower" if kind == "photo" else "Draw a black cat"
    handled = await intercept_new_turn(
        deps,
        Settings(image_search_enabled=kind == "photo"),
        user=user,
        chat_id=uuid4(),
        content=content,
        outcome=outcome,
        recent_messages=[],
        prior_count=0,
    )

    assert handled is True
    assert order == ["stop", kind]


@pytest.mark.asyncio
@pytest.mark.parametrize("regenerate", [False, True])
@pytest.mark.parametrize(
    "kind, content, phase",
    [
        ("photo", "Show me a photo of the Eiffel Tower", "finding_photo"),
        ("picture", "Draw a black cat", "image_gen"),
    ],
)
async def test_a_photo_or_picture_on_the_chat_path_says_so_before_it_runs(
    kind: str, content: str, phase: str, regenerate: bool
) -> None:
    """Regression: the tool loop's photo or picture put up its label, the same work
    on the chat path did not: plain typing dots for the seconds it took."""
    from app.modules.chat.turn_intercepts import intercept_new_turn, intercept_regenerate
    from app.modules.chat.turn_prep import RegenerateBackup

    order: list[str] = []
    found = _found(uuid4())

    async def work(*_args: Any, **_kwargs: Any) -> Any:
        order.append(kind)
        return await found()

    async def on_status(
        phase: str, detail: str | None = None, *, elapsed_ms: int | None = None
    ) -> None:
        order.append(f"{phase}: {detail}")

    deps = turn_deps(
        image_search={"search_and_attach_for_chat": work},
        image_generation={"generate_for_chat": work, "image_reference_ids": lambda _c: []},
        plan={"can_use": MagicMock(return_value=True)},
    )
    settings = Settings(image_search_enabled=kind == "photo")
    turn: dict[str, Any] = {
        "user": make_user(),
        "chat_id": uuid4(),
        "content": content,
        "outcome": TurnOutcome(),
    }
    if regenerate:
        model = "image-search-model" if kind == "photo" else "image-gen-model"
        backup = RegenerateBackup(content="[Image]", model=model, message_id=uuid4())
        handled = await intercept_regenerate(
            deps, settings, **turn, backup=backup, on_status=on_status
        )
    else:
        handled = await intercept_new_turn(
            deps, settings, **turn, recent_messages=[], prior_count=0, on_status=on_status
        )

    assert handled is True
    assert len(order) == 2 and order[0].startswith(f"{phase}: ") and order[1] == kind


_MOLECULE_ROWS = [
    SimpleNamespace(id=uuid4(), role="user", content="why is water bent tho, co2 isnt"),
    SimpleNamespace(
        id=uuid4(),
        role="assistant",
        content="Water has two lone pairs on oxygen, so it is bent; CO2 has none, so it is linear.",
        model="free-chat",
    ),
]
# A chat that names two things but asks no shape: "show me both" is the resolver's.
_TWO_THINGS_ROWS = [
    SimpleNamespace(id=uuid4(), role="user", content="tell me about water and co2"),
    SimpleNamespace(
        id=uuid4(),
        role="assistant",
        content="Water is H2O; carbon dioxide is CO2, the gas we breathe out.",
        model="free-chat",
    ),
]


async def _new_turn(
    rows: list[SimpleNamespace], content: str, resolved: str | None, *, pro: bool = True
) -> tuple[bool, AsyncMock, AsyncMock, set[str]]:
    from app.modules.chat.turn_intercepts import intercept_new_turn

    search_and_attach = _found(uuid4())
    resolve = AsyncMock(return_value=resolved)
    deps = turn_deps(
        image_search={"search_and_attach_for_chat": search_and_attach},
        references={"resolve_reference": resolve},
    )
    misses: set[str] = set()
    handled = await intercept_new_turn(
        deps,
        Settings(image_search_enabled=True, image_generation_enabled=True),
        user=make_user(plan="pro" if pro else "free"),
        chat_id=uuid4(),
        content=content,
        outcome=TurnOutcome(),
        recent_messages=list(rows),
        prior_count=len(rows),
        misses=misses,
    )
    return handled, resolve, search_and_attach, misses


async def _show_me_both(
    rows: list[SimpleNamespace], resolved: str | None
) -> tuple[bool, AsyncMock, AsyncMock, set[str]]:
    return await _new_turn(rows, "can u show me both", resolved)


@pytest.mark.parametrize(
    "content",
    [
        "can u show me both",
        "show me both of them",
        "show me what they look like",
        "show me each of them",
        "show me the shapes",
        "show me the models",
        "show us both",
        "show me both then",
        "show me the drawings",
        "display them",
        "lol no the molecules",
    ],
)
@pytest.mark.parametrize("resolved", ["water and carbon dioxide", None])
@pytest.mark.asyncio
async def test_a_show_line_after_a_shape_answer_is_drawn_not_searched_or_generated(
    content: str, resolved: str | None, thread_sympy_executor: None
) -> None:
    """ "can u show me both" searched the word "both" and showed a meme (2026-10-25). After a
    shape answer chemistry draws the molecules, whatever a resolver would have named, before a
    photo or a generated picture is asked."""
    handled, resolve, search_and_attach, misses = await _new_turn(_MOLECULE_ROWS, content, resolved)
    assert handled is False
    resolve.assert_not_awaited()
    search_and_attach.assert_not_awaited()
    assert "photo" in misses


_SHOW_LINES = (
    "can u show me both",
    "show me both of them",
    "show me what they look like",
    "show me each of them",
    "show me the shapes",
    "show me the models",
    "show us both",
    "show me both then",
    "show me the drawings",
    "show me pictures of both",
    "display them",
    "let me see them",
    "what do they look like",
    "lol no the molecules",
)


@pytest.mark.parametrize("content", _SHOW_LINES)
def test_the_composer_sends_every_show_line_to_the_chat_turn(content: str) -> None:
    """The composer reads a send before the chat turn exists: a picture it draws is the
    picture the chat turn would draw. Every line chemistry claims is a photo lookup or a plain
    send there, so it reaches the chat turn and its intercept."""
    from app.modules.images.intent import composer_image_intent

    assert composer_image_intent(content, list(_MOLECULE_ROWS)).request is None


@pytest.mark.parametrize("content", ["draw both", "draw both of them", "draw them", "sketch them"])
@pytest.mark.asyncio
async def test_a_draw_line_after_a_shape_answer_is_left_to_image_generation(
    content: str, thread_sympy_executor: None
) -> None:
    """The composer sends "draw both" to /images/generate before any chat turn; chemistry
    claiming it on the chat path would split that one reading."""
    from app.modules.chat.turn_intercepts import _chemistry_draws_it

    assert not await _chemistry_draws_it(Settings(), content, list(_MOLECULE_ROWS))


@pytest.mark.asyncio
async def test_a_regenerated_show_line_takes_the_photo_tool_out_too(
    thread_sympy_executor: None,
) -> None:
    from app.modules.chat.turn_intercepts import intercept_regenerate
    from app.modules.chat.turn_prep import RegenerateBackup

    deps = turn_deps(messages={"list_recent": AsyncMock(return_value=list(_MOLECULE_ROWS))})
    misses: set[str] = set()
    handled = await intercept_regenerate(
        deps,
        Settings(image_search_enabled=True),
        user=make_user(),
        chat_id=uuid4(),
        content="can u show me both",
        backup=RegenerateBackup(content="Here.", model="free-chat", message_id=uuid4()),
        outcome=TurnOutcome(),
        misses=misses,
    )
    assert handled is False
    assert "photo" in misses


@pytest.mark.asyncio
async def test_a_photo_of_both_after_a_shape_answer_stays_a_photo(
    thread_sympy_executor: None,
) -> None:
    handled, resolve, search_and_attach, _misses = await _new_turn(
        _MOLECULE_ROWS, "show me a photo of both", "water and carbon dioxide"
    )
    assert handled is True
    resolve.assert_awaited_once()
    assert _awaited(search_and_attach).kwargs["query"] == "water and carbon dioxide"


@pytest.mark.asyncio
async def test_a_photo_turn_in_another_chat_never_waits_on_the_pool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.modules.chat import turn_intercepts

    pool = AsyncMock()
    monkeypatch.setattr(turn_intercepts, "run_sympy", pool)
    handled, _resolve, _search, _misses = await _new_turn(
        list(_CALMENT_ROWS), "show me her image", "Jeanne Calment"
    )
    assert handled is True
    pool.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_pool_that_gives_up_leaves_the_photo_path_and_the_turns_readings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core import readings
    from app.modules.chat import turn_intercepts

    readings.begin_turn()
    monkeypatch.setattr(turn_intercepts, "run_sympy", AsyncMock(side_effect=TimeoutError))
    handled, resolve, _search, _misses = await _new_turn(
        _MOLECULE_ROWS, "can u show me both", "water and carbon dioxide"
    )
    assert handled is True
    resolve.assert_awaited_once()
    memo = readings._MEMO.get()
    assert memo is not None and readings._DECLINED not in memo


@pytest.mark.parametrize(
    "resolved, query",
    [
        ("water and carbon dioxide molecules", None),
        (None, None),
        ("crocodile and alligator", "crocodile and alligator"),
        ("Times Square at night", "Times Square at night"),
    ],
)
@pytest.mark.asyncio
async def test_show_me_both_reads_both_from_the_chat(
    resolved: str | None, query: str | None, thread_sympy_executor: None
) -> None:
    handled, resolve, search_and_attach, misses = await _show_me_both(_TWO_THINGS_ROWS, resolved)
    assert _awaited(resolve).kwargs["request"] == "can u show me both"
    assert handled is (query is not None)
    if query is None:
        search_and_attach.assert_not_awaited()
    else:
        assert _awaited(search_and_attach).kwargs["query"] == query
    # A drawn thing takes the photo tool out of the turn's loop as well; an unclear
    # reference leaves it to the model, as before.
    assert ("photo" in misses) is (resolved is not None and query is None)

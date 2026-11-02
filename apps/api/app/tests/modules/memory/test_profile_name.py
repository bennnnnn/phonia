"""The profile name is the user's name: a saved fact naming them otherwise stays out."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.models.orm import User
from app.modules.memory.facts import identity_core, render_memory_block
from app.modules.memory.pass_writes import writes_from_ops
from app.modules.memory.profile_name import without_conflicting_names
from app.modules.memory.schemas import MemoryFactOp
from app.modules.memory.user_name import (
    as_chosen_name,
    names_another_person,
    names_the_user,
    stated_user_name,
)

_SAID = datetime(2026, 10, 24, tzinfo=UTC)
# The live account: profile name Dev, an older test fact naming the user Sam.
_SAM = "User's name is Sam; they are a nursing student living in Chicago"


def _fact(text: str, kind: str = "profile", said: datetime = _SAID) -> SimpleNamespace:
    return SimpleNamespace(
        type=kind, text=text, last_confirmed_at=said, created_at=said, confidence=1.0
    )


def _block(*texts: str) -> str:
    return render_memory_block(
        [_fact(text) for text in texts] + [_fact("User prefers dark mode", "preference")]
    )


@pytest.mark.parametrize(
    ("fact", "profile_name"),
    [
        (_SAM, "Dev"),
        ("The user's name is Sam", "Dev Patel"),
        ("Sam is the user's name", "Dev"),
        ("User is named Sam", "Dev"),
        ("User's name is Дима", "Taro Yamada"),
        # A stated name with a nickname is still a stated name.
        ("User's name is Sam; also goes by Sammy", "Dev"),
    ],
)
def test_a_fact_naming_someone_else_is_another_person(fact: str, profile_name: str) -> None:
    assert names_another_person(fact, profile_name)


@pytest.mark.parametrize(
    ("fact", "profile_name"),
    [
        ("User's name is Dev", "Dev"),
        ("User's name is dev", "Dev Patel"),
        ("User's name is Patel", "Dev Patel"),
        # A short form of the profile name is the same person.
        ("User's name is Bini", "Binalfew Mecuriaw"),
        ("User's name is Sam", "Samantha"),
        ("User's name is Al", "Alan"),
        # The name they chose to be called stays beside the profile name.
        ("User goes by Sam", "Dev"),
        ("User's name is Dev; also goes by Sam", "Dev"),
        # Not a name for the user at all: a bare "User is X" is a trait, not a name.
        ("User is a nursing student", "Dev"),
        ("User's dog is named Sam", "Dev"),
        ("User's sister's name is Sam", "Dev"),
        ("User's mother's name is Sam", "Dev"),
        ("User's son is named Sam", "Dev"),
        ("User's company name is Acme", "Dev"),
        ("User's username is samx", "Dev"),
        ("User's user name is samx", "Dev"),
        ("User's Instagram user name is Sam", "Dev"),
        ("User's Wi-Fi network name is Sam", "Dev"),
        ("User's last name is Smith", "Dev"),
        ("User's middle name is Lee", "Dev"),
        ("User's maiden name is Smith", "Dev"),
        ("The user's manager is Sam Lee", "Dev"),
        ("The user is Sam", "Dev"),
        ("User is Sam, a student", "Dev"),
        # No profile name: memory is the only source of the name.
        (_SAM, None),
        (_SAM, ""),
        (_SAM, "  "),
    ],
)
def test_facts_that_agree_or_name_no_one_stay(fact: str, profile_name: str | None) -> None:
    assert not names_another_person(fact, profile_name)


@pytest.mark.parametrize(
    "trait",
    [
        "User is retired",
        "User is married",
        "User is pregnant",
        "User is diabetic",
        "User is Christian",
        "User is Ethiopian",
        "User is bilingual",
        "User is self-employed",
        "User is left-handed",
        "User is vegetarian",
        "the user is vegetarian",
    ],
)
def test_a_one_word_trait_is_not_a_name_and_stays(trait: str) -> None:
    block = _block(trait)

    assert stated_user_name(trait) is None
    assert without_conflicting_names(block, "Dev") == block


def test_the_block_drops_the_line_naming_someone_else() -> None:
    block = _block(_SAM)

    filtered = without_conflicting_names(block, "Dev")

    assert "Sam" not in filtered
    assert "## Profile" not in filtered
    assert "User prefers dark mode" in filtered
    assert filtered == render_memory_block([_fact("User prefers dark mode", "preference")])


def test_the_block_keeps_other_profile_lines() -> None:
    block = _block(_SAM, "User is from Ethiopia")

    filtered = without_conflicting_names(block, "Dev")

    assert "Sam" not in filtered
    assert "User is from Ethiopia" in filtered
    assert "## Profile" in filtered


def test_a_block_of_only_the_conflicting_name_is_empty() -> None:
    assert without_conflicting_names(render_memory_block([_fact(_SAM)]), "Dev") == ""


@pytest.mark.parametrize("profile_name", ["Sam", "Samuel Lee", None])
def test_the_block_is_unchanged_when_nothing_conflicts(profile_name: str | None) -> None:
    block = _block(_SAM)
    assert without_conflicting_names(block, profile_name) == block


def test_a_name_in_another_section_is_left_alone() -> None:
    block = render_memory_block([_fact("User's name is Sam", "fact")])
    assert without_conflicting_names(block, "Dev") == block


def test_a_mock_profile_name_reads_as_none() -> None:
    block = _block(_SAM)
    assert without_conflicting_names(block, AsyncMock()) == block


@pytest.mark.asyncio
async def test_every_prompt_reads_the_block_without_the_other_name(fake_redis) -> None:
    from app.modules.memory import get_memory_block

    user = User(id=uuid4(), email="dev@example.com", name="Dev", memory_enabled=True)
    rows = [
        SimpleNamespace(
            id=uuid4(),
            type=kind,
            text=text,
            status="active",
            confidence=1.0,
            importance=0.8,
            sensitivity="normal",
            topic=None,
            last_confirmed_at=_SAID,
            created_at=_SAID,
        )
        for kind, text in (("profile", _SAM), ("preference", "User prefers dark mode"))
    ]
    with patch("app.modules.memory.repository.list_for_user", AsyncMock(return_value=rows)):
        block = await get_memory_block(
            AsyncMock(), user, Settings(semantic_memory_enabled=False), scope="self"
        )
        # A renamed profile takes effect on the cached block too.
        user.name = "Sam"
        renamed = await get_memory_block(
            AsyncMock(), user, Settings(semantic_memory_enabled=False), scope="self"
        )

    assert "Sam" not in block
    assert "User prefers dark mode" in block
    assert _SAM in renamed


@pytest.mark.parametrize(
    ("text", "speech", "profile_name", "saved"),
    [
        ("User's name is Sam", "User: call me Sam", None, "User goes by Sam"),
        (
            "The user's name is Sam.",
            "User: Please call me Sam from now on!",
            "Dev",
            "User goes by Sam",
        ),
        ("User's name is Sam", "User: I go by Sam", None, "User goes by Sam"),
        ("User is named Sam", "User: I'd like to be called Sam", None, "User goes by Sam"),
        ("User's name is Sam", "User: My friends call me Sam", None, "User goes by Sam"),
        # Their own name that differs from the account: the name they go by.
        ("User's name is Bill", "User: My name is Bill", "William Smith", "User goes by Bill"),
        ("User's name is Liz", "User: my name's Liz", "Elizabeth", "User goes by Liz"),
        (
            "User's name is Дима",
            "User: my name is Дима",
            "Dmitry",
            "User goes by Дима",
        ),
        ("User's name is 太郎", "User: my name is 太郎", "Taro Yamada", "User goes by 太郎"),
        (
            "User's name is Bill; they teach maths",
            "User: My name is Bill and I teach maths",
            "William",
            "User goes by Bill; they teach maths",
        ),
        # Their own name that agrees with the account, or no account name: unchanged.
        ("User's name is Sam", "User: my name is Sam", None, "User's name is Sam"),
        ("User's name is Sam", "User: my name is Sam", "Samantha", "User's name is Sam"),
        ("User's name is Sam", "User: I'm Sam. Call me Sam.", None, "User's name is Sam"),
        # "I'm Sam" against another account name is as often a role: it stays a stated
        # name, which the read leaves out (the live fact, 2026-10-25).
        (_SAM, "User: I'm Sam, a nursing student in Chicago. Plan my week.", "Dev", _SAM),
        (_SAM, "User: Pretend I'm Sam, a nursing student in Chicago.", "Dev", _SAM),
        ("User's name is Liz", "User: I'm Liz", "Elizabeth", "User's name is Liz"),
        ("User's name is Sam", "User: imagine my name is Sam", "Dev", "User's name is Sam"),
        # A role word further back is not a role: an introduction.
        (
            "User's name is Sam",
            "User: I imagine you are busy, but my name is Sam",
            "Dev",
            "User goes by Sam",
        ),
        # A refusal, a filler word or a name they never gave: unchanged.
        (
            "User's name is Sam",
            "User: don't call me Sam, my name is Samuel",
            "Dev",
            "User's name is Sam",
        ),
        ("User's name is When", "User: call me when you're done", None, "User's name is When"),
        ("User's name is Sam", "User: call me Ben", "Dev", "User's name is Sam"),
        ("User works at Stripe", "User: call me Sam", "Dev", "User works at Stripe"),
        (
            "User's sister's name is Sam",
            "User: my name is Sam",
            "Dev",
            "User's sister's name is Sam",
        ),
    ],
)
def test_the_name_they_go_by_is_saved_as_one(
    text: str, speech: str, profile_name: str | None, saved: str
) -> None:
    assert as_chosen_name(text, speech, profile_name) == saved


def test_the_old_test_fact_is_still_dropped_on_read() -> None:
    assert names_another_person(_SAM, "Dev")
    assert without_conflicting_names(render_memory_block([_fact(_SAM)]), "Dev") == ""


def test_call_me_is_written_as_a_nickname() -> None:
    op = MemoryFactOp(
        op="add", type="profile", text="User's name is Sam", confidence=0.9, importance=0.8
    )

    writes, skipped = writes_from_ops(
        [op],
        chat_id=uuid4(),
        explicit_remember=False,
        include_sensitive=False,
        min_confidence=0.5,
        transcript="User: call me Sam",
    )

    assert skipped == 0
    assert [write.text for write in writes] == ["User goes by Sam"]
    assert not names_another_person(writes[0].text, "Dev")


def test_a_self_stated_name_unlike_the_account_is_written_as_a_nickname() -> None:
    op = MemoryFactOp(
        op="add", type="profile", text="User's name is Bill", confidence=0.9, importance=0.8
    )

    writes, _ = writes_from_ops(
        [op],
        chat_id=uuid4(),
        explicit_remember=False,
        include_sensitive=False,
        min_confidence=0.5,
        transcript="User: My name is Bill",
        profile_name="William Smith",
    )

    assert [write.text for write in writes] == ["User goes by Bill"]


@pytest.mark.parametrize(
    "fact",
    [
        "User's name is pronounced BEE-nee",
        "User's name is spelled with one n",
        "User's name is short for Binalfew",
        "User's name is often misspelled",
        "User's name is hard to pronounce",
        "User's name is Ethiopian in origin",
        "Name is not important to them",
        "User goes by bike to work",
        "User goes by they/them pronouns",
        "User goes by They",
        "User's name is private",
        "User's name is de Sam",
    ],
)
def test_a_fact_about_the_name_names_no_one(fact: str) -> None:
    assert stated_user_name(fact) is None
    assert not names_the_user(fact)
    assert not names_another_person(fact, "Binalfew Mecuriaw")


@pytest.mark.parametrize(
    ("fact", "name"),
    [
        ("User's name is Sam Okafor", "Sam Okafor"),
        ("User's name is Sam and they nurse", "Sam"),
        ("User's name is Sam, a nurse", "Sam"),
        ("Sam is the user's name", "Sam"),
        ("User's name is 太郎", "太郎"),
        ("User's name is Maria de la Cruz", "Maria de la Cruz"),
        ("User's name is Omar al-Hassan", "Omar al-Hassan"),
        ("User's name is Abebe Bikila Tesfaye Haile Mariam", "Abebe Bikila Tesfaye Haile Mariam"),
        ("User's name is sam", "sam"),
        ("User's full name is Sam Lee", "Sam Lee"),
        ("User's first name is Sam", "Sam"),
        ("User's name is Dr. Sam Lee", "Sam Lee"),
    ],
)
def test_a_name_runs_to_the_end_of_its_clause(fact: str, name: str) -> None:
    assert stated_user_name(fact) == name


def test_a_fact_about_how_they_travel_never_takes_the_slot() -> None:
    own = _ranked("User's name is Binalfew", said=datetime(2026, 1, 1, tzinfo=UTC), importance=1.0)
    pronouns = _ranked(
        "User goes by they/them pronouns", said=datetime(2026, 10, 1, tzinfo=UTC), importance=0.4
    )
    bike = _ranked(
        "User goes by bike to work", said=datetime(2026, 10, 2, tzinfo=UTC), importance=0.4
    )

    core = identity_core([own, pronouns, bike])  # type: ignore[list-item]

    assert [memory.text for memory in core] == ["User's name is Binalfew"]


@pytest.mark.parametrize(
    "fact", ["User's nickname is Bini", "User's preferred name is Bini", "User goes by Dr. Bini"]
)
def test_a_nickname_or_preferred_name_names_the_user_and_stays(fact: str) -> None:
    assert names_the_user(fact)
    assert stated_user_name(fact) is None
    assert not names_another_person(fact, "Sam Lee")


def test_a_full_name_unlike_the_account_is_left_out() -> None:
    assert names_another_person("User's full name is Sam Lee", "Dev")


def test_stated_names_leave_out_nicknames() -> None:
    assert stated_user_name("User's name is Dev; also goes by Sam") == "Dev"
    assert stated_user_name("User goes by Sam") is None


def test_the_newest_name_is_the_one_in_every_prompt() -> None:
    older = _fact("User's name is Bini", said=datetime(2026, 1, 5, tzinfo=UTC))
    older_but_important = _fact("User goes by B", said=datetime(2026, 2, 5, tzinfo=UTC))
    older_but_important.importance = 1.0
    newest = _fact("User goes by Ben", said=datetime(2026, 9, 1, tzinfo=UTC))
    newest.importance = 0.5

    core = identity_core([older, older_but_important, newest])  # type: ignore[list-item]

    assert [memory.text for memory in core] == ["User goes by Ben"]


def _ranked(text: str, *, said: datetime, importance: float) -> SimpleNamespace:
    memory = _fact(text, said=said)
    memory.importance = importance
    return memory


def test_another_persons_name_never_takes_the_users_slot() -> None:
    own = _ranked("User's name is Binalfew", said=datetime(2026, 1, 1, tzinfo=UTC), importance=1.0)
    sister = _ranked(
        "User's sister's name is Sam", said=datetime(2026, 10, 1, tzinfo=UTC), importance=0.5
    )
    dog = _ranked(
        "User's dog's name is Max", said=datetime(2026, 10, 2, tzinfo=UTC), importance=0.4
    )

    core = identity_core([own, sister, dog])  # type: ignore[list-item]

    assert [memory.text for memory in core] == ["User's name is Binalfew"]


def test_a_conflicting_name_never_takes_the_slot() -> None:
    nickname = _ranked("User goes by Ben", said=datetime(2026, 3, 1, tzinfo=UTC), importance=0.5)
    conflicting = _ranked(
        "User's name is Sam", said=datetime(2026, 10, 1, tzinfo=UTC), importance=1.0
    )

    core = identity_core([nickname, conflicting], profile_name="Dev")  # type: ignore[list-item]

    assert [memory.text for memory in core] == ["User goes by Ben"]
    # Without an account name, the newest name is the user's.
    assert [m.text for m in identity_core([nickname, conflicting])] == [  # type: ignore[list-item]
        "User's name is Sam"
    ]

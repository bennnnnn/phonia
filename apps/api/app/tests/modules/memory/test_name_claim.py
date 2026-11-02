from uuid import uuid4

from app.modules.memory.name_claim import is_unclaimed_user_name
from app.modules.memory.pass_writes import writes_from_ops
from app.modules.memory.schemas import MemoryFactOp

_PROBLEM = "User: Bebe has 2 pens and if he gives that to Cal, how many does he have?"
_INTRO = "User: My name is Bini. I also go by Ben."


def test_word_problem_names_are_not_the_user():
    assert is_unclaimed_user_name("The user's name is Bebe", _PROBLEM)
    assert is_unclaimed_user_name("The user's name is Cal", _PROBLEM)


def test_claimed_name_and_nickname_stay():
    fact = "User's name is Bini; also goes by Ben."
    assert is_unclaimed_user_name(fact, _INTRO) is False


def test_possessive_is_not_a_name_claim():
    speech = "User: I am Bebe's friend and Cal has the pens."
    assert is_unclaimed_user_name("The user's name is Bebe", speech)


def test_stored_name_supports_a_later_nickname():
    fact = "User's name is Bini; also goes by Ben."
    speech = "User: I also go by Ben."
    assert is_unclaimed_user_name(fact, speech)
    assert is_unclaimed_user_name(fact, speech, existing_texts=["User's name is Bini"]) is False


def test_pet_nickname_is_not_the_users_name():
    fact = "The user has a dog named Max who also goes by Maxi"
    speech = "User: My dog Max also goes by Maxi."
    assert is_unclaimed_user_name(fact, speech) is False


def test_other_name_sentences_still_need_a_claim():
    assert is_unclaimed_user_name("The user is Bebe", _PROBLEM)
    assert is_unclaimed_user_name("Bebe is the user's name", _PROBLEM)
    assert (
        is_unclaimed_user_name(
            "The user is a software engineer",
            "User: I am a software engineer",
        )
        is False
    )


def test_job_fact_is_not_a_name_check():
    assert (
        is_unclaimed_user_name(
            "The user works at Uber",
            "User: As a software engineer at Uber I build mobile apps",
        )
        is False
    )


def test_writes_drop_unclaimed_names_and_keep_a_real_one():
    dropped = MemoryFactOp(
        op="add",
        type="profile",
        text="The user's name is Bebe",
        confidence=0.9,
        importance=0.8,
    )
    kept = MemoryFactOp(
        op="add",
        type="profile",
        text="User's name is Bini",
        confidence=0.9,
        importance=0.8,
    )
    writes, skipped = writes_from_ops(
        [dropped, kept],
        chat_id=uuid4(),
        explicit_remember=False,
        include_sensitive=False,
        min_confidence=0.5,
        transcript="User: Bebe has 2 pens. My name is Bini.",
    )
    assert skipped == 1
    assert [write.text for write in writes] == ["User's name is Bini"]

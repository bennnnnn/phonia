"""A profile question asks for the user's own saved detail, and is answered without the model."""

from __future__ import annotations

import pytest

from app.modules.turn_reading.profile_ask import is_profile_fact_question


@pytest.mark.parametrize(
    "text",
    [
        "what is my second language?",
        "My second langauge",
        "What is my education level",
        "what's my education level?",
        "do you know my school?",
        "what's the name of my school?",
        "tell me my degree",
        "which school do I go to?",
        "what grade am I in?",
        "which university did I attend?",
        "what languages do I speak",
        "how many languages do I speak?",
        "where did I study?",
        "where do I live?",
        "where am I from?",
        "I'm in which grade?",
    ],
)
def test_own_detail_is_a_profile_question(text: str) -> None:
    assert is_profile_fact_question(text)


@pytest.mark.parametrize(
    "text",
    [
        # Someone or something else at the school.
        "who is the principal of my school?",
        "who teaches math at my school",
        "what are the rules at my university?",
        # What the school or the grades do.
        "when does my school start?",
        "what time does my school start?",
        "why does my school close early on fridays",
        "is my college accredited?",
        "my grades dropped this term",
        "my school's mascot?",
        "what's my grade on the test?",
        # Someone else's, or a choice to make.
        "what grade should my son be in?",
        "what language should I learn?",
        "how do I improve my grades?",
        "I'm worried about school",
        # A writing request that mentions the user.
        "write an email to the school saying my son is sick and my name is Bini",
        "rewrite my bio: I am a teacher and I live in Addis",
    ],
)
def test_other_questions_are_not(text: str) -> None:
    assert not is_profile_fact_question(text)

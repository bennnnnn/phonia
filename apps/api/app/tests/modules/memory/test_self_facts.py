from types import SimpleNamespace
from uuid import uuid4

from app.modules.memory.self_facts import stated_fact_writes, stated_self_facts


def test_working_on_project_is_a_memory() -> None:
    found = stated_self_facts("User: I am working on a chemistry solver")
    assert found == [
        ("project", "User is working on a chemistry solver", "a chemistry solver"),
    ]


def test_im_working_on_cuts_the_help_request() -> None:
    found = stated_self_facts("I'm working on Recall, can you help me debug the build?")
    assert len(found) == 1
    assert found[0][0] == "project"
    assert found[0][2] == "Recall"


def test_story_character_working_on_is_not_the_user() -> None:
    assert stated_self_facts("Bebe is working on a chemistry solver") == []


def test_pronoun_and_problem_are_not_projects() -> None:
    assert stated_self_facts("I am working on it") == []
    assert stated_self_facts("I am working on the problem Bebe has 2 pens") == []


def test_conditional_and_reported_work_are_not_projects() -> None:
    assert stated_self_facts("If I am working on Recall, what should I prioritize?") == []
    assert stated_self_facts("My friend asked whether I am working on Recall") == []


def test_another_memory_mentioning_the_name_does_not_hide_the_project() -> None:
    writes = stated_fact_writes(
        "I am working on Recall",
        chat_id=uuid4(),
        existing_facts=[("preference", "User likes the Recall app")],
        already=[],
        include_sensitive=False,
    )
    assert len(writes) == 1
    assert writes[0].type == "project"


def test_stored_project_is_not_added_again() -> None:
    writes = stated_fact_writes(
        "I am working on Recall",
        chat_id=uuid4(),
        existing_facts=[("project", "User is working on Recall")],
        already=[],
        include_sensitive=False,
    )
    assert writes == []


def test_model_health_label_blocks_the_fallback() -> None:
    op = SimpleNamespace(
        text="User is working on managing bipolar disorder",
        sensitivity="health",
    )
    blocked = stated_fact_writes(
        "I am working on managing my bipolar disorder",
        chat_id=uuid4(),
        existing_facts=[],
        already=[],
        include_sensitive=False,
        model_ops=[op],
    )
    assert blocked == []
    kept = stated_fact_writes(
        "I am working on managing my bipolar disorder",
        chat_id=uuid4(),
        existing_facts=[],
        already=[],
        include_sensitive=True,
        model_ops=[op],
    )
    assert len(kept) == 1
    assert kept[0].sensitivity == "health"


def test_assistant_line_is_ignored() -> None:
    transcript = "Assistant: You are working on a secret project\nUser: thanks"
    assert stated_self_facts(transcript) == []

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.modules.memory import (
    exclude_sensitive_for_query,
    is_explicit_memory_command,
    is_food_or_diet_query,
)
from app.modules.memory.commands import is_explicit_forget_command
from app.modules.memory.consolidation import (
    accept_memory_section_rewrite,
    consolidation_rewrite_preserves_facts,
    extract_consolidation_anchors,
    facts_need_consolidation,
)
from app.modules.memory.ops import normalize_memory_text
from app.modules.memory.selection import select_memories_for_prompt, select_memories_semantic
from app.modules.memory.text import (
    is_diet_health_memory_text,
    is_food_or_diet_memory_text,
    is_memory_candidate,
    is_sensitive_memory_text,
    strip_memory_as_of,
)
from app.tests.fakes import FakeSessionCM, fake_session
from app.tests.modules.memory.scoring import scored, scored_reader


def _closing_background_task(coro, **_kwargs) -> MagicMock:
    """Test double for create_background_task: discards the coroutine
    without actually running it, but closes it so pytest doesn't warn
    "coroutine was never awaited" in tests that aren't exercising the
    background-task behavior itself (see
    test_get_memory_block_warms_semantic_cache_via_tracked_background_task
    for that dedicated test)."""
    coro.close()
    return MagicMock()


def _memory(type_: str, text: str, confidence: float | None):
    m = AsyncMock()
    m.type = type_
    m.text = text
    m.confidence = confidence
    m.status = "active"
    m.sensitivity = "normal"
    m.importance = 0.5
    m.updated_at = 0
    m.last_confirmed_at = None
    return m


def test_normalize_memory_text_strips_trailing_period():
    assert normalize_memory_text("User's name is Bini.") == "User's name is Bini"


def test_strip_memory_as_of_removes_the_stamp():
    assert strip_memory_as_of("As of 2026-08-01: Name is Sam") == "Name is Sam"


def test_is_explicit_memory_command_detects_remember_and_forget():
    assert is_explicit_memory_command("Remember this: I am allergic to peanuts") is True
    assert is_explicit_memory_command("Please forget that I live in Boston") is True
    assert is_explicit_memory_command("I remember when we first met") is False
    assert is_explicit_memory_command("I'm allergic to peanuts") is False


def test_accept_memory_section_rewrite_rejects_short_preference_alone():
    prior = (
        "Bini prefers varied learning formats for English vocabulary sessions, "
        "alternating between teach then use, use then define, and occasional "
        "multiple-choice questions"
    )
    assert (
        accept_memory_section_rewrite(
            section_type="preference",
            prior=prior,
            summary="Drinks oat milk",
            confidence=0.9,
            min_confidence=0.4,
        )
        is None
    )


def test_forget_requests_name_the_fact_not_the_command():
    from app.modules.memory.commands import forget_requests

    assert forget_requests("Forget that I'm a nurse") == ["I'm a nurse"]
    assert forget_requests("Please forget that I use React, thanks") == ["I use React"]
    assert forget_requests("forget my old address") == ["my old address"]
    assert forget_requests("Please forget that") == []
    assert forget_requests("don't forget I like tea") == []


@pytest.mark.parametrize(
    ("phrase", "fact", "named"),
    [
        ("I'm a nurse", "Works as a nurse in Boston", True),
        ("I use React", "User uses React", True),
        # One shared word is not the fact: React Native is another name.
        ("I use React", "User builds Recall with React Native and FastAPI", False),
        ("I use React", "User uses React Native for mobile", False),
        ("I live in Nairobi", "User lives in Nairobi", True),
        # About the user's sister, not the user.
        ("I live in Nairobi", "User's sister lives in Nairobi suburbs", False),
        ("my sister", "User's sister lives in Nairobi suburbs", True),
        ("my dog Max", "User has a dog named Max", True),
        ("that", "User lives in Nairobi", False),
    ],
)
def test_forget_phrase_names_only_the_fact_it_says(phrase, fact, named):
    from app.modules.memory.forget_match import phrase_names_fact

    assert phrase_names_fact(phrase, fact) is named


@pytest.mark.parametrize(
    ("text", "remember_or_forget", "forget"),
    [
        # Talk about remembering is not an instruction (found by the behavior sweep).
        ("do you remember that song from Titanic?", False, False),
        ("Remember that song from Titanic?", False, False),
        ("I always forget my keys — any tips?", False, False),
        ("I don't remember the formula for kinetic energy", False, False),
        # Dropping a question is not dropping a saved fact about Canada.
        ("Forget about the previous question — what's the capital of Canada?", False, False),
        ("forget my last message", False, False),
        # Instructions, with or without a polite lead.
        ("remember that I'm vegetarian", True, False),
        ("can you remember that I take my coffee black?", True, False),
        ("oh and remember that my sister is Hana", True, False),
        ("Also, please don\u2019t forget I like tea", True, False),
        ("don't remember my address", True, True),
        ("user: forget that I work at Hooh", True, True),
        ("stop remembering my location", True, True),
        ("remember im allergic to peanuts 🥜", True, False),
        ("for future chats keep in mind that i'm vegetarian", True, False),
        ("remember my name?", False, False),
        ("I remember my first day at school", False, False),
    ],
)
def test_memory_commands_are_instructions_not_talk(text, remember_or_forget, forget):
    assert is_explicit_memory_command(text) is remember_or_forget
    assert is_explicit_forget_command(text) is forget


def test_is_explicit_forget_command_ignores_dont_forget():
    assert is_explicit_forget_command("Please forget that I live in Boston") is True
    assert is_explicit_forget_command("forget this: I work at Hooh") is True
    assert is_explicit_forget_command("don't forget I like tea") is False
    assert is_explicit_forget_command("dont forget I like tea") is False
    assert is_explicit_forget_command("Remember this: I like tea") is False
    assert is_explicit_forget_command("don't forget my birthday, but forget my old address") is True


def test_is_sensitive_memory_text_flags_health_and_finance():
    assert is_sensitive_memory_text("Has a peanut allergy") is True
    assert is_sensitive_memory_text("As of 2026-07-20: Paying off credit card debt") is True
    assert is_sensitive_memory_text("Likes Italian cooking") is False


@pytest.mark.parametrize(
    "text,sensitive",
    [
        ("User is dating someone from work", True),
        ("User started dating Sam in June", True),
        ("User and Sam are dating", True),
        ("User is building Africana, a dating app for the diaspora", False),
        ("User's side project is a dating app", False),
    ],
)
def test_is_sensitive_memory_text_reads_dating_as_the_users_love_life(text, sensitive):
    assert is_sensitive_memory_text(text) is sensitive


@pytest.mark.parametrize(
    "sensitivity,text",
    [
        ("health", "Has a peanut allergy"),
        ("legal", "User is divorcing"),
        ("finance", "Salary is $200k"),
        ("relationship", "User has a girlfriend"),
        ("identity", "User ethnicity is listed"),
        ("highly_sensitive", "User is Catholic"),
        ("", "Has a peanut allergy"),
    ],
)
def test_should_skip_sensitive_persist_without_opt_in(sensitivity, text):
    from app.modules.memory.facts import should_skip_sensitive_persist

    assert (
        should_skip_sensitive_persist(
            sensitivity=sensitivity,
            text=text,
            explicit_remember=False,
            include_sensitive=False,
        )
        is True
    )
    assert (
        should_skip_sensitive_persist(
            sensitivity=sensitivity,
            text=text,
            explicit_remember=True,
            include_sensitive=False,
        )
        is False
    )
    assert (
        should_skip_sensitive_persist(
            sensitivity=sensitivity,
            text=text,
            explicit_remember=False,
            include_sensitive=True,
        )
        is False
    )


def test_exclude_sensitive_for_query_injects_only_on_matching_asks():
    assert exclude_sensitive_for_query(None) is True
    assert exclude_sensitive_for_query("  ") is True
    assert exclude_sensitive_for_query("what's the weather") is True
    assert exclude_sensitive_for_query("I have a peanut allergy, what can I eat?") is False
    assert exclude_sensitive_for_query("help with my credit card debt") is False
    assert exclude_sensitive_for_query("what should I eat tonight") is True
    assert is_food_or_diet_query("what should I eat tonight") is True
    assert is_food_or_diet_query("what's the weather") is False
    assert is_food_or_diet_query("What milk do I drink.") is True
    assert is_food_or_diet_memory_text("Bini consumes oat milk") is True
    assert is_food_or_diet_memory_text("Building a rocket hobby app") is False
    assert is_diet_health_memory_text("Peanut allergy") is True
    assert is_diet_health_memory_text("Paying off a mortgage") is False


def test_filter_surface_memories_keeps_allergy_on_food_query():
    from app.modules.memory.retrieval import filter_surface_memories

    allergy = _memory("preference", "Peanut allergy", 0.9)
    salary = _memory("fact", "Salary is $200k", 0.9)
    kept = filter_surface_memories(
        [allergy, salary],
        exclude_sensitive=True,
        query_text="what should I eat tonight",
    )
    assert allergy in kept
    assert salary not in kept
    weather = filter_surface_memories(
        [allergy, salary],
        exclude_sensitive=True,
        query_text="what's the weather",
    )
    assert allergy not in weather
    assert salary not in weather


def test_extract_consolidation_anchors_names_and_orgs():
    prior = "User's name is Bini. User works at Hooh on Recall. Contact: dev@example.com"
    anchors = extract_consolidation_anchors(prior)
    assert "bini" in anchors
    assert "hooh" in anchors
    assert "recall" in anchors
    assert "dev@example.com" in anchors


def test_consolidation_rewrite_preserves_facts_accepts_good_rewrite():
    prior = "User's name is Bini. User works at Hooh. User is a developer."
    summary = "Bini is a developer at Hooh building mobile apps."
    assert consolidation_rewrite_preserves_facts(prior, summary) is True


def test_consolidation_rewrite_preserves_facts_rejects_dropped_anchor():
    prior = "User's name is Bini. User works at Hooh. User is a developer."
    summary = "Bini is a software developer building mobile apps."
    assert consolidation_rewrite_preserves_facts(prior, summary) is False


def test_consolidation_rewrite_preserves_facts_rejects_exactly_20_percent_drop():
    """BUG FIX (off-by-one): "drop >= 20% of anchors" must reject at exactly
    the 20%-dropped / 80%-preserved boundary, not just past it. 5 anchors,
    1 dropped = exactly 80% preserved."""
    prior = "Alice likes Boston, Chicago, Denver, and Everett."
    summary_drops_one = "Alice likes Boston, Chicago, and Denver."
    assert extract_consolidation_anchors(prior) == frozenset(
        {"alice", "boston", "chicago", "denver", "everett"}
    )
    assert consolidation_rewrite_preserves_facts(prior, summary_drops_one) is False
    # Sanity check the gate isn't just always-False now: preserving all 5
    # (dropping none) still passes.
    summary_keeps_all = "Alice loves Boston, Chicago, Denver, and Everett."
    assert consolidation_rewrite_preserves_facts(prior, summary_keeps_all) is True


def test_accept_memory_section_rewrite_rejects_dropped_anchors():
    prior = "User's name is Bini. User works at Hooh. User is a developer."
    bad = "Bini is a software developer building mobile apps."
    assert (
        accept_memory_section_rewrite(
            section_type="profile",
            prior=prior,
            summary=bad,
            confidence=0.9,
            min_confidence=0.4,
        )
        is None
    )


def test_accept_memory_section_rewrite_keeps_expanding_rewrite():
    prior = "User's name is Bini. User works at Hooh. User is a developer."
    good = "Bini is a developer at Hooh building Recall."
    assert (
        accept_memory_section_rewrite(
            section_type="profile",
            prior=prior,
            summary=good,
            confidence=0.9,
            min_confidence=0.4,
        )
        == "Bini is a developer at Hooh building Recall"
    )


def test_accept_memory_section_rewrite_keeps_omitted_diet_fact():
    prior = "Bini has started learning Spanish. Bini consumes oat milk"
    summary = "Bini has started learning Spanish and wants to announce this on LinkedIn"
    accepted = accept_memory_section_rewrite(
        section_type="fact",
        prior=prior,
        summary=summary,
        confidence=0.9,
        min_confidence=0.4,
    )
    assert accepted is not None
    assert "oat milk" in accepted.lower()
    assert "linkedin" in accepted.lower()


def test_accept_memory_section_rewrite_allow_clear_empties_on_forget():
    prior = "User's name is Bini. User works at Hooh."
    assert (
        accept_memory_section_rewrite(
            section_type="profile",
            prior=prior,
            summary="",
            confidence=0.9,
            min_confidence=0.4,
            allow_clear=True,
        )
        == ""
    )
    shortened = "Bini lives in Seattle."
    assert (
        accept_memory_section_rewrite(
            section_type="profile",
            prior=prior,
            summary=shortened,
            confidence=0.9,
            min_confidence=0.4,
            allow_clear=True,
        )
        is None
    )


def test_select_memories_filters_low_confidence():
    settings = Settings(memory_min_confidence=0.5, memory_inject_limit=10)
    memories = [
        _memory("preference", "Likes Python", 0.9),
        _memory("preference", "Debugging API", 0.3),
    ]
    selected = select_memories_for_prompt(memories, settings)
    assert len(selected) == 1
    assert selected[0].text == "Likes Python"


def test_select_memories_respects_limit_and_priority():
    settings = Settings(memory_min_confidence=0.0, memory_inject_limit=2)
    memories = [
        _memory("focus", "Low priority", 1.0),
        _memory("profile", "Name is Sam", 0.7),
        _memory("preference", "Short answers", 0.6),
    ]
    selected = select_memories_for_prompt(memories, settings)
    assert len(selected) == 2
    assert selected[0].type == "profile"
    assert selected[1].type == "preference"


def test_select_memories_for_prompt_includes_project_fact_focus():
    settings = Settings(memory_min_confidence=0.0, memory_inject_limit=10)
    memories = [
        _memory("focus", "Ship the quiz this week", 0.8),
        _memory("fact", "Works at Hooh", 0.9),
        _memory("project", "Building Recall", 0.9),
        _memory("profile", "Name is Sam", 0.7),
        _memory("preference", "Short answers", 0.6),
    ]
    selected = select_memories_for_prompt(memories, settings)
    assert [m.type for m in selected] == [
        "profile",
        "preference",
        "project",
        "fact",
        "focus",
    ]


def test_select_memories_semantic_scores_unembedded_facts_by_words():
    """A fact with no vector yet needs a word in common, not a free pass (M5)."""
    settings = Settings(
        memory_min_confidence=0.0, memory_inject_limit=5, memory_min_similarity=0.35
    )
    profile = _memory("profile", "Name is Sam", 1.0)
    profile.embedding_json = "[1.0, 0.0, 0.0]"
    fact = _memory("fact", "Favorite color is blue", 1.0)
    fact.embedding_json = None
    chess = _memory("fact", "Plays chess on weekends", 1.0)
    chess.embedding_json = None

    off_topic = select_memories_semantic(
        scored([profile, fact, chess], [1.0, 0.0, 0.0]),
        settings,
        query_text="how should I structure auth in my app?",
    )
    on_topic = select_memories_semantic(
        scored([profile, fact, chess], [1.0, 0.0, 0.0]),
        settings,
        query_text="what's my favorite color?",
    )

    assert [m.text for m in off_topic] == ["Name is Sam"]
    assert [m.text for m in on_topic] == ["Name is Sam", "Favorite color is blue"]


def test_semantic_tech_query_omits_offtopic_location_and_job():
    """M5: the identity core is the name and reply preferences, nothing else."""
    settings = Settings(
        memory_min_confidence=0.0, memory_inject_limit=8, memory_min_similarity=0.35
    )
    name = _memory("profile", "User's name is Bini", 1.0)
    name.embedding_json = "[0.0, 1.0, 0.0]"
    job = _memory("profile", "Works as a nurse at a clinic", 1.0)
    job.embedding_json = "[0.0, 1.0, 0.0]"
    city = _memory("profile", "Lives in Addis Ababa", 1.0)
    city.embedding_json = "[0.0, 0.0, 1.0]"
    chess = _memory("fact", "Plays chess", 1.0)
    chess.embedding_json = None
    concise = _memory("preference", "Prefers concise answers", 1.0)
    concise.embedding_json = "[0.0, 1.0, 0.0]"

    selected = select_memories_semantic(
        scored([name, job, city, chess, concise], [1.0, 0.0, 0.0]),
        settings,
        query_text="How should I structure auth?",
    )

    assert [m.text for m in selected] == ["User's name is Bini", "Prefers concise answers"]


def test_select_memories_semantic_ranks_by_similarity():
    settings = Settings(
        memory_min_confidence=0.0, memory_inject_limit=2, memory_min_similarity=0.15
    )
    python = _memory("fact", "Python programming", 1.0)
    python.embedding_json = "[1.0, 0.0, 0.0]"
    cooking = _memory("fact", "Cooking recipes", 1.0)
    cooking.embedding_json = "[0.0, 1.0, 0.0]"
    selected = select_memories_semantic(scored([python, cooking], [0.95, 0.05, 0.0]), settings)
    assert selected[0].text == "Python programming"


def test_select_memories_semantic_keeps_profile_drops_off_topic_fact():
    """Cooking query must not pull in an unrelated sensitive fact."""
    settings = Settings(
        memory_min_confidence=0.0, memory_inject_limit=5, memory_min_similarity=0.35
    )
    profile = _memory("profile", "Name is Sam", 1.0)
    health = _memory("fact", "Has a peanut allergy and sees Dr. Chen weekly", 1.0)
    health.embedding_json = "[0.0, 1.0, 0.0]"  # orthogonal to cooking query
    cooking = _memory("fact", "Loves Italian cooking and pasta", 1.0)
    cooking.embedding_json = "[1.0, 0.0, 0.0]"
    selected = select_memories_semantic(
        scored([profile, health, cooking], [1.0, 0.0, 0.0]),
        settings,
    )
    texts = [m.text for m in selected]
    assert "Name is Sam" in texts
    assert "Loves Italian cooking and pasta" in texts
    assert "peanut allergy" not in " ".join(texts)


def test_select_memories_semantic_injects_diet_fact_on_milk_query():
    """Milk/drink asks must see an oat-milk fact even when its embedding is off-topic."""
    settings = Settings(
        memory_min_confidence=0.0, memory_inject_limit=5, memory_min_similarity=0.35
    )
    profile = _memory("profile", "Name is Bini", 1.0)
    oat = _memory(
        "fact",
        "Bini has started learning Spanish. Bini consumes oat milk",
        1.0,
    )
    oat.embedding_json = "[0.0, 1.0, 0.0]"  # orthogonal to a milk query vector
    salary = _memory("fact", "Salary is $200k", 1.0)
    salary.embedding_json = "[0.0, 1.0, 0.0]"
    selected = select_memories_semantic(
        scored([profile, oat, salary], [1.0, 0.0, 0.0]),
        settings,
        query_text="What milk do I drink.",
    )
    texts = [m.text for m in selected]
    assert "Name is Bini" in texts
    assert "oat milk" in " ".join(texts).lower()
    assert "Salary" not in " ".join(texts)


def test_format_memory_block_respects_char_budget():
    from app.modules.memory.selection import format_memory_block

    long_pref = _memory("preference", "x" * 2000, 1.0)
    other = _memory("focus", "Ship the quiz this week", 1.0)
    block = format_memory_block([long_pref, other], max_chars=200)
    assert "Ship the quiz" in block
    assert "x" * 20 not in block
    assert len(block) <= 200
    assert not block.endswith("…")


def test_format_memory_block_keeps_relevant_focus_over_unread_tail():
    from app.modules.memory.selection import format_memory_block

    profile = _memory("profile", "Name is Sam. " + ("bio " * 200), 1.0)
    focus = _memory("focus", "Ship the quiz this week", 1.0)
    block = format_memory_block([profile, focus], max_chars=180)
    assert "Ship the quiz" in block
    assert "…" not in block


def test_is_memory_candidate_skips_small_talk():
    assert is_memory_candidate("hey there") is False
    assert is_memory_candidate("User: thanks") is False
    assert is_memory_candidate("Assistant: The user's dog is Max.\nUser: thanks") is False
    assert is_memory_candidate("I like Python") is True
    assert is_memory_candidate("Remember that my dog is Max") is True
    assert is_memory_candidate("My favorite color is blue") is True
    assert is_memory_candidate("We moved to Boston") is True
    assert is_memory_candidate("Call me Sam") is True
    assert is_memory_candidate("As a software engineer at Uber, I work on mobile apps") is True
    assert is_memory_candidate("I want short, direct answers with examples") is True
    assert is_memory_candidate("Long walls of text make it hard for me to scan") is True
    assert is_memory_candidate("Please keep replies concise and show the steps") is True


def test_facts_need_consolidation_detects_exact_and_near_duplicates():
    a = _memory("fact", "Bini likes tea in the morning.", 1.0)
    b = _memory("fact", "Bini likes tea in the morning.", 1.0)
    c = _memory("fact", "Bini likes tea in the morning now.", 1.0)
    unique = _memory("preference", "Drinks tea.", 1.0)
    assert facts_need_consolidation([a, unique]) is False
    assert facts_need_consolidation([a, b]) is True
    assert facts_need_consolidation([a, c]) is True


@pytest.mark.asyncio
async def test_load_relevant_memories_ranks_in_process_from_list():
    """Semantic recall ranks the ≤5 list_for_user rows in-process."""
    from app.modules.memory.retrieval import load_relevant_memories

    user = AsyncMock()
    user.id = uuid4()
    user.memory_enabled = True
    session = fake_session()
    settings = Settings(semantic_memory_enabled=True, memory_min_confidence=0.4)

    db_hit = _memory("fact", "Hikes every weekend", 0.9)
    db_hit.embedding_json = "[0.1, 0.2, 0.3]"

    with (
        patch("app.modules.memory.repository.list_scored_for_user", scored_reader([db_hit])),
        patch(
            "app.gateways.embedding_gateway.embed_text",
            AsyncMock(return_value=[0.1, 0.2, 0.3]),
        ) as embed_mock,
    ):
        result = await load_relevant_memories(session, user, settings, query_vec=[0.1, 0.2, 0.3])

    assert result == [db_hit]
    embed_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_load_relevant_memories_applies_similarity_cutoff_in_process():
    """Unembedded facts need a word in common with the question; identity core stays."""
    from app.modules.memory.retrieval import load_relevant_memories

    user = AsyncMock()
    user.id = uuid4()
    user.memory_enabled = True
    session = fake_session()
    settings = Settings(
        semantic_memory_enabled=True,
        memory_min_confidence=0.4,
        memory_min_similarity=0.15,
    )

    unembedded_profile = _memory("profile", "Name is Sam", 0.9)
    unembedded_profile.embedding = None
    unembedded_profile.embedding_json = None
    unembedded_fact = _memory("fact", "Hikes every weekend", 0.9)
    unembedded_fact.embedding = None
    unembedded_fact.embedding_json = None

    with (
        patch(
            "app.modules.memory.repository.list_scored_for_user",
            scored_reader([unembedded_profile, unembedded_fact]),
        ),
    ):
        result = await load_relevant_memories(session, user, settings, query_vec=[0.1, 0.2, 0.3])

    # The name is always in; a fact with no vector and no question is not.
    assert result == [unembedded_profile]


@pytest.mark.asyncio
async def test_load_relevant_memories_includes_low_score_when_cutoff_disabled():
    """When memory_min_similarity is 0, a gated section with any embedding injects."""
    from app.modules.memory.retrieval import load_relevant_memories

    user = AsyncMock()
    user.id = uuid4()
    user.memory_enabled = True
    session = fake_session()
    settings = Settings(
        semantic_memory_enabled=True,
        memory_min_confidence=0.4,
        memory_min_similarity=0.0,
        memory_inject_limit=5,
    )

    fact = _memory("fact", "Hikes every weekend", 0.9)
    fact.embedding_json = "[1.0, 0.0, 0.0]"

    with (
        patch("app.modules.memory.repository.list_scored_for_user", scored_reader([fact])),
    ):
        result = await load_relevant_memories(session, user, settings, query_vec=[0.0, 1.0, 0.0])

    assert result == [fact]


@pytest.mark.asyncio
async def test_load_relevant_memories_falls_back_to_in_memory_when_db_empty():
    """Ranks from embedding_json on the list_for_user rows — one round-trip."""
    from app.modules.memory.retrieval import load_relevant_memories

    user = AsyncMock()
    user.id = uuid4()
    user.memory_enabled = True
    session = fake_session()
    settings = Settings(
        semantic_memory_enabled=True, memory_min_confidence=0.0, memory_inject_limit=5
    )

    in_memory_hit = _memory("fact", "Python programming", 1.0)
    in_memory_hit.embedding = None
    in_memory_hit.embedding_json = "[1.0, 0.0, 0.0]"

    with (
        patch(
            "app.modules.memory.repository.list_scored_for_user",
            scored_reader([in_memory_hit]),
        ),
    ):
        result = await load_relevant_memories(session, user, settings, query_vec=[0.95, 0.05, 0.0])

    assert result == [in_memory_hit]


@pytest.mark.asyncio
async def test_load_relevant_memories_keeps_profile_when_vectors_populated_but_no_match():
    """Empty db_hits with populated vectors means no gated section cleared the
    similarity bar — do not fall back to dumping facts, but still inject
    profile/preference."""
    from app.modules.memory.retrieval import load_relevant_memories

    user = AsyncMock()
    user.id = uuid4()
    user.memory_enabled = True
    session = fake_session()
    settings = Settings(
        semantic_memory_enabled=True, memory_min_confidence=0.0, memory_inject_limit=5
    )

    profile = _memory("profile", "Name is Sam", 0.9)
    fact = _memory("fact", "Off-topic allergy detail", 0.9)
    fact.embedding_json = "[1.0, 0.0, 0.0]"
    read = AsyncMock(side_effect=scored_reader([profile, fact]))
    with (
        patch("app.modules.memory.repository.list_scored_for_user", read),
    ):
        result = await load_relevant_memories(session, user, settings, query_vec=[0.0, 1.0, 0.0])

    assert result == [profile]
    read.assert_awaited()


@pytest.mark.asyncio
async def test_load_relevant_memories_priority_fallback_when_no_query():
    from app.modules.memory.retrieval import load_relevant_memories

    user = AsyncMock()
    user.id = uuid4()
    user.memory_enabled = True
    session = fake_session()
    settings = Settings(
        semantic_memory_enabled=True, memory_min_confidence=0.0, memory_inject_limit=5
    )

    profile = _memory("profile", "Name is Sam", 0.7)
    fact = _memory("fact", "Likes Python", 0.9)

    with (
        patch(
            "app.modules.memory.repository.list_for_user",
            AsyncMock(return_value=[fact, profile]),
        ),
    ):
        result = await load_relevant_memories(session, user, settings, query_text=None)

    # No query → type-priority fallback (includes fact/project/focus).
    assert [m.type for m in result] == ["profile", "fact"]


@pytest.mark.asyncio
@pytest.mark.parametrize("query_vec", [None, [0.1, 0.2, 0.3]])
async def test_load_relevant_memories_returns_empty_on_db_exception(query_vec):
    """BUG FIX: a transient Neon/pgvector failure here used to propagate out
    of load_relevant_memories and, via build_prompt_messages's
    asyncio.gather(...), fail the ENTIRE chat turn over a memory lookup.
    Must degrade to an empty list instead, same as every Redis call in this
    file already does on failure."""
    from app.modules.memory.retrieval import load_relevant_memories

    user = AsyncMock()
    user.id = uuid4()
    user.memory_enabled = True
    session = fake_session()
    settings = Settings(semantic_memory_enabled=True)

    unavailable = AsyncMock(side_effect=RuntimeError("db unavailable"))
    with (
        patch("app.modules.memory.repository.list_for_user", unavailable),
        # With a query the facts are ranked in the database: that read fails too.
        patch("app.modules.memory.repository.list_scored_for_user", unavailable),
    ):
        result = await load_relevant_memories(session, user, settings, query_vec=query_vec)

    assert result == []


@pytest.mark.asyncio
async def test_get_memory_block_degrades_to_empty_on_db_exception(fake_redis):
    """End-to-end through the caching layer prompt_builder.py actually
    calls: a DB failure inside load_relevant_memories must not propagate out
    of get_memory_block either, so a simulated chat-turn prompt build still
    completes instead of raising."""
    from app.modules.memory import get_memory_block

    user = AsyncMock()
    user.id = uuid4()
    user.memory_enabled = True
    session = fake_session()
    settings = Settings(semantic_memory_enabled=False)

    with (
        patch(
            "app.modules.memory.repository.list_for_user",
            AsyncMock(side_effect=RuntimeError("db unavailable")),
        ),
    ):
        block = await get_memory_block(session, user, settings)

    assert block == ""


@pytest.mark.asyncio
async def test_get_memory_block_warms_semantic_cache_via_tracked_background_task(fake_redis):
    """BUG FIX: the semantic-cache warm task used to be scheduled via bare
    asyncio.create_task, held only by the local `warm_task` variable that
    goes out of scope the instant get_memory_block returns — per asyncio's
    own docs, an unreferenced task is eligible for GC before it completes.
    Must go through create_background_task (a module-level strong-reference
    set), the same primitive chat/stream.py already uses correctly for its
    own fire-and-forget tasks."""
    from app.modules.memory import get_memory_block

    user = AsyncMock()
    user.id = uuid4()
    user.memory_enabled = True
    session = fake_session()
    settings = Settings(semantic_memory_enabled=True, memory_query_cache_ttl=120)

    fake_task = MagicMock()

    def _create_task_stub(coro, **_kwargs) -> MagicMock:
        # Don't actually run the coroutine (this test only cares which
        # scheduling primitive is used, not the warm-cache logic itself —
        # see test_warm_semantic_cache_write_racing_invalidation_is_never_served
        # for that) — close it so pytest doesn't warn "never awaited".
        coro.close()
        return fake_task

    create_task_mock = MagicMock(side_effect=_create_task_stub)

    with (
        patch("app.modules.memory.retrieval.load_relevant_memories", AsyncMock(return_value=[])),
        patch("app.core.background_tasks.create_background_task", create_task_mock),
        # Live embed fails → fall through to type-priority + background warm.
        patch(
            "app.gateways.embedding_gateway.embed_text",
            AsyncMock(return_value=None),
        ),
    ):
        await get_memory_block(session, user, settings, query_text="outdoor hobbies")

    create_task_mock.assert_called_once()
    assert create_task_mock.call_args.kwargs.get("name") == "warm_semantic_memory_cache"
    fake_task.add_done_callback.assert_called_once()


@pytest.mark.asyncio
async def test_get_memory_block_live_embed_on_cache_miss(fake_redis):
    """On embed-cache miss, try a short live embed before type-priority fallback."""
    from app.modules.memory import get_memory_block

    user = AsyncMock()
    user.id = uuid4()
    user.memory_enabled = True
    session = fake_session()
    settings = Settings(semantic_memory_enabled=True, memory_query_cache_ttl=120)
    query_vec = [0.1, 0.2, 0.3]

    with (
        patch(
            "app.gateways.embedding_gateway.embed_text",
            AsyncMock(return_value=query_vec),
        ) as embed_mock,
        patch(
            "app.modules.memory.retrieval.load_relevant_memories",
            AsyncMock(return_value=[_memory("fact", "Likes hiking", 0.9)]),
        ) as load_mock,
        patch(
            "app.core.background_tasks.create_background_task", side_effect=_closing_background_task
        ),
    ):
        block = await get_memory_block(session, user, settings, query_text="outdoor hobbies")

    assert "Likes hiking" in block
    embed_mock.assert_awaited_once()
    assert load_mock.await_args.kwargs.get("query_vec") == query_vec


@pytest.mark.asyncio
async def test_get_memory_block_query_cache(fake_redis):
    from app.modules.memory import get_memory_block

    user = AsyncMock()
    user.id = uuid4()
    user.memory_enabled = True
    session = fake_session()
    settings = Settings(semantic_memory_enabled=True, memory_query_cache_ttl=120)

    with (
        patch(
            "app.modules.memory.retrieval.load_relevant_memories",
            AsyncMock(return_value=[_memory("fact", "Likes hiking", 0.9)]),
        ) as load_mock,
        patch(
            "app.core.background_tasks.create_background_task", side_effect=_closing_background_task
        ),
    ):
        first = await get_memory_block(session, user, settings, query_text="outdoor hobbies")
        second = await get_memory_block(session, user, settings, query_text="outdoor hobbies")
    assert "Likes hiking" in first
    assert second == first
    load_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_invalidate_memory_block_bumps_generation_and_clears_block_keys(fake_redis):
    """New generation + memblock DEL. Query keys are not SCAN-deleted — generation
    fold makes them unreachable; they expire via memory_query_cache_ttl."""
    from app.modules.memory import get_memory_block, invalidate_memory_block
    from app.modules.memory.cache import memory_block_key, memory_generation_key

    user = AsyncMock()
    user.id = uuid4()
    user.memory_enabled = True
    session = fake_session()
    settings = Settings(semantic_memory_enabled=True, memory_query_cache_ttl=120)

    load_mock = AsyncMock(return_value=[_memory("fact", "Likes hiking", 0.9)])
    with (
        patch("app.modules.memory.retrieval.load_relevant_memories", load_mock),
        patch(
            "app.core.background_tasks.create_background_task", side_effect=_closing_background_task
        ),
    ):
        await get_memory_block(session, user, settings)
        await get_memory_block(session, user, settings, query_text="outdoor hobbies")

        assert await fake_redis.exists(memory_block_key(user.id)) == 1

        await invalidate_memory_block(user.id)

        assert await fake_redis.exists(memory_block_key(user.id)) == 0
        gen = await fake_redis.get(memory_generation_key(user.id))
        assert gen not in (None, "0")
        # One key per user: it must expire instead of staying forever.
        assert await fake_redis.ttl(memory_generation_key(user.id)) > 0

        load_mock.reset_mock()
        await get_memory_block(session, user, settings, query_text="outdoor hobbies")
        load_mock.assert_awaited()


@pytest.mark.asyncio
async def test_invalidate_memory_block_makes_query_cache_unreachable(fake_redis):
    from app.modules.memory import get_memory_block, invalidate_memory_block

    user = AsyncMock()
    user.id = uuid4()
    user.memory_enabled = True
    session = fake_session()
    settings = Settings(semantic_memory_enabled=True, memory_query_cache_ttl=120)

    load_mock = AsyncMock(return_value=[_memory("fact", "Likes hiking", 0.9)])
    with (
        patch("app.modules.memory.retrieval.load_relevant_memories", load_mock),
        patch(
            "app.core.background_tasks.create_background_task", side_effect=_closing_background_task
        ),
    ):
        await get_memory_block(session, user, settings, query_text="outdoor hobbies")
        await get_memory_block(session, user, settings, query_text="weekend plans")
        assert load_mock.await_count == 2

        await invalidate_memory_block(user.id)

        load_mock.reset_mock()
        await get_memory_block(session, user, settings, query_text="outdoor hobbies")
        await get_memory_block(session, user, settings, query_text="weekend plans")
        assert load_mock.await_count == 2


@pytest.mark.asyncio
async def test_warm_semantic_cache_write_racing_invalidation_is_never_served(fake_redis):
    """BUG FIX regression: warm_semantic_memory_cache checks the generation,
    then does a separate write — a concurrent invalidation landing in that
    gap used to be able to resurrect a stale block under the current
    generation. The write is now scoped to the generation it was computed
    under, so even if a write lands after the gap, no later reader can
    retrieve it."""
    from app.modules.memory import get_memory_block
    from app.modules.memory.cache import memory_generation_key
    from app.modules.memory.retrieval import warm_semantic_memory_cache

    user_id = uuid4()
    user = AsyncMock()
    user.id = user_id
    user.memory_enabled = True
    session = fake_session()
    settings = Settings(semantic_memory_enabled=True, memory_query_cache_ttl=120)

    stale_memories = [_memory("fact", "Stale — computed before invalidation", 0.9)]
    fresh_memories = [_memory("fact", "Fresh — computed after invalidation", 0.9)]

    real_set = fake_redis.set
    triggered = False

    async def racy_set(key: str, *args: object, **kwargs: object) -> object:
        # Fire exactly once, on the query-cache write — simulating a
        # concurrent memory write bumping the generation in the narrow gap
        # between warm_semantic_memory_cache's gen_after check (which
        # already passed by the time .set() is called) and this write
        # actually landing.
        nonlocal triggered
        if not triggered and str(key).startswith("memquery:"):
            triggered = True
            await fake_redis.incr(memory_generation_key(user_id))
        return await real_set(key, *args, **kwargs)

    fake_redis.set = racy_set

    # The warm and the reader must use this client, whose ``set`` races.
    with (
        patch("app.modules.memory.retrieval.get_redis_client", return_value=fake_redis),
        patch("app.modules.memory.cache.get_redis_client", return_value=fake_redis),
        patch(
            "app.gateways.embedding_gateway.embed_text",
            AsyncMock(return_value=[0.1, 0.2, 0.3]),
        ),
        patch("app.repositories.users.get_by_id", AsyncMock(return_value=user)),
        patch(
            "app.modules.memory.retrieval.semantic_memories_from_vec",
            AsyncMock(return_value=stale_memories),
        ),
        patch("app.core.db.SessionLocal", return_value=FakeSessionCM(session)),
    ):
        await warm_semantic_memory_cache(settings, user_id, "outdoor hobbies")

        with patch(
            "app.modules.memory.retrieval.load_relevant_memories",
            AsyncMock(return_value=fresh_memories),
        ):
            block = await get_memory_block(session, user, settings, query_text="outdoor hobbies")

    assert "Stale — computed before invalidation" not in block
    assert "Fresh — computed after invalidation" in block
    # The stale write did land — just under a generation nothing reads anymore.
    current_gen = await fake_redis.get(memory_generation_key(user_id))
    assert current_gen == "1"


@pytest.mark.asyncio
async def test_memory_reenable_loads_fresh_after_invalidation(fake_redis):
    from app.modules.memory import get_memory_block, invalidate_memory_block

    user = AsyncMock()
    user.id = uuid4()
    user.memory_enabled = True
    session = fake_session()
    settings = Settings(memory_cache_ttl=120)

    load_mock = AsyncMock(
        side_effect=[
            [_memory("fact", "Old fact", 0.9)],
            [_memory("fact", "New fact", 0.9)],
        ]
    )
    with (
        patch("app.modules.memory.retrieval.load_relevant_memories", load_mock),
    ):
        first = await get_memory_block(session, user, settings)
        user.memory_enabled = False
        assert await get_memory_block(session, user, settings) == ""
        await invalidate_memory_block(user.id)
        user.memory_enabled = True
        second = await get_memory_block(session, user, settings)

    assert "Old fact" in first
    assert "New fact" in second
    assert load_mock.await_count == 2


def test_split_and_join_memory_facts():
    from app.modules.memory.text import join_memory_facts, split_memory_facts

    text = "Likes hiking. Prefers morning runs. Lives in Austin."
    facts = split_memory_facts(text)
    assert len(facts) == 3
    assert join_memory_facts(facts) == text


@pytest.mark.asyncio
async def test_update_memory_rewrites_text_and_reembeds():
    from app.modules.memory.crud import update_memory

    user_id = uuid4()
    session = fake_session()
    settings = Settings(mock_llm_enabled=True)
    memory = _memory("fact", "Old fact about hiking", 0.9)
    memory.id = uuid4()
    vector = [0.1, 0.2, 0.3]

    async def fake_update_text_and_embedding(
        session,
        user_id,
        memory_id,
        text,
        embedding,
        *,
        embedding_text_hash=None,
        commit=True,
    ):
        assert commit is False
        memory.text = text
        memory.embedding = embedding
        memory.embedding_text_hash = embedding_text_hash
        return memory

    with (
        patch(
            "app.modules.memory.repository.get_by_id",
            AsyncMock(return_value=memory),
        ),
        patch(
            "app.gateways.embedding_gateway.embed_text",
            AsyncMock(return_value=vector),
        ),
        patch(
            "app.modules.memory.repository.update_text_and_embedding",
            AsyncMock(side_effect=fake_update_text_and_embedding),
        ) as update_embed,
        patch("app.modules.memory.cache.invalidate_memory_block", AsyncMock()) as invalidate,
        patch(
            "app.modules.memory.locks.take_memory_write_lock",
            AsyncMock(return_value=True),
        ),
        patch("app.modules.memory.locks.release_memory_write_lock", AsyncMock()),
    ):
        updated = await update_memory(session, settings, user_id, memory.id, "Likes hiking trails")

    assert updated is not None
    assert not updated.text.startswith("As of ")
    assert "Likes hiking trails" in updated.text
    update_embed.assert_awaited_once()
    invalidate.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_memory_rolls_back_without_invalidating_on_commit_failure():
    from app.modules.memory.crud import update_memory

    user_id = uuid4()
    session = fake_session()
    # The first commit ends the read before the embedding call; the write's fails.
    session.commit.side_effect = [None, RuntimeError("commit failed")]
    settings = Settings(mock_llm_enabled=True)
    memory = _memory("fact", "Old fact", 0.9)
    memory.id = uuid4()
    update_text = AsyncMock(return_value=memory)
    invalidate = AsyncMock()

    with (
        patch("app.modules.memory.repository.get_by_id", AsyncMock(return_value=memory)),
        patch("app.gateways.embedding_gateway.embed_text", AsyncMock(return_value=None)),
        patch("app.modules.memory.repository.update_text", update_text),
        patch("app.modules.memory.cache.invalidate_memory_block", invalidate),
        patch(
            "app.modules.memory.locks.take_memory_write_lock",
            AsyncMock(return_value=True),
        ),
        patch("app.modules.memory.locks.release_memory_write_lock", AsyncMock()),
    ):
        with pytest.raises(RuntimeError, match="commit failed"):
            await update_memory(session, settings, user_id, memory.id, "New fact")

    assert update_text.await_args.kwargs["commit"] is False
    session.rollback.assert_awaited_once()
    invalidate.assert_not_awaited()


@pytest.mark.asyncio
async def test_delete_memory_releases_lock_even_when_delete_fails():
    """A row delete takes the write lock and always releases it, even when the row
    is already gone."""
    from app.modules.memory.crud import delete_memory

    user_id = uuid4()
    session = fake_session()

    with (
        patch(
            "app.modules.memory.locks.take_memory_write_lock",
            AsyncMock(return_value=True),
        ) as acquire_lock,
        patch("app.modules.memory.locks.release_memory_write_lock", AsyncMock()) as release_lock,
        patch("app.modules.memory.repository.delete_by_id", AsyncMock(return_value=False)),
        patch("app.modules.memory.cache.invalidate_memory_block", AsyncMock()) as invalidate,
    ):
        ok = await delete_memory(session, user_id, uuid4())

    assert ok is False
    invalidate.assert_not_awaited()
    acquire_lock.assert_awaited_once_with(user_id)
    release_lock.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_all_memories_releases_lock():
    from app.modules.memory import delete_all_memories

    user_id = uuid4()
    session = fake_session()

    with (
        patch(
            "app.modules.memory.locks.take_memory_write_lock",
            AsyncMock(return_value=True),
        ) as acquire_lock,
        patch("app.modules.memory.locks.release_memory_write_lock", AsyncMock()) as release_lock,
        patch("app.modules.memory.repository.delete_all_for_user", AsyncMock(return_value=3)),
        patch("app.modules.memory.cache.invalidate_memory_block", AsyncMock()) as invalidate,
    ):
        removed = await delete_all_memories(session, user_id)

    assert removed == 3
    invalidate.assert_awaited_once()
    acquire_lock.assert_awaited_once_with(user_id)
    release_lock.assert_awaited_once()


def _fact(type_: str, text: str, *, topic: str | None = None, vec: str | None = None):
    memory = _memory(type_, text, 1.0)
    memory.topic = topic
    memory.embedding_json = vec
    return memory


def _store() -> list:
    """A user who builds Recall, and a lot about them that has nothing to do with auth."""
    return [
        _fact("profile", "User's name is Bini", topic="profile"),
        _fact("profile", "Bini works as a nurse at a clinic", topic="profile"),
        _fact("profile", "Bini lives in Addis Ababa", topic="profile"),
        _fact("preference", "Bini prefers concise answers", topic="preferences"),
        _fact("fact", "Bini has a cat named Mimi", topic="interests"),
        _fact("fact", "Bini is training for a marathon", topic="goals"),
        _fact("fact", "Bini uses React Native and FastAPI", topic="tech-stack"),
        _fact("project", "Bini builds Recall with React Native and FastAPI", topic="area:recall"),
        _fact("project", "Bini's wedding is planned for June", topic="area:wedding"),
        _fact("fact", "Bini wants auth tokens kept off the device logs", topic="notes"),
    ]


@pytest.mark.asyncio
async def test_embed_timeout_injects_only_identity_core(fake_redis):
    """M6: no query vector means the name, reply preferences and facts that share a
    word with the question, never the whole store; the block is not cached."""
    from app.modules.memory import MemoryLoadReport, get_memory_block

    user = AsyncMock()
    user.id = uuid4()
    user.memory_enabled = True
    settings = Settings(semantic_memory_enabled=True, memory_min_confidence=0.0)
    report = MemoryLoadReport()
    warm = MagicMock(side_effect=_closing_background_task)

    with (
        patch("app.gateways.embedding_gateway.get_or_embed_query", AsyncMock(return_value=None)),
        patch("app.modules.memory.repository.list_for_user", AsyncMock(return_value=_store())),
        patch("app.core.background_tasks.create_background_task", warm),
    ):
        block = await get_memory_block(
            AsyncMock(),
            user,
            settings,
            query_text="How should I structure auth in my app?",
            exclude_sensitive=True,
            report=report,
        )

    assert "User's name is Bini" in block
    assert "Bini prefers concise answers" in block
    assert "auth tokens" in block
    for unrelated in ("nurse", "Addis Ababa", "Mimi", "marathon", "wedding"):
        assert unrelated not in block
    assert report.status == "partial"
    assert not [key async for key in fake_redis.scan_iter("memquery:*")]


@pytest.mark.asyncio
async def test_warm_repairs_the_scope_the_turn_read(fake_redis):
    """M6: after an embed miss, the warm writes the key the next turn reads."""
    from app.modules.memory.cache import memory_query_scoped_key
    from app.modules.memory.retrieval import warm_semantic_memory_cache

    user = AsyncMock()
    user.id = uuid4()
    user.memory_enabled = True
    settings = Settings(semantic_memory_enabled=True, memory_query_cache_ttl=120)
    with (
        patch(
            "app.gateways.embedding_gateway.get_or_embed_query",
            AsyncMock(return_value=[1.0, 0.0, 0.0]),
        ),
        patch("app.repositories.users.get_by_id", AsyncMock(return_value=user)),
        patch(
            "app.modules.memory.retrieval.semantic_memories_from_vec",
            AsyncMock(return_value=[_memory("fact", "Likes hiking", 0.9)]),
        ),
        patch("app.core.db.SessionLocal", return_value=FakeSessionCM(AsyncMock())),
    ):
        await warm_semantic_memory_cache(
            settings, user.id, "outdoor hobbies", exclude_sensitive=True
        )

    read_key = memory_query_scoped_key(user.id, None, "outdoor hobbies", exclude_sensitive=True)
    other_key = memory_query_scoped_key(user.id, None, "outdoor hobbies", exclude_sensitive=False)
    assert "Likes hiking" in (await fake_redis.get(read_key) or "")
    assert await fake_redis.get(other_key) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("semantic", [True, False])
async def test_a_failed_read_is_reported_and_never_cached(fake_redis, semantic):
    """M17: a DB error is "unavailable", not an empty memory, and the next turn retries."""
    from app.modules.memory import MemoryLoadReport, get_memory_block

    user = AsyncMock()
    user.id = uuid4()
    user.memory_enabled = True
    settings = Settings(semantic_memory_enabled=semantic)
    report = MemoryLoadReport()
    unavailable = AsyncMock(side_effect=RuntimeError("db unavailable"))
    with (
        patch(
            "app.gateways.embedding_gateway.get_or_embed_query",
            AsyncMock(return_value=[1.0, 0.0, 0.0]),
        ),
        patch("app.modules.memory.repository.list_for_user", unavailable),
        # A semantic read ranks the facts in the database: that read fails too.
        patch("app.modules.memory.repository.list_scored_for_user", unavailable),
    ):
        block = await get_memory_block(
            fake_session(), user, settings, query_text="what's my job?", report=report
        )

    assert block == ""
    assert report.status == "unavailable"
    assert not [key async for key in fake_redis.scan_iter("mem*:*")]


def test_work_scope_reads_the_stack_and_what_the_user_builds():
    """M2/M5: a programming turn gets the stack and the software areas, nothing else."""
    from app.modules.memory.selection import select_work_memories

    settings = Settings(memory_min_confidence=0.0)
    texts = [memory.text for memory in select_work_memories(_store(), settings)]

    assert texts[:2] == ["User's name is Bini", "Bini prefers concise answers"]
    assert "Bini uses React Native and FastAPI" in texts
    assert "Bini builds Recall with React Native and FastAPI" in texts
    for unrelated in ("nurse", "Addis Ababa", "Mimi", "marathon", "wedding"):
        assert not any(unrelated in text for text in texts)


def test_profile_scope_keeps_the_profile_document():
    settings = Settings(memory_min_confidence=0.0, memory_min_similarity=0.35)
    selected = select_memories_semantic(
        scored(_store(), [1.0, 0.0, 0.0]),
        settings,
        query_text="should I ask for a promotion?",
        with_profile=True,
    )
    texts = [memory.text for memory in selected]
    assert "Bini works as a nurse at a clinic" in texts
    assert "Bini has a cat named Mimi" not in texts


def test_fact_lines_say_when_and_how_sure():
    """M18: a fact carries the month it was said, and a doubtful one says so."""
    from datetime import UTC, datetime

    from app.modules.memory.selection import format_memory_block

    sure = _memory("profile", "Works at Stripe", 0.95)
    sure.last_confirmed_at = datetime(2026, 5, 2, tzinfo=UTC)
    unsure = _memory("fact", "Might be moving to Lisbon", 0.45)
    unsure.last_confirmed_at = datetime(2026, 9, 9, tzinfo=UTC)

    block = format_memory_block([sure, unsure])

    assert "- Works at Stripe (said 2026-05)" in block
    assert "- Might be moving to Lisbon (said 2026-09, unconfirmed)" in block

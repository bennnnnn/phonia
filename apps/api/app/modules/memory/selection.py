"""Which memories go into a prompt, in what order, and how they're rendered.

Pure ranking and formatting — no Redis, no DB, no awaits. ``retrieval`` calls them
through this module, so a test that patches ``selection.format_memory_block`` reaches
the prompt path too.
"""

import re

from app.core.config import Settings
from app.models.orm import Memory
from app.modules.memory.facts import (
    fallback_score,
    identity_core,
    is_active_memory,
    pack_memories,
    render_memory_block,
    semantic_score,
)
from app.modules.memory.lexical import overlap, terms
from app.modules.memory.text import is_food_or_diet_memory_text, is_food_or_diet_query
from app.modules.memory.topics import fact_topic, is_area

# Topics that hold what the user builds, besides areas.
_WORK_TOPICS = frozenset({"side-projects", "recent-work"})
# A fact about software the user builds or runs: its words, or a technology it names.
_WORK_CUE = re.compile(
    r"\b(?:apps?|application|apis?|backend|front-?end|website|web ?app|code|codebase|repo|"
    r"software|startup|saas|mvp|platform|develop(?:s|ing|er|ment)?|program(?:s|ming|mer)?|"
    r"engineer(?:s|ing)?|tech ?stack|server|database|deploy\w*|frameworks?|library|sdk|"
    r"extension|bot|react|native|expo|fastapi|django|flask|rails|laravel|spring|node(?:\.?js)?|"
    r"next\.?js|vue|angular|svelte|flutter|swiftui|swift|kotlin|python|javascript|typescript|"
    r"java|golang|rust|ruby|php|postgres(?:ql)?|mysql|sqlite|mongodb|redis|supabase|firebase|"
    r"neon|aws|gcp|azure|vercel|docker|kubernetes|graphql|tailwind)\b",
    re.IGNORECASE,
)


def _confidence_value(memory: Memory) -> float:
    if memory.confidence is None:
        return 1.0
    return float(memory.confidence)


def _eligible_memory(memory: Memory, settings: Settings) -> bool:
    if not is_active_memory(memory):
        return False
    return _confidence_value(memory) >= settings.memory_min_confidence and bool(memory.text.strip())


def select_memories_for_prompt(
    memories: list[Memory],
    settings: Settings,
    *,
    profile_name: str | None = None,
) -> list[Memory]:
    """Non-semantic fallback: identity core + scored remaining facts."""
    filtered = [memory for memory in memories if _eligible_memory(memory, settings)]
    core = identity_core(filtered, profile_name=profile_name)
    core_ids = {id(memory) for memory in core}
    rest = [memory for memory in filtered if id(memory) not in core_ids]
    rest.sort(key=fallback_score, reverse=True)
    return [*core, *rest][: settings.memory_inject_limit]


def format_memory_block(memories: list[Memory], *, max_chars: int = 0) -> str:
    packed = pack_memories(memories, max_chars=max_chars)
    return render_memory_block(packed)


def select_memories_semantic(
    scored: list[tuple[Memory, float | None]],
    settings: Settings,
    *,
    query_text: str | None = None,
    with_profile: bool = False,
    profile_name: str | None = None,
) -> list[Memory]:
    """Identity core always; remaining facts only above similarity.

    ``scored`` pairs each fact with its cosine similarity to the question, computed in
    SQL (``repository.list_scored_for_user``); None for a fact with no vector yet, which
    needs a word in common with the question instead of riding along on every turn.
    Food/drink asks also keep diet facts whose embedding would otherwise miss.
    """
    eligible = [(memory, cosine) for memory, cosine in scored if _eligible_memory(memory, settings)]
    facts = [memory for memory, _ in eligible]
    always = _always_in(facts, with_profile=with_profile, profile_name=profile_name)
    always_ids = {id(memory) for memory in always}
    query_terms = terms(query_text)
    ranked: list[tuple[float, Memory]] = []
    min_sim = settings.memory_min_similarity
    for memory, cosine in eligible:
        if id(memory) in always_ids:
            continue
        if cosine is None:
            if overlap(query_terms, memory.text):
                ranked.append((fallback_score(memory), memory))
            continue
        if min_sim > 0 and cosine < min_sim:
            continue
        ranked.append((semantic_score(memory, cosine), memory))
    ranked.sort(key=lambda pair: pair[0], reverse=True)
    merged = always + [memory for _, memory in ranked]
    return _with_diet_facts(merged, facts, query_text)[: settings.memory_inject_limit]


def select_memories_lexical(
    memories: list[Memory],
    settings: Settings,
    *,
    query_text: str | None,
    with_profile: bool = False,
    profile_name: str | None = None,
) -> list[Memory]:
    """When the query embed is unavailable: identity core plus facts sharing a word.

    Never the whole store: an auth question with no vector gets the name, reply
    preferences and anything that says "auth", not the cat and the marathon.
    """
    eligible = [memory for memory in memories if _eligible_memory(memory, settings)]
    always = _always_in(eligible, with_profile=with_profile, profile_name=profile_name)
    always_ids = {id(memory) for memory in always}
    query_terms = terms(query_text)
    scored = [
        (overlap(query_terms, memory.text), fallback_score(memory), memory)
        for memory in eligible
        if id(memory) not in always_ids
    ]
    matched = [entry for entry in scored if entry[0] > 0]
    matched.sort(key=lambda entry: (entry[0], entry[1]), reverse=True)
    merged = always + [memory for _, _, memory in matched]
    return _with_diet_facts(merged, eligible, query_text)[: settings.memory_inject_limit]


def select_work_memories(
    memories: list[Memory], settings: Settings, *, profile_name: str | None = None
) -> list[Memory]:
    """Memory for a programming or "my app" turn: the stack and what the user builds.

    Identity core, then the tech-stack document, then facts about what they build:
    side projects and recent work that read as software, and every fact of an area
    that does ("User builds Recall with React Native and FastAPI"). A wedding area,
    the user's job or their city stay out.
    """
    eligible = [memory for memory in memories if _eligible_memory(memory, settings)]
    always = identity_core(eligible, profile_name=profile_name)
    always_ids = {id(memory) for memory in always}
    work_areas = {
        fact_topic(memory)
        for memory in eligible
        if is_area(fact_topic(memory)) and _WORK_CUE.search(memory.text)
    }
    stack: list[Memory] = []
    built: list[Memory] = []
    for memory in eligible:
        if id(memory) in always_ids:
            continue
        topic = fact_topic(memory)
        if topic == "tech-stack":
            stack.append(memory)
        elif topic in work_areas or (topic in _WORK_TOPICS and _WORK_CUE.search(memory.text)):
            built.append(memory)
    stack.sort(key=fallback_score, reverse=True)
    built.sort(key=fallback_score, reverse=True)
    return [*always, *stack, *built][: settings.memory_inject_limit]


def _always_in(
    eligible: list[Memory], *, with_profile: bool, profile_name: str | None
) -> list[Memory]:
    """The identity core, plus the profile document when the turn is about the user."""
    core = identity_core(eligible, profile_name=profile_name)
    if not with_profile:
        return core
    have = {id(memory) for memory in core}
    profile = [m for m in eligible if m.type == "profile" and id(m) not in have]
    profile.sort(key=fallback_score, reverse=True)
    return [*core, *profile]


def _with_diet_facts(
    merged: list[Memory], eligible: list[Memory], query_text: str | None
) -> list[Memory]:
    if not (query_text and is_food_or_diet_query(query_text)):
        return merged
    have = {id(memory) for memory in merged}
    extra = [
        memory
        for memory in eligible
        if id(memory) not in have and is_food_or_diet_memory_text(memory.text)
    ]
    return [*merged, *extra]
